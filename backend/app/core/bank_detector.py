"""Bank detection using IFSC, header names, header-column signatures and a
generic bank-name fallback for banks without a dedicated profile."""
from __future__ import annotations

import logging
import re
from collections import Counter

from app.core.bank_profiles import IFSC_TO_PROFILE, PROFILES, all_profiles, get_profile
from app.core.bank_profiles.base import BANK_NAME_ALIASES, IFSC_BANK_NAMES
from app.core.layout import group_lines
from app.core.types import BankDetection, PageWords

logger = logging.getLogger(__name__)

# OCR often inserts spaces between the four-letter prefix, the zero and the
# six-character branch code. It also reads the separator as the letter O.
IFSC_RE = re.compile(r"\b([A-Z0-9]{4})\s*[0O]\s*([A-Z0-9]{6})\b")

# Common OCR digit/letter confusions inside the four-letter bank prefix.
_PREFIX_FIX = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B"})

_PROFILE_BY_NAME = {profile.name: profile.id for profile in all_profiles()}


def _compact(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _page_text(pages: list[PageWords], limit: int = 3) -> str:
    return "\n".join(
        " ".join(word.text for word in page.words) for page in pages[:limit]
    )


def _header_text(pages: list[PageWords], max_pages: int = 2, max_lines: int = 12) -> str:
    """Top-of-page lines only, so counterparty names in narrations cannot win."""
    chunks: list[str] = []
    for page in pages[:max_pages]:
        for line in group_lines(page.words)[:max_lines]:
            text = line.text.strip()
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _canonical_ifsc(prefix: str, suffix: str) -> str:
    return f"{prefix.upper().translate(_PREFIX_FIX)}0{suffix.upper()}"


def _ifsc_from_header(pages: list[PageWords]) -> list[str]:
    """Prefer the account-block IFSC over IFSC-like strings in narrations.

    Transaction descriptions often contain counterparty IFSCs (e.g.
    NEFT/HDFC0000123/...). Those must not decide the bank.
    """
    if not pages:
        return []
    labelled: list[str] = []
    header: list[str] = []
    for page in pages[:3]:
        for line in group_lines(page.words):
            text = line.text.upper()
            matches = [_canonical_ifsc(prefix, suffix) for prefix, suffix in IFSC_RE.findall(text)]
            if not matches:
                continue
            if re.search(r"(?i)\bIFSC\b|\bIFS\s*CODE\b", text):
                labelled.extend(matches)
                continue
            if re.match(r"^\s*\d{1,2}[/.\-]\d{1,2}", text):
                continue
            if re.search(r"(?i)\bNEFT\b|\bRTGS\b|\bIMPS\b|\bUPI\b|\bREF\b|\bCHQ\b|\bCHEQUE\b", text):
                continue
            header.extend(matches)
    return labelled or header


def _match_bank_alias(text: str) -> tuple[int, str] | None:
    """Return (score, canonical bank name) for the longest alias in the text."""
    compact = _compact(text)
    if not compact:
        return None
    best: tuple[int, str] | None = None
    for bank_name, aliases in BANK_NAME_ALIASES.items():
        for alias in aliases:
            key = _compact(alias)
            if len(key) >= 3 and key in compact:
                if best is None or len(key) > best[0]:
                    best = (len(key), bank_name)
    return best


_BANK_PHRASE_STOPWORDS = {
    "A",
    "AN",
    "AND",
    "AT",
    "BY",
    "FOR",
    "FROM",
    "IS",
    "MY",
    "OF",
    "OUR",
    "STATEMENT",
    "THE",
    "THIS",
    "TO",
    "WELCOME",
    "WITH",
    "YOUR",
}

_BANK_SUFFIXES = {"LTD", "LIMITED", "PLC", "NA"}


def _bank_phrase(text: str) -> str | None:
    """Extract a bank-name phrase such as "Riverbend Test Bank" or "ABC Bank Ltd".

    Statement headers often append the document title on the same line
    ("Riverbend Test Bank Everyday Checking statement"). Taking only the words
    immediately before "Bank" avoids returning the whole line.
    """
    words = re.sub(r"\s+", " ", text).strip().split()
    for index, raw in enumerate(words):
        token = raw.strip(".,;:()[]")
        if token.upper() != "BANK":
            continue
        # Ignore lowercase prose such as "a fictional bank for test data".
        if not (token[0].isupper() or token.isupper()):
            continue
        prefix: list[str] = []
        cursor = index - 1
        while cursor >= 0 and len(prefix) < 4:
            candidate = words[cursor].strip(".,;:()[]")
            if not candidate or not re.search(r"[A-Za-z]", candidate):
                break
            upper = candidate.upper()
            if upper in _BANK_PHRASE_STOPWORDS:
                break
            if not (candidate[0].isupper() or candidate.isupper()):
                break
            prefix.insert(0, candidate)
            cursor -= 1
        if not prefix:
            continue
        name_words = prefix + [token]
        if index + 1 < len(words):
            suffix = words[index + 1].strip(".,;:()[]").upper()
            if suffix in _BANK_SUFFIXES:
                name_words.append(words[index + 1].strip(".,;:()[]"))
        phrase = " ".join(name_words).strip(" .,:-")
        if 2 <= len(phrase.split()) <= 8 and len(phrase) <= 75:
            return phrase
    return None


def _guess_bank_name(pages: list[PageWords]) -> str | None:
    """Last-resort bank name for regional/co-operative/foreign banks."""
    if not pages:
        return None
    for line in group_lines(pages[0].words)[:20]:
        text = re.sub(r"\s+", " ", line.text).strip(" .,:-")
        if "BANK" not in text.upper():
            continue
        letters = sum(1 for ch in text if ch.isalpha())
        if letters / max(1, len(text)) < 0.55:
            continue
        phrase = _bank_phrase(text)
        if phrase:
            return phrase
    return None


def _header_score(text: str, profile_id: str) -> int:
    profile = get_profile(profile_id)
    normalized = " ".join(text.replace("/", " ").replace("-", " ").lower().split())
    canonicals: set[str] = set()
    for phrase, canonical, _count in profile.alias_entries():
        if phrase and phrase in normalized:
            canonicals.add(canonical)
    return len(canonicals)


def detect_bank(pages: list[PageWords], full_text: str | None = None) -> BankDetection:
    text = (full_text or "") + "\n" + _page_text(pages)
    upper = text.upper()
    header = _header_text(pages)
    warnings: list[str] = []

    ifsc_matches = IFSC_RE.findall(upper)
    all_ifscs = [_canonical_ifsc(prefix, suffix) for prefix, suffix in ifsc_matches]
    header_ifscs = _ifsc_from_header(pages)
    ifscs = header_ifscs or all_ifscs
    known_ifscs = [
        ifsc
        for ifsc in ifscs
        if ifsc[:4] in IFSC_TO_PROFILE or ifsc[:4] in IFSC_BANK_NAMES
    ]
    unknown_ifsc = ifscs[0] if ifscs else None

    if known_ifscs:
        prefixes = [ifsc[:4] for ifsc in known_ifscs]
        counts = Counter(prefixes)
        prefix = counts.most_common(1)[0][0]
        if len(counts) > 1:
            warnings.append(
                f"multiple_ifsc_codes_detected: {', '.join(sorted(counts))}; using {prefix}."
            )
        profile_id = IFSC_TO_PROFILE.get(prefix)
        bank_name = IFSC_BANK_NAMES.get(prefix)
        if profile_id:
            profile = get_profile(profile_id)
            return BankDetection(
                profile_id=profile.id,
                bank_name=profile.name,
                method="ifsc",
                confidence=0.99,
                ifsc=known_ifscs[0],
                warnings=warnings,
            )
        return BankDetection(
            profile_id="generic",
            bank_name=bank_name or f"Unknown bank ({prefix})",
            method="ifsc",
            confidence=0.85,
            ifsc=known_ifscs[0],
            warnings=warnings
            + [f"no_dedicated_profile_for_ifsc_prefix_{prefix}: using generic profile."],
        )

    # Bank name / logo text. Only the top of the first pages is considered so
    # counterparty names inside transaction narrations cannot decide the bank.
    alias = _match_bank_alias(header)
    if alias:
        bank_name = alias[1]
        profile_id = _PROFILE_BY_NAME.get(bank_name, "generic")
        if profile_id != "generic":
            profile = get_profile(profile_id)
            return BankDetection(
                profile_id=profile.id,
                bank_name=profile.name,
                method="name",
                confidence=0.92,
                ifsc=unknown_ifsc,
                warnings=warnings,
            )
        return BankDetection(
            profile_id="generic",
            bank_name=bank_name,
            method="name",
            confidence=0.9,
            ifsc=unknown_ifsc,
            warnings=warnings
            + [f"no_dedicated_profile_for_{_compact(bank_name).lower()}: using generic profile."],
        )

    # Header-row signature.
    scores = {profile.id: _header_score(text, profile.id) for profile in all_profiles()}
    profile_id, score = max(scores.items(), key=lambda item: item[1])
    generic_score = scores.get("generic", 0)
    if score >= 5 and profile_id != "generic" and score > generic_score:
        profile = PROFILES[profile_id]
        return BankDetection(
            profile_id=profile.id,
            bank_name=profile.name,
            method="header_signature",
            confidence=min(0.8, 0.45 + score * 0.04),
            ifsc=unknown_ifsc,
            warnings=warnings,
        )

    # Regional / co-operative bank without an IFSC or a known alias.
    guessed = _guess_bank_name(pages)
    if guessed:
        return BankDetection(
            profile_id="generic",
            bank_name=guessed,
            method="name_guess",
            confidence=0.55,
            ifsc=unknown_ifsc,
            warnings=warnings + ["bank_name_guessed_from_header: verify the bank name."],
        )

    if unknown_ifsc:
        prefix = unknown_ifsc[:4]
        return BankDetection(
            profile_id="generic",
            bank_name=f"Unknown bank ({prefix})",
            method="ifsc",
            confidence=0.6,
            ifsc=unknown_ifsc,
            warnings=warnings
            + [f"no_dedicated_profile_for_ifsc_prefix_{prefix}: using generic profile."],
        )

    return BankDetection(
        profile_id="generic",
        bank_name="Unknown Bank",
        method="generic",
        confidence=0.3,
        warnings=warnings,
    )
