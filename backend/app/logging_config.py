"""Structured, privacy-aware logging."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

from app.config import settings

_ACCOUNT_RE = re.compile(r"\b\d{9,18}\b")
_MASKED_RE = re.compile(r"\b[Xx*]{2,}\d{2,6}\b")


def mask_account(value: str | None) -> str | None:
    """Mask any long digit sequence so account numbers never reach logs."""
    if value is None:
        return None
    value = str(value)
    if _MASKED_RE.search(value):
        return _MASKED_RE.sub(lambda m: "X" * max(0, len(m.group(0)) - 4) + m.group(0)[-4:], value)

    def _replace(match: re.Match[str]) -> str:
        digits = match.group(0)
        return "X" * max(0, len(digits) - 4) + digits[-4:]

    return _ACCOUNT_RE.sub(_replace, value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": mask_account(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = mask_account(self.formatException(record.exc_info))
        for key in ("job_id", "pdf_type", "bank", "page", "duration_ms", "code"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_level.upper() == "JSON":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
        )
    root.addHandler(handler)
    logging.getLogger("pdfminer").setLevel(logging.WARNING)
    logging.getLogger("pdfplumber").setLevel(logging.WARNING)
