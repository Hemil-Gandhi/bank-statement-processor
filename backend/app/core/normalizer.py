"""Date, amount, description and reference normalization.

All money parsing returns Decimal. Parsers are deliberately fail-soft: they return
None instead of raising on ambiguous input.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from dateutil import parser as dateutil_parser

MONEY_QUANT = Decimal("0.01")

DATE_FORMATS: tuple[str, ...] = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d.%m.%y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d %B %Y",
    "%d-%B-%Y",
    "%d %b, %Y",
    "%d %B, %Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%b %d %Y",
    "%B %d %Y",
    "%d %b",
    "%d-%b",
    "%d %B",
)

_ORDINAL_RE = re.compile(r"(\d+)(st|nd|rd|th)\b", re.IGNORECASE)
_DASH_RE = re.compile(r"[\u2010-\u2015\u2212]")
_CURRENCY_RE = re.compile(
    r"(?i)(?:₹|rs\.?|inr|rupees|usd|\$|eur|€)\s*"
)
_SPACE_RE = re.compile(r"\s+")
_OCR_NUMERIC_MAP = str.maketrans(
    {"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "S": "5", "s": "5", "B": "8", "Z": "2"}
)
_NUMERICISH_RE = re.compile(r"^[\dOoIlSsBZ|,.\-\s()]+$")
_MARKER_SUFFIX_RE = re.compile(r"(?i)\s*(?:\(?\s*(cr|dr)\.?\s*\)?)\s*$")


def _adjust_year(value: date, reference: date | None) -> date:
    if reference is None:
        return value
    # If a 2-digit year was mis-pivoted by a century, snap it near the statement period.
    if abs(value.year - reference.year) > 60:
        try:
            return value.replace(year=value.year + (100 if value.year < reference.year else -100))
        except ValueError:
            return value
    return value


def parse_date(
    value: str | None,
    *,
    reference: date | None = None,
    default_year: int | None = None,
) -> date | None:
    """Parse the date formats commonly used by Indian banks (day-first by default)."""
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = _DASH_RE.sub("-", text)
    text = _ORDINAL_RE.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" .,;:-/|")
    if not text:
        return None
    # A bare day/month number is not a date. This guards against address lines
    # such as "12 Somewhere Street" being parsed as the 12th of the current month.
    if re.fullmatch(r"\d{1,2}", text):
        return None
    # Drop time components such as 01/04/2024 10:31:00
    text = re.split(r"\s+\d{1,2}:\d{2}", text)[0].strip()
    # Remove a leading weekday ("Mon, 01 Apr 2024")
    text = re.sub(
        r"(?i)^(mon|tue|wed|thu|fri|sat|sun)[a-z]*,?\s+", "", text
    ).strip()
    if not text:
        return None

    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt).date()
            if "%Y" not in fmt and "%y" not in fmt and default_year:
                parsed = parsed.replace(year=default_year)
            return _adjust_year(parsed, reference)
        except ValueError:
            continue

    # Numeric fallback with a deliberate day-first bias.
    try:
        parsed = dateutil_parser.parse(text, dayfirst=True, fuzzy=False).date()
        return _adjust_year(parsed, reference)
    except (ValueError, OverflowError, TypeError):
        pass

    # Missing year, e.g. "01 Apr" — attach default year.
    if default_year:
        for fmt in ("%d %b", "%d-%b", "%d %B", "%d-%B"):
            try:
                parsed = datetime.strptime(text, fmt).replace(year=default_year).date()
                return _adjust_year(parsed, reference)
            except ValueError:
                continue
    return None


def extract_dates(text: str, *, reference: date | None = None) -> list[date]:
    """Find date-like substrings inside a longer line (used for statement periods)."""
    if not text:
        return []
    patterns = [
        r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b",
        r"\b\d{1,2}[\s\-](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,\-]\d{2,4}\b",
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]
    found: list[date] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            parsed = parse_date(match.group(0), reference=reference)
            if parsed and parsed not in found:
                found.append(parsed)
    return found


def _fix_ocr_numeric(token: str) -> str:
    if not _NUMERICISH_RE.match(token):
        return token
    if not any(ch.isdigit() for ch in token) and not re.search(r"[OoIlSsBZ|]", token):
        return token
    translated = token.translate(_OCR_NUMERIC_MAP)
    if any(ch.isdigit() for ch in translated):
        return translated
    return token


def _normalize_separators(token: str) -> str:
    """Resolve comma/dot confusion and Indian digit grouping."""
    token = token.replace(" ", "").replace("'", "")
    if not token:
        return token
    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            # European style: 1.234,56
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif "," in token:
        parts = token.split(",")
        if len(parts) == 2 and len(parts[1]) == 2 and len(parts[0]) <= 3:
            # OCR likely turned a decimal point into a comma: 12,50 -> 12.50
            token = f"{parts[0]}.{parts[1]}"
        else:
            token = token.replace(",", "")
    elif "." in token:
        parts = token.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            # "1.234" is almost always Indian thousands grouping.
            token = token.replace(".", "")
        elif len(parts) > 2:
            token = "".join(parts[:-1]) + "." + parts[-1]
    return token


def parse_amount(value: str | None) -> tuple[Decimal | None, str | None]:
    """Parse an amount and an optional Dr/Cr marker.

    Handles ₹/Rs./INR, Indian grouping (1,00,000.00), trailing minus,
    parentheses, Dr/Cr suffixes and conservative OCR digit fixes.
    """
    if value is None:
        return None, None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if not text:
        return None, None
    text = _CURRENCY_RE.sub("", text).strip()
    text = re.sub(r"(?i)/-\s*$", "", text).strip()
    if not text or text in {"-", "--", "NA", "N/A", "NIL"}:
        return None, None

    marker: str | None = None
    match = _MARKER_SUFFIX_RE.search(text)
    if match:
        marker = "credit" if match.group(1).lower() == "cr" else "debit"
        text = text[: match.start()].strip()

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    if text.startswith("-") or text.endswith("-"):
        negative = True
        text = text.strip("-").strip()
    if text.startswith("+"):
        text = text[1:].strip()

    text = _fix_ocr_numeric(text)
    text = _normalize_separators(text)
    text = re.sub(r"[^0-9.\-]", "", text)
    if not re.search(r"\d", text):
        return None, marker
    if text.count("-") > 1 or "-" in text[1:]:
        text = text.replace("-", "")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None, marker
    if negative:
        amount = -amount
    amount = amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    return amount, marker


def format_amount(value: Decimal | None) -> str:
    return "" if value is None else f"{value:,.2f}"


def clean_description(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace("\u00a0", " ").replace("\u200b", "")
    text = _DASH_RE.sub("-", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([/|])\s*", r"\1", text)
    text = re.sub(r"\s*-\s*", " - ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,:;|-")
    return text[:1000]


def extract_reference(description: str) -> str | None:
    """Pull a UTR / RRN / cheque / reference number out of a narration."""
    if not description:
        return None
    patterns = (
        r"(?i)\b(?:UTR|RRN|REF(?:ERENCE)?|CHQ|CHEQUE|TXN|TRN)[\s:/\-]*([A-Z0-9]{6,22})\b",
        r"(?i)\b(?:NEFT|RTGS|IMPS)[/\-]([A-Z0-9]{6,22})\b",
        r"\b(\d{12})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            candidate = match.group(1)
            if not re.fullmatch(r"(?:19|20)\d{6}", candidate):
                return candidate
    return None


def detect_channel(description: str) -> str:
    text = (description or "").upper()
    checks = (
        ("UPI", r"\bUPI\b|@(?:OK|YBL|AXL|PAYTM|IBL|SBI|HDFC|ICICI)"),
        ("ATM", r"\bATM\b|\bNFS\b|CASH\s*WDL|CASH\s*WITHDRAWAL"),
        ("POS", r"\bPOS\b|\bECOM\b|CARD\s*PAYMENT"),
        ("NEFT", r"\bNEFT\b"),
        ("RTGS", r"\bRTGS\b"),
        ("IMPS", r"\bIMPS\b"),
        ("CHEQUE", r"\bCHQ\b|\bCHEQUE\b|\bCLG\b"),
        ("CASH", r"\bCASH\b"),
        ("INTEREST", r"\bINT\.?\s*(?:PD|CR|CREDIT)\b|INTEREST"),
        ("CHARGES", r"\bCHARGES?\b|\bFEE\b|\bGST\b|\bSMS\s*ALERT\b"),
        ("ECS/NACH", r"\bECS\b|\bNACH\b|\bACH\b"),
    )
    for channel, pattern in checks:
        if re.search(pattern, text):
            return channel
    return "OTHER"


def amount_bucket(amount: Decimal | None) -> str:
    if amount is None:
        return "none"
    value = abs(amount)
    if value < Decimal("100"):
        return "micro"
    if value < Decimal("1000"):
        return "small"
    if value < Decimal("10000"):
        return "medium"
    if value < Decimal("100000"):
        return "large"
    return "xl"


def statement_reference_date(
    period_from: date | None, period_to: date | None
) -> date | None:
    return period_to or period_from
