"""
Email helpers. Credentials come from environment variables (never hardcoded).

If EMAIL_SENDER / EMAIL_PASSWORD are not configured, send_email() returns
False instead of raising, so the rest of the app keeps working in a
demo/no-email setup.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app


def _smtp_config():
    cfg = current_app.config
    return (
        cfg.get("EMAIL_SENDER"),
        cfg.get("EMAIL_PASSWORD"),
        cfg.get("EMAIL_SMTP_HOST", "smtp.gmail.com"),
        cfg.get("EMAIL_SMTP_PORT", 587),
    )


def send_email(to_email: str, subject: str, body: str, html: bool = False) -> bool:
    sender, password, host, port = _smtp_config()
    if not sender or not password:
        print("[email] EMAIL_SENDER/EMAIL_PASSWORD not configured; skipping send.")
        return False

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html" if html else "plain"))

    try:
        if int(port) == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        server.login(sender, password)
        server.sendmail(sender, to_email, msg.as_string())
        server.quit()
        print(f"[email] sent to {to_email}")
        return True
    except Exception as exc:
        print(f"[email] failed to send to {to_email}: {exc}")
        return False
