# TKREC Attendance Dashboard

A lightweight, locally hosted web application built with Python (Flask) that scrapes and enhances the attendance dashboard from the TKREC student portal (`tkrec.in`).

It provides real-time statistics, an interactive attendance target calculator, daily logs, and bunk forecasting—all wrapped in a clean, modern user interface.

---

## Features

- **Local & Secure:** Runs exclusively on your local machine (`127.0.0.1:5000`). Credentials are sent directly to the official portal for authentication and are never stored anywhere.
- **Attendance Gauge:** Instant visual overview of your overall percentage status.
- **Target Calculator:** Calculate how many consecutive classes you need to attend (or how many you can safely miss) to reach or maintain a specific target percentage (e.g., 75%).
- **Bunk Predictor:** Analyze how skipping 1 class, a half day, or a full day affects your overall attendance percentage.
- **Time Tracker:** Estimates total hours spent in class based on period duration settings.
- **Subject-wise Breakdown & Daily Logs:** Visual period-by-period breakdown for recent daily records and individual subjects.

---

## Project Structure

```text
attendance_app/
├── app.py                 # Flask server & scraping/parsing logic
├── static/
│   └── style.css          # Modern dark-themed CSS styling
└── templates/
    ├── index.html         # Login interface
    └── dashboard.html     # Interactive attendance dashboard
