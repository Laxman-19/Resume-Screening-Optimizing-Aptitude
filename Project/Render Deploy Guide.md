## Deploy on Render

Push to GitHub, then create a **New Web Service** from the repo:

- Set root as Project.
- Build command: pip install -r requirements.txt
- Start command: gunicorn --chdir Project app:app --workers 2 --timeout 120
- Environment variables: `SECRET_KEY`, `GEMINI_API_KEY` (and the `EMAIL_*` vars if you want email). Leave `DATABASE_URL` unset to use SQLite.

