# TKREC Attendance Dashboard

A modern, highly optimized web application built with Python (Flask) that safely scrapes and enhances the attendance dashboard from the official TKREC student portal. 

It provides real-time attendance statistics, an interactive target calculator, and bunk forecasting, all wrapped in a clean, dark-themed UI with strict privacy and rate-limiting protections.

**Live Demo:** [mytkem.vercel.app](https://mytkem.vercel.app)

---

## Key Features

* **Advanced Scraper Integration:** Direct authentication with the official portal using `requests.Session()` pooling, User-Agent masking, and explicit timeouts to prevent serverless IP blocking.
* **Privacy-First Architecture:** Zero credential storage. Authentication details are processed transiently in-memory, complying with strict data minimization principles.
* **Interactive Calculators:** Calculate how many consecutive classes are needed to reach (or safely miss) target percentages (65%, 75%, 85%, 90%).
* **SEO & Social Ready:** Fully configured with Open Graph (`og:image`, `og:title`) meta tags for rich link previews on WhatsApp, Telegram, and social media.
* **Accessible UI:** Dark-themed responsive interface built with WCAG-compliant color contrast, explicit form labels, and keyboard-friendly navigation.
* **Legal Compliance:** Integrated Terms of Service and Privacy Policy pages clarifying data usage and unofficial status.

---

## Project Structure

```text
Mytkem/
├── app.py              # Flask server, session pooling, and scraping logic
├── static/
│   ├── style.css       # Dark dashboard styling and layout
│   ├── preview.png     # Open Graph social sharing thumbnail
│   └── favicon.ico     # Site favicon
├── templates/
│   ├── index.html      # Login page (SEO optimized, accessible)
│   ├── dashboard.html  # Main analysis and charting dashboard
│   ├── privacy.html    # Privacy policy and zero-storage guarantee
│   └── terms.html      # Unofficial utility disclaimers
├── public/
│   └── robots.txt      # Search engine crawler instructions
├── requirements.txt    # Python dependencies (Flask, requests, gunicorn)
└── README.md           # Project documentation
