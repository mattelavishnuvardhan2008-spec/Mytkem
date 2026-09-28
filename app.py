import os
from flask import Flask, render_template, request, jsonify
import requests

app = Flask(__name__)

# Standard Chrome User-Agent header to avoid basic scraper/bot blocks
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': 'https://tkrec.in/'
}

# Optional proxy configuration via Vercel Environment Variables
PROXY_URL = os.getenv('PROXY_URL')
PROXIES = {'http': PROXY_URL, 'https': PROXY_URL} if PROXY_URL else None


def fetch_student_data(username, password):
    """
    Creates a persistent HTTP session to authenticate and fetch attendance data.
    Reuses TCP connections and enforces a strict timeout to prevent Vercel 504 errors.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    
    login_url = "https://tkrec.in/login"  # Replace with target login endpoint
    payload = {
        'username': username,
        'password': password
    }

    try:
        # 8-second timeout prevents exceeding Vercel's 10-second execution limit
        response = session.post(
            login_url, 
            data=payload, 
            proxies=PROXIES, 
            timeout=8
        )
        response.raise_for_status()

        # Insert HTML parsing logic here
        return {"status": "success", "data": response.text}

    except requests.exceptions.Timeout:
        return {"error": "The college portal is taking too long to respond. Please try again shortly."}
    except requests.exceptions.RequestException:
        return {"error": "Failed to connect to the college portal. Please check your credentials or try later."}


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

    result = fetch_student_data(username, password)

    if "error" in result:
        return render_template('index.html', error=result["error"])

    return render_template('dashboard.html', data_json=result)


if __name__ == '__main__':
    app.run(debug=True)
    
