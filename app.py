#!/usr/bin/env python3
import json
import math
import os
import re
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from flask_compress import Compress
from flask_talisman import Talisman

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

Compress(app)

# Updated CSP to allow client-side fetches to CORS proxies
csp = {
    'default-src': "'self'",
    'script-src': ["'self'", "'unsafe-inline'"],
    'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
    'font-src': ["'self'", "https://fonts.gstatic.com"],
    'connect-src': ["'self'", "https://api.allorigins.win", "https://corsproxy.io"],
    'img-src': ["'self'", "data:", "https:"]
}

Talisman(
    app,
    content_security_policy=csp,
    force_https=True,
    session_cookie_secure=True,
    session_cookie_http_only=True
)


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


def parse_dashboard_html(html):
    soup = BeautifulSoup(html, "html.parser")
    data = {"profile": {}, "subjects": {}, "grand_total": None, "days": [], "analysis": {}}

    def extract_int(val_str):
        numbers = re.findall(r'\d+', val_str)
        return int(numbers[0]) if numbers else None

    # Parse Student Profile
    for cell in soup.find_all(["td", "th", "div", "span"]):
        txt = text_of(cell)
        if ("Roll No" in txt or "HTNO" in txt or "PIN" in txt) and ":" in txt:
            data["profile"]["roll"] = txt.split(":")[-1].strip()
        elif ("Student" in txt or "Name" in txt) and ":" in txt:
            data["profile"]["name"] = txt.split(":")[-1].strip()

    all_rows = soup.find_all("tr")

    # Extract Subject Metrics and Grand Total
    total_held_sum = 0
    total_present_sum = 0

    for row in all_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        row_text = [text_of(c) for c in cells]
        combined_text = " ".join(row_text).lower()

        if any(kw in combined_text for kw in ["s.no", "sl.no", "subject name", "code", "percentage", "%"]):
            if "total" not in combined_text:
                continue

        row_numbers = []
        subject_label = ""

        for cell_txt in row_text:
            num = extract_int(cell_txt)
            if num is not None:
                row_numbers.append(num)
            elif not subject_label and len(cell_txt) > 2:
                subject_label = cell_txt

        if len(row_numbers) >= 2:
            held = row_numbers[0]
            present = row_numbers[1]

            if present <= held and held > 0:
                if "total" in combined_text or "grand" in combined_text:
                    data["grand_total"] = {"held": held, "present": present}
                else:
                    if not subject_label:
                        subject_label = f"Subject {len(data['subjects']) + 1}"
                    
                    analysis = calculate_analysis(held, present)
                    data["subjects"][subject_label] = {
                        "held": held,
                        "present": present,
                        "pct": analysis["current_pct"],
                        "status": analysis["status"],
                        "margin_message": analysis["margin_message"]
                    }
                    total_held_sum += held
                    total_present_sum += present

    if not data["grand_total"] and total_held_sum > 0:
        data["grand_total"] = {"held": total_held_sum, "present": total_present_sum}

    # Extract Daily History
    for row in all_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 3:
            continue

        date_text = text_of(cells[0])
        if re.match(r"^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}$", date_text):
            period_cells = [text_of(c).upper() for c in cells[1:-2]]
            periods = [p for p in period_cells if p in ("P", "A", "PRES", "ABS")]

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


# --- ROUTES ---

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/parse", methods=["POST"])
def parse():
    payload = request.get_json(silent=True) or {}
    html_content = payload.get("html", "")

    if not html_content:
        return jsonify({"success": False, "error": "No HTML content received."}), 400

    parsed_data = parse_dashboard_html(html_content)

    if not parsed_data["subjects"] and not parsed_data["days"] and not parsed_data["grand_total"]:
        return jsonify({"success": False, "error": "Dashboard loaded, but attendance data could not be parsed."}), 422

    return jsonify({"success": True, "data": parsed_data})


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(debug=False)
    
