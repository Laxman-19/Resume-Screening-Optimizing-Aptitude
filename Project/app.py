"""
Application entry point (app factory pattern).

Run locally:        python app.py
Run in production:  gunicorn "app:create_app()"
"""
import os

from flask import Flask, render_template, request

from config import Config
from extensions import db


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Make sure the uploads folder exists at startup.
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)

    # Import models so SQLAlchemy registers them, then create tables.
    with app.app_context():
        import models  # noqa: F401
        db.create_all()

    # Blueprints
    from blueprints.screening import screening_bp
    from blueprints.optimizing import optimizing_bp
    from blueprints.aptitude import aptitude_bp

    app.register_blueprint(screening_bp, url_prefix="/screening")
    app.register_blueprint(optimizing_bp, url_prefix="/optimizing")
    app.register_blueprint(aptitude_bp, url_prefix="/aptitude")

    # Static pages
    @app.route("/")
    def home():
        return render_template("home.html")

    @app.route("/features")
    def features():
        return render_template("feature.html")

    @app.route("/contact", methods=["GET", "POST"])
    def contact():
        name = message = None
        if request.method == "POST":
            name = request.form.get("name")
            # email / feedback captured but not persisted in this demo
            message = "Thanks for reaching out."
        return render_template("contact.html", message=message, name=name)

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}, 200

    return app


# Gunicorn / `python app.py` both work with this module-level app.
app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
