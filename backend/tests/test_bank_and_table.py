"""Bank detection and table reconstruction against generated fixtures."""
from __future__ import annotations

from pathlib import Path

from app.core.bank_detector import detect_bank
from app.core.bank_profiles import get_profile
from app.core.pdf_detector import detect_pdf
from app.core.table_reconstructor import detect_header, reconstruct_transactions
from app.core.text_extractor import extract_page_words
from app.core.account_extractor import extract_account_details
from app.core.types import PageWords, Word


def _text_pages(path: Path):
    detection = detect_pdf(path)
    return detection, extract_page_words(path, detection.per_page_types, None)


def _synthetic_page(lines: list[str]) -> list[PageWords]:
    words: list[Word] = []
    for row, line in enumerate(lines):
        x = 10.0
        for token in line.split():
            width = max(12.0, len(token) * 5.5)
            words.append(
                Word(
                    text=token,
                    x0=x,
                    y0=row * 14.0,
                    x1=x + width,
                    y1=row * 14.0 + 11.0,
                    page=1,
                )
            )
            x += width + 6.0
    return [PageWords(page=1, width=600, height=800, words=words, source="text")]


def test_detects_sbi_from_ifsc_and_header(sbi_pdf: Path) -> None:
    detection, pages = _text_pages(sbi_pdf)
    full_text = " ".join(word.text for page in pages for word in page.words)
    bank = detect_bank(pages, full_text)
    assert bank.profile_id == "sbi"
    assert bank.bank_name == "State Bank of India"
    assert bank.ifsc == "SBIN0001234"
    assert detection.pdf_type == "TEXT"


def test_generic_borderless_fallback_skips_address_line(generic_pdf: Path) -> None:
    _detection, pages = _text_pages(generic_pdf)
    profile = get_profile("generic")
    result = reconstruct_transactions(pages, profile)
    assert len(result.transactions) == 8
    assert result.transactions[0].date_text == "01/04/2024"
    assert all("Somewhere" not in txn.description for txn in result.transactions)
    assert any("borderless" in warning for warning in result.warnings)


def test_sbi_header_and_multiline_rows(sbi_pdf: Path) -> None:
    _detection, pages = _text_pages(sbi_pdf)
    profile = get_profile("sbi")
    header, headers = detect_header(pages, profile)
    assert header is not None
    assert len(headers) == 2
    result = reconstruct_transactions(pages, profile)
    assert len(result.transactions) == 36
    assert result.header_found is True
    # A UPI narration wrapped across two visual lines must be merged.
    assert any("FOOD ORDER" in txn.description for txn in result.transactions)


def test_detects_bank_from_ifsc_without_dedicated_profile() -> None:
    pages = _synthetic_page(
        [
            "CANARA BANK",
            "Account Statement",
            "IFSC: CNRB0001234",
            "Account No: 123456789012",
        ]
    )
    bank = detect_bank(pages)
    assert bank.bank_name == "Canara Bank"
    assert bank.profile_id == "generic"
    assert bank.method == "ifsc"
    assert bank.ifsc == "CNRB0001234"


def test_detects_ifsc_with_spaces_and_ocr_zero() -> None:
    pages = _synthetic_page(
        [
            "STATE BANK OF INDIA",
            "IFSC Code: SBIN O 001234",
            "Branch: Ahmedabad Main",
        ]
    )
    bank = detect_bank(pages)
    assert bank.profile_id == "sbi"
    assert bank.bank_name == "State Bank of India"
    assert bank.ifsc == "SBIN0001234"


def test_detects_unknown_bank_from_header_alias() -> None:
    pages = _synthetic_page(
        [
            "IDFC FIRST BANK",
            "Statement of Account",
            "Customer Name: SAMPLE CUSTOMER",
        ]
    )
    bank = detect_bank(pages)
    assert bank.bank_name == "IDFC FIRST Bank"
    assert bank.profile_id == "generic"
    assert bank.method == "name"


def test_guesses_regional_bank_name_from_header() -> None:
    pages = _synthetic_page(
        [
            "ABC CO-OPERATIVE BANK LTD",
            "Statement of Account",
            "Account No: 123456789012",
        ]
    )
    bank = detect_bank(pages)
    assert bank.bank_name == "ABC CO-OPERATIVE BANK LTD"
    assert bank.profile_id == "generic"
    assert bank.method == "name_guess"
    assert any("bank_name_guessed" in warning for warning in bank.warnings)


def test_counterparty_ifsc_does_not_override_header_ifsc() -> None:
    pages = _synthetic_page(
        [
            "CANARA BANK",
            "IFSC: CNRB0001234",
            "01/04/2024 NEFT/HDFC0000123/PAYMENT 500.00 1000.00",
        ]
    )
    bank = detect_bank(pages)
    assert bank.bank_name == "Canara Bank"
    assert bank.ifsc == "CNRB0001234"


def test_account_details_handle_grouped_number_and_spaced_ifsc() -> None:
    pages = _synthetic_page(
        [
            "CANARA BANK",
            "Account Name: MR. SAMPLE CUSTOMER",
            "Account No: 1234 5678 9012",
            "IFSC: CNRB 0 001234",
            "Statement Period: 01/04/2024 to 30/06/2024",
        ]
    )
    bank = detect_bank(pages)
    details, warnings = extract_account_details(pages, bank)
    assert details.account_holder_name == "SAMPLE CUSTOMER"
    assert details.account_number == "123456789012"
    assert details.account_number_masked == "XXXXXXXX9012"
    assert details.ifsc == "CNRB0001234"
    assert details.statement_period_from.isoformat() == "2024-04-01"
    assert details.statement_period_to.isoformat() == "2024-06-30"
    assert not any("account_fields_missing" in warning for warning in warnings)


def test_guesses_bank_phrase_from_merged_header_line() -> None:
    pages = _synthetic_page(
        [
            "Riverbend Test Bank Everyday Checking statement",
            "A fictional bank for test data September 1 - September 30, 2026",
            "Account XXXX XXXX 0000",
        ]
    )
    bank = detect_bank(pages)
    assert bank.bank_name == "Riverbend Test Bank"
    assert bank.profile_id == "generic"
    assert bank.method == "name_guess"


def test_extracts_us_holder_and_month_name_period() -> None:
    pages = _synthetic_page(
        [
            "Riverbend Test Bank Everyday Checking statement",
            "A fictional bank for test data September 1 - September 30, 2026",
            "Account XXXX XXXX 0000",
            "Ava Okafor Opening balance $2,418.36",
            "1200 Example Ave, Apt 4B Deposits $6,500.00",
            "Springfield, IL 62701 Withdrawals $2,393.72",
            "Closing balance $6,524.64",
        ]
    )
    bank = detect_bank(pages)
    details, warnings = extract_account_details(pages, bank)
    assert details.bank_name == "Riverbend Test Bank"
    assert details.account_holder_name == "Ava Okafor"
    assert details.account_number == "XXXXXXXX0000"
    assert details.statement_period_from.isoformat() == "2026-09-01"
    assert details.statement_period_to.isoformat() == "2026-09-30"
    assert details.currency == "USD"
    assert not any("account_fields_missing" in warning for warning in warnings)
