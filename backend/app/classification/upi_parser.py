"""UPI narration parser: extracts payee, VPA, reference and remark."""
from __future__ import annotations

import re
from dataclasses import dataclass

_BANK_CODES = {
    "SBIN",
    "HDFC",
    "ICIC",
    "UTIB",
    "KKBK",
    "PUNB",
    "BARB",
    "CNRB",
    "UBIN",
    "IDIB",
    "YESB",
    "INDB",
    "PAYTM",
    "OKAXIS",
    "OKHDFCBANK",
    "OKICICI",
    "OKSBI",
    "YBL",
    "AXL",
    "IBL",
}
_SKIP_SEGMENTS = {"UPI", "DR", "CR", "NA", "N/A", "NULL", "-", "0", "1", "2"}
_NUMERIC_RE = re.compile(r"^[A-Z]?\d{4,}$")


@dataclass(slots=True)
class UPIDetails:
    is_upi: bool
    payee: str | None = None
    vpa: str | None = None
    reference: str | None = None
    remark: str | None = None
    segments: list[str] | None = None


def _clean_segment(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9@.\-_ ]+", " ", value).strip(" -_")
    return re.sub(r"\s+", " ", value)


def parse_upi(description: str) -> UPIDetails:
    if not description:
        return UPIDetails(is_upi=False)
    upper = description.upper()
    if "UPI" not in upper and not re.search(r"@[A-Z]{2,}", upper):
        return UPIDetails(is_upi=False)
    normalized = re.sub(r"^.*?\bUPI\b[\s:/\-]*", "", upper)
    segments = [_clean_segment(part) for part in re.split(r"[/|]", normalized)]
    segments = [part for part in segments if part and part not in _SKIP_SEGMENTS]
    vpa = next((part for part in segments if "@" in part), None)
    reference = next(
        (part for part in segments if _NUMERIC_RE.match(part.replace(" ", ""))),
        None,
    )
    payee = None
    if vpa:
        index = segments.index(vpa)
        for candidate in reversed(segments[:index]):
            compact = candidate.replace(" ", "")
            if (
                not _NUMERIC_RE.match(compact)
                and candidate.upper() not in _BANK_CODES
                and not re.fullmatch(r"\d+", compact)
                and len(compact) >= 2
            ):
                payee = candidate
                break
    if not payee:
        for candidate in segments:
            compact = candidate.replace(" ", "")
            if (
                candidate != vpa
                and not _NUMERIC_RE.match(compact)
                and candidate.upper() not in _BANK_CODES
                and not re.fullmatch(r"\d+", compact)
                and len(compact) >= 3
            ):
                payee = candidate
                break
    remark = None
    if segments:
        for candidate in reversed(segments):
            if candidate not in {payee, vpa, reference} and len(candidate) >= 3:
                remark = candidate
                break
    return UPIDetails(
        is_upi=True,
        payee=payee,
        vpa=vpa,
        reference=reference,
        remark=remark,
        segments=segments,
    )


_PERIOD_TOKENS = {
    "JAN",
    "JANUARY",
    "FEB",
    "FEBRUARY",
    "MAR",
    "MARCH",
    "APR",
    "APRIL",
    "MAY",
    "JUN",
    "JUNE",
    "JUL",
    "JULY",
    "AUG",
    "AUGUST",
    "SEP",
    "SEPT",
    "SEPTEMBER",
    "OCT",
    "OCTOBER",
    "NOV",
    "NOVEMBER",
    "DEC",
    "DECEMBER",
}


def merchant_key(description: str) -> str:
    """Stable merchant-ish key used by recurring-transaction detection."""
    details = parse_upi(description)
    if details.payee:
        return re.sub(r"\s+", " ", details.payee.upper()).strip()
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", (description or "").upper())
    tokens = [
        token
        for token in text.split()
        if token not in {"UPI", "NEFT", "RTGS", "IMPS", "ATM", "POS", "DR", "CR", "TO", "FROM", "BY"}
        and token not in _PERIOD_TOKENS
        and not token.isdigit()
        and len(token) > 2
    ]
    return " ".join(tokens[:3])
