"""Shared domain types used across the extraction pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(slots=True)
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page: int
    conf: float = 100.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(slots=True)
class PageWords:
    page: int
    width: float
    height: float
    words: list[Word]
    source: str  # "text" | "ocr"
    vertical_lines: list[float] = field(default_factory=list)
    horizontal_lines: list[float] = field(default_factory=list)
    ocr_confidence: float | None = None


@dataclass(slots=True)
class DetectionResult:
    pdf_type: str  # TEXT | IMAGE | MIXED
    per_page_types: list[str]
    num_pages: int
    warnings: list[str] = field(default_factory=list)
    encrypted: bool = False


@dataclass(slots=True)
class AccountDetails:
    account_holder_name: str | None = None
    account_number: str | None = None
    account_number_masked: str | None = None
    ifsc: str | None = None
    bank_name: str | None = None
    branch: str | None = None
    micr: str | None = None
    customer_id: str | None = None
    address: str | None = None
    statement_period_from: date | None = None
    statement_period_to: date | None = None
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    currency: str = "INR"

    def as_dict(self) -> dict:
        return {
            "account_holder_name": self.account_holder_name,
            "account_number": self.account_number,
            "account_number_masked": self.account_number_masked,
            "ifsc": self.ifsc,
            "bank_name": self.bank_name,
            "branch": self.branch,
            "micr": self.micr,
            "customer_id": self.customer_id,
            "address": self.address,
            "statement_period_from": self.statement_period_from.isoformat()
            if self.statement_period_from
            else None,
            "statement_period_to": self.statement_period_to.isoformat()
            if self.statement_period_to
            else None,
            "opening_balance": str(self.opening_balance)
            if self.opening_balance is not None
            else None,
            "closing_balance": str(self.closing_balance)
            if self.closing_balance is not None
            else None,
            "currency": self.currency,
        }


@dataclass(slots=True)
class BankDetection:
    profile_id: str
    bank_name: str
    method: str
    confidence: float
    ifsc: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RawTransaction:
    page: int
    date_text: str
    description: str = ""
    reference_no: str | None = None
    debit_text: str | None = None
    credit_text: str | None = None
    balance_text: str | None = None
    amount_text: str | None = None
    drcr: str | None = None
    y: float = 0.0
    flags: list[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass(slots=True)
class ReconstructionResult:
    transactions: list[RawTransaction]
    warnings: list[str] = field(default_factory=list)
    header_found: bool = False
    column_map: dict[str, tuple[float, float]] = field(default_factory=dict)


@dataclass(slots=True)
class TransactionDraft:
    page: int
    txn_date: date
    value_date: date | None
    description: str
    raw_description: str
    reference_no: str | None
    debit: Decimal | None
    credit: Decimal | None
    balance: Decimal | None
    category: str = "Uncategorized"
    category_source: str = "fallback"
    category_confidence: float = 0.0
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    recurring: bool = False
    sort_index: int = 0

    @property
    def direction(self) -> str:
        if self.debit is not None and self.debit > 0:
            return "debit"
        if self.credit is not None and self.credit > 0:
            return "credit"
        return "unknown"

    @property
    def amount(self) -> Decimal:
        return self.debit or self.credit or Decimal("0")


@dataclass(slots=True)
class ValidationResult:
    transactions: list[TransactionDraft]
    warnings: list[str] = field(default_factory=list)
    reconciled_rows: int = 0
    total_rows: int = 0
    reconciled_ratio: float = 0.0
    extraction_confidence: float = 0.0
    reverse_chronological: bool = False
    duplicates_removed: int = 0
    opening_balance: Decimal | None = None
    closing_balance: Decimal | None = None
    closing_reconciled: bool = False
    total_debit: Decimal = Decimal("0")
    total_credit: Decimal = Decimal("0")


@dataclass(slots=True)
class ProcessedStatement:
    job_id: str
    filename: str
    detection: DetectionResult
    bank: BankDetection
    account: AccountDetails
    transactions: list[TransactionDraft]
    validation: ValidationResult
    warnings: list[str]
    duration_ms: int
