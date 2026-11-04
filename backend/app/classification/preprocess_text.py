"""Description cleaning and feature construction for the classical ML model."""
from __future__ import annotations

import re
import unicodedata

from app.core.normalizer import amount_bucket, detect_channel
from decimal import Decimal

_REF_TOKEN_RE = re.compile(r"\b(?:[A-Z]{2,}\d{6,}|[A-Z0-9]{10,})\b", re.IGNORECASE)
_DATE_TOKEN_RE = re.compile(r"\b\d{1,4}[/.\-]\d{1,2}[/.\-]\d{2,4}\b")
_DIGITS_RE = re.compile(r"\b\d+\b")
_NOISE_TOKENS = {
    "UPI",
    "NEFT",
    "RTGS",
    "IMPS",
    "ATM",
    "POS",
    "DR",
    "CR",
    "NA",
    "N A",
    "REF",
    "TXN",
    "TRANSACTION",
    "PAYMENT",
    "PAY",
    "TO",
    "FROM",
    "BY",
    "VIA",
    "BANK",
    "LTD",
    "PVT",
    "INDIA",
    "INR",
}


def preprocess_description(description: str) -> str:
    """Uppercase, remove refs/dates/digit-only tokens but preserve merchant words."""
    text = unicodedata.normalize("NFKC", description or "").upper()
    text = _DATE_TOKEN_RE.sub(" ", text)
    text = _REF_TOKEN_RE.sub(" ", text)
    text = re.sub(r"[^A-Z0-9@/&\- ]+", " ", text)
    tokens = []
    for token in text.split():
        token = token.strip("/-&")
        if not token:
            continue
        if token.isdigit():
            continue
        if len(token) > 28:
            continue
        tokens.append(token)
    return " ".join(tokens)


def normalize_for_override(description: str) -> str:
    """Stable key for the user-override memory (channel/ref agnostic)."""
    text = unicodedata.normalize("NFKC", description or "").upper()
    text = _DATE_TOKEN_RE.sub(" ", text)
    text = re.sub(r"@[A-Z0-9.\-]+", " ", text)  # VPA handles
    text = re.sub(r"\b(?:UPI|NEFT|RTGS|IMPS|ATM|POS|ECS|NACH|CHQ|CHEQUE)\b", " ", text)
    text = re.sub(r"\b[A-Z0-9]{8,}\b", " ", text)  # references / UTRs
    text = re.sub(r"\b\d+\b", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    tokens = [token for token in text.split() if token not in _NOISE_TOKENS]
    normalized = " ".join(tokens).strip()
    return normalized[:500]


def build_feature_text(
    description: str,
    direction: str,
    amount: Decimal | None,
    channel: str | None = None,
) -> str:
    cleaned = preprocess_description(description)
    channel = channel or detect_channel(description)
    return (
        f"DESC {cleaned} CHANNEL_{channel} DIR_{direction.upper()} "
        f"AMT_{amount_bucket(amount).upper()}"
    )
