#!/usr/bin/env python3
import json
import math
import os
import re
from bs4 import BeautifulSoup
from cachetools import TTLCache
from flask import Flask, render_template, request
from flask_compress import Compress
from flask_talisman import Talisman

# Anti-Bot TLS Fingerprinting
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests
    HAS_CURL_CFFI = False

BASE_URL = "https://tkrec.in"
LOGIN_PAGE = f"{BASE_URL}/index.php"
LOGIN_ACTION = f"{BASE_URL}/student_login_action.php"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

Compress(app)
csp = {
    'default-src': "'self'",
    'script-src': ["'self'", "'unsafe-inline'"],
    'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
    'font-src': ["'self'", "https://fonts.gstatic.com"],
    'img-src': ["'self'", "data:", "https:"]
}

Talisman(
    app,
    content_security_policy=csp,
    force_https=True,
    session_cookie_secure=True,
    session_cookie_http_only=True
)

# 30-minute server cache to mitigate rate-limiting
ATTENDANCE_CACHE = TTLCache(maxsize=500, ttl=1800)


def text_of(el):
    return el.get_text(strip=True) if el else ""


def calculate_analysis(held, present, target_pct=75.0):
    if held <= 0:
        return {"current_pct": 0.0, "status": "No Data", "margin_message": "No classes recorded yet."}

    current_pct = (present / held) * 100.0

    if current_pct >= target_pct:
        bunkable = math.floor((100 * present - target_pct * held) / target_pct)
        return {
            "current_pct": round(current_pct, 2),
            "status": "Safe",
            "bunkable": bunkable,
            "margin_message": f"You can safely skip {bunkable} classes while maintaining {target_pct}%."
        }
    else:
        needed = math.ceil((target_pct * held - 100 * present) / (100 - target_pct))
        return {
            "current_pct": round(current_pct, 2),
            "status": "Shortage",
            "needed": needed,
            "margin_message": f"You must attend {needed} consecutive classes to reach {target_pct}%."
        }


def get_http_session():
    if HAS_CURL_CFFI:
        return curl_requests.Session(impersonate="chrome120")
    import requests
    return requests.Session()


def authenticate_and_fetch_html(username, password):
    session = get_http_session()
    if not HAS_CURL_CFFI:
        session.headers.update(HEADERS)

    try:
        session.get(BASE_URL, timeout=10)
        res = session.get(LOGIN_PAGE, timeout=10)
        
        soup = BeautifulSoup(res.text, "html.parser")
        token_input = (
            soup.find("input", {"name": "token"}) or
            soup.find("input", {"name": "csrf_token"}) or
            soup.find("input", {"name": "csrf"})
        )
        token = token_input["value"] if (token_input and token_input.get("value")) else ""

        login_payload = {"username": username, "password": password, "submit": "Login"}
        if token:
            login_payload["token"] = token

        post_headers = {**HEADERS, "Referer": LOGIN_PAGE} if not HAS_CURL_CFFI else {}
        res_login = session.post(LOGIN_ACTION, data=login_payload, headers=post_headers, timeout=10)
        
        html_content = res_login.text
        if "studentloginform" in html_content.lower() or "invalid" in html_content.lower():
            res_dashboard = session.get(f"{BASE_URL}/student/index.php", timeout=10)
            if "studentloginform" in res_dashboard.text.lower():
                raise RuntimeError("Invalid Roll Number or Password.")
            html_content = res_dashboard.text

        return html_content
    finally:
        session.close()


def parse_dashboard_html(html):
    soup = BeautifulSoup(html, "html.parser")
    data = {"profile": {}, "subjects": {}, "grand_total": None, "days": [], "analysis": {}}

    all_rows = soup.find_all("tr")

    def extract_int(val_str):
        numbers = re.findall(r'\d+', val_str)
        return int(numbers[0]) if numbers else None

    # Parse Details
    for cell in soup.find_all(["td", "th"]):
        txt = text_of(cell)
        if "Roll No" in txt or "HTNO" in txt:
            data["profile"]["roll"] = txt.split(":")[-1].strip() if ":" in txt else txt
        elif "Student" in txt or "Name" in txt:
            data["profile"]["name"] = txt.split(":")[-1].strip() if ":" in txt else txt

    # Parse Subject Metrics
    for row in all_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        col0 = text_of(cells[0])
        col1_str = text_of(cells[1])
        col2_str = text_of(cells[2])

        if any(kw in col0.lower() for kw in ["subject", "classes", "absentees", "message"]):
            continue

        held = extract_int(col1_str)
        present = extract_int(col2_str)

        if held is None or present is None:
            continue

        if "total" in col0.lower() or "grand" in col0.lower():
            data["grand_total"] = {"held": held, "present": present}
        else:
            analysis = calculate_analysis(held, present)
            data["subjects"][col0] = {
                "held": held,
                "present": present,
                "pct": analysis["current_pct"],
                "status": analysis["status"],
                "margin_message": analysis["margin_message"]
            }

    # Parse Daily History
    for row in all_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 4:
            continue

        date_text = text_of(cells[0])
        if re.match(r"^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}$", date_text):
            period_cells = [text_of(c).upper() for c in cells[1:-2]]
            periods = [p for p in period_cells if p in ("P", "A")]

            tot_val = extract_int(text_of(cells[-2]))
            att_val = extract_int(text_of(cells[-1]))

            data["days"].append({
                "date": date_text,
                "periods": periods,
                "total": tot_val if tot_val is not None else len(periods),
                "attend": att_val if att_val is not None else periods.count("P")
            })

    if data["grand_total"]:
        data["analysis"] = calculate_analysis(
            data["grand_total"]["held"],
            data["grand_total"]["present"]
        )

    return data


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password or len(username) > 30 or not re.match(r"^[a-zA-Z0-9]+$", username):
        return render_template("index.html", error="Invalid input formatting.")

    if username in ATTENDANCE_CACHE:
        return render_template("dashboard.html", data_json=json.dumps(ATTENDANCE_CACHE[username]))

    try:
        html = authenticate_and_fetch_html(username, password)
        parsed_data = parse_dashboard_html(html)

        if not parsed_data["subjects"] and not parsed_data["days"] and not parsed_data["grand_total"]:
            return render_template("index.html", error="Dashboard found, but attendance format could not be parsed.")

        ATTENDANCE_CACHE[username] = parsed_data
        return render_template("dashboard.html", data_json=json.dumps(parsed_data))

    except RuntimeError as err:
        return render_template("index.html", error=str(err))
    except Exception:
        return render_template("index.html", error="Portal connection timeout. Try again shortly.")
