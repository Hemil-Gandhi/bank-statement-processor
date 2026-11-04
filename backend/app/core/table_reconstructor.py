"""Table reconstruction from the unified word-box layer.

The algorithm is layout-independent:
1. locate a header row using bank-profile aliases (fuzzy),
2. derive column x-ranges (ruling lines when available, else header anchors),
3. group words into visual lines,
4. start a row when the date column parses, otherwise merge the line into the
   previous narration (multi-line descriptions and page-boundary continuations),
5. skip repeated headers, footers and summary rows.

A borderless fallback infers numeric columns from right-aligned token clusters.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz

from app.core.bank_profiles.base import BankProfile
from app.core.layout import Line, group_lines
from app.core.normalizer import (
    clean_description,
    extract_reference,
    parse_amount,
    parse_date,
)
from app.core.types import PageWords, RawTransaction, ReconstructionResult, Word

logger = logging.getLogger(__name__)

DATE_OCR_MAP = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8"})
_MONEY_TOKEN_RE = re.compile(r"^[\s₹Rs.INR()\-+]*[\dOoIlSsBZ][\dOoIlSsBZ,.\-]*\s*(?:Cr|Dr|CR|DR)?\.?$")
# A date *token* must carry an explicit separator or month name. Bare numbers
# such as "12" in "12 Somewhere Street" must never be interpreted as dates.
_DATE_LIKE_TOKEN_RE = re.compile(
    r"(?i)^(?:\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}|"
    r"\d{1,2}[\s\-](?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,\-]?\d{2,4}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]\d{1,2},?[\s\-]\d{2,4})$"
)
_METADATA_RE = re.compile(
    r"(?i)^\s*(?:statement\s+period|statement\s+from|period|account\s+(?:no|number|name)|"
    r"a/?c\s+(?:no|number)|ifsc|micr|customer\s+(?:id|no)|cif|branch|address|"
    r"opening\s+balance|closing\s+balance|balance\s+[bc]/?f|brought\s+forward|"
    r"carried\s+forward|statement\s+summary|summary|generated\s+on|"
    r"this\s+is\s+a\s+(?:computer|system)|page\s+\d+|nomination|registered\s+office)"
)
_SUMMARY_RE = re.compile(r"(?i)^\s*(?:opening\s+balance|closing\s+balance|balance\s+[bc]/?f|"
                          r"brought\s+forward|carried\s+forward|grand\s+total|total\b|"
                          r"debit\s+total|credit\s+total|statement\s+summary|summary\b)")
_FOOTER_RE = re.compile(r"(?i)^\s*(?:page\s+\d+\s*(?:of\s+\d+)?$|page\s+\d+\s*/\s*\d+$|"
                        r"generated\s+on|this\s+is\s+a\s+(?:computer|system)\s+generated|"
                        r"this\s+is\s+an?\s+electronically\s+generated|registered\s+office|"
                        r"customer\s+care|please\s+examine|subject\s+to|for\s+any\s+queries|"
                        r"end\s+of\s+statement|continued|\(?contd)")

COLUMN_ORDER = (
    "serial",
    "date",
    "value_date",
    "description",
    "ref",
    "debit",
    "credit",
    "amount",
    "drcr",
    "balance",
)


@dataclass(slots=True)
class HeaderInfo:
    page: int
    y0: float
    y1: float
    columns: dict[str, tuple[float, float]]
    order: list[str]
    matched_count: int


@dataclass(slots=True)
class ColumnRange:
    name: str
    start: float
    end: float


def _norm_token(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _line_tokens(line: Line) -> tuple[list[str], list[int]]:
    tokens: list[str] = []
    owners: list[int] = []
    for index, word in enumerate(line.words):
        for token in _norm_token(word.text):
            tokens.append(token)
            owners.append(index)
    return tokens, owners


def _match_header_line(line: Line, profile: BankProfile) -> dict[str, set[int]]:
    tokens, owners = _line_tokens(line)
    if len(tokens) < 3:
        return {}
    entries = profile.alias_entries()
    matched: dict[str, set[int]] = defaultdict(set)
    used: set[int] = set()
    position = 0
    while position < len(tokens):
        found = False
        for phrase, canonical, token_count in entries:
            phrase_tokens = phrase.split()
            if token_count > len(tokens) - position:
                continue
            window = tokens[position : position + token_count]
            if window == phrase_tokens or all(
                fuzz.ratio(left, right) >= 90
                for left, right in zip(window, phrase_tokens)
            ):
                for owner in owners[position : position + token_count]:
                    matched[canonical].add(owner)
                    used.add(owner)
                position += token_count
                found = True
                break
        if not found:
            position += 1
    return dict(matched)


def _header_columns(
    line: Line, matched: dict[str, set[int]]
) -> dict[str, tuple[float, float]]:
    columns: dict[str, tuple[float, float]] = {}
    for canonical, indices in matched.items():
        words = [line.words[index] for index in sorted(indices)]
        if not words:
            continue
        columns[canonical] = (
            min(word.x0 for word in words),
            max(word.x1 for word in words),
        )
    return columns


def detect_header(
    pages: list[PageWords], profile: BankProfile
) -> tuple[HeaderInfo | None, list[HeaderInfo]]:
    headers: list[HeaderInfo] = []
    for page in pages:
        lines = group_lines(page.words, tolerance_factor=0.6 if page.source == "ocr" else 0.55)
        best: HeaderInfo | None = None
        for line in lines:
            if line.y0 > page.height * 0.8:
                continue
            matched = _match_header_line(line, profile)
            if len(matched) < 3:
                continue
            has_date = "date" in matched
            has_description = "description" in matched
            has_money = any(key in matched for key in ("debit", "credit", "amount", "balance"))
            if not (has_date and has_description and has_money):
                continue
            info = HeaderInfo(
                page=page.page,
                y0=line.y0,
                y1=line.y1,
                columns=_header_columns(line, matched),
                order=[key for key in COLUMN_ORDER if key in matched],
                matched_count=len(matched),
            )
            if best is None or info.matched_count > best.matched_count:
                best = info
        if best:
            headers.append(best)
    return (headers[0] if headers else None), headers


def _build_ranges(header: HeaderInfo, page_width: float, vertical_lines: list[float]) -> list[ColumnRange]:
    # Prefer ruling lines when they clearly segment the table.
    usable_lines = [line for line in vertical_lines if 15 < line < page_width - 5]
    if len(usable_lines) >= 3:
        ranges: list[ColumnRange] = []
        for canonical, (x0, x1) in header.columns.items():
            center = (x0 + x1) / 2
            segment = None
            for index in range(len(usable_lines) - 1):
                if usable_lines[index] - 2 <= center <= usable_lines[index + 1] + 2:
                    segment = (usable_lines[index], usable_lines[index + 1])
                    break
            if segment:
                ranges.append(ColumnRange(canonical, segment[0], segment[1]))
        if len(ranges) >= 3:
            ranges.sort(key=lambda item: item.start)
            return ranges

    ordered = sorted(header.columns.items(), key=lambda item: item[1][0])
    ranges = []
    for index, (canonical, (x0, x1)) in enumerate(ordered):
        start = max(0.0, x0 - 3)
        end = ordered[index + 1][1][0] - 3 if index + 1 < len(ordered) else page_width
        if end <= start:
            end = start + 20
        ranges.append(ColumnRange(canonical, start, end))
    return ranges


def _column_for(word: Word, ranges: list[ColumnRange]) -> str | None:
    center = word.cx
    for column in ranges:
        if column.start <= center < column.end:
            return column.name
    # Right-aligned amount that starts slightly before its header anchor.
    for column in ranges:
        if column.name in {"debit", "credit", "balance", "amount"} and column.start - 14 <= word.x1 <= column.end + 4:
            return column.name
    if ranges:
        nearest = min(ranges, key=lambda column: min(abs(center - column.start), abs(center - column.end)))
        if min(abs(center - nearest.start), abs(center - nearest.end)) <= 18:
            return nearest.name
    return None


def _parse_date_tokens(words: list[Word], reference: date | None) -> date | None:
    if not words:
        return None
    texts = [word.text for word in sorted(words, key=lambda w: w.x0)]
    # A row may contain both a transaction date and a value date in the same
    # detected column (OCR often duplicates them). Try the whole cell first,
    # then each token individually and accept the first valid date.
    candidates = [" ".join(texts), "".join(texts), *texts]
    candidates += [text.translate(DATE_OCR_MAP) for text in list(candidates)]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        parsed = parse_date(candidate, reference=reference)
        if parsed:
            return parsed
    return None


def _amount_from_words(words: list[Word]) -> tuple:
    if not words:
        return None, None
    texts = [word.text.strip() for word in sorted(words, key=lambda w: w.x0) if word.text.strip()]
    if not texts:
        return None, None
    candidates = [" ".join(texts), "".join(texts)]
    if len(texts) >= 2 and re.fullmatch(r"\d{1,2}", texts[-1]) and texts[-2][-1:] in {".", ","}:
        candidates.insert(0, "".join(texts[:-1]) + "." + texts[-1])
    for candidate in candidates:
        amount, marker = parse_amount(candidate)
        if amount is not None:
            return amount, marker
    for text in reversed(texts):
        amount, marker = parse_amount(text)
        if amount is not None:
            return amount, marker
    return None, None


def _text_of(words: list[Word]) -> str:
    return clean_description(" ".join(word.text for word in sorted(words, key=lambda w: w.x0)))


def _is_numeric_line(text: str) -> bool:
    compact = text.replace(" ", "")
    return bool(compact) and bool(re.fullmatch(r"[\d,.\-+()CrDr/]+", compact))


def _is_metadata(text: str) -> bool:
    return bool(_METADATA_RE.search(text))


def _is_footer(text: str, profile: BankProfile) -> bool:
    return bool(_FOOTER_RE.search(text))


def _is_summary(text: str, profile: BankProfile) -> bool:
    return bool(_SUMMARY_RE.search(text))


def _header_like(line: Line, profile: BankProfile) -> bool:
    matched = _match_header_line(line, profile)
    return len(matched) >= 3 and "date" in matched and "description" in matched


def _assign_line(
    line: Line,
    ranges: list[ColumnRange],
    row: RawTransaction,
    *,
    append: bool,
) -> None:
    buckets: dict[str, list[Word]] = defaultdict(list)
    unknown: list[Word] = []
    for word in line.words:
        column = _column_for(word, ranges)
        if column:
            buckets[column].append(word)
        else:
            unknown.append(word)

    description = _text_of(buckets.get("description", []))
    if not description and unknown:
        description = _text_of([w for w in unknown if not _MONEY_TOKEN_RE.match(w.text)])
    reference = _text_of(buckets.get("ref", [])) or None
    debit, debit_marker = _amount_from_words(buckets.get("debit", []))
    credit, credit_marker = _amount_from_words(buckets.get("credit", []))
    balance, _ = _amount_from_words(buckets.get("balance", []))
    amount, amount_marker = _amount_from_words(buckets.get("amount", []))
    drcr_text = _text_of(buckets.get("drcr", []))
    marker = amount_marker or debit_marker or credit_marker
    if not marker and drcr_text:
        if re.search(r"(?i)\bdr\b", drcr_text):
            marker = "debit"
        elif re.search(r"(?i)\bcr\b", drcr_text):
            marker = "credit"

    if append:
        if description:
            row.description = clean_description(f"{row.description} {description}")
        if reference and not row.reference_no:
            row.reference_no = reference
        if debit is not None and row.debit_text is None:
            row.debit_text = str(debit)
        if credit is not None and row.credit_text is None:
            row.credit_text = str(credit)
        if balance is not None and row.balance_text is None:
            row.balance_text = str(balance)
        if amount is not None and row.amount_text is None:
            row.amount_text = str(amount)
        if marker and not row.drcr:
            row.drcr = marker
        row.raw_text = clean_description(f"{row.raw_text} {line.text}")
        return

    row.description = description
    row.reference_no = reference
    row.debit_text = str(debit) if debit is not None else None
    row.credit_text = str(credit) if credit is not None else None
    row.balance_text = str(balance) if balance is not None else None
    row.amount_text = str(amount) if amount is not None else None
    row.drcr = marker
    row.raw_text = line.text

    # Single Amount + Dr/Cr marker layout.
    if row.amount_text is not None and row.debit_text is None and row.credit_text is None:
        if marker == "debit":
            row.debit_text = row.amount_text
            row.amount_text = None
        elif marker == "credit":
            row.credit_text = row.amount_text
            row.amount_text = None
    # Some banks put the Dr/Cr marker in the narration.
    if row.amount_text is not None and not marker:
        if re.search(r"(?i)(?:\bdr\b|\bdebit\b)\s*$", row.description):
            row.debit_text = row.amount_text
            row.amount_text = None
        elif re.search(r"(?i)(?:\bcr\b|\bcredit\b)\s*$", row.description):
            row.credit_text = row.amount_text
            row.amount_text = None


def _date_words(
    line: Line, ranges: list[ColumnRange], page: PageWords
) -> tuple[list[Word], list[Word]]:
    date_words: list[Word] = []
    value_words: list[Word] = []
    for word in line.words:
        column = _column_for(word, ranges)
        if column == "date":
            date_words.append(word)
        elif column == "value_date":
            value_words.append(word)
    if not date_words:
        # Headerless pages: the date is almost always one of the first few tokens.
        for word in line.words[:4]:
            if _DATE_LIKE_TOKEN_RE.match(word.text) and parse_date(word.text, reference=None):
                date_words.append(word)
                break
    return date_words, value_words


def _finalize(row: RawTransaction) -> RawTransaction:
    row.description = clean_description(row.description)
    if not row.reference_no:
        row.reference_no = extract_reference(row.description)
    if not row.raw_text:
        row.raw_text = row.description
    return row


def _extract_rows_with_header(
    pages: list[PageWords],
    profile: BankProfile,
    reference: date | None,
) -> tuple[list[RawTransaction], bool, list[str]]:
    _, headers = detect_header(pages, profile)
    header_by_page = {header.page: header for header in headers}
    warnings: list[str] = []
    rows: list[RawTransaction] = []
    current: RawTransaction | None = None
    ranges: list[ColumnRange] | None = None
    last_header_page = 0

    for page in pages:
        header = header_by_page.get(page.page)
        if header:
            ranges = _build_ranges(header, page.width, page.vertical_lines)
            last_header_page = page.page
        elif ranges is None:
            continue
        assert ranges is not None
        start_y = (header.y1 + 2) if header else 0.0
        lines = group_lines(page.words, tolerance_factor=0.62 if page.source == "ocr" else 0.55)
        for line in lines:
            if line.y0 < start_y:
                continue
            text = clean_description(line.text)
            if not text:
                continue
            if _is_footer(text, profile):
                continue
            if _is_metadata(text) and _is_summary(text, profile):
                continue
            if header and _header_like(line, profile):
                # Repeated header inside the page; refresh boundaries.
                continue
            if not header and _header_like(line, profile):
                continue
            if _is_summary(text, profile):
                continue

            date_words, value_words = _date_words(line, ranges, page)
            parsed_date = _parse_date_tokens(date_words, reference)
            if parsed_date is None and not date_words:
                # Try the first few tokens regardless of column. Require an
                # explicit date shape so address/number-only lines are ignored.
                for word in line.words[:3]:
                    if not _DATE_LIKE_TOKEN_RE.match(word.text):
                        continue
                    parsed = parse_date(word.text.translate(DATE_OCR_MAP), reference=reference)
                    if parsed:
                        parsed_date = parsed
                        date_words = [word]
                        break
            if parsed_date:
                if current:
                    rows.append(_finalize(current))
                current = RawTransaction(
                    page=page.page,
                    date_text=date_words[0].text if date_words else line.words[0].text,
                    y=line.y0,
                )
                _assign_line(line, ranges, current, append=False)
                value_date = _parse_date_tokens(value_words, reference)
                if value_date:
                    current.flags.append(f"value_date:{value_date.isoformat()}")
                if page.source == "ocr" and any(word.conf < 60 for word in line.words):
                    current.flags.append("low_ocr_confidence")
            elif current is not None:
                if _is_numeric_line(text) and current.debit_text is None and current.credit_text is None:
                    _assign_line(line, ranges, current, append=True)
                else:
                    _assign_line(line, ranges, current, append=True)
    if current:
        rows.append(_finalize(current))
    return rows, bool(headers), warnings


def _numeric_tokens(line: Line) -> list[Word]:
    result = []
    for word in line.words:
        if _MONEY_TOKEN_RE.match(word.text) and any(ch.isdigit() for ch in word.text):
            result.append(word)
    return result


def _extract_rows_fallback(
    pages: list[PageWords], profile: BankProfile, reference: date | None
) -> tuple[list[RawTransaction], list[str]]:
    warnings = ["header_row_not_found: using borderless numeric-column fallback."]
    rows: list[RawTransaction] = []
    current: RawTransaction | None = None
    for page in pages:
        lines = group_lines(page.words, tolerance_factor=0.62 if page.source == "ocr" else 0.55)
        for line in lines:
            text = clean_description(line.text)
            if not text or _is_footer(text, profile) or _is_summary(text, profile):
                continue
            if _is_metadata(text):
                continue
            parsed_date = None
            date_word: Word | None = None
            for word in line.words[:4]:
                if not _DATE_LIKE_TOKEN_RE.match(word.text):
                    continue
                parsed = parse_date(word.text.translate(DATE_OCR_MAP), reference=reference)
                if parsed:
                    parsed_date = parsed
                    date_word = word
                    break
            if parsed_date and date_word:
                if current:
                    rows.append(_finalize(current))
                current = RawTransaction(
                    page=page.page,
                    date_text=date_word.text,
                    y=line.y0,
                )
                numeric = [word for word in _numeric_tokens(line) if word is not date_word]
                description_words = [
                    word
                    for word in line.words
                    if word is not date_word
                    and word not in numeric
                    and not _DATE_LIKE_TOKEN_RE.match(word.text)
                ]
                current.description = _text_of(description_words)
                current.raw_text = line.text
                if numeric:
                    balance = numeric[-1]
                    amount = numeric[-2] if len(numeric) >= 2 else None
                    current.balance_text = balance.text
                    if amount is not None:
                        current.amount_text = amount.text
                        amount_value, marker = parse_amount(amount.text)
                        if marker == "debit":
                            current.debit_text = str(abs(amount_value)) if amount_value is not None else None
                            current.amount_text = None
                        elif marker == "credit":
                            current.credit_text = str(abs(amount_value)) if amount_value is not None else None
                            current.amount_text = None
                        elif re.search(r"(?i)\bdr\b|\bdebit\b", current.description):
                            current.debit_text = str(abs(amount_value)) if amount_value is not None else None
                            current.amount_text = None
                        elif re.search(r"(?i)\bcr\b|\bcredit\b", current.description):
                            current.credit_text = str(abs(amount_value)) if amount_value is not None else None
                            current.amount_text = None
                    elif re.search(r"(?i)\bdr\b|\bdebit\b", current.description):
                        current.debit_text = current.balance_text
                        current.balance_text = None
            elif current is not None:
                continuation = _text_of([word for word in line.words if word not in _numeric_tokens(line)])
                if continuation:
                    current.description = clean_description(f"{current.description} {continuation}")
                    current.raw_text = clean_description(f"{current.raw_text} {line.text}")
    if current:
        rows.append(_finalize(current))
    return rows, warnings


def reconstruct_transactions(
    pages: list[PageWords],
    profile: BankProfile,
    *,
    reference_date: date | None = None,
) -> ReconstructionResult:
    rows, header_found, warnings = _extract_rows_with_header(pages, profile, reference_date)
    if not rows:
        fallback_rows, fallback_warnings = _extract_rows_fallback(pages, profile, reference_date)
        if fallback_rows:
            rows = fallback_rows
            warnings.extend(fallback_warnings)
            header_found = False
    if not rows:
        warnings.append("no_rows_reconstructed")
    # Drop rows with no date parse (should not happen) and keep deterministic order.
    rows = [row for row in rows if parse_date(row.date_text, reference=reference_date)]
    for index, row in enumerate(rows):
        row.flags.append(f"row:{index}")
    logger.info("table reconstructed rows=%s header=%s", len(rows), header_found)
    return ReconstructionResult(
        transactions=rows,
        warnings=warnings,
        header_found=header_found,
    )
