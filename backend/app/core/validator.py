"""Normalization, balance reconciliation, repair, de-duplication and quality scoring."""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date
from decimal import Decimal

from app.core.normalizer import (
    clean_description,
    extract_reference,
    parse_amount,
    parse_date,
)
from app.core.types import (
    AccountDetails,
    DetectionResult,
    RawTransaction,
    TransactionDraft,
    ValidationResult,
)

logger = logging.getLogger(__name__)

TOLERANCE = Decimal("0.01")


def _abs_or_none(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if value == 0:
        return None
    return abs(value)


def _to_draft(row: RawTransaction, reference: date | None) -> TransactionDraft | None:
    txn_date = parse_date(row.date_text, reference=reference)
    if txn_date is None:
        return None
    value_date = None
    flags: list[str] = []
    for flag in row.flags:
        if flag.startswith("value_date:"):
            try:
                value_date = date.fromisoformat(flag.split(":", 1)[1])
            except ValueError:
                pass
        elif flag.startswith("row:"):
            continue
        else:
            flags.append(flag)

    debit, _ = parse_amount(row.debit_text)
    credit, _ = parse_amount(row.credit_text)
    balance, _ = parse_amount(row.balance_text)
    amount, marker = parse_amount(row.amount_text)
    debit = _abs_or_none(debit)
    credit = _abs_or_none(credit)

    if amount is not None and amount != 0 and debit is None and credit is None:
        if marker == "debit" or row.drcr == "debit":
            debit = abs(amount)
        elif marker == "credit" or row.drcr == "credit":
            credit = abs(amount)
    if debit is not None and credit is not None:
        if debit == 0:
            debit = None
        if credit == 0:
            credit = None
        if debit is not None and credit is not None:
            flags.append("both_amounts_present")
    if debit is None and credit is None and amount is None:
        flags.append("missing_amount")
    if balance is None:
        flags.append("missing_balance")

    description = clean_description(row.description)
    if not description:
        description = "(no description)"
        flags.append("missing_description")
    if any(ord(ch) > 127 for ch in description):
        flags.append("non_ascii_description")

    return TransactionDraft(
        page=row.page,
        txn_date=txn_date,
        value_date=value_date,
        description=description,
        raw_description=clean_description(row.raw_text or row.description),
        reference_no=row.reference_no or extract_reference(description),
        debit=debit,
        credit=credit,
        balance=balance,
        flags=flags,
    )


def _dedupe(transactions: list[TransactionDraft]) -> tuple[list[TransactionDraft], int]:
    seen: set[tuple] = set()
    result: list[TransactionDraft] = []
    removed = 0
    for transaction in transactions:
        if transaction.balance is not None:
            key = (
                transaction.txn_date,
                re.sub(r"\W+", "", transaction.description.lower()),
                transaction.debit,
                transaction.credit,
                transaction.balance,
            )
        else:
            key = (
                transaction.txn_date,
                re.sub(r"\W+", "", transaction.description.lower()),
                transaction.reference_no,
                transaction.debit,
                transaction.credit,
            )
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        result.append(transaction)
    return result, removed


def _amount_variants(amount: Decimal) -> list[Decimal]:
    variants: list[Decimal] = []
    text = f"{abs(amount):.2f}"
    digits = list(text)
    for index, char in enumerate(digits):
        if not char.isdigit():
            continue
        for replacement in "0123456789":
            if replacement == char:
                continue
            candidate = digits.copy()
            candidate[index] = replacement
            try:
                variants.append(Decimal("".join(candidate)).quantize(TOLERANCE))
            except Exception:
                continue
    for factor in (Decimal("10"), Decimal("100"), Decimal("0.1"), Decimal("0.01")):
        variants.append((abs(amount) * factor).quantize(TOLERANCE))
    return variants


def _repair_amount(amount: Decimal | None, target: Decimal) -> Decimal | None:
    if target <= 0:
        return None
    if amount is not None and abs(amount - target) <= TOLERANCE:
        return amount
    if amount is None:
        return None
    for candidate in _amount_variants(amount):
        if abs(candidate - target) <= TOLERANCE:
            return candidate
    return None


def _infer_direction_from_delta(transaction: TransactionDraft, delta: Decimal) -> None:
    if transaction.debit is None and transaction.credit is None:
        if delta > 0:
            transaction.credit = delta
            transaction.flags.append("amount_inferred_from_balance")
        elif delta < 0:
            transaction.debit = abs(delta)
            transaction.flags.append("amount_inferred_from_balance")
        else:
            transaction.flags.append("zero_net_transaction")


def _reconcile(
    transactions: list[TransactionDraft], opening: Decimal | None
) -> tuple[int, list[str], Decimal | None, bool]:
    warnings: list[str] = []
    reconciled = 0
    previous = opening
    if previous is None and transactions:
        first = transactions[0]
        if first.balance is not None and (first.debit is not None or first.credit is not None):
            previous = first.balance + (first.debit or Decimal("0")) - (first.credit or Decimal("0"))
            warnings.append("opening_balance_inferred_from_first_row")
    reconciled_any = False

    for index, transaction in enumerate(transactions):
        if transaction.balance is None and previous is not None:
            if transaction.debit is not None or transaction.credit is not None:
                transaction.balance = previous + (transaction.credit or Decimal("0")) - (
                    transaction.debit or Decimal("0")
                )
                transaction.flags.append("balance_inferred")
                if "missing_balance" in transaction.flags:
                    transaction.flags.remove("missing_balance")

        if transaction.balance is not None and previous is not None:
            delta = transaction.balance - previous
            _infer_direction_from_delta(transaction, delta)
            debit = transaction.debit or Decimal("0")
            credit = transaction.credit or Decimal("0")
            expected = previous + credit - debit
            if abs(expected - transaction.balance) > TOLERANCE:
                # 1) Both sides present: keep only the one matching the balance delta,
                #    otherwise try swapping the two amounts.
                if transaction.debit is not None and transaction.credit is not None:
                    need = abs(delta)
                    if delta > 0 and abs(credit - need) <= TOLERANCE:
                        transaction.debit = None
                        transaction.flags.append("auto_repaired_swapped")
                        reconciled += 1
                        reconciled_any = True
                        previous = transaction.balance
                        continue
                    if delta < 0 and abs(debit - need) <= TOLERANCE:
                        transaction.credit = None
                        transaction.flags.append("auto_repaired_swapped")
                        reconciled += 1
                        reconciled_any = True
                        previous = transaction.balance
                        continue
                    swapped = previous + debit - credit
                    if abs(swapped - transaction.balance) <= TOLERANCE:
                        transaction.debit, transaction.credit = transaction.credit, transaction.debit
                        transaction.flags.append("auto_repaired_swapped")
                        reconciled += 1
                        reconciled_any = True
                        previous = transaction.balance
                        continue
                # 2) One side was spurious; try zeroing it.
                if transaction.debit is not None and abs(previous - transaction.debit - transaction.balance) <= TOLERANCE:
                    transaction.credit = None
                    transaction.flags.append("auto_repaired_zero_credit")
                    reconciled += 1
                    reconciled_any = True
                    previous = transaction.balance
                    continue
                if transaction.credit is not None and abs(previous + transaction.credit - transaction.balance) <= TOLERANCE:
                    transaction.debit = None
                    transaction.flags.append("auto_repaired_zero_debit")
                    reconciled += 1
                    reconciled_any = True
                    previous = transaction.balance
                    continue
                # 3) OCR digit repair.
                target_debit = previous - transaction.balance
                target_credit = transaction.balance - previous
                repaired_debit = _repair_amount(transaction.debit, target_debit)
                repaired_credit = _repair_amount(transaction.credit, target_credit)
                if repaired_debit is not None and target_debit > 0:
                    transaction.debit = repaired_debit
                    transaction.credit = None
                    transaction.flags.append("auto_repaired_ocr_digit")
                    reconciled += 1
                    reconciled_any = True
                elif repaired_credit is not None and target_credit > 0:
                    transaction.credit = repaired_credit
                    transaction.debit = None
                    transaction.flags.append("auto_repaired_ocr_digit")
                    reconciled += 1
                    reconciled_any = True
                else:
                    transaction.flags.append("balance_mismatch")
            else:
                reconciled += 1
                reconciled_any = True
            previous = transaction.balance
        elif transaction.balance is not None:
            previous = transaction.balance
            transaction.flags.append("balance_unverified")
        else:
            transaction.flags.append("balance_unverified")

        if transaction.debit is not None and transaction.debit < 0:
            transaction.debit = abs(transaction.debit)
        if transaction.credit is not None and transaction.credit < 0:
            transaction.credit = abs(transaction.credit)
        if transaction.debit == 0:
            transaction.debit = None
        if transaction.credit == 0:
            transaction.credit = None

    return reconciled, warnings, previous, reconciled_any


def _detect_reverse(transactions: list[TransactionDraft]) -> bool:
    if len(transactions) < 3:
        return False
    decreases = 0
    increases = 0
    for left, right in zip(transactions, transactions[1:]):
        if right.txn_date < left.txn_date:
            decreases += 1
        elif right.txn_date > left.txn_date:
            increases += 1
    return decreases > increases and decreases >= max(2, len(transactions) // 3)


def validate_transactions(
    rows: list[RawTransaction],
    account: AccountDetails,
    detection: DetectionResult,
    page_confidences: dict[int, float] | None = None,
    reference_date: date | None = None,
) -> ValidationResult:
    page_confidences = page_confidences or {}
    warnings: list[str] = []
    reference = reference_date or account.statement_period_to

    drafts: list[TransactionDraft] = []
    for row in rows:
        draft = _to_draft(row, reference)
        if draft is None:
            warnings.append("row_with_unparseable_date_skipped")
            continue
        if reference and (draft.txn_date.year > reference.year + 1 or draft.txn_date.year < reference.year - 10):
            draft.flags.append("date_out_of_range")
        drafts.append(draft)

    drafts, duplicates = _dedupe(drafts)
    if duplicates:
        warnings.append(f"duplicate_transactions_removed: {duplicates}")

    reverse = _detect_reverse(drafts)
    if reverse:
        drafts.reverse()
        warnings.append("reverse_chronological_statement: rows normalized to ascending date order.")

    reconciled, reconcile_warnings, last_balance, _ = _reconcile(drafts, account.opening_balance)
    warnings.extend(reconcile_warnings)

    total_debit = sum((d.debit or Decimal("0") for d in drafts), Decimal("0"))
    total_credit = sum((d.credit or Decimal("0") for d in drafts), Decimal("0"))

    if account.opening_balance is None and drafts:
        first = drafts[0]
        if first.balance is not None:
            account.opening_balance = first.balance + (first.debit or Decimal("0")) - (
                first.credit or Decimal("0")
            )
    if account.closing_balance is None and drafts:
        account.closing_balance = drafts[-1].balance or last_balance

    closing_reconciled = False
    if account.opening_balance is not None and account.closing_balance is not None:
        computed = account.opening_balance + total_credit - total_debit
        closing_reconciled = abs(computed - account.closing_balance) <= TOLERANCE
        if not closing_reconciled:
            warnings.append(
                "closing_balance_mismatch: opening + credits - debits does not equal closing balance."
            )
    elif account.closing_balance is not None and last_balance is not None:
        closing_reconciled = abs(account.closing_balance - last_balance) <= TOLERANCE

    rows_with_balance = sum(1 for d in drafts if d.balance is not None)
    reconciled_ratio = reconciled / max(1, rows_with_balance)
    required = 0
    for draft in drafts:
        if draft.description and draft.txn_date and (draft.debit is not None or draft.credit is not None):
            required += 1
    required_ratio = required / max(1, len(drafts))
    account_fields = [
        account.account_holder_name,
        account.account_number,
        account.ifsc,
        account.statement_period_from,
        account.opening_balance,
        account.closing_balance,
    ]
    account_completeness = sum(1 for value in account_fields if value) / len(account_fields)

    confidences = [value for value in page_confidences.values() if value is not None]
    ocr_quality = (sum(confidences) / len(confidences) / 100.0) if confidences else 1.0
    confidence = (
        0.45 * reconciled_ratio
        + 0.20 * required_ratio
        + 0.15 * account_completeness
        + 0.15 * ocr_quality
        + 0.05 * (1.0 if closing_reconciled else 0.0)
    )
    confidence = round(max(0.0, min(1.0, confidence)), 4)

    for index, draft in enumerate(drafts):
        draft.sort_index = index
    if detection.pdf_type in {"IMAGE", "MIXED"}:
        warnings.append("ocr_path_used: verify low-confidence rows against the source PDF.")
    if reverse:
        warnings.append("reverse_chronological: statement order was normalized for reconciliation.")

    return ValidationResult(
        transactions=drafts,
        warnings=warnings,
        reconciled_rows=reconciled,
        total_rows=len(drafts),
        reconciled_ratio=round(reconciled_ratio, 4),
        extraction_confidence=confidence,
        reverse_chronological=reverse,
        duplicates_removed=duplicates,
        opening_balance=account.opening_balance,
        closing_balance=account.closing_balance,
        closing_reconciled=closing_reconciled,
        total_debit=total_debit,
        total_credit=total_credit,
    )
