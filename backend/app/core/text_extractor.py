"""Text-PDF word-box extraction with pdfplumber, plus ruling-line hints."""
from __future__ import annotations

import logging
from pathlib import Path

import pdfplumber

from app.core.types import PageWords, Word

logger = logging.getLogger(__name__)


def _dedupe_positions(values: list[float], tolerance: float = 2.0) -> list[float]:
    result: list[float] = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > tolerance:
            result.append(round(value, 2))
    return result


def extract_page_words(
    path: str | Path,
    page_types: list[str],
    password: str | None = None,
) -> list[PageWords]:
    """Extract word boxes for pages detected as TEXT. IMAGE pages are skipped here."""
    pages: list[PageWords] = []
    try:
        with pdfplumber.open(str(path), password=password or "") as pdf:
            for index, page in enumerate(pdf.pages):
                page_number = index + 1
                if index >= len(page_types) or page_types[index] != "TEXT":
                    continue
                raw_words = page.extract_words(
                    x_tolerance=1.5,
                    y_tolerance=2,
                    keep_blank_chars=False,
                    use_text_flow=False,
                ) or []
                words: list[Word] = []
                for raw in raw_words:
                    text = (raw.get("text") or "").strip()
                    if not text:
                        continue
                    words.append(
                        Word(
                            text=text,
                            x0=float(raw["x0"]),
                            y0=float(raw["top"]),
                            x1=float(raw["x1"]),
                            y1=float(raw["bottom"]),
                            page=page_number,
                            conf=100.0,
                        )
                    )
                vertical: list[float] = []
                horizontal: list[float] = []
                for collection in (getattr(page, "lines", []) or [], getattr(page, "rects", []) or []):
                    for obj in collection:
                        try:
                            x0, x1 = float(obj["x0"]), float(obj["x1"])
                            top, bottom = float(obj["top"]), float(obj["bottom"])
                        except (KeyError, TypeError, ValueError):
                            continue
                        if abs(x1 - x0) <= 1.5 and abs(bottom - top) > 12:
                            vertical.append((x0 + x1) / 2)
                        elif abs(bottom - top) <= 1.5 and abs(x1 - x0) > 12:
                            horizontal.append((top + bottom) / 2)
                pages.append(
                    PageWords(
                        page=page_number,
                        width=float(page.width),
                        height=float(page.height),
                        words=words,
                        source="text",
                        vertical_lines=_dedupe_positions(vertical),
                        horizontal_lines=_dedupe_positions(horizontal),
                    )
                )
    except Exception as exc:
        logger.warning("pdfplumber extraction failed: %s", exc)
        raise
    return pages
