"""
Optimizing blueprint (AI resume analyzer).

Migrated from the deprecated `google-generativeai` SDK to the current unified
`google-genai` SDK. The model is configurable via the GEMINI_MODEL env var
(default: gemini-2.5-flash).

Given one resume + a job description, Gemini returns a JSON object with a match
percentage, missing keywords, and a profile summary. We then build Coursera
course links for each missing keyword.
"""
import json
import os
import re

from flask import (
    Blueprint, current_app, redirect, render_template,
    request, send_from_directory, url_for,
)
from werkzeug.utils import secure_filename

from utils.text_extract import extract_text

optimizing_bp = Blueprint("optimizingbp", __name__)

INPUT_PROMPT = """\
You are a highly experienced ATS (Applicant Tracking System) with deep
knowledge of software engineering, data science, data analytics, and big data.
Evaluate the resume against the job description. The market is competitive, so
give the most useful improvement feedback. Assign a percentage match and list
missing keywords accurately.

resume: {text}
job_description: {jd}

Respond ONLY with a single JSON object, no markdown, with this exact structure:
{{
  "JD Match": "<number>%",
  "MissingKeywords": ["..."],
  "Profile Summary": "..."
}}
"""


def _upload_dir():
    path = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(path, exist_ok=True)
    return path


def _get_gemini_response(prompt: str) -> str:
    """Call Gemini with the new google-genai SDK and return raw text."""
    from google import genai
    from google.genai import types

    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=api_key)
    model = current_app.config.get("GEMINI_MODEL", "gemini-2.5-flash")
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return response.text or ""


def _get_course_suggestions(skills):
    suggestions = {}
    for skill in skills or []:
        suggestions[skill] = {
            "title": f"Explore {skill} courses",
            "platform": "Coursera",
            "url": f"https://www.coursera.org/search?query={skill}",
        }
    return suggestions


@optimizing_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(_upload_dir(), filename)


@optimizing_bp.route("/")
def optimizing_home():
    return render_template("optimizing.html")


@optimizing_bp.route("/analyzer", methods=["GET", "POST"])
def analyzer():
    if request.method != "POST":
        return render_template("optimizing.html")

    job_description = (request.form.get("job_description") or "").strip()
    resume_files = request.files.getlist("resume")
    resume_files = [f for f in resume_files if f and f.filename]

    if not resume_files or not job_description:
        return render_template(
            "optimizing.html",
            message="Please paste a job description and upload a resume.",
        )

    resume_file = resume_files[0]
    dest = os.path.join(_upload_dir(), secure_filename(resume_file.filename))
    resume_file.save(dest)
    resume_text = extract_text(dest)

    prompt = INPUT_PROMPT.format(text=resume_text, jd=job_description)

    try:
        raw = _get_gemini_response(prompt)
    except Exception as exc:
        print(f"[optimizing] Gemini call failed: {exc}")
        return render_template(
            "optimizing.html",
            message="The AI service could not be reached. Check the GEMINI_API_KEY "
                    "configuration and try again.",
        )

    if not raw.strip():
        return render_template(
            "optimizing.html",
            message="Received an empty response from the AI service. Please try again.",
        )

    # The SDK is asked for JSON, but we defensively pull out the {...} block.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return render_template(
            "optimizing.html",
            message="Invalid response format from the AI service. Please try again.",
        )

    try:
        result = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        print(f"[optimizing] JSON decode error: {exc}")
        return render_template(
            "optimizing.html",
            message="Invalid response format from the AI service. Please try again.",
        )

    match_percentage = result.get("JD Match", "N/A")
    missing_keywords = result.get("MissingKeywords", [])
    profile_summary = result.get("Profile Summary", "No summary available.")
    course_suggestions = _get_course_suggestions(missing_keywords)

    return render_template(
        "optimizing.html",
        message="We analysed the resume and found that...",
        match_percentage=match_percentage,
        missing_keywords=missing_keywords,
        profile_summary=profile_summary,
        course_suggestions=course_suggestions,
    )
