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
LOGIN_PAGE = f"{BASE_URL}/index.php"
LOGIN_ACTION = f"{BASE_URL}/student_login_action.php"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

app = Flask(__name__)
Compress(app)

# Content Security Policy configured to permit frontend analysis and dashboard chart rendering
csp = {
    'default-src': "'self'",
    'script-src': ["'self'", "'unsafe-inline'", "'unsafe-eval'"],
    'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
    'font-src': ["'self'", "https://fonts.gstatic.com"],
    'img-src': ["'self'", "data:", "https:"]
}

Talisman(
    app,
    content_security_policy=csp,
    force_https=True
)

# Bounded TTL + LRU Cache: max 500 records, automatically expires after 30 minutes (1800s)
ATTENDANCE_CACHE = TTLCache(maxsize=500, ttl=1800)


def text_of(el):
    return el.get_text(strip=True) if el else ""


def authenticate_and_fetch_html(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)

    # Fetch initial page
    res = session.get(LOGIN_PAGE, timeout=10)
    res.raise_for_status()

    # Robust DOM token lookup
    soup = BeautifulSoup(res.text, "html.parser")
    token_input = soup.find("input", {"name": "token"})
    if not token_input or not token_input.get("value"):
        raise RuntimeError("Failed to extract login token. Portal structure may have changed.")

    token = token_input["value"]

    login_payload = {
        "token": token,
        "username": username,
        "password": password,
        "submit": "Login",
    }

    # Authenticate
    res_login = session.post(
        LOGIN_ACTION,
        data=login_payload,
        headers={**HEADERS, "Referer": LOGIN_PAGE},
        timeout=10,
    )
    res_login.raise_for_status()
    html_content = res_login.text

    if "studentloginform" in html_content or "Invalid" in html_content:
        res_dashboard = session.get(f"{BASE_URL}/student/index.php", timeout=10)
        if "studentloginform" in res_dashboard.text:
            raise RuntimeError("Login failed. Check your username and password.")
        html_content = res_dashboard.text

    session.close()
    return html_content


def parse_dashboard_html(html):
    soup = BeautifulSoup(html, "html.parser")
    data = {"profile": {}, "subjects": {}, "grand_total": None, "days": []}

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            label = text_of(cells[0]).lower()
            if "roll no" in label:
                data["profile"]["roll"] = text_of(cells[1])
            elif "student" in label and "name" in label:
                data["profile"]["name"] = text_of(cells[1])

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        header_text = " ".join(text_of(c) for c in rows[0].find_all(["td", "th"])).lower()

        if "subject" in header_text:
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue
                subj = text_of(cells[0])
                c_txt, a_txt = text_of(cells[1]), text_of(cells[2])

                if subj.lower().startswith("total"):
                    if c_txt.isdigit() and a_txt.isdigit():
                        data["grand_total"] = {"held": int(c_txt), "present": int(a_txt)}
                    continue

                if c_txt.isdigit() and a_txt.isdigit():
                    data["subjects"][subj] = {"held": int(c_txt), "present": int(a_txt)}

        if "date" in header_text and ("total" in header_text or "attend" in header_text):
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue
                date = text_of(cells[0])
                if not re.match(r"^\d{1,2}-\d{1,2}-\d{2,4}$", date):
                    continue

                mid = [text_of(c) for c in cells[1:-2]]
                periods = [p.upper() for p in mid if p.upper() in ("P", "A")]
                total_txt, attend_txt = text_of(cells[-2]), text_of(cells[-1])

                total = int(total_txt) if total_txt.isdigit() else len(periods)
                attend = int(attend_txt) if attend_txt.isdigit() else periods.count("P")

                data["days"].append(
                    {"date": date, "periods": periods, "total": total, "attend": attend}
                )

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

    # Input validation guard
    if not username or not password:
        return render_template("index.html", error="Please enter both Roll Number and Password.")

    if len(username) > 30 or not re.match(r"^[a-zA-Z0-9_-]+$", username):
        return render_template("index.html", error="Invalid Roll Number format.")

    # 1. CHECK IN-MEMORY TTL CACHE
    if username in ATTENDANCE_CACHE:
        return render_template("dashboard.html", data_json=json.dumps(ATTENDANCE_CACHE[username]))

    # 2. PERFORM PORTAL SCRAPING
    try:
        html = authenticate_and_fetch_html(username, password)
        parsed_data = parse_dashboard_html(html)

        if not parsed_data["subjects"] and not parsed_data["days"] and not parsed_data["grand_total"]:
            return render_template("index.html", error="Logged in, but no attendance tables were found.")

        # Store directly in TTLCache
        ATTENDANCE_CACHE[username] = parsed_data

        return render_template("dashboard.html", data_json=json.dumps(parsed_data))

    except requests.exceptions.Timeout:
        return render_template("index.html", error="The college portal is taking too long to respond. Please try again.")
    except requests.exceptions.RequestException:
        return render_template("index.html", error="Could not reach the college portal. Please check your connection or try later.")
    except RuntimeError as err:
        return render_template("index.html", error=str(err))
    except Exception:
        return render_template("index.html", error="An unexpected error occurred. Please check your credentials and try again.")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(debug=True)
