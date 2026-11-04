"""CSV export (UTF-8 BOM so Excel renders ₹ and Indian text correctly)."""
from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

HEADERS = [
    "Date",
    "Value Date",
    "Description",
    "Reference No",
    "Debit",
    "Credit",
    "Balance",
    "Category",
    "Category Source",
    "Confidence",
    "Flags",
]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _amount(value: Any) -> str:
    parsed = _decimal(value)
    return "" if parsed is None else f"{parsed:.2f}"


def write_csv(
    transactions: Iterable[Any],
    path: str | Path,
    *,
    include_statement: bool = False,
    statement_names: dict[str, str] | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    statement_names = statement_names or {}
    headers = (["Statement"] if include_statement else []) + HEADERS
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for txn in transactions:
            row = [
                txn.txn_date.isoformat() if txn.txn_date else "",
                txn.value_date.isoformat() if getattr(txn, "value_date", None) else "",
                txn.description,
                getattr(txn, "reference_no", None) or "",
                _amount(txn.debit),
                _amount(txn.credit),
                _amount(txn.balance),
                txn.category,
                txn.category_source,
                f"{float(txn.category_confidence or 0):.4f}",
                "; ".join(getattr(txn, "flags", None) or []),
            ]
            if include_statement:
                row.insert(0, statement_names.get(txn.statement_id, txn.statement_id))
            writer.writerow(row)
    return path
