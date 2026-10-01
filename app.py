#!/usr/bin/env python3
import json
import re
from bs4 import BeautifulSoup
from cachetools import TTLCache
from flask import Flask, render_template, request, jsonify
from flask_compress import Compress
from flask_talisman import Talisman

app = Flask(__name__)
Compress(app)

# Content Security Policy configured for client-side proxy communication
csp = {
    'default-src': "'self'",
    'script-src': ["'self'", "'unsafe-inline'", "'unsafe-eval'"],
    'style-src': ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com"],
    'font-src': ["'self'", "https://fonts.gstatic.com"],
    'connect-src': ["'self'", "https://corsproxy.io", "https://api.allorigins.win"],
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
                if not re.match(r"^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}$", date):
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
    return render_template("index.html")


@app.route("/parse", methods=["POST"])
def parse():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "").strip()
    html_content = payload.get("html", "")

    if not html_content:
        return jsonify({"success": False, "error": "No HTML content received."}), 400

    parsed_data = parse_dashboard_html(html_content)

    if not parsed_data["subjects"] and not parsed_data["days"] and not parsed_data["grand_total"]:
        return jsonify({"success": False, "error": "Logged in, but no attendance tables could be parsed."}), 422

    # Store parsed result in server cache
    if username:
        ATTENDANCE_CACHE[username] = parsed_data

    return jsonify({"success": True, "redirect": f"/dashboard?user={username}"})


@app.route("/dashboard", methods=["GET"])
def dashboard():
    username = request.args.get("user", "").strip()

    if username and username in ATTENDANCE_CACHE:
        parsed_data = ATTENDANCE_CACHE[username]
    else:
        return render_template("index.html", error="Session expired or invalid user. Please log in again.")

    return render_template("dashboard.html", data_json=json.dumps(parsed_data))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


if __name__ == "__main__":
    app.run(debug=True)
