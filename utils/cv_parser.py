"""
CV / Resume Parser
===================
Extracts plain text from PDF or DOCX resume files for LLM consumption.
"""

import re
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


def parse_cv(filepath: str) -> str:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"CV file not found at: {filepath}")
    extension = path.suffix.lower()
    logger.info(f"Parsing CV: {path.name} (format: {extension})")
    if extension == ".pdf":
        return _parse_pdf(path)
    elif extension == ".docx":
        return _parse_docx(path)
    else:
        raise ValueError(f"Unsupported CV format: '{extension}'")


def _parse_pdf(path):
    from PyPDF2 import PdfReader
    reader = PdfReader(str(path))
    pages_text = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            pages_text.append(text.strip())
    full_text = "\n\n".join(pages_text)
    logger.info(f"CV parsed: {len(full_text)} chars from {len(reader.pages)} pages")
    return _clean_text(full_text)


def _parse_docx(path):
    from docx import Document
    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    full_text = "\n".join(paragraphs)
    logger.info(f"CV parsed: {len(full_text)} chars from {len(paragraphs)} paragraphs")
    return _clean_text(full_text)


def _clean_text(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines)
