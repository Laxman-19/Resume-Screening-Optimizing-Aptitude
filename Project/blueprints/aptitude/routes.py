"""
Aptitude blueprint.

HR creates tests/questions, sends tokenized one-time links to candidates,
candidates take the test, answers are auto-scored, and HR views results.

Notable fix vs. the original: test submission now redirects to the existing
`test_results` route (the original referenced a `test_resultcopy` endpoint that
was never defined, which crashed on submit).
"""
import secrets
from datetime import datetime, timedelta

from flask import (
    Blueprint, flash, jsonify, redirect, render_template, request, url_for,
)

from extensions import db
from models import (
    Answer, AptitudeTest, Candidate, Option, Question, TestAttempt, TestLink,
)
from utils.email_utils import send_email

# template_folder so this blueprint finds its own templates/aptitude/*.html
aptitude_bp = Blueprint("aptitude", __name__, template_folder="templates")


def _send_test_link_email(to_email, candidate_name, test_title, test_link):
    body = f"""\
    <html><body>
        <h2>Hello {candidate_name},</h2>
        <p>You have been selected to take an aptitude test as part of your application.</p>
        <p><strong>Test:</strong> {test_title}</p>
        <p><a href="{test_link}"
              style="padding:10px 20px;background:#007bff;color:#fff;
                     text-decoration:none;border-radius:5px;">Start Test</a></p>
        <p>This link will expire in 7 days.</p>
        <p>Best regards,<br>HR Team</p>
    </body></html>
    """
    return send_email(to_email, f"Invitation to take {test_title} Aptitude Test",
                      body, html=True)


# ---- HR: manage tests -----------------------------------------------------
@aptitude_bp.route("/")
def aptitude_home():
    tests = AptitudeTest.query.order_by(AptitudeTest.created_at.desc()).all()
    return render_template("aptitude/home.html", tests=tests)


@aptitude_bp.route("/delete_test/<int:test_id>", methods=["POST"])
def delete_test(test_id):
    test = db.get_or_404(AptitudeTest, test_id)
    for attempt in test.test_attempts:
        Answer.query.filter_by(attempt_id=attempt.id).delete()
    TestAttempt.query.filter_by(test_id=test_id).delete()
    TestLink.query.filter_by(test_id=test_id).delete()
    for question in test.questions:
        Option.query.filter_by(question_id=question.id).delete()
    Question.query.filter_by(test_id=test_id).delete()
    db.session.delete(test)
    db.session.commit()
    flash("Test has been deleted successfully.", "success")
    return redirect(url_for("aptitude.aptitude_home"))


@aptitude_bp.route("/create_test", methods=["GET", "POST"])
def create_test():
    if request.method == "POST":
        new_test = AptitudeTest(
            title=request.form.get("title"),
            description=request.form.get("description"),
            time_limit=request.form.get("time_limit", 60, type=int),
            passing_score=request.form.get("passing_score", 60, type=int),
            created_by=request.form.get("created_by"),
        )
        db.session.add(new_test)
        db.session.commit()
        return redirect(url_for("aptitude.edit_test", test_id=new_test.id))
    return render_template("aptitude/create_test.html")


@aptitude_bp.route("/edit_test/<int:test_id>", methods=["GET", "POST"])
def edit_test(test_id):
    test = db.get_or_404(AptitudeTest, test_id)
    questions = Question.query.filter_by(test_id=test_id).all()
    return render_template("aptitude/edit_test.html", test=test, questions=questions)


@aptitude_bp.route("/add_question/<int:test_id>", methods=["POST"])
def add_question(test_id):
    db.get_or_404(AptitudeTest, test_id)
    new_question = Question(
        test_id=test_id,
        text=request.form.get("question_text"),
        question_type=request.form.get("question_type", "multiple_choice"),
    )
    db.session.add(new_question)
    db.session.commit()

    options = request.form.getlist("option_text[]")
    correct_option = request.form.get("correct_option", type=int)
    for i, option_text in enumerate(options):
        if option_text.strip():
            db.session.add(Option(
                question_id=new_question.id,
                option_text=option_text,
                is_correct=(i == correct_option),
            ))
    db.session.commit()
    return redirect(url_for("aptitude.edit_test", test_id=test_id))


@aptitude_bp.route("/send_test/<int:test_id>", methods=["GET", "POST"])
def send_test(test_id):
    test = db.get_or_404(AptitudeTest, test_id)
    if request.method == "POST":
        candidate_emails = (request.form.get("candidate_emails", "") or "").split(",")
        base_url = request.host_url.rstrip("/")
        for email in candidate_emails:
            email = email.strip()
            if not email:
                continue
            candidate = Candidate.query.filter_by(email=email).first()
            if not candidate:
                candidate = Candidate(name=email.split("@")[0], email=email)
                db.session.add(candidate)
                db.session.commit()

            token = secrets.token_urlsafe(32)
            test_link = TestLink(
                token=token,
                candidate_id=candidate.id,
                test_id=test_id,
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
            db.session.add(test_link)
            db.session.commit()

            test_url = f"{base_url}/aptitude/take_test/{test_link.token}"
            _send_test_link_email(email, candidate.name, test.title, test_url)

        flash("Test links have been sent to the candidates.")
        return redirect(url_for("aptitude.aptitude_home"))
    return render_template("aptitude/send_test.html", test=test)


# ---- Candidate: take test -------------------------------------------------
@aptitude_bp.route("/take_test/<token>")
def take_test(token):
    test_link = TestLink.query.filter_by(token=token).first_or_404()
    if test_link.expires_at < datetime.utcnow():
        return render_template("aptitude/expired.html")
    if test_link.is_used:
        return render_template("aptitude/already_taken.html")

    test = test_link.test
    candidate = test_link.candidate

    attempt = TestAttempt(
        candidate_id=candidate.id, test_id=test.id, start_time=datetime.utcnow()
    )
    db.session.add(attempt)
    db.session.commit()

    questions = Question.query.filter_by(test_id=test.id).all()
    questions_data = [{
        "id": q.id,
        "text": q.text,
        "type": q.question_type,
        "options": Option.query.filter_by(question_id=q.id).all(),
    } for q in questions]

    return render_template(
        "aptitude/take_test.html",
        test=test, candidate=candidate, questions=questions_data,
        attempt_id=attempt.id, time_limit=test.time_limit,
    )


@aptitude_bp.route("/submit_test/<int:attempt_id>", methods=["POST"])
def submit_test(attempt_id):
    attempt = db.get_or_404(TestAttempt, attempt_id)
    attempt.end_time = datetime.utcnow()
    test = attempt.test

    data = request.get_json(silent=True) or {}
    answers = data.get("answers", {})

    correct_count = 0
    total_questions = len(answers)
    for question_index, option_id in answers.items():
        question = db.session.get(Question, int(question_index))
        selected_option = db.session.get(Option, int(option_id))
        if not question or not selected_option:
            continue
        db.session.add(Answer(
            attempt_id=attempt_id,
            question_id=question.id,
            selected_option_id=selected_option.id,
            is_correct=selected_option.is_correct,
        ))
        if selected_option.is_correct:
            correct_count += 1

    score = (correct_count / total_questions) * 100 if total_questions else 0
    attempt.score = score

    test_link = (TestLink.query
                 .filter_by(candidate_id=attempt.candidate_id,
                            test_id=attempt.test_id, is_used=False)
                 .order_by(TestLink.created_at.desc()).first())
    if test_link:
        test_link.is_used = True
        db.session.add(test_link)

    attempt.passed = float(score) >= float(test.passing_score)
    db.session.commit()

    # Fixed: original pointed at a non-existent 'test_resultcopy' endpoint.
    return jsonify({
        "success": True,
        "redirect": url_for("aptitude.test_results", attempt_id=attempt_id),
    })


@aptitude_bp.route("/test_results/<int:attempt_id>")
def test_results(attempt_id):
    attempt = db.get_or_404(TestAttempt, attempt_id)
    test = attempt.test
    candidate = attempt.candidate
    answers = (Answer.query
               .join(Question, Answer.question_id == Question.id)
               .filter(Answer.attempt_id == attempt_id)
               .filter(Question.test_id == test.id)
               .order_by(Question.id).all())
    return render_template(
        "aptitude/test_results.html",
        attempt=attempt, test=test, candidate=candidate, answers=answers,
    )


# ---- HR: view results -----------------------------------------------------
@aptitude_bp.route("/results/<int:test_id>")
def view_results(test_id):
    test = db.get_or_404(AptitudeTest, test_id)
    attempts = (TestAttempt.query.filter_by(test_id=test_id)
                .order_by(TestAttempt.end_time.desc()).all())
    return render_template("aptitude/view_results.html", test=test, attempts=attempts)
