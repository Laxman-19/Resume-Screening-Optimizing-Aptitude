"""
Database models.

The relational design is unchanged from the original project; only the
`db` import was moved to extensions.py to avoid circular imports.
"""
from datetime import datetime

from extensions import db


class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    resume_path = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    test_links = db.relationship("TestLink", backref="candidate", lazy=True)
    test_attempts = db.relationship("TestAttempt", backref="candidate", lazy=True)


class AptitudeTest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    time_limit = db.Column(db.Integer, nullable=False)   # minutes
    passing_score = db.Column(db.Integer, nullable=False)  # percentage
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    questions = db.relationship("Question", backref="test", lazy=True)
    test_links = db.relationship("TestLink", backref="test", lazy=True)
    test_attempts = db.relationship("TestAttempt", backref="test", lazy=True)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey("aptitude_test.id"), nullable=False)
    question_type = db.Column(db.String(50), default="multiple_choice")
    options = db.relationship("Option", backref="question", lazy=True)
    answers = db.relationship("Answer", backref="question", lazy=True)


class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    option_text = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)


class TestLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey("aptitude_test.id"), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)


class TestAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey("aptitude_test.id"), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidate.id"), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    score = db.Column(db.Float)
    passed = db.Column(db.Boolean, default=False)
    answers = db.relationship("Answer", backref="attempt", lazy=True)


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("test_attempt.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    selected_option_id = db.Column(db.Integer, db.ForeignKey("option.id"), nullable=False)
    is_correct = db.Column(db.Boolean)
