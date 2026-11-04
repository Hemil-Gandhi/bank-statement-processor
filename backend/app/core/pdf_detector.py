"""Per-page PDF type detection: TEXT, IMAGE (scanned) or MIXED.

The detector also catches the common "garbage OCR text layer" case where a scanned
page carries a poor invisible text layer. Such pages are routed through OCR again.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import fitz  # PyMuPDF

from app.config import settings
from app.core.errors import InvalidFileError, NeedsPasswordError, TooManyPagesError
from app.core.types import DetectionResult

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"\S+")


def _text_quality(text: str, word_count: int) -> tuple[bool, str]:
    stripped = text.strip()
    if len(stripped) < 50 or word_count < 8:
        return False, "too_little_text"
    printable = sum(1 for ch in stripped if ch.isprintable()) / max(1, len(stripped))
    letters = sum(1 for ch in stripped if ch.isalpha()) / max(1, len(stripped))
    digits = sum(1 for ch in stripped if ch.isdigit()) / max(1, len(stripped))
    tokens = _WORD_RE.findall(stripped)
    avg_len = sum(len(t) for t in tokens) / max(1, len(tokens))
    if printable < 0.88:
        return False, "unprintable"
    if letters < 0.30 and (letters + digits) < 0.55:
        return False, "symbol_noise"
    if avg_len > 28:
        return False, "token_noise"
    # Real statements contain many short dictionary-like tokens.
    short_tokens = sum(1 for t in tokens if 2 <= len(t) <= 20)
    if short_tokens / max(1, len(tokens)) < 0.55:
        return False, "token_noise"
    return True, "ok"


def _image_coverage(page: fitz.Page) -> float:
    page_area = abs(page.rect.width * page.rect.height)
    if page_area <= 0:
        return 0.0
    covered = 0.0
    try:
        for img in page.get_images(full=True):
            xref = img[0]
            for rect in page.get_image_rects(xref):
                clipped = fitz.Rect(rect) & page.rect
                covered += abs(clipped.width * clipped.height)
    except Exception:  # pragma: no cover - defensive
        return 0.0
    return min(1.0, covered / page_area)


def detect_pdf(path: str | Path, password: str | None = None) -> DetectionResult:
    path = Path(path)
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise InvalidFileError(f"Could not open the PDF: {exc}") from exc

    encrypted = False
    try:
        if doc.needs_pass:
            encrypted = True
            candidates = [password] if password else ["", None]
            authenticated = False
            for candidate in candidates:
                if candidate is not None and doc.authenticate(candidate):
                    authenticated = True
                    break
            if not authenticated:
                raise NeedsPasswordError()
        if doc.page_count == 0:
            raise InvalidFileError("The PDF contains no pages.")
        if doc.page_count > settings.max_pages:
            raise TooManyPagesError(
                f"The PDF has {doc.page_count} pages; the limit is {settings.max_pages}."
            )

        per_page: list[str] = []
        warnings: list[str] = []
        for index, page in enumerate(doc):
            text = page.get_text("text") or ""
            words = page.get_text("words") or []
            usable, reason = _text_quality(text, len(words))
            coverage = _image_coverage(page)
            if usable:
                per_page.append("TEXT")
            else:
                per_page.append("IMAGE")
                if text.strip() and reason != "too_little_text":
                    warnings.append(
                        f"page_{index + 1}_garbage_text_layer: OCR text layer was poor; using image OCR."
                    )
                elif coverage < 0.05 and not text.strip():
                    warnings.append(
                        f"page_{index + 1}_no_text_or_image: page may be blank or vector-only."
                    )
    finally:
        doc.close()

    if not per_page:
        raise InvalidFileError("The PDF contains no readable pages.")
    if all(t == "TEXT" for t in per_page):
        pdf_type = "TEXT"
    elif all(t == "IMAGE" for t in per_page):
        pdf_type = "IMAGE"
    else:
        pdf_type = "MIXED"
    logger.info("pdf detected type=%s pages=%s", pdf_type, len(per_page))
    return DetectionResult(
        pdf_type=pdf_type,
        per_page_types=per_page,
        num_pages=len(per_page),
        warnings=warnings,
        encrypted=encrypted,
    )
