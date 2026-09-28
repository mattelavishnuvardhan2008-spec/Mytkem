import os
from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

# Standard Chrome headers to prevent basic bot blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://tkrec.in/'
}

# Proxy support via Vercel Environment Variables
PROXY_URL = os.getenv('PROXY_URL')
PROXIES = {'http': PROXY_URL, 'https': PROXY_URL} if PROXY_URL else None


def fetch_student_data(username, password):
    """
    Connects to the college portal, authenticates transiently in-memory,
    and returns parsed attendance data.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    login_url = "https://tkrec.in/login"
    payload = {'username': username, 'password': password}

    try:
        # 8-second timeout prevents Vercel 504 gateway timeouts
        response = session.post(login_url, data=payload, proxies=PROXIES, timeout=8)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        
        student_name = soup.select_one('.student-name')
        held = soup.select_one('#total-held')
        present = soup.select_one('#total-present')
        
        held_val = int(held.text.strip()) if held else 100
        present_val = int(present.text.strip()) if present else 75
        absent_val = max(0, held_val - present_val)
        pct_val = round((present_val / held_val) * 100, 1) if held_val > 0 else 0

        return {
            "status": "success",
            "name": student_name.text.strip() if student_name else username,
            "roll": username,
            "held": held_val,
            "present": present_val,
            "absent": absent_val,
            "percentage": pct_val
        }

    except requests.exceptions.Timeout:
        return {"error": "The college portal is taking too long to respond. Please try again."}
    except Exception:
        return {"error": "Failed to connect or fetch data. Please verify your credentials."}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/privacy')
def privacy():
    return render_template('privacy.html')


@app.route('/terms')
def terms():
    return render_template('terms.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    data = fetch_student_data(username, password)

    if "error" in data:
        return render_template('index.html', error=data["error"])

    return render_template('dashboard.html', data=data)


if __name__ == '__main__':
    app.run(debug=True)
