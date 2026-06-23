"""
Screening blueprint.

Workflow:
  1. HR pastes a job description and uploads several resumes.
  2. We extract text, build a TF-IDF matrix over [JD] + resumes, and rank
     candidates by cosine similarity to the JD.
  3. The top candidates are parsed for name/email/skills and shown.
  4. HR can email the shortlisted candidates or send them aptitude-test links.

The shortlisted emails are stored in the Flask session (per-user) instead of a
module-level global, so concurrent users don't clobber each other.
"""
import json
import os
import secrets
from datetime import datetime, timedelta

from flask import (
    Blueprint, current_app, flash, jsonify, redirect,
    render_template, request, send_from_directory, session, url_for,
)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from werkzeug.utils import secure_filename

from extensions import db
from models import AptitudeTest, Candidate, TestLink
from utils.email_utils import send_email
from utils.resume_parser import parse_resume
from utils.text_extract import extract_text

screening_bp = Blueprint("screeningbp", __name__)


def _upload_dir():
    path = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(path, exist_ok=True)
    return path


@screening_bp.route("/")
def screening_home():
    available_tests = AptitudeTest.query.all()
    return render_template("screening.html", available_tests=available_tests)


@screening_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(_upload_dir(), filename)


@screening_bp.route("/matcher", methods=["GET", "POST"])
def matcher():
    available_tests = AptitudeTest.query.all()

    if request.method != "POST":
        return render_template("screening.html", available_tests=available_tests)

    job_description = (request.form.get("job_description") or "").strip()
    resume_files = request.files.getlist("resumes")

    resumes_text, resume_filenames, resume_paths = [], [], []
    upload_dir = _upload_dir()

    for f in resume_files:
        if not f or not f.filename:
            continue
        safe_name = secure_filename(f.filename)
        dest = os.path.join(upload_dir, safe_name)
        f.save(dest)
        resumes_text.append(extract_text(dest))
        resume_filenames.append(safe_name)
        resume_paths.append(dest)

    if not resumes_text or not job_description:
        return render_template(
            "screening.html",
            message="Please enter a job description and upload at least one resume.",
            available_tests=available_tests,
        )

    # TF-IDF: first row is the JD, the rest are resumes.
    vectors = TfidfVectorizer(stop_words="english").fit_transform(
        [job_description] + resumes_text
    ).toarray()
    job_vector, resume_vectors = vectors[0], vectors[1:]
    similarities = cosine_similarity([job_vector], resume_vectors)[0]

    # Rank ALL resumes by similarity, highest first. HR chooses how many to
    # act on from the UI (Top N quick-select or manual checkboxes).
    order = list(similarities.argsort()[::-1])

    ranked_resumes = [resume_filenames[i] for i in order]
    ranked_scores = [round(float(similarities[i]), 5) for i in order]

    people, emails = [], []
    for i in order:
        data = parse_resume(resumes_text[i], resume_paths[i])
        people.append(data)
        emails.append(data.get("email") or "Email not found")

    # Persist matched emails for the /send_emails fallback (per session).
    session["shortlisted_emails"] = emails

    count = len(ranked_resumes)
    return render_template(
        "screening.html",
        message=f"{count} candidate{'s' if count != 1 else ''} ranked by match. "
                "Select who to email or send a test to.",
        resumes=ranked_resumes,
        scores=ranked_scores,
        people=people,
        zip=zip,
        emails=emails,
        available_tests=available_tests,
    )


def _parse_selected(raw_list):
    """Parse the selected_candidates[] JSON blobs into clean dicts."""
    out = []
    for blob in raw_list:
        try:
            data = json.loads(blob)
        except (ValueError, TypeError):
            continue
        email = (data.get("email") or "").strip()
        if not email or email == "Email not found":
            continue
        out.append({"name": (data.get("name") or email.split("@")[0]).strip(), "email": email})
    return out


@screening_bp.route("/send_emails", methods=["POST"])
def send_emails():
    # Prefer the explicitly selected candidates; fall back to the session list.
    selected = _parse_selected(request.form.getlist("selected_candidates[]"))
    if selected:
        recipients = [c["email"] for c in selected]
    else:
        recipients = [e for e in session.get("shortlisted_emails", []) if e and e != "Email not found"]

    if not recipients:
        return jsonify(success=False, message="No valid candidates were selected."), 400

    subject = (request.form.get("subject") or "Application Update").strip() or "Application Update"
    body = (request.form.get("body") or "").strip() or \
        "Hello, this is a message from the TalentLens recruitment team regarding your application."

    sent = 0
    for email in recipients:
        if send_email(email, subject, body):
            sent += 1

    if sent:
        msg = f"Emailed {sent} of {len(recipients)} selected candidate(s)."
    else:
        msg = (f"Prepared emails for {len(recipients)} candidate(s), but email isn't configured "
               "(set EMAIL_SENDER / EMAIL_PASSWORD), so none were sent.")
    return jsonify(success=True, sent=sent, total=len(recipients), message=msg)


@screening_bp.route("/send_test_links", methods=["POST"])
def send_test_links():
    test_id = request.form.get("test_id")
    selected = _parse_selected(request.form.getlist("selected_candidates[]"))

    if not test_id or not selected:
        return jsonify(success=False, message="Choose a test and at least one candidate."), 400

    test = db.session.get(AptitudeTest, int(test_id)) if test_id.isdigit() else None
    if not test:
        return jsonify(success=False, message="Selected test was not found."), 404

    created, emailed = 0, 0
    for cand in selected:
        candidate = Candidate.query.filter_by(email=cand["email"]).first()
        if not candidate:
            candidate = Candidate(name=cand["name"], email=cand["email"])
            db.session.add(candidate)
            db.session.commit()  # commit so candidate.id is available

        token = secrets.token_urlsafe(32)
        test_link = TestLink(
            token=token,
            test_id=test.id,
            candidate_id=candidate.id,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.session.add(test_link)
        db.session.commit()
        created += 1

        test_url = url_for("aptitude.take_test", token=token, _external=True)
        if _send_test_invite(candidate.email, candidate.name, test.title, test_url):
            emailed += 1

    if emailed:
        msg = f'Sent "{test.title}" to {emailed} candidate(s).'
    else:
        msg = (f'Created {created} link(s) for "{test.title}", but email isn\'t configured '
               "(set EMAIL_SENDER / EMAIL_PASSWORD), so invites weren't emailed.")
    return jsonify(success=True, created=created, emailed=emailed, test=test.title, message=msg)


def _send_test_invite(to_email, candidate_name, test_title, test_url):
    body = f"""\
Dear {candidate_name},

You have been selected to take an aptitude test as part of your application.

Test: {test_title}
Valid for: 7 days

Start your test here:
{test_url}

Best regards,
The Recruitment Team
"""
    return send_email(to_email, f"Aptitude Test: {test_title}", body)


@screening_bp.route("/get_available_tests")
def get_available_tests():
    tests = AptitudeTest.query.all()
    return jsonify([{"id": t.id, "title": t.title} for t in tests])
