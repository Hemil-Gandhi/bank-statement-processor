"""Tesseract OCR over rendered PDF pages, producing the unified word-box layer."""
from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
import pytesseract
from pytesseract import Output

from app.config import settings
from app.core.errors import OcrFailedError
from app.core.preprocess import preprocess_image
from app.core.types import PageWords, Word

logger = logging.getLogger(__name__)

if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd


def ocr_available() -> bool:
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def tesseract_version() -> str | None:
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return None


def _render_page(page: fitz.Page, dpi: int) -> np.ndarray:
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False, colorspace=fitz.csRGB)
    array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return array[:, :, ::-1].copy()  # RGB -> BGR


def extract_page_words(page: fitz.Page, page_number: int, dpi: int | None = None) -> PageWords:
    if not settings.tesseract_cmd:
        raise OcrFailedError(
            "Tesseract OCR is not installed. Install tesseract-ocr (see README) or use Docker."
        )
    dpi = dpi or settings.ocr_dpi
    try:
        rendered = _render_page(page, dpi)
        processed = preprocess_image(rendered)
        data = pytesseract.image_to_data(
            processed.image,
            lang=settings.ocr_language,
            config=f"--oem 3 --psm {settings.ocr_psm} -c preserve_interword_spaces=1",
            output_type=Output.DICT,
        )
    except OcrFailedError:
        raise
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrFailedError("Tesseract OCR is not installed or not on PATH.") from exc
    except Exception as exc:
        raise OcrFailedError(f"OCR failed on page {page_number}: {exc}") from exc

    x_scale = page.rect.width / max(1, processed.image.shape[1])
    y_scale = page.rect.height / max(1, processed.image.shape[0])
    words: list[Word] = []
    confidences: list[float] = []
    count = len(data.get("text", []))
    for i in range(count):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf < settings.ocr_min_confidence:
            continue
        x, y, w, h = (int(data[k][i]) for k in ("left", "top", "width", "height"))
        words.append(
            Word(
                text=text,
                x0=x * x_scale,
                y0=y * y_scale,
                x1=(x + w) * x_scale,
                y1=(y + h) * y_scale,
                page=page_number,
                conf=conf,
            )
        )
        confidences.append(conf)
    average = sum(confidences) / len(confidences) if confidences else 0.0
    logger.info(
        "ocr page=%s words=%s avg_conf=%.1f deskew=%.2f",
        page_number,
        len(words),
        average,
        processed.deskew_angle,
    )
    return PageWords(
        page=page_number,
        width=float(page.rect.width),
        height=float(page.rect.height),
        words=words,
        source="ocr",
        ocr_confidence=average,
    )


def extract_ocr_pages(
    path: str | Path,
    page_types: list[str],
    password: str | None = None,
) -> list[PageWords]:
    pages: list[PageWords] = []
    doc = fitz.open(path)
    try:
        if doc.needs_pass:
            doc.authenticate(password or "")
        for index, page in enumerate(doc):
            if index >= len(page_types) or page_types[index] != "IMAGE":
                continue
            pages.append(extract_page_words(page, index + 1))
    finally:
        doc.close()
    return pages
