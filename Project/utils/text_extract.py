"""Resume text extraction for PDF, DOCX and TXT files."""
import docx2txt
from pypdf import PdfReader


def extract_text_from_pdf(file_path: str) -> str:
    text = []
    reader = PdfReader(file_path)
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text.append(page_text)
    return "\n".join(text)


def extract_text_from_docx(file_path: str) -> str:
    return docx2txt.process(file_path) or ""


def extract_text_from_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def extract_text(file_path: str) -> str:
    """Dispatch on file extension. Returns '' for unsupported types."""
    lower = file_path.lower()
    try:
        if lower.endswith(".pdf"):
            return extract_text_from_pdf(file_path)
        if lower.endswith(".docx"):
            return extract_text_from_docx(file_path)
        if lower.endswith(".txt"):
            return extract_text_from_txt(file_path)
    except Exception as exc:  # corrupt file, unreadable page, etc.
        print(f"[text_extract] failed to read {file_path}: {exc}")
        return ""
    return ""
