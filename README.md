# TKREC Attendance Dashboard

A modern, lightweight web application built with Python (Flask) that scrapes and enhances the attendance dashboard from the official TKREC student portal (`tkrec.in`).

It provides real-time attendance statistics, an interactive target calculator, daily attendance logs, and bunk forecasting—all wrapped in a clean, dark-themed user interface.

---

## Features

* **Instant Scraper Integration:** Direct authentication against the official portal with zero credential storage.
* **Overall Attendance Gauge:** Visual circular progress arc displaying current percentage status.
* **Target Percentage Calculator:** Calculate how many consecutive classes you need to attend (or safely miss) to reach or maintain target attendance (65%, 75%, 85%, 90%).
* **Bunk Forecasting:** Preview how skipping 1 class, a half day, or a full day affects your overall percentage.
* **Live Class Simulator:** Interactive slider to project future percentage increases.
* **Subject-Wise Breakdown & Daily Log:** Visual period-by-period breakdown for recent daily records and individual subjects.
* **Responsive Dark Interface:** Styled with clean typography and custom top navigation.

---

## Project Structure

```text
Mytkem/
├── app.py              # Flask server, scraping & parsing logic
├── static/
│   └── style.css       # Complete dark & dashboard styling
├── templates/
│   ├── index.html      # Login page
│   └── dashboard.html  # Main analysis dashboard
├── requirements.txt    # Python dependencies
├── vercel.json         # Vercel deployment configuration
└── README.md           # Project documentation
