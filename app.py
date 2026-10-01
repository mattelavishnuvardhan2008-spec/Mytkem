#!/usr/bin/env python3
import json
import re
from bs4 import BeautifulSoup
from cachetools import TTLCache
from flask import Flask, render_template, request
from flask_compress import Compress
from flask_talisman import Talisman
import requests

BASE_URL = "https://tkrec.in"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

app = Flask(__name__)
Compress(app)

csp = {
    'default-src': "'self'",
    'script-src': ["'self'", "'unsafe-inline'", "'unsafe-eval'"],
    'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
    'font-src': ["'self'", "https://fonts.gstatic.com"],
    'img-src': ["'self'", "data:", "https:"]
}

Talisman(app, content_security_policy=csp, force_https=True)
ATTENDANCE_CACHE = TTLCache(maxsize=500, ttl=1800)


def text_of(el):
    return el.get_text(strip=True) if el else ""


def authenticate_and_fetch_html(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. Fetch homepage containing the Student Login form
    res_home = session.get(BASE_URL, timeout=10)
    res_home.raise_for_status()

    soup = BeautifulSoup(res_home.text, "html.parser")

    # Locate the Student Login form or block
    login_form = None
    for form in soup.find_all("form"):
        form_text = form.get_text().lower()
        if "student" in form_text or "login" in form_text:
            login_form = form
            break

    if not login_form:
        login_form = soup  # Fallback to entire document if form tag isn't explicitly wrapped

    # 2. Extract input field names dynamically
    user_input = login_form.find("input", {"type": lambda t: t in ["text", "email"] if t else True})
    pass_input = login_form.find("input", {"type": "password"})

    user_field_name = user_input.get("name") if (user_input and user_input.get("name")) else "username"
    pass_field_name = pass_input.get("name") if (pass_input and pass_input.get("name")) else "password"

    # Determine post URL from form action attribute
    action_url = BASE_URL
    if login_form and login_form.name == "form" and login_form.get("action"):
        action = login_form["action"].strip()
        if action.startswith("http"):
            action_url = action
        else:
            action_url = f"{BASE_URL}/{action.lstrip('/')}"
    else:
        action_url = f"{BASE_URL}/student_login_action.php"

    # Build payload with hidden input values + user credentials
    payload = {}
    for hidden in login_form.find_all("input", {"type": "hidden"}):
        if hidden.get("name") and hidden.get("value"):
            payload[hidden["name"]] = hidden["value"]

    payload[user_field_name] = username
    payload[pass_field_name] = password
    
    # Include submit button payload if present
    submit_btn = login_form.find("input", {"type": "submit"}) or login_form.find("button", {"type": "submit"})
    if submit_btn and submit_btn.get("name"):
        payload[submit_btn["name"]] = submit_btn.get("value", "Login")

    # 3. Submit Authentication POST request
    res_login = session.post(
        action_url,
        data=payload,
        headers={**HEADERS, "Referer": BASE_URL},
        allow_redirects=True,
        timeout=10,
    )
    res_login.raise_for_status()

    html_content = res_login.text

    # 4. Handle post-login redirection or sub-page checks
    if "username" in user_field_name and ("studentloginform" in html_content.lower() or "invalid" in html_content.lower()):
        # Attempt fallback to known dashboard routes if redirected back to index
        for dashboard_path in ["/student/index.php", "/student/home.php", "/student/attendance.php"]:
            res_dash = session.get(f"{BASE_URL}{dashboard_path}", timeout=10)
            if "login" not in res_dash.url and len(res_dash.text) > 1000:
                html_content = res_dash.text
                break
        else:
            raise RuntimeError("Login failed. Please check your Roll Number and Password.")

    session.close()
    return html_content


def parse_dashboard_html(html):
    soup = BeautifulSoup(html, "html.parser")
    data = {"profile": {}, "subjects": {}, "grand_total": None, "days": []}

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            label = text_of(cells[0]).lower()
            if "roll" in label or "htno" in label:
                data["profile"]["roll"] = text_of(cells[1])
            elif "student" in label or "name" in label:
                data["profile"]["name"] = text_of(cells[1])

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header_text = " ".join(text_of(c) for c in rows[0].find_all(["td", "th"])).lower()

        if any(k in header_text for k in ["subject", "code", "pres", "attd", "held", "total"]):
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue
                subj = text_of(cells[0])
                c_txt, a_txt = text_of(cells[1]), text_of(cells[2])

                if subj.lower().startswith("total") or "grand" in subj.lower():
                    if c_txt.isdigit() and a_txt.isdigit():
                        data["grand_total"] = {"held": int(c_txt), "present": int(a_txt)}
                    continue

                if c_txt.isdigit() and a_txt.isdigit():
                    data["subjects"][subj] = {"held": int(c_txt), "present": int(a_txt)}

        if "date" in header_text:
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue
                date = text_of(cells[0])
                if not re.match(r"^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}$", date):
                    continue

                mid = [text_of(c) for c in cells[1:-2]]
                periods = ["P" if p.upper() in ("P", "PRESENT") else "A" for p in mid if p.upper() in ("P", "A", "PRESENT", "ABSENT")]

                total_txt, attend_txt = text_of(cells[-2]), text_of(cells[-1])
                total = int(total_txt) if total_txt.isdigit() else len(periods)
                attend = int(attend_txt) if attend_txt.isdigit() else periods.count("P")

                data["days"].append({"date": date, "periods": periods, "total": total, "attend": attend})

    return data


@app.after_request
def add_cache_headers(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", error=None)


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        return render_template("index.html", error="Please enter both Roll Number and Password.")

    if len(username) > 40:
        return render_template("index.html", error="Invalid Roll Number length.")

    if username in ATTENDANCE_CACHE:
        return render_template("dashboard.html", data_json=json.dumps(ATTENDANCE_CACHE[username]))

    try:
        html = authenticate_and_fetch_html(username, password)
        parsed_data = parse_dashboard_html(html)

        if not parsed_data["subjects"] and not parsed_data["days"] and not parsed_data["grand_total"]:
            return render_template("index.html", error="Logged in, but no attendance tables were found.")

        ATTENDANCE_CACHE[username] = parsed_data
        return render_template("dashboard.html", data_json=json.dumps(parsed_data))

    except requests.exceptions.Timeout:
        return render_template("index.html", error="The college portal is taking too long to respond. Please try again.")
    except requests.exceptions.RequestException:
        return render_template("index.html", error="Could not reach the college portal. Please check your connection or try later.")
    except RuntimeError as err:
        return render_template("index.html", error=str(err))
    except Exception as e:
        print(f"Error during execution: {e}")
        return render_template("index.html", error="An unexpected error occurred. Please check your credentials and try again.")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(debug=True)
