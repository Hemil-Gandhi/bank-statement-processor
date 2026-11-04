"""Normalizer tests: dates, Indian amounts, Dr/Cr, references and channels."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.core.normalizer import (
    amount_bucket,
    detect_channel,
    extract_reference,
    parse_amount,
    parse_date,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("01/04/2024", date(2024, 4, 1)),
        ("01-04-2024", date(2024, 4, 1)),
        ("01/04/24", date(2024, 4, 1)),
        ("01 Apr 2024", date(2024, 4, 1)),
        ("01-Apr-24", date(2024, 4, 1)),
        ("2024-04-01", date(2024, 4, 1)),
        ("Apr 01, 2024", date(2024, 4, 1)),
        ("Mon, 01 Apr 2024", date(2024, 4, 1)),
        ("01/04/2024 10:31:00", date(2024, 4, 1)),
    ],
)
def test_parse_date_formats(text: str, expected: date) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", ["12", "12 Somewhere Street", "42/04/2024", "not a date", ""])
def test_parse_date_rejects_non_dates(text: str) -> None:
    assert parse_date(text) is None


def test_parse_date_uses_reference_year_for_short_dates() -> None:
    assert parse_date("01 Apr", reference=date(2024, 6, 30), default_year=2024) == date(2024, 4, 1)


@pytest.mark.parametrize(
    ("text", "amount", "marker"),
    [
        ("₹1,00,000.00", Decimal("100000.00"), None),
        ("Rs. 2,499.00 Cr", Decimal("2499.00"), "credit"),
        ("1,234.00 Dr", Decimal("1234.00"), "debit"),
        ("-550.00", Decimal("-550.00"), None),
        ("(1,234.00)", Decimal("-1234.00"), None),
        ("1.234,56", Decimal("1234.56"), None),
        ("12,50", Decimal("12.50"), None),
        ("O,500.00", Decimal("500.00"), None),
        ("", None, None),
    ],
)
def test_parse_amount(text: str, amount: Decimal | None, marker: str | None) -> None:
    parsed, parsed_marker = parse_amount(text)
    assert parsed == amount
    assert parsed_marker == marker


def test_reference_and_channel_extraction() -> None:
    assert extract_reference("UPI/ZOMATO/412345678901/ORDER") == "412345678901"
    assert extract_reference("NEFT/HDFC0000123/HOUSE RENT") == "HDFC0000123"
    assert detect_channel("UPI/ZOMATO/ORDER") == "UPI"
    assert detect_channel("ATM CASH WITHDRAWAL") == "ATM"
    assert detect_channel("NEFT CR FROM CLIENT") == "NEFT"
    assert detect_channel("SMS ALERT CHARGES") == "CHARGES"
    assert detect_channel("SOMETHING ELSE") == "OTHER"


def test_amount_buckets() -> None:
    assert amount_bucket(Decimal("49")) == "micro"
    assert amount_bucket(Decimal("499")) == "small"
    assert amount_bucket(Decimal("4999")) == "medium"
    assert amount_bucket(Decimal("49999")) == "large"
    assert amount_bucket(Decimal("100000")) == "xl"
    assert amount_bucket(None) == "none"
