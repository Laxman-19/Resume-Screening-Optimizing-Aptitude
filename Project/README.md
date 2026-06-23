# TalentLens - Resume Screening and Analyzing

A Flask app for resume screening (TF-IDF matching), AI resume optimization
(Google Gemini), and aptitude testing for candidates.

## Quick start (local)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# edit the included .env and add your GEMINI_API_KEY
python app.py                    # http://127.0.0.1:5000
```

The app boots with SQLite out of the box - no database setup needed. Only the
AI optimizer needs a `GEMINI_API_KEY` (free from https://aistudio.google.com/apikey).

## Deploy on Render

Push to GitHub, then create a **New Web Service** from the repo:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn "app:app" --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- Environment variables: `SECRET_KEY`, `GEMINI_API_KEY` (and the `EMAIL_*` vars
  if you want email). Leave `DATABASE_URL` unset to use SQLite.

See **Project Description.txt** for full details (architecture, env vars,
database/hosting notes, and what changed from the original project).
