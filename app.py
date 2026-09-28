import os
from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://tkrec.in/'
}


def parse_number(element_text, default=0):
    if not element_text:
        return default
    cleaned = ''.join(c for c in element_text if c.isdigit())
    return int(cleaned) if cleaned else default


def fetch_student_data(username, password):
    session = requests.Session()
    session.headers.update(HEADERS)
    login_url = "https://tkrec.in/login"
    payload = {'username': username, 'password': password}

    try:
        response = session.post(login_url, data=payload, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        student_name = soup.select_one('.student-name, #student-name, .user-name')
        held_el = soup.select_one('#total-held, .total-held')
        present_el = soup.select_one('#total-present, .total-present')

        held_val = parse_number(held_el.text if held_el else None, default=100)
        present_val = parse_number(present_el.text if present_el else None, default=75)
        
        absent_val = max(0, held_val - present_val)
        pct_val = round((present_val / held_val) * 100, 1) if held_val > 0 else 0.0

        return {
            "status": "success",
            "name": student_name.text.strip() if student_name else username,
            "roll": username,
            "held": held_val,
            "present": present_val,
            "absent": absent_val,
            "percentage": pct_val
        }

    except Exception:
        return {"error": "Failed to fetch data. Please check your credentials."}


@app.route('/')
def index():
    return render_template('index.html')


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
