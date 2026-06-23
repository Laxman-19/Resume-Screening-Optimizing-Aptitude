"""
Lightweight resume field extractor.

This replaces `pyresparser` (which pinned spaCy 2.x + an old language model and
no longer installs on modern Python). It returns the SAME dictionary keys the
screening template expects:

    {
        "name": str | None,
        "email": str | None,
        "mobile_number": str | None,
        "skills": list[str],
        "total_experience": float | None,
    }

It uses regular expressions and a curated skills keyword list. It needs no
machine-learning model, so installation and deployment are painless.
"""
import os
import re

# A pragmatic, extensible skill vocabulary. Add to this list as needed.
SKILL_KEYWORDS = [
    # languages
    "python", "java", "javascript", "typescript", "c++", "c#", "c programming",
    "go", "golang", "rust", "ruby", "php", "scala", "kotlin", "swift", "r",
    "matlab", "sql", "pl/sql", "bash", "shell scripting",
    # web / frameworks
    "html", "css", "react", "angular", "vue", "node", "node.js", "express",
    "django", "flask", "fastapi", "spring", "spring boot", "laravel",
    "bootstrap", "tailwind", "jquery", "rest api", "graphql",
    # data / ml
    "machine learning", "deep learning", "nlp", "natural language processing",
    "computer vision", "data analysis", "data science", "pandas", "numpy",
    "scikit-learn", "tensorflow", "pytorch", "keras", "opencv", "tableau",
    "power bi", "excel", "statistics", "data visualization",
    # databases
    "mysql", "postgresql", "postgres", "mongodb", "sqlite", "redis",
    "oracle", "cassandra", "firebase", "elasticsearch",
    # cloud / devops
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "jenkins",
    "terraform", "ansible", "ci/cd", "git", "github", "gitlab", "linux",
    # general
    "agile", "scrum", "jira", "rest", "microservices", "api", "selenium",
    "junit", "pytest", "communication", "leadership", "project management",
    "problem solving", "teamwork",
]

# Common top-level domains, including two-part ones (co.in, co.uk, ac.in...).
# Matching against a known TLD list is what stops PDF text like
# "name@gmail.comOBJECTIVE" being captured as "name@gmail.comOBJECTIVE":
# the match ends cleanly at the real TLD ("com") and the glued-on word is left
# behind. A generic pattern is kept as a fallback for unusual domains.
_TLD = (
    r"(?:com|org|net|edu|gov|mil|io|co|in|ai|me|info|dev|us|uk|au|de|fr|jp|sg|"
    r"biz|app|tech|live|email|xyz|online|site|store|cloud|ac|edu|gmail)"
)
EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.(?:com|org|net|edu|gov|mil|io|co|in|ai|"
    r"me|info|dev|us|uk|au|de|fr|jp|sg|biz|app|tech|live|email|xyz|online|site|"
    r"store|cloud|ac)(?:\.(?:in|uk|us|au|ca|co|org|net|edu|gov))?",
    re.IGNORECASE,
)
EMAIL_RE_GENERIC = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Generic local parts that are NOT a person's name (used when deriving a name
# from an email address).
GENERIC_LOCALS = {
    "info", "hr", "contact", "admin", "jobs", "careers", "career", "support",
    "sales", "hello", "team", "mail", "email", "resume", "cv", "noreply",
    "no-reply", "office", "enquiry", "enquiries", "help", "service", "services",
}

# Matches Indian and international phone formats (optional country code, spaces,
# dashes, dots, parentheses). The digit-count check below filters false hits.
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,5}\)?[\s\-.]?){2,5}\d{2,4}(?!\d)")

# "5 years", "3+ yrs", "2.5 years of experience"
EXPERIENCE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", re.IGNORECASE
)


def _clean_email(raw: str):
    if not raw:
        return None
    e = raw.strip().strip(".").strip(",").lower()
    # local@domain sanity check
    if e.count("@") != 1:
        return None
    local, _, domain = e.partition("@")
    if not local or "." not in domain:
        return None
    return e


def _extract_email(text: str):
    # Prefer the known-TLD pattern (robust to glued-on words), then fall back.
    for m in EMAIL_RE.finditer(text):
        cleaned = _clean_email(m.group(0))
        if cleaned:
            return cleaned
    for m in EMAIL_RE_GENERIC.finditer(text):
        cleaned = _clean_email(m.group(0))
        if cleaned:
            return cleaned
    return None


def _extract_phone(text: str):
    best = None
    for candidate in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", candidate)
        # Plausible phone numbers have 10-13 digits (with optional country code).
        if 10 <= len(digits) <= 13:
            cand = candidate.strip()
            # Prefer the first well-formed hit.
            return cand
    return best


def _name_from_email(email: str):
    """Derive a likely full name from an email local part (firstname.lastname)."""
    if not email:
        return None
    local = email.split("@")[0]
    local = re.sub(r"\d+", "", local)               # drop digits
    parts = [p for p in re.split(r"[._\-]+", local) if p.isalpha() and len(p) >= 2]
    if not (2 <= len(parts) <= 3):
        return None
    if parts[0].lower() in GENERIC_LOCALS:
        return None
    return " ".join(p.capitalize() for p in parts)


def _extract_skills(text: str):
    lowered = text.lower()
    found = []
    for skill in SKILL_KEYWORDS:
        # word-boundary match so "r" doesn't match every word, etc.
        pattern = r"(?<![a-zA-Z0-9+#.])" + re.escape(skill) + r"(?![a-zA-Z0-9+#])"
        if re.search(pattern, lowered):
            found.append(skill.title() if skill.islower() else skill)
    # de-duplicate while preserving order
    seen, unique = set(), []
    for s in found:
        if s.lower() not in seen:
            seen.add(s.lower())
            unique.append(s)
    return unique


def _extract_experience(text: str):
    years = [float(m) for m in EXPERIENCE_RE.findall(text)]
    return max(years) if years else None


# Words that frequently appear as section headings or labels at the top of a
# resume. A candidate "name" line containing any of these is rejected, which
# stops headers like "Education Skills" or "Career Objective" being mistaken
# for a person's name.
NAME_STOPWORDS = {
    "resume", "curriculum", "vitae", "cv", "biodata", "profile", "summary",
    "objective", "career", "education", "experience", "skills", "skill",
    "projects", "project", "work", "employment", "history", "contact",
    "details", "detail", "personal", "information", "info", "address",
    "phone", "mobile", "email", "e-mail", "tel", "telephone", "linkedin",
    "github", "portfolio", "achievements", "achievement", "certifications",
    "certification", "certificate", "languages", "language", "interests",
    "interest", "hobbies", "hobby", "references", "reference", "declaration",
    "about", "me", "technical", "professional", "academic", "qualification",
    "qualifications", "strengths", "expertise", "internship", "training",
    "extracurricular", "activities", "awards", "publications", "courses",
    # common job-title words (a title line often sits between name and contact)
    "developer", "engineer", "scientist", "analyst", "manager", "designer",
    "consultant", "intern", "architect", "administrator", "specialist",
    "lead", "officer", "executive", "associate", "data", "web", "software",
    "senior", "junior", "full", "stack", "frontend", "backend", "fullstack",
    "programmer", "tester", "freelancer", "student", "graduate",
}


def _looks_like_name(line: str) -> bool:
    """True if a line plausibly is a person's name (not a header/contact line)."""
    if not line or len(line) > 40:
        return False
    if EMAIL_RE.search(line) or PHONE_RE.search(line):
        return False
    if re.search(r"\d", line):            # names don't contain digits
        return False
    if any(ch in line for ch in "@/\\|:•·,()[]{}<>"):
        return False
    words = line.split()
    if not (2 <= len(words) <= 4):        # "John Doe" .. "Mary Anne Van Dyke"
        return False
    for w in words:
        core = re.sub(r"[^A-Za-z]", "", w)
        if not core:                       # token had no letters
            return False
        if core.lower() in NAME_STOPWORDS:
            return False
        if not w[0].isupper():             # each word starts with a capital
            return False
    return True


def _name_from_filename(file_path: str):
    if not file_path:
        return None
    base = os.path.splitext(os.path.basename(file_path))[0]
    base = re.sub(r"[_\-]+", " ", base)
    base = re.sub(r"(?i)\b(resume|cv|curriculum|vitae|new|final|updated|copy)\b", "", base)
    base = re.sub(r"\d+", "", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base.title() if base else None


def _clean_candidate_line(line: str) -> str:
    """Names often share a line with a title/credential after a separator;
    keep only the part before the first separator (| , / etc.)."""
    return re.split(r"[|•·/\\,;:\t]", line)[0].strip()


def _extract_name(text: str, file_path: str = ""):
    """
    Heuristic name detection, in order of confidence:
      1. A name-like line just above the first email/phone (the contact block
         almost always follows the name).
      2. The first name-like line in the top portion of the document.
      3. A name derived from the email local part (firstname.lastname).
      4. A cleaned-up version of the filename.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # 1) Lines immediately above the first contact detail.
    contact_idx = None
    for i, line in enumerate(lines[:25]):
        if EMAIL_RE.search(line) or EMAIL_RE_GENERIC.search(line) or _extract_phone(line):
            contact_idx = i
            break
    if contact_idx is not None:
        for j in range(contact_idx - 1, max(contact_idx - 4, -1), -1):
            cand = _clean_candidate_line(lines[j])
            if _looks_like_name(cand):
                return cand.title()

    # 2) First name-like line near the top.
    for line in lines[:12]:
        cand = _clean_candidate_line(line)
        if _looks_like_name(cand):
            return cand.title()

    # 3) Derive from the email address (e.g. laxman.sawant@... -> Laxman Sawant).
    from_email = _name_from_email(_extract_email(text))
    if from_email:
        return from_email

    # 4) Fallback to the filename ("Laxman_Resume_New.pdf" -> "Laxman").
    return _name_from_filename(file_path)


def parse_resume(text: str, file_path: str = "") -> dict:
    """Extract structured fields from already-extracted resume text."""
    text = text or ""
    return {
        "name": _extract_name(text, file_path),
        "email": _extract_email(text),
        "mobile_number": _extract_phone(text),
        "skills": _extract_skills(text),
        "total_experience": _extract_experience(text),
    }
