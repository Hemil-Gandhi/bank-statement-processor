"""Balance reconciliation, dedupe, reverse-order and inference tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.types import AccountDetails, DetectionResult, RawTransaction
from app.core.validator import validate_transactions


def _detection() -> DetectionResult:
    return DetectionResult(pdf_type="TEXT", per_page_types=["TEXT"], num_pages=1)


def _account(opening: str = "1000.00", closing: str = "900.00") -> AccountDetails:
    return AccountDetails(
        account_holder_name="TEST USER",
        account_number="12345678901",
        ifsc="SBIN0001234",
        statement_period_from=date(2024, 4, 1),
        statement_period_to=date(2024, 4, 30),
        opening_balance=Decimal(opening),
        closing_balance=Decimal(closing),
    )


def test_reconciles_and_closes() -> None:
    rows = [
        RawTransaction(
            page=1,
            date_text="01/04/2024",
            description="ATM WITHDRAWAL",
            debit_text="100.00",
            balance_text="900.00",
        )
    ]
    result = validate_transactions(rows, _account(), _detection())
    assert len(result.transactions) == 1
    assert result.reconciled_rows == 1
    assert result.reconciled_ratio == 1.0
    assert result.closing_reconciled is True
    assert result.total_debit == Decimal("100.00")


def test_missing_amount_is_inferred_from_balance_delta() -> None:
    rows = [
        RawTransaction(
            page=1,
            date_text="01/04/2024",
            description="UNKNOWN DEBIT",
            balance_text="900.00",
        )
    ]
    result = validate_transactions(rows, _account(), _detection())
    assert result.transactions[0].debit == Decimal("100.00")
    assert "amount_inferred_from_balance" in result.transactions[0].flags


def test_duplicate_rows_are_removed() -> None:
    row = dict(
        page=1,
        date_text="01/04/2024",
        description="SALARY CREDIT",
        credit_text="100.00",
        balance_text="1100.00",
    )
    rows = [RawTransaction(**row), RawTransaction(**row)]
    result = validate_transactions(
        rows,
        _account(opening="1000.00", closing="1100.00"),
        _detection(),
    )
    assert len(result.transactions) == 1
    assert result.duplicates_removed == 1


def test_reverse_chronological_rows_are_normalized() -> None:
    rows = [
        RawTransaction(
            page=1,
            date_text="03/04/2024",
            description="THIRD",
            credit_text="30.00",
            balance_text="1030.00",
        ),
        RawTransaction(
            page=1,
            date_text="02/04/2024",
            description="SECOND",
            credit_text="20.00",
            balance_text="1000.00",
        ),
        RawTransaction(
            page=1,
            date_text="01/04/2024",
            description="FIRST",
            credit_text="10.00",
            balance_text="980.00",
        ),
    ]
    result = validate_transactions(
        rows,
        _account(opening="970.00", closing="1030.00"),
        _detection(),
    )
    assert result.reverse_chronological is True
    assert [txn.txn_date for txn in result.transactions] == [
        date(2024, 4, 1),
        date(2024, 4, 2),
        date(2024, 4, 3),
    ]
    assert any("reverse_chronological" in warning for warning in result.warnings)


def test_swapped_debit_credit_is_repaired() -> None:
    rows = [
        RawTransaction(
            page=1,
            date_text="01/04/2024",
            description="SWAPPED ROW",
            debit_text="200.00",
            credit_text="100.00",
            balance_text="1100.00",
        )
    ]
    result = validate_transactions(
        rows,
        _account(opening="1000.00", closing="1100.00"),
        _detection(),
    )
    txn = result.transactions[0]
    assert txn.credit == Decimal("100.00")
    assert txn.debit is None
    assert "auto_repaired_swapped" in txn.flags
