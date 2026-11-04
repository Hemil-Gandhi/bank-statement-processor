"""Rule engine, UPI parser, override matching and ML fallback tests."""
from __future__ import annotations

from decimal import Decimal

from app.classification.classifier import (
    ClassificationEngine,
    OverrideEntry,
    match_override,
    similarity,
)
from app.classification.taxonomy import CATEGORIES
from app.classification.upi_parser import merchant_key, parse_upi


def test_upi_narration_is_parsed() -> None:
    details = parse_upi("UPI/DR/123456789012/SWIGGY/YESB/swiggy@ybl/FOOD ORDER")
    assert details.is_upi is True
    assert details.vpa == "SWIGGY@YBL"
    assert details.payee == "SWIGGY"
    assert details.reference == "123456789012"
    assert details.remark is not None and "FOOD ORDER" in details.remark


def test_non_upi_narration_is_ignored() -> None:
    details = parse_upi("ATM CASH WITHDRAWAL BANGALORE")
    assert details.is_upi is False
    assert details.payee is None


def test_merchant_key_prefers_upi_payee() -> None:
    assert merchant_key("UPI/DR/998877665544/BLINKIT/HDFC/blinkit@ybl/GROCERY") == "BLINKIT"
    assert merchant_key("POS 4321 AMAZON RETAIL") == "AMAZON RETAIL"


def test_salary_credit_rule() -> None:
    engine = ClassificationEngine()
    outcome = engine.classify("SALARY CREDIT APRIL 2024", "credit", Decimal("75000"))
    assert outcome.category == "Salary/Income"
    assert outcome.source == "rule"
    assert outcome.confidence >= 0.75


def test_atm_debit_rule() -> None:
    engine = ClassificationEngine()
    outcome = engine.classify("ATM WDL 1234 BANGALORE", "debit", Decimal("2000"))
    assert outcome.category == "Cash Withdrawal (ATM)"
    assert outcome.source == "rule"


def test_upi_food_rule_uses_payee() -> None:
    engine = ClassificationEngine()
    outcome = engine.classify(
        "UPI/DR/123456789012/SWIGGY/YESB/swiggy@ybl/ORDER", "debit", Decimal("450")
    )
    assert outcome.category == "Food & Dining"


def test_user_override_takes_precedence() -> None:
    engine = ClassificationEngine()
    overrides = [
        OverrideEntry(normalized="SWIGGY ORDER", category="Groceries", pattern="SWIGGY ORDER")
    ]
    outcome = engine.classify(
        "SWIGGY ORDER", "debit", Decimal("450"), overrides=overrides
    )
    assert outcome.category == "Groceries"
    assert outcome.source == "user"


def test_override_fuzzy_match_and_similarity() -> None:
    overrides = [
        OverrideEntry(
            normalized="AMAZON PAY INDIA",
            category="Shopping/E-commerce",
            pattern="AMAZON PAY INDIA",
        )
    ]
    matched = match_override("AMAZON PAY INDIA PVT LTD", overrides)
    assert matched is not None
    assert matched.category == "Shopping/E-commerce"
    assert similarity("AMAZON PAY INDIA", "AMAZON PAY INDIA PVT") >= 88


def test_unseen_description_returns_valid_category() -> None:
    engine = ClassificationEngine()
    outcome = engine.classify("QWERTYZXCV RANDOM NARRATION 42", "debit", Decimal("1234"))
    assert outcome.category in CATEGORIES
    assert 0.0 <= outcome.confidence <= 1.0
