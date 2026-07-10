"""
CV / Resume Parser
===================
Extracts plain text from PDF or DOCX resume files for LLM consumption.
Auto-detects file format based on extension.

Usage:
    from utils.cv_parser import parse_cv
    text = parse_cv("./assets/updated_cv.pdf")
"""

import os
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)


def parse_cv(filepath: str) -> str:
    """Parse a CV/resume file and extract its text content.

    Supports PDF (.pdf) and Word (.docx) formats. Auto-detects
    the format based on file extension.

    Args:
        filepath: Path to the CV file (PDF or DOCX).

    Returns:
        Cleaned plain text content of the CV.

    Raises:
        FileNotFoundError: If the file does not exist at the given path.
        ValueError: If the file format is not supported (not PDF or DOCX).
        RuntimeError: If text extraction fails for any reason.
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(
            f"CV file not found at: {filepath}\n"
            f"Please place your CV at the expected location."
        )

    extension = path.suffix.lower()
    logger.info(f"Parsing CV: {path.name} (format: {extension})")

    if extension == ".pdf":
        return _parse_pdf(path)
    elif extension == ".docx":
        return _parse_docx(path)
    else:
        raise ValueError(
            f"Unsupported CV format: '{extension}'. "
            f"Please provide a .pdf or .docx file."
        )


def _parse_pdf(path: Path) -> str:
    """Extract text from a PDF file using PyPDF2.

    Args:
        path: Path object pointing to the PDF file.

    Returns:
        Concatenated text from all pages, cleaned of excess whitespace.

    Raises:
        RuntimeError: If PDF reading fails.
    """
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(str(path))
        pages_text = []

        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())
                logger.debug(f"  Page {i + 1}: extracted {len(text)} characters")

        full_text = "\n\n".join(pages_text)
        logger.info(f"CV parsed successfully: {len(full_text)} characters from {len(reader.pages)} pages")
        return _clean_text(full_text)

    except ImportError:
        raise RuntimeError(
            "PyPDF2 is not installed. Run: pip install PyPDF2"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to parse PDF: {e}")


def _parse_docx(path: Path) -> str:
    """Extract text from a DOCX file using python-docx.

    Args:
        path: Path object pointing to the DOCX file.

    Returns:
        Concatenated text from all paragraphs, cleaned of excess whitespace.

    Raises:
        RuntimeError: If DOCX reading fails.
    """
    try:
        from docx import Document

        doc = Document(str(path))
        paragraphs = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)

        full_text = "\n".join(paragraphs)
        logger.info(f"CV parsed successfully: {len(full_text)} characters from {len(paragraphs)} paragraphs")
        return _clean_text(full_text)

    except ImportError:
        raise RuntimeError(
            "python-docx is not installed. Run: pip install python-docx"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to parse DOCX: {e}")


def _clean_text(text: str) -> str:
    """Clean extracted text by normalizing whitespace.

    Args:
        text: Raw extracted text from CV file.

    Returns:
        Text with normalized whitespace — multiple spaces collapsed,
        multiple newlines reduced to double newlines.
    """
    import re

    # Collapse multiple spaces into single space
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse 3+ newlines into double newline
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines)
