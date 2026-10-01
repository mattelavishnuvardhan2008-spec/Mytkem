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

# Optional import for advanced TLS fingerprinting to bypass strict anti-bot WAFs
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests
    HAS_CURL_CFFI = False

BASE_URL = "https://tkrec.in"
LOGIN_PAGE = f"{BASE_URL}/index.php"
LOGIN_ACTION = f"{BASE_URL}/student_login_action.php"

# Real browser request headers to avoid automated blocklisting
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
}

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Security Headers Configuration
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

# Server-Side Cache: 500 records max for 30 minutes to reduce upstream rate-limiting
ATTENDANCE_CACHE = TTLCache(maxsize=500, ttl=1800)


def text_of(el):
    """Helper to safely extract stripped text from HTML tags."""
    return el.get_text(strip=True) if el else ""


def calculate_analysis(held, present, target_pct=75.0):
    """Calculates attendance percentages, bunk margins, or required classes."""
    if held <= 0:
        return {
            "current_pct": 0.0,
            "status": "No Data",
            "margin_message": "No classes recorded yet."
        }

    current_pct = (present / held) * 100.0

    if current_pct >= target_pct:
        bunkable = math.floor((100 * present - target_pct * held) / target_pct)
        return {
            "current_pct": round(current_pct, 2),
            "status": "Safe",
            "bunkable": bunkable,
            "margin_message": (
                f"You can safely skip the next {bunkable} classes while staying above {target_pct}%."
                if bunkable > 0 else f"You are currently right at the {target_pct}% threshold."
            )
        }
    else:
        needed = math.ceil((target_pct * held - 100 * present) / (100 - target_pct))
        return {
            "current_pct": round(current_pct, 2),
            "status": "Shortage",
            "needed": needed,
            "margin_message": f"You must attend the next {needed} classes consecutively to hit {target_pct}%."
        }


def get_http_session():
    """Initializes session client using curl_cffi if available or standard requests."""
    if HAS_CURL_CFFI:
        return curl_requests.Session(impersonate="chrome120")
    import requests
    return requests.Session()


def authenticate_and_fetch_html(username, password):
    """Performs cookie initializations, scrapes tokens, and submits credentials."""
    session = get_http_session()
    
    if not HAS_CURL_CFFI:
        session.headers.update(HEADERS)

    try:
        # Pre-flight request to establish initial PHP session cookie
        session.get(BASE_URL, timeout=10)
        
        # Fetch login page to retrieve embedded tokens
        res = session.get(LOGIN_PAGE, timeout=10)
        
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

        # Post login request
        post_headers = {**HEADERS, "Referer": LOGIN_PAGE} if not HAS_CURL_CFFI else {}
        res_login = session.post(
            LOGIN_ACTION,
            data=login_payload,
            headers=post_headers,
            timeout=10
        )
        
        html_content = res_login.text

        # Redirect check if the portal forwards back to login screen on failure
        if "studentloginform" in html_content.lower() or "invalid" in html_content.lower():
            res_dashboard = session.get(f"{BASE_URL}/student/index.php", timeout=10)
            if "studentloginform" in res_dashboard.text.lower():
                raise RuntimeError("Invalid Roll Number or Password.")
            html_content = res_dashboard.text

        return html_content

    finally:
        session.close()


def parse_dashboard_html(html):
    """Extracts attendance and profile metrics using structural line scans."""
    soup = BeautifulSoup(html, "html.parser")
    data = {
        "profile": {},
        "subjects": {},
        "grand_total": None,
        "days": [],
        "analysis": {}
    }

    all_rows = soup.find_all("tr")

    # 1. Parse Student Details
    for cell in soup.find_all(["td", "th"]):
        txt = text_of(cell)
        if "Roll No" in txt or "HTNO" in txt:
            data["profile"]["roll"] = txt.split(":")[-1].strip() if ":" in txt else txt
        elif "Student" in txt or "Name" in txt:
            data["profile"]["name"] = txt.split(":")[-1].strip() if ":" in txt else txt

    # 2. Extract Subject-wise Metrics
    for row in all_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        col0 = text_of(cells[0])
        col1 = text_of(cells[1])
        col2 = text_of(cells[2])

        # Validate numerical attendance counts
        if not col1.isdigit() or not col2.isdigit():
            continue

        held = int(col1)
        present = int(col2)

        if "total" in col0.lower() or "grand" in col0.lower():
            data["grand_total"] = {"held": held, "present": present}
        else:
            subject_analysis = calculate_analysis(held, present)
            data["subjects"][col0] = {
                "held": held,
                "present": present,
                "pct": subject_analysis["current_pct"],
                "status": subject_analysis["status"],
                "margin_message": subject_analysis["margin_message"]
            }

    # 3. Extract Period-wise Daily History
    for row in all_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 4:
            continue

        date_text = text_of(cells[0])
        # Validate date string (DD-MM-YY or DD/MM/YYYY)
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

    # Overall Attendance Analysis
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

    # Input validation & sanitization guards
    if not username or not password:
        return render_template("index.html", error="Please enter both Roll Number and Password.")

    if len(username) > 30 or not re.match(r"^[a-zA-Z0-9]+$", username):
        return render_template("index.html", error="Invalid Roll Number format.")

    # Check Cache first
    if username in ATTENDANCE_CACHE:
        return render_template("dashboard.html", data_json=json.dumps(ATTENDANCE_CACHE[username]))

    try:
        html = authenticate_and_fetch_html(username, password)
        parsed_data = parse_dashboard_html(html)

        if not parsed_data["subjects"] and not parsed_data["days"] and not parsed_data["grand_total"]:
            return render_template("index.html", error="Authentication succeeded, but attendance tables could not be parsed.")

        # Cache response
        ATTENDANCE_CACHE[username] = parsed_data
        return render_template("dashboard.html", data_json=json.dumps(parsed_data))

    except RuntimeError as err:
        return render_template("index.html", error=str(err))
    except Exception as e:
        # Generic error mask to avoid leaking stack traces to the user
        print(f"Internal Scraping Error: {e}")
        return render_template("index.html", error="Unable to connect to college server. Please verify credentials or try again later.")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(debug=False)
