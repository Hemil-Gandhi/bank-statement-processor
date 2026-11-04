"""Pydantic API schemas. Money is exposed as float for JSON transport while the
domain/database layers keep Decimal precision."""
from __future__ import annotations

from datetime import date as Date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AccountDetailsOut(BaseModel):
    account_holder_name: str | None = None
    account_number: str | None = None
    account_number_masked: str | None = None
    ifsc: str | None = None
    bank_name: str | None = None
    branch: str | None = None
    micr: str | None = None
    customer_id: str | None = None
    address: str | None = None
    statement_period_from: Date | None = None
    statement_period_to: Date | None = None
    opening_balance: float | None = None
    closing_balance: float | None = None
    currency: str = "INR"


class TransactionOut(BaseModel):
    id: int
    statement_id: str
    page: int
    date: Date = Field(validation_alias="txn_date")
    value_date: Date | None = None
    description: str
    raw_description: str = ""
    reference_no: str | None = None
    debit: float | None = None
    credit: float | None = None
    balance: float | None = None
    category: str
    category_source: str
    category_confidence: float
    reason: str = ""
    flags: list[str] = Field(default_factory=list)
    recurring: bool = False
    sort_index: int = 0

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class StatementStats(BaseModel):
    transaction_count: int = 0
    total_debit: float = 0
    total_credit: float = 0
    net: float = 0
    reconciled_rows: int = 0
    reconciled_ratio: float = 0
    closing_reconciled: bool = False
    flagged_count: int = 0
    recurring_count: int = 0
    duplicates_removed: int = 0
    reverse_chronological: bool = False


class StatementOut(BaseModel):
    id: str
    filename: str
    status: str
    pdf_type: str
    per_page_types: list[str] = Field(default_factory=list)
    bank_detected: str | None = None
    bank_profile: str | None = None
    num_pages: int = 0
    extraction_confidence: float = 0
    warnings: list[str] = Field(default_factory=list)
    account: AccountDetailsOut = Field(default_factory=AccountDetailsOut)
    stats: StatementStats = Field(default_factory=StatementStats)
    error_code: str | None = None
    error_message: str | None = None
    password_protected: bool = False
    created_at: datetime
    duration_ms: int = 0


class StatementListItem(BaseModel):
    id: str
    filename: str
    status: str
    pdf_type: str
    bank_detected: str | None = None
    num_pages: int = 0
    extraction_confidence: float = 0
    transaction_count: int = 0
    created_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int
    pages: int
    total_debit: float
    total_credit: float


class CategoryBreakdown(BaseModel):
    category: str
    count: int
    debit: float
    credit: float
    net: float


class MonthlyFlow(BaseModel):
    month: str
    credit: float
    debit: float
    net: float
    closing_balance: float | None = None


class TopMerchant(BaseModel):
    merchant: str
    count: int
    amount: float


class BalancePoint(BaseModel):
    date: Date
    balance: float
    description: str = ""


class StatementSummary(BaseModel):
    statement_id: str
    transaction_count: int
    total_debit: float
    total_credit: float
    net: float
    opening_balance: float | None = None
    closing_balance: float | None = None
    closing_reconciled: bool = False
    category_breakdown: list[CategoryBreakdown] = Field(default_factory=list)
    monthly: list[MonthlyFlow] = Field(default_factory=list)
    top_merchants: list[TopMerchant] = Field(default_factory=list)
    balance_series: list[BalancePoint] = Field(default_factory=list)
    flagged_count: int = 0
    recurring_count: int = 0
    extraction_confidence: float = 0


class CategoryOut(BaseModel):
    name: str
    type: Literal["income", "expense", "transfer", "neutral"] = "expense"


class CategoryPatchIn(BaseModel):
    category: str
    apply_to_similar: bool = True


class CategoryPatchOut(BaseModel):
    transaction: TransactionOut
    updated_count: int
    override_saved: bool


class RetrainOut(BaseModel):
    status: str
    samples: int
    overrides_used: int
    accuracy: float | None = None
    model_path: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    job_id: str | None = None


class HealthOut(BaseModel):
    status: str
    version: str
    timestamp: datetime
    ocr_available: bool
    model_available: bool
    database: str
