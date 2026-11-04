"""Account-holder detail extraction using label proximity + regex."""
from __future__ import annotations

import logging
import re

from rapidfuzz import fuzz

from app.core.layout import Line, group_lines
from app.core.normalizer import (
    clean_description,
    extract_dates,
    parse_amount,
    parse_date,
)
from app.core.types import AccountDetails, BankDetection, PageWords

logger = logging.getLogger(__name__)

IFSC_RE = re.compile(r"\b([A-Z0-9]{4})\s*[0O]\s*([A-Z0-9]{6})\b")
ACCOUNT_RE = re.compile(r"(?i)(?:[x*]{2,}\s*\d{2,6}|\d{9,18})")
MICR_RE = re.compile(r"\b\d{9}\b")
CUSTOMER_RE = re.compile(r"\b([A-Z0-9]{6,20})\b")

ACCOUNT_LABELS = (
    "account number",
    "account no",
    "a/c number",
    "a/c no",
    "acct no",
    "account #",
    "account",
)
NAME_LABELS = (
    "account holder name",
    "account name",
    "customer name",
    "a/c holder name",
    "account holder",
    "name",
)
BRANCH_LABELS = ("branch name", "home branch", "branch", "br name")
MICR_LABELS = ("micr code", "micr")
CUSTOMER_LABELS = ("customer id", "customer no", "cif no", "cif", "cust id", "client id")
ADDRESS_LABELS = (
    "communication address",
    "registered address",
    "mailing address",
    "address",
)
PERIOD_LABELS = (
    "statement period",
    "statement from",
    "period from",
    "period",
    "statement date",
)
OPENING_LABELS = (
    "opening balance",
    "balance b/f",
    "balance bf",
    "opening bal",
    "b/f",
    "brought forward",
)
CLOSING_LABELS = (
    "closing balance",
    "balance c/f",
    "balance cf",
    "closing bal",
    "c/f",
    "carried forward",
)

_BANK_NOISE = (
    "BANK",
    "STATEMENT",
    "ACCOUNT",
    "BRANCH",
    "IFSC",
    "ADDRESS",
    "PERIOD",
    "CUSTOMER",
    "DATE",
    "PAGE",
)
# "CUSTOMER" is valid inside a person's/company's name ("SAMPLE CUSTOMER"),
# so label values use a stricter list than the free-text fallback.
_NAME_VALUE_NOISE = (
    "BANK",
    "STATEMENT",
    "ACCOUNT",
    "BRANCH",
    "IFSC",
    "ADDRESS",
    "PERIOD",
    "DATE",
    "PAGE",
)


def _normalize_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _line_tokens(line: Line) -> tuple[list[str], list[int]]:
    tokens: list[str] = []
    owners: list[int] = []
    for index, word in enumerate(line.words):
        for token in _normalize_tokens(word.text):
            tokens.append(token)
            owners.append(index)
    return tokens, owners


def _find_label(line: Line, labels: tuple[str, ...]) -> tuple[int, int] | None:
    tokens, owners = _line_tokens(line)
    if not tokens:
        return None
    for label in sorted(labels, key=lambda item: -len(item.split())):
        label_tokens = _normalize_tokens(label)
        if not label_tokens:
            continue
        for start in range(0, len(tokens) - len(label_tokens) + 1):
            window = tokens[start : start + len(label_tokens)]
            exact = window == label_tokens
            fuzzy = all(
                fuzz.ratio(left, right) >= 88 for left, right in zip(window, label_tokens)
            )
            if exact or fuzzy:
                owner_start = owners[start]
                owner_end = owners[start + len(label_tokens) - 1] + 1
                return owner_start, owner_end
    return None


def _clean_value(value: str) -> str:
    value = clean_description(value)
    value = re.sub(r"^[\s:;/#.\-]+", "", value)
    return value.strip()[:200]


def _value_right(line: Line, end_index: int) -> str:
    if end_index >= len(line.words):
        return ""
    anchor = line.words[end_index - 1]
    words = []
    last_x1 = anchor.x1
    for word in line.words[end_index:]:
        if word.x0 < anchor.x1 - 4:
            continue
        # Stop at a large horizontal gap: the same visual line often contains
        # an unrelated label/value pair on the right (e.g. Opening Balance).
        if words and word.x0 - last_x1 > 45:
            break
        words.append(word)
        last_x1 = word.x1
    return _clean_value(" ".join(word.text for word in words))


def _value_below(lines: list[Line], line_index: int, max_lines: int = 2) -> str:
    base = lines[line_index]
    collected: list[str] = []
    for offset in range(1, max_lines + 1):
        index = line_index + offset
        if index >= len(lines):
            break
        candidate = lines[index]
        if candidate.y0 - base.y1 > 28 * offset:
            break
        text = _clean_value(candidate.text)
        if not text:
            continue
        if _find_label(candidate, ACCOUNT_LABELS + NAME_LABELS + ADDRESS_LABELS + PERIOD_LABELS):
            break
        collected.append(text)
        if len(collected) >= 1 and not any(
            ch.isdigit() for ch in text
        ):
            break
    return " ".join(collected)[:300]


def _label_value(
    lines: list[Line], labels: tuple[str, ...], *, below: bool = True
) -> str | None:
    for index, line in enumerate(lines):
        match = _find_label(line, labels)
        if not match:
            continue
        value = _value_right(line, match[1])
        if value:
            return value
        if below:
            value = _value_below(lines, index)
            if value:
                return value
    return None


def _mask_account(account_number: str | None) -> str | None:
    if not account_number:
        return None
    compact = re.sub(r"\s+", "", account_number).upper()
    if re.search(r"[X*]", compact):
        digits = re.sub(r"\D", "", compact)
        if not digits:
            return compact
        return "X" * max(0, len(compact) - 4) + compact[-4:]
    digits = re.sub(r"\D", "", compact)
    if len(digits) < 4:
        return None
    return "X" * max(0, len(digits) - 4) + digits[-4:]


def _extract_account_number(lines: list[Line], full_text: str) -> str | None:
    value = _label_value(lines, ACCOUNT_LABELS)
    if value:
        match = ACCOUNT_RE.search(re.sub(r"\s+", "", value))
        if match:
            return re.sub(r"\s+", "", match.group(0)).upper()
    # Real statements frequently print the number in groups: "1234 5678 9012".
    joined_digits = re.sub(r"(?<=\d)\s+(?=\d)", "", full_text)
    match = re.search(
        r"(?i)(?:a/?c|account)\s*(?:number|no|#)?\.?\s*[:/\-]?\s*"
        r"([x*]{2,}\s*\d{2,6}|\d{9,18})",
        joined_digits,
    )
    if match:
        return re.sub(r"\s+", "", match.group(1)).upper()
    return None


def _extract_ifsc(lines: list[Line], full_text: str) -> str | None:
    value = _label_value(lines, ("ifsc code", "ifsc", "ifs code"))
    if value:
        match = IFSC_RE.search(value.upper())
        if match:
            return f"{match.group(1)}0{match.group(2)}"
    match = IFSC_RE.search(full_text.upper())
    if match:
        return f"{match.group(1)}0{match.group(2)}"
    return None


_SUMMARY_LABEL_RE = re.compile(
    r"(?i)\b(?:opening\s+balance|closing\s+balance|deposits?|withdrawals?)\b"
)
_ADDRESS_HINT_RE = re.compile(
    r"(?i)\b(?:street|st|avenue|ave|road|rd|lane|ln|drive|dr|boulevard|blvd|"
    r"apartment|apt|suite|floor|nagar|colony|sector|city)\b"
)


def _name_from_left_column(lines: list[Line]) -> str | None:
    """Read a holder name printed left of a right-column balance summary."""
    for index, line in enumerate(lines[:14]):
        text = _clean_value(line.text)
        if not text:
            continue
        match = _SUMMARY_LABEL_RE.search(text)
        if not match:
            continue
        left = text[: match.start()].strip(" .,:-")
        words = left.split()
        if not (2 <= len(words) <= 5) or len(left) > 60:
            continue
        if any(ch.isdigit() for ch in left):
            continue
        if any(noise in left.upper() for noise in _NAME_VALUE_NOISE):
            continue
        letters = sum(1 for ch in left if ch.isalpha())
        if letters / max(1, len(left)) < 0.7:
            continue
        # Only trust this when the account block is nearby and the next line
        # looks like a postal address, which is the usual statement layout.
        context = " ".join(
            _clean_value(lines[offset].text)
            for offset in range(max(0, index - 2), index)
        )
        if not re.search(r"(?i)\baccount\b|\ba/?c\b", context):
            continue
        for offset in range(1, 3):
            if index + offset >= len(lines):
                break
            following = _clean_value(lines[index + offset].text)
            if _ADDRESS_HINT_RE.search(following) and any(
                ch.isdigit() for ch in following
            ):
                return left
    return None


def _extract_name(lines: list[Line], bank: BankDetection) -> str | None:
    value = _label_value(lines, NAME_LABELS)
    if value:
        value = re.sub(r"(?i)^(mr|mrs|ms|dr|m/s)\.?\s+", "", value).strip(" .,:-")
        if 2 <= len(value) <= 90 and not any(
            noise in value.upper() for noise in _NAME_VALUE_NOISE
        ):
            return value
    # US-style statements put the holder name in a left column next to the
    # balance summary, so it arrives as "Ava Okafor Opening balance $2,418.36".
    fallback = _name_from_left_column(lines)
    if fallback:
        return fallback
    bank_keywords = {keyword.upper() for keyword in bank.bank_name.upper().split()}
    for line in lines[:18]:
        text = _clean_value(line.text)
        if not (3 <= len(text) <= 80):
            continue
        upper = text.upper()
        if any(noise in upper for noise in _BANK_NOISE):
            continue
        if any(keyword and keyword in upper for keyword in bank_keywords if len(keyword) > 3):
            continue
        if any(ch.isdigit() for ch in text):
            continue
        words = text.split()
        if not (2 <= len(words) <= 6):
            continue
        letters = sum(1 for ch in text if ch.isalpha())
        if letters / max(1, len(text)) < 0.7:
            continue
        return text.strip(" .,:-")
    return None


def _extract_address(lines: list[Line]) -> str | None:
    for index, line in enumerate(lines):
        match = _find_label(line, ADDRESS_LABELS)
        if not match:
            continue
        parts: list[str] = []
        right = _value_right(line, match[1])
        if right and len(right) > 3:
            parts.append(right)
        for offset in range(1, 4):
            if index + offset >= len(lines):
                break
            candidate = lines[index + offset]
            if candidate.y0 - line.y1 > 45:
                break
            text = _clean_value(candidate.text)
            if not text:
                continue
            if _find_label(candidate, NAME_LABELS + ACCOUNT_LABELS + BRANCH_LABELS):
                break
            if re.search(r"(?i)statement|period|ifsc|micr|customer", text):
                break
            parts.append(text)
        if parts:
            return ", ".join(dict.fromkeys(parts))[:300]
    return None


_MONTH_NAMES = (
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)"
)
_MONTH_RANGE_RE = re.compile(
    rf"(?i)\b({_MONTH_NAMES})\s+(\d{{1,2}})(?:,?\s*(\d{{4}}))?\s*[-–—]\s*"
    rf"({_MONTH_NAMES})\s+(\d{{1,2}}),?\s*(\d{{4}})\b"
)


def _extract_month_range(text: str) -> tuple:
    match = _MONTH_RANGE_RE.search(text)
    if not match:
        return None, None
    month1, day1, year1, month2, day2, year2 = match.groups()
    end_year = int(year2)
    start = parse_date(f"{month1} {day1} {year1 or end_year}")
    end = parse_date(f"{month2} {day2} {end_year}")
    if start and end:
        return min(start, end), max(start, end)
    return None, None


def _extract_period(lines: list[Line]) -> tuple:
    reference = None
    for line in lines[:15]:
        start, end = _extract_month_range(line.text)
        if start and end:
            return start, end
    for line in lines[:30]:
        text = line.text
        if not re.search(r"(?i)period|statement\s+from|from\s+\d|to\s+\d", text):
            continue
        dates = extract_dates(text, reference=reference)
        if len(dates) >= 2:
            return min(dates[0], dates[1]), max(dates[0], dates[1])
        if len(dates) == 1 and re.search(r"(?i)\bto\b", text):
            return dates[0], dates[0]
    # Fallback: a top-of-page "01/04/2024 - 30/06/2024" line.
    for line in lines[:15]:
        dates = extract_dates(line.text)
        if len(dates) >= 2:
            return min(dates[0], dates[1]), max(dates[0], dates[1])
    return None, None


def _extract_balance(lines: list[Line], labels: tuple[str, ...]) -> str | None:
    value = _label_value(lines, labels)
    if not value:
        return None
    match = re.search(r"[-+]?[\d,]+(?:\.\d{1,2})?", value)
    return match.group(0) if match else None


def _extract_micr(lines: list[Line], full_text: str) -> str | None:
    value = _label_value(lines, MICR_LABELS)
    if value:
        match = MICR_RE.search(value)
        if match:
            return match.group(0)
    match = re.search(r"(?i)MICR[^\d]{0,12}(\d{9})", full_text)
    return match.group(1) if match else None


def _extract_customer_id(lines: list[Line]) -> str | None:
    value = _label_value(lines, CUSTOMER_LABELS)
    if not value:
        return None
    match = CUSTOMER_RE.search(value.upper())
    return match.group(1) if match else None


def extract_account_details(
    pages: list[PageWords],
    bank: BankDetection,
    *,
    full_text: str | None = None,
) -> tuple[AccountDetails, list[str]]:
    warnings: list[str] = []
    first = next((page for page in pages if page.page == 1), pages[0] if pages else None)
    last = pages[-1] if pages else None
    if first is None:
        return AccountDetails(bank_name=bank.bank_name), ["account_details_unavailable"]

    first_lines = group_lines(first.words)
    last_lines = group_lines(last.words) if last else []
    text = full_text or "\n".join(
        " ".join(word.text for word in page.words) for page in pages
    )

    account_number = _extract_account_number(first_lines, text)
    ifsc = _extract_ifsc(first_lines, text)
    name = _extract_name(first_lines, bank)
    branch = _label_value(first_lines, BRANCH_LABELS)
    address = _extract_address(first_lines)
    period_from, period_to = _extract_period(first_lines)
    opening_text = _extract_balance(first_lines + last_lines, OPENING_LABELS)
    closing_text = _extract_balance(last_lines + first_lines, CLOSING_LABELS)
    opening, _ = parse_amount(opening_text)
    closing, _ = parse_amount(closing_text)

    currency = "INR"
    if re.search(r"(?i)\bUSD\b|\$", text[:4000]):
        currency = "USD"
    elif re.search(r"(?i)\bEUR\b|€", text[:4000]):
        currency = "EUR"

    details = AccountDetails(
        account_holder_name=name,
        account_number=account_number,
        account_number_masked=_mask_account(account_number),
        ifsc=ifsc,
        bank_name=bank.bank_name,
        branch=branch,
        micr=_extract_micr(first_lines, text),
        customer_id=_extract_customer_id(first_lines),
        address=address,
        statement_period_from=period_from,
        statement_period_to=period_to,
        opening_balance=opening,
        closing_balance=closing,
        currency=currency,
    )
    required_fields = [
        ("account_number", details.account_number),
        ("account_holder_name", details.account_holder_name),
        ("statement_period", details.statement_period_from),
    ]
    if currency == "INR":
        required_fields.append(("ifsc", details.ifsc))
    missing = [field for field, value in required_fields if not value]
    if missing:
        warnings.append("account_fields_missing: " + ", ".join(missing))
    if period_from and period_to and period_from > period_to:
        warnings.append("statement_period_inverted")
    return details, warnings
