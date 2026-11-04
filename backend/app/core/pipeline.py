"""End-to-end statement processing pipeline (text and OCR share the word-box layer)."""
from __future__ import annotations

import logging
import re
import time
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import fitz  # PyMuPDF

from app.classification.classifier import get_engine, load_overrides
from app.classification.upi_parser import merchant_key
from app.config import settings
from app.core.account_extractor import extract_account_details
from app.core.bank_detector import detect_bank
from app.core.bank_profiles import IFSC_TO_PROFILE, get_profile
from app.core.bank_profiles.base import IFSC_BANK_NAMES
from app.core.errors import NoTransactionsError, OcrFailedError
from app.core.ocr_extractor import extract_page_words as ocr_page_words
from app.core.pdf_detector import detect_pdf
from app.core.table_reconstructor import reconstruct_transactions
from app.core.text_extractor import extract_page_words as text_page_words
from app.core.types import (
    BankDetection,
    DetectionResult,
    PageWords,
    ProcessedStatement,
    TransactionDraft,
    Word,
)
from app.core.validator import validate_transactions

logger = logging.getLogger(__name__)

ACCOUNT_NUMBER_RE = re.compile(
    r"(?i)(?:account|a/?c)\s*(?:no|number|#)?\.?\s*[:/\-]?\s*([x*]{2,}\s*\d{2,6}|\d{9,18})"
)


def _fitz_word_pages(path: Path, page_types: list[str], password: str | None) -> list[PageWords]:
    pages: list[PageWords] = []
    doc = fitz.open(path)
    try:
        if doc.needs_pass:
            doc.authenticate(password or "")
        for index, page in enumerate(doc):
            if index >= len(page_types) or page_types[index] != "TEXT":
                continue
            words = []
            for item in page.get_text("words") or []:
                x0, y0, x1, y1, text = item[:5]
                if str(text).strip():
                    words.append(
                        Word(
                            text=str(text).strip(),
                            x0=float(x0),
                            y0=float(y0),
                            x1=float(x1),
                            y1=float(y1),
                            page=index + 1,
                        )
                    )
            pages.append(
                PageWords(
                    page=index + 1,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    words=words,
                    source="text",
                )
            )
    finally:
        doc.close()
    return pages


def _extract_word_boxes(
    path: Path, detection: DetectionResult, password: str | None
) -> tuple[list[PageWords], list[str]]:
    warnings: list[str] = []
    pages: list[PageWords] = []
    if "TEXT" in detection.per_page_types:
        try:
            pages.extend(text_page_words(path, detection.per_page_types, password))
        except Exception as exc:
            warnings.append(f"pdfplumber_failed: {exc}; falling back to PyMuPDF word boxes.")
            pages.extend(_fitz_word_pages(path, detection.per_page_types, password))

    if "IMAGE" in detection.per_page_types:
        doc = fitz.open(path)
        try:
            if doc.needs_pass:
                doc.authenticate(password or "")
            for index, page_type in enumerate(detection.per_page_types):
                if page_type != "IMAGE":
                    continue
                page = doc[index]
                try:
                    pages.append(ocr_page_words(page, index + 1))
                except OcrFailedError as exc:
                    warnings.append(f"page_{index + 1}_ocr_failed: {exc.message}")
                except Exception as exc:
                    warnings.append(f"page_{index + 1}_ocr_failed: {exc}")
        finally:
            doc.close()

    pages.sort(key=lambda page: page.page)
    if not pages:
        raise OcrFailedError(
            "No pages could be read. If this is a scanned PDF, install Tesseract OCR or run via Docker."
        )
    return pages, warnings


def _detect_multi_statement(pages: list[PageWords]) -> list[str]:
    warnings: list[str] = []
    numbers: set[str] = set()
    periods: set[tuple[date | None, date | None]] = set()
    for page in pages:
        text = " ".join(word.text for word in page.words)
        for match in ACCOUNT_NUMBER_RE.finditer(text):
            compact = re.sub(r"\s+", "", match.group(1)).upper()
            if compact:
                numbers.add(compact)
        period_match = re.search(
            r"(?i)(?:statement\s+period|period)\s*[:\-]?\s*"
            r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})\s*(?:to|-)\s*"
            r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})",
            text,
        )
        if period_match:
            from app.core.normalizer import parse_date

            periods.add(
                (
                    parse_date(period_match.group(1)),
                    parse_date(period_match.group(2)),
                )
            )
    if len(numbers) > 1:
        warnings.append(
            "multiple_accounts_detected: the file contains more than one account number; "
            "transactions were combined. Split the file for per-account exports."
        )
    if len(periods) > 1:
        warnings.append(
            "multiple_statement_periods_detected: the file appears to contain multiple statements; "
            "transactions were combined and flagged for review."
        )
    return warnings


def mark_recurring(transactions: list[TransactionDraft]) -> int:
    groups: dict[tuple[str, Decimal], list[TransactionDraft]] = defaultdict(list)
    for transaction in transactions:
        if transaction.amount <= 0:
            continue
        key = (merchant_key(transaction.description), abs(transaction.amount))
        if key[0]:
            groups[key].append(transaction)
    count = 0
    for items in groups.values():
        months = {item.txn_date.strftime("%Y-%m") for item in items}
        if len(months) >= 2 or len(items) >= 3:
            for item in items:
                item.recurring = True
                if "recurring" not in item.flags:
                    item.flags.append("recurring")
                count += 1
    return count


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for warning in warnings:
        if warning and warning not in seen:
            seen.add(warning)
            result.append(warning)
    return result


def _persist(
    session,  # type: ignore[no-untyped-def]
    *,
    job_id: str,
    filename: str,
    detection: DetectionResult,
    bank,
    account,
    validation,
    warnings: list[str],
    duration_ms: int,
) -> None:
    from app.models.db_models import StatementJob, TransactionRecord

    stats = {
        "transaction_count": len(validation.transactions),
        "total_debit": float(validation.total_debit),
        "total_credit": float(validation.total_credit),
        "net": float(validation.total_credit - validation.total_debit),
        "reconciled_rows": validation.reconciled_rows,
        "reconciled_ratio": validation.reconciled_ratio,
        "closing_reconciled": validation.closing_reconciled,
        "flagged_count": sum(1 for txn in validation.transactions if txn.flags),
        "recurring_count": sum(1 for txn in validation.transactions if txn.recurring),
        "duplicates_removed": validation.duplicates_removed,
        "reverse_chronological": validation.reverse_chronological,
    }
    job = StatementJob(
        id=job_id,
        filename=filename,
        status="completed",
        pdf_type=detection.pdf_type,
        per_page_types=detection.per_page_types,
        bank_detected=bank.bank_name,
        bank_profile=bank.profile_id,
        num_pages=detection.num_pages,
        extraction_confidence=validation.extraction_confidence,
        warnings=warnings,
        account_details=account.as_dict(),
        stats=stats,
        password_protected=detection.encrypted,
        duration_ms=duration_ms,
    )
    session.add(job)
    for transaction in validation.transactions:
        session.add(
            TransactionRecord(
                statement_id=job_id,
                page=transaction.page,
                txn_date=transaction.txn_date,
                value_date=transaction.value_date,
                description=transaction.description,
                raw_description=transaction.raw_description,
                reference_no=transaction.reference_no,
                debit=transaction.debit,
                credit=transaction.credit,
                balance=transaction.balance,
                category=transaction.category,
                category_source=transaction.category_source,
                category_confidence=transaction.category_confidence,
                reason=transaction.reason,
                flags=transaction.flags,
                recurring=transaction.recurring,
                sort_index=transaction.sort_index,
            )
        )
    session.commit()


def process_statement(
    path: str | Path,
    filename: str,
    session,  # type: ignore[no-untyped-def]
    *,
    password: str | None = None,
) -> ProcessedStatement:
    started = time.perf_counter()
    path = Path(path)
    job_id = str(uuid.uuid4())

    detection = detect_pdf(path, password)
    pages, word_warnings = _extract_word_boxes(path, detection, password)
    full_text = "\n".join(" ".join(word.text for word in page.words) for page in pages)

    bank = detect_bank(pages, full_text)
    account, account_warnings = extract_account_details(pages, bank, full_text=full_text)

    # If the header did not identify the bank but the account block carries an
    # IFSC, resolve the bank from that IFSC before table reconstruction.
    if bank.profile_id == "generic" and account.ifsc and (
        bank.bank_name.startswith("Unknown") or bank.method in {"generic", "name_guess"}
    ):
        prefix = account.ifsc[:4].upper()
        profile_id = IFSC_TO_PROFILE.get(prefix)
        resolved_name = (
            get_profile(profile_id).name if profile_id else IFSC_BANK_NAMES.get(prefix)
        )
        if resolved_name:
            bank = BankDetection(
                profile_id=profile_id or "generic",
                bank_name=resolved_name,
                method="account_ifsc",
                confidence=0.9,
                ifsc=account.ifsc,
                warnings=list(bank.warnings),
            )

    profile = get_profile(bank.profile_id)
    reference = account.statement_period_to

    reconstruction = reconstruct_transactions(pages, profile, reference_date=reference)
    page_confidences = {
        page.page: (page.ocr_confidence if page.ocr_confidence is not None else 100.0)
        for page in pages
    }
    validation = validate_transactions(
        reconstruction.transactions,
        account,
        detection,
        page_confidences=page_confidences,
        reference_date=reference,
    )

    if not validation.transactions:
        raise NoTransactionsError(
            "No transaction table could be reconstructed. The statement layout may be unsupported, "
            "or OCR quality may be too low."
        )

    overrides = load_overrides(session)
    engine = get_engine()
    engine.classify_transactions(validation.transactions, overrides)
    recurring_count = mark_recurring(validation.transactions)

    if account.statement_period_from is None and validation.transactions:
        account.statement_period_from = min(txn.txn_date for txn in validation.transactions)
    if account.statement_period_to is None and validation.transactions:
        account.statement_period_to = max(txn.txn_date for txn in validation.transactions)
    if account.opening_balance is None:
        account.opening_balance = validation.opening_balance
    if account.closing_balance is None:
        account.closing_balance = validation.closing_balance

    warnings = _dedupe_warnings(
        detection.warnings
        + word_warnings
        + bank.warnings
        + account_warnings
        + reconstruction.warnings
        + validation.warnings
        + engine.warnings
        + _detect_multi_statement(pages)
    )
    if recurring_count:
        warnings.append(f"recurring_transactions_detected: {recurring_count}")

    duration_ms = int((time.perf_counter() - started) * 1000)
    _persist(
        session,
        job_id=job_id,
        filename=filename,
        detection=detection,
        bank=bank,
        account=account,
        validation=validation,
        warnings=warnings,
        duration_ms=duration_ms,
    )
    logger.info(
        "processed job=%s file=%s pages=%s bank=%s txns=%s confidence=%.2f duration_ms=%s",
        job_id,
        filename,
        detection.num_pages,
        bank.bank_name,
        len(validation.transactions),
        validation.extraction_confidence,
        duration_ms,
    )
    return ProcessedStatement(
        job_id=job_id,
        filename=filename,
        detection=detection,
        bank=bank,
        account=account,
        transactions=validation.transactions,
        validation=validation,
        warnings=warnings,
        duration_ms=duration_ms,
    )
