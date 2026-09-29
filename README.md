# TKREC Attendance Tracker & Visualizer

A fast, lightweight web application built with Flask and Python designed to help students at **TKR College of Engineering and Technology** effortlessly check, visualize, and analyze their attendance metrics.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)
![Deployment](https://img.shields.io/badge/Deployment-Vercel-black.svg)

---

## Key Features

* **Real-time Attendance Scraping:** Authenticates securely with the official TKREC student portal to fetch up-to-date attendance records instantly.
* **Interactive Dashboard:** Beautiful dark-themed interface showcasing overall attendance percentage, subject-wise breakdowns, and daily logs.
* **Smart Bunk & Projection Simulator:** Interactive tools to calculate how many classes you can afford to skip (or need to attend) to hit target attendance percentages.
* **Privacy-First Design:** Zero database storage. User credentials and attendance details are processed in-memory during session requests and immediately discarded.
* **Terms & Privacy Integration:** Built-in dedicated legal pages outlining data privacy and app terms.

---

## Project Structure

```text
├── app.py                  # Flask application server & web scraper logic
├── requirements.txt        # Python dependencies
├── vercel.json             # Deployment configuration for Vercel
├── static/
│   └── style.css           # Global styling for login, dashboard, and legal pages
└── templates/
    ├── index.html          # Login page template
    ├── dashboard.html      # Attendance visualizer & calculator dashboard
    ├── terms.html          # Terms & Conditions page
    └── privacy.html        # Privacy Policy page
