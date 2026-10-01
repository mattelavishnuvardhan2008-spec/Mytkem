#!/usr/bin/env python3
import json
import math
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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
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


def calculate_analysis(held, present, target_pct=75.0):
    """Calculates bunkable/required classes to maintain 75% attendance."""
    if held <= 0:
        return {"current_pct": 0.0, "status": "No Data", "margin_message": "No classes held yet."}

    current_pct = (present / held) * 100

    if current_pct >= target_pct:
        bunkable = math.floor((100 * present - target_pct * held) / target_pct)
        return {
            "current_pct": round(current_pct, 2),
            "status": "Safe",
            "bunkable": bunkable,
            "margin_message": f"You can safely skip the next {bunkable} classes." if bunkable > 0 else "You are right at the 75% threshold."
        }
    else:
        needed = math.ceil((target_pct * held - 100 * present) / (100 - target_pct))
        return {
            "current_pct": round(current_pct, 2),
            "status": "Shortage",
            "needed": needed,
            "margin_message": f"You need to attend the next {needed} classes consecutively to reach 75%."
        }


def authenticate_and_fetch_html(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)

    # Base request to establish cookies
    try:
        session.get(BASE_URL, timeout=10)
    except Exception as e:
        print(f"Base site request warning: {e}")

    # GET login page
    res = session.get(LOGIN_PAGE, timeout=10)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    token_input = (
        soup.find("input", {"name": "token"}) or
        soup.find("input", {"name": "csrf_token"}) or
        soup.find("input", {"name": "csrf"})
    )
    token = token_input["value"] if (token_input and token_input.get("value")) else ""

    login_payload = {
        "username": username,
        "password": password,
        "submit": "Login",
    }
    if token:
        login_payload["token"] = token

    # POST authentication
    res_login = session.post(
        LOGIN_ACTION,
        data=login_payload,
        headers={**HEADERS, "Referer": LOGIN_PAGE},
        timeout=10,
    )
    res_login.raise_for_status()
    html_content = res_login.text

    # Follow redirect to student dashboard if required
    if "studentloginform" in html_content.lower() or "invalid" in html_content.lower():
        res_dashboard = session.get(f"{BASE_URL}/student/index.php", timeout=10)
        if "studentloginform" in res_dashboard.text.lower():
            raise RuntimeError("Login failed. Check your username and password.")
        html_content = res_dashboard.text

    session.close()
    return html_content


def parse_dashboard_html(html):
    soup = BeautifulSoup(html, "html.parser")
    data = {"profile": {}, "subjects": {}, "grand_total": None, "days": [], "analysis": {}}

    # 1. Parse Student Profile
    for cell in soup.find_all(["td", "th"]):
        txt = text_of(cell)
        if "Roll No" in txt or "HTNO" in txt:
            data["profile"]["roll"] = txt.split(":")[-1].strip() if ":" in txt else txt
        elif "Student" in txt or "Name" in txt:
            data["profile"]["name"] = txt.split(":")[-1].strip() if ":" in txt else txt

    # 2. Parse Tables
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        table_text = table.get_text().lower()

        # Subject-wise attendance table
        if "subject" in table_text and ("classes" in table_text or "c" in table_text):
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue

                subj_name = text_of(cells[0])
                c_val = text_of(cells[1])
                a_val = text_of(cells[2])

                if "total" in subj_name.lower():
                    if c_val.isdigit() and a_val.isdigit():
                        data["grand_total"] = {"held": int(c_val), "present": int(a_val)}
                    continue

                if c_val.isdigit() and a_val.isdigit():
                    if subj_name.lower() in ["subject", "classes", "attendance"]:
                        continue
                    
                    held = int(c_val)
                    present = int(a_val)
                    subject_analysis = calculate_analysis(held, present)
                    
                    data["subjects"][subj_name] = {
                        "held": held,
                        "present": present,
                        "pct": subject_analysis["current_pct"],
                        "status": subject_analysis["status"],
                        "margin_message": subject_analysis["margin_message"]
                    }

        # Daily Attendance Table
        if "periods" in table_text or "date" in table_text:
            for row in rows:
                cells = row.find_all(["td", "th"])
                if len(cells) < 4:
                    continue

                date_text = text_of(cells[0])
                if re.match(r"^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}$", date_text):
                    period_cells = [text_of(c).upper() for c in cells[1:-2]]
                    periods = [p for p in period_cells if p in ("P", "A")]

                    tot_txt = text_of(cells[-2])
                    att_txt = text_of(cells[-1])

                    total = int(tot_txt) if tot_txt.isdigit() else len(periods)
                    attend = int(att_txt) if att_txt.isdigit() else periods.count("P")

                    data["days"].append({
                        "date": date_text,
                        "periods": periods,
                        "total": total,
                        "attend": attend
                    })

    # Overall Analysis calculation
    if data["grand_total"]:
        data["analysis"] = calculate_analysis(
            data["grand_total"]["held"],
            data["grand_total"]["present"]
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
        print(f"Unexpected login error: {e}")
        return render_template("index.html", error="An unexpected error occurred. Please check your credentials and try again.")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(debug=True)
