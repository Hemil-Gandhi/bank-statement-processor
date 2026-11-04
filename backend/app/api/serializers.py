"""Convert ORM rows into API schemas and compute dashboard summaries."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.classification.upi_parser import merchant_key
from app.models.db_models import StatementJob, TransactionRecord
from app.models.schemas import (
    AccountDetailsOut,
    BalancePoint,
    CategoryBreakdown,
    MonthlyFlow,
    StatementOut,
    StatementStats,
    StatementSummary,
    TopMerchant,
    TransactionOut,
)


def _decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def job_to_out(job: StatementJob) -> StatementOut:
    account = AccountDetailsOut(**(job.account_details or {}))
    stats = StatementStats(**(job.stats or {}))
    return StatementOut(
        id=job.id,
        filename=job.filename,
        status=job.status,
        pdf_type=job.pdf_type,
        per_page_types=job.per_page_types or [],
        bank_detected=job.bank_detected,
        bank_profile=job.bank_profile,
        num_pages=job.num_pages,
        extraction_confidence=job.extraction_confidence,
        warnings=job.warnings or [],
        account=account,
        stats=stats,
        error_code=job.error_code,
        error_message=job.error_message,
        password_protected=job.password_protected,
        created_at=job.created_at,
        duration_ms=job.duration_ms,
    )


def transaction_to_out(transaction: TransactionRecord) -> TransactionOut:
    return TransactionOut.model_validate(transaction)


def build_summary(job: StatementJob, transactions: list[TransactionRecord]) -> StatementSummary:
    total_debit = sum((_decimal(txn.debit) for txn in transactions), Decimal("0"))
    total_credit = sum((_decimal(txn.credit) for txn in transactions), Decimal("0"))
    categories: dict[str, dict] = defaultdict(lambda: {"count": 0, "debit": Decimal("0"), "credit": Decimal("0")})
    months: dict[str, dict] = defaultdict(lambda: {"credit": Decimal("0"), "debit": Decimal("0"), "closing": None})
    merchants: dict[str, dict] = defaultdict(lambda: {"count": 0, "amount": Decimal("0")})
    balance_series: list[BalancePoint] = []

    for txn in sorted(transactions, key=lambda item: (item.txn_date, item.sort_index)):
        category = categories[txn.category]
        category["count"] += 1
        category["debit"] += _decimal(txn.debit)
        category["credit"] += _decimal(txn.credit)
        month_key = txn.txn_date.strftime("%Y-%m")
        month = months[month_key]
        month["credit"] += _decimal(txn.credit)
        month["debit"] += _decimal(txn.debit)
        if txn.balance is not None:
            month["closing"] = _decimal(txn.balance)
        merchant = merchant_key(txn.description)
        if merchant:
            merchants[merchant]["count"] += 1
            merchants[merchant]["amount"] += _decimal(txn.debit) or _decimal(txn.credit)
        if txn.balance is not None:
            balance_series.append(
                BalancePoint(
                    date=txn.txn_date,
                    balance=float(_decimal(txn.balance)),
                    description=txn.description[:90],
                )
            )

    category_breakdown = [
        CategoryBreakdown(
            category=category,
            count=value["count"],
            debit=float(value["debit"]),
            credit=float(value["credit"]),
            net=float(value["credit"] - value["debit"]),
        )
        for category, value in sorted(
            categories.items(),
            key=lambda item: (item[1]["debit"] + item[1]["credit"], item[1]["count"]),
            reverse=True,
        )
    ]
    monthly = [
        MonthlyFlow(
            month=month,
            credit=float(value["credit"]),
            debit=float(value["debit"]),
            net=float(value["credit"] - value["debit"]),
            closing_balance=float(value["closing"]) if value["closing"] is not None else None,
        )
        for month, value in sorted(months.items())
    ]
    top_merchants = [
        TopMerchant(merchant=merchant, count=value["count"], amount=float(value["amount"]))
        for merchant, value in sorted(
            merchants.items(), key=lambda item: item[1]["amount"], reverse=True
        )[:8]
    ]
    details = job.account_details or {}
    opening = _decimal(details.get("opening_balance")) if details.get("opening_balance") else None
    closing = _decimal(details.get("closing_balance")) if details.get("closing_balance") else None
    stats = job.stats or {}
    return StatementSummary(
        statement_id=job.id,
        transaction_count=len(transactions),
        total_debit=float(total_debit),
        total_credit=float(total_credit),
        net=float(total_credit - total_debit),
        opening_balance=float(opening) if opening is not None else None,
        closing_balance=float(closing) if closing is not None else None,
        closing_reconciled=bool(stats.get("closing_reconciled", False)),
        category_breakdown=category_breakdown,
        monthly=monthly,
        top_merchants=top_merchants,
        balance_series=balance_series,
        flagged_count=sum(1 for txn in transactions if txn.flags),
        recurring_count=sum(1 for txn in transactions if txn.recurring),
        extraction_confidence=job.extraction_confidence,
    )


def filter_transactions(
    transactions: list[TransactionRecord],
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    category: str | None = None,
    txn_type: str | None = None,
    search: str | None = None,
    flagged_only: bool = False,
    sort: str = "date_asc",
) -> list[TransactionRecord]:
    result = list(transactions)
    if date_from:
        result = [txn for txn in result if txn.txn_date >= date_from]
    if date_to:
        result = [txn for txn in result if txn.txn_date <= date_to]
    if category:
        wanted = {item.strip() for item in category.split(",") if item.strip()}
        if wanted:
            result = [txn for txn in result if txn.category in wanted]
    if txn_type == "debit":
        result = [txn for txn in result if txn.debit is not None and _decimal(txn.debit) > 0]
    elif txn_type == "credit":
        result = [txn for txn in result if txn.credit is not None and _decimal(txn.credit) > 0]
    if search:
        needle = search.lower()
        result = [
            txn
            for txn in result
            if needle in (txn.description or "").lower()
            or needle in (txn.reference_no or "").lower()
            or needle in (txn.category or "").lower()
        ]
    if flagged_only:
        result = [txn for txn in result if txn.flags]
    if sort == "date_desc":
        result.sort(key=lambda txn: (txn.txn_date, txn.sort_index), reverse=True)
    elif sort == "amount_asc":
        result.sort(key=lambda txn: (_decimal(txn.debit) or _decimal(txn.credit), txn.sort_index))
    elif sort == "amount_desc":
        result.sort(
            key=lambda txn: (_decimal(txn.debit) or _decimal(txn.credit), txn.sort_index),
            reverse=True,
        )
    else:
        result.sort(key=lambda txn: (txn.txn_date, txn.sort_index))
    return result
