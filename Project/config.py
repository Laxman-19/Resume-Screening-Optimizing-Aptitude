"""
Central configuration. Everything sensitive is read from environment
variables so that no secrets ever live in the source code.

Local development: values are read from a .env file (see .env.example).
Production (Render): values are set in the dashboard / render.yaml.
"""
import os
from dotenv import load_dotenv

# Load a local .env file if present (no-op in production where real env vars are set)
load_dotenv()


def _normalize_db_url(url: str) -> str:
    """
    Managed Postgres providers (Render, Heroku, Railway) hand out URLs that
    start with 'postgres://'. SQLAlchemy 2.x requires the 'postgresql://'
    scheme, so we rewrite it. Everything else is passed through untouched.
    """
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    # Database:
    #   - In production set DATABASE_URL (e.g. the Render Postgres internal URL).
    #   - Locally, with no DATABASE_URL set, we fall back to a SQLite file so
    #     the app runs out of the box.
    SQLALCHEMY_DATABASE_URI = _normalize_db_url(
        os.getenv("DATABASE_URL", "sqlite:///resume_app.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Recycle connections so a sleeping free-tier Postgres doesn't return a
    # stale/dropped connection after the web service wakes up.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Where uploaded resumes are temporarily written.
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB total upload cap

    # Google Gemini (resume optimizer). Accept either env name.
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Email (sending test links / notifications). Optional: if unset, the app
    # still runs and simply skips sending, flashing a message instead.
    EMAIL_SENDER = os.getenv("EMAIL_SENDER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
    EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
