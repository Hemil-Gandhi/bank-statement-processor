"""Multi-sheet Excel export with real dates/numbers, filters and charts."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import xlsxwriter

from app.classification.taxonomy import CATEGORIES


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _as_float(value: Any) -> float:
    return float(_decimal(value))


def _month_key(value: date) -> str:
    return value.strftime("%Y-%m")


def _aggregate(transactions: Iterable[Any]) -> tuple[list[dict], list[dict]]:
    categories: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "debit": Decimal("0"), "credit": Decimal("0")}
    )
    months: dict[str, dict] = defaultdict(
        lambda: {"credit": Decimal("0"), "debit": Decimal("0"), "closing": None, "order": None}
    )
    for txn in transactions:
        entry = categories[txn.category]
        entry["count"] += 1
        entry["debit"] += _decimal(txn.debit)
        entry["credit"] += _decimal(txn.credit)
        key = _month_key(txn.txn_date)
        month = months[key]
        month["credit"] += _decimal(txn.credit)
        month["debit"] += _decimal(txn.debit)
        if txn.balance is not None:
            month["closing"] = _decimal(txn.balance)
        month["order"] = key
    category_rows = [
        {
            "category": category,
            "count": value["count"],
            "debit": value["debit"],
            "credit": value["credit"],
            "net": value["credit"] - value["debit"],
        }
        for category, value in categories.items()
    ]
    category_rows.sort(key=lambda row: (row["debit"] + row["credit"], row["count"]), reverse=True)
    month_rows = [
        {
            "month": key,
            "credit": value["credit"],
            "debit": value["debit"],
            "net": value["credit"] - value["debit"],
            "closing": value["closing"],
        }
        for key, value in sorted(months.items())
    ]
    return category_rows, month_rows


def _base_formats(workbook: xlsxwriter.Workbook) -> dict[str, Any]:
    return {
        "title": workbook.add_format({"bold": True, "font_size": 18, "font_color": "#1F2A44"}),
        "subtitle": workbook.add_format({"italic": True, "font_color": "#5B6B85"}),
        "label": workbook.add_format({"bold": True, "bg_color": "#EEF2F8", "border": 1}),
        "value": workbook.add_format({"border": 1}),
        "header": workbook.add_format(
            {
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#2F5D8A",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
            }
        ),
        "date": workbook.add_format({"num_format": "dd/mm/yyyy", "border": 1}),
        "money": workbook.add_format({"num_format": "#,##0.00", "border": 1}),
        "number": workbook.add_format({"num_format": "0.0000", "border": 1}),
        "text": workbook.add_format({"border": 1}),
        "text_wrap": workbook.add_format({"border": 1, "text_wrap": True, "valign": "top"}),
        "flagged": workbook.add_format({"bg_color": "#FDE2E1", "border": 1}),
        "flagged_money": workbook.add_format(
            {"bg_color": "#FDE2E1", "border": 1, "num_format": "#,##0.00"}
        ),
        "flagged_date": workbook.add_format(
            {"bg_color": "#FDE2E1", "border": 1, "num_format": "dd/mm/yyyy"}
        ),
        "recurring": workbook.add_format({"bg_color": "#E3F2FD", "border": 1}),
        "recurring_money": workbook.add_format(
            {"bg_color": "#E3F2FD", "border": 1, "num_format": "#,##0.00"}
        ),
        "recurring_date": workbook.add_format(
            {"bg_color": "#E3F2FD", "border": 1, "num_format": "dd/mm/yyyy"}
        ),
        "section": workbook.add_format(
            {"bold": True, "font_size": 12, "font_color": "#2F5D8A", "bottom": 1}
        ),
    }


def _write_account_sheet(
    workbook: xlsxwriter.Workbook,
    formats: dict[str, Any],
    statements: list[Any],
    merged: bool,
) -> None:
    sheet = workbook.add_worksheet("Account Details")
    sheet.set_tab_color("#2F5D8A")
    sheet.set_column("A:A", 28)
    sheet.set_column("B:B", 55)
    sheet.set_column("C:C", 22)
    sheet.set_column("D:D", 22)
    sheet.set_column("E:E", 18)
    sheet.set_column("F:F", 18)
    sheet.set_column("G:G", 18)
    sheet.set_column("H:H", 18)
    sheet.write("A1", "Bank Statement Processing & Classification", formats["title"])
    sheet.write("A2", "Account Details", formats["subtitle"])
    row = 4
    if not merged and statements:
        job = statements[0]
        details = job.account_details or {}
        fields = [
            ("File name", job.filename),
            ("Bank", job.bank_detected),
            ("Bank profile", job.bank_profile),
            ("PDF type", job.pdf_type),
            ("Pages", job.num_pages),
            ("Extraction confidence", f"{float(job.extraction_confidence or 0):.2%}"),
            ("Account holder", details.get("account_holder_name")),
            ("Account number", details.get("account_number")),
            ("Masked account", details.get("account_number_masked")),
            ("IFSC", details.get("ifsc")),
            ("Branch", details.get("branch")),
            ("MICR", details.get("micr")),
            ("Customer ID / CIF", details.get("customer_id")),
            ("Address", details.get("address")),
            ("Statement period from", details.get("statement_period_from")),
            ("Statement period to", details.get("statement_period_to")),
            ("Opening balance", details.get("opening_balance")),
            ("Closing balance", details.get("closing_balance")),
            ("Currency", details.get("currency")),
            ("Password protected", "Yes" if job.password_protected else "No"),
            ("Processed at", job.created_at.strftime("%Y-%m-%d %H:%M:%S") if job.created_at else ""),
            ("Warnings", "\n".join(job.warnings or [])),
        ]
        for label, value in fields:
            sheet.write(row, 0, label, formats["label"])
            sheet.write(row, 1, "" if value is None else str(value), formats["value"])
            row += 1
    else:
        headers = [
            "Statement",
            "File",
            "Bank",
            "Account",
            "IFSC",
            "Period From",
            "Period To",
            "Opening",
            "Closing",
            "PDF Type",
            "Confidence",
        ]
        for column, header in enumerate(headers):
            sheet.write(row, column, header, formats["header"])
        row += 1
        for job in statements:
            details = job.account_details or {}
            sheet.write(row, 0, job.id, formats["text"])
            sheet.write(row, 1, job.filename, formats["text"])
            sheet.write(row, 2, job.bank_detected or "", formats["text"])
            sheet.write(row, 3, details.get("account_number_masked") or "", formats["text"])
            sheet.write(row, 4, details.get("ifsc") or "", formats["text"])
            sheet.write(row, 5, details.get("statement_period_from") or "", formats["text"])
            sheet.write(row, 6, details.get("statement_period_to") or "", formats["text"])
            sheet.write(row, 7, details.get("opening_balance") or "", formats["text"])
            sheet.write(row, 8, details.get("closing_balance") or "", formats["text"])
            sheet.write(row, 9, job.pdf_type, formats["text"])
            sheet.write(row, 10, float(job.extraction_confidence or 0), formats["number"])
            row += 1


def _write_categories_sheet(
    workbook: xlsxwriter.Workbook, formats: dict[str, Any]
) -> None:
    """Hidden lookup sheet so category validation works beyond Excel's 255-char limit."""
    sheet = workbook.add_worksheet("Categories")
    for index, category in enumerate(CATEGORIES):
        sheet.write(index, 0, category, formats["text"])
    sheet.hide()


def _write_transactions_sheet(
    workbook: xlsxwriter.Workbook,
    formats: dict[str, Any],
    transactions: list[Any],
    statements_by_id: dict[str, Any],
    merged: bool,
) -> int:
    sheet = workbook.add_worksheet("Transactions")
    sheet.set_tab_color("#2F8A5D")
    headers = [
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
        "Page",
        "Recurring",
    ]
    if merged:
        headers.insert(0, "Statement")
    for column, header in enumerate(headers):
        sheet.write(0, column, header, formats["header"])
    sheet.set_column(0 if not merged else 1, 0 if not merged else 1, 12)
    sheet.set_column(2 if not merged else 3, 2 if not merged else 3, 55)
    sheet.set_column(3 if not merged else 4, 3 if not merged else 4, 18)
    sheet.set_column(4 if not merged else 5, 6 if not merged else 7, 15)
    sheet.set_column(7 if not merged else 8, 8 if not merged else 9, 28)
    sheet.set_column(10 if not merged else 11, 10 if not merged else 11, 36)
    sheet.freeze_panes(1, 0)
    sheet.autofilter(0, 0, max(1, len(transactions)), len(headers) - 1)

    for index, txn in enumerate(transactions, start=1):
        flagged = bool(getattr(txn, "flags", None))
        recurring = bool(getattr(txn, "recurring", False))
        if flagged:
            text_format = formats["flagged"]
            money_format = formats["flagged_money"]
            date_format = formats["flagged_date"]
        elif recurring:
            text_format = formats["recurring"]
            money_format = formats["recurring_money"]
            date_format = formats["recurring_date"]
        else:
            text_format = formats["text"]
            money_format = formats["money"]
            date_format = formats["date"]
        column = 0
        if merged:
            statement = statements_by_id.get(txn.statement_id)
            sheet.write(
                index,
                column,
                statement.filename if statement else txn.statement_id,
                text_format,
            )
            column += 1
        if txn.txn_date:
            sheet.write_datetime(index, column, datetime.combine(txn.txn_date, time.min), date_format)
        else:
            sheet.write(index, column, "", text_format)
        column += 1
        if getattr(txn, "value_date", None):
            sheet.write_datetime(
                index, column, datetime.combine(txn.value_date, time.min), date_format
            )
        else:
            sheet.write(index, column, "", text_format)
        column += 1
        sheet.write(index, column, txn.description, text_format)
        column += 1
        sheet.write(index, column, getattr(txn, "reference_no", None) or "", text_format)
        column += 1
        for value in (txn.debit, txn.credit, txn.balance):
            if value is None:
                sheet.write(index, column, "", text_format)
            else:
                sheet.write_number(index, column, _as_float(value), money_format)
            column += 1
        sheet.write(index, column, txn.category, text_format)
        column += 1
        sheet.write(index, column, txn.category_source, text_format)
        column += 1
        sheet.write_number(index, column, float(txn.category_confidence or 0), formats["number"])
        column += 1
        sheet.write(index, column, "; ".join(getattr(txn, "flags", None) or []), text_format)
        column += 1
        sheet.write_number(index, column, int(getattr(txn, "page", 1) or 1), text_format)
        column += 1
        sheet.write(index, column, "Yes" if recurring else "", text_format)

    category_column = 8 if merged else 7
    if transactions:
        sheet.data_validation(
            1,
            category_column,
            len(transactions),
            category_column,
            {
                "validate": "list",
                "source": f"=Categories!$A$1:$A${len(CATEGORIES)}",
            },
        )
    return len(transactions)


def _write_summary_sheets(
    workbook: xlsxwriter.Workbook,
    formats: dict[str, Any],
    transactions: list[Any],
) -> None:
    category_rows, month_rows = _aggregate(transactions)

    category_sheet = workbook.add_worksheet("Category Summary")
    category_sheet.set_tab_color("#8A5D2F")
    category_sheet.set_column("A:A", 38)
    category_sheet.set_column("B:B", 10)
    category_sheet.set_column("C:E", 18)
    headers = ["Category", "Count", "Total Debit", "Total Credit", "Net"]
    for column, header in enumerate(headers):
        category_sheet.write(0, column, header, formats["header"])
    for index, row in enumerate(category_rows, start=1):
        category_sheet.write(index, 0, row["category"], formats["text"])
        category_sheet.write_number(index, 1, row["count"], formats["text"])
        category_sheet.write_number(index, 2, _as_float(row["debit"]), formats["money"])
        category_sheet.write_number(index, 3, _as_float(row["credit"]), formats["money"])
        category_sheet.write_number(index, 4, _as_float(row["net"]), formats["money"])
    category_sheet.freeze_panes(1, 0)
    if category_rows:
        category_sheet.autofilter(0, 0, len(category_rows), 4)
        last = len(category_rows)
        chart = workbook.add_chart({"type": "column"})
        chart.add_series(
            {
                "name": "Total Debit",
                "categories": ["Category Summary", 1, 0, last, 0],
                "values": ["Category Summary", 1, 2, last, 2],
                "fill": {"color": "#C0504D"},
            }
        )
        chart.add_series(
            {
                "name": "Total Credit",
                "categories": ["Category Summary", 1, 0, last, 0],
                "values": ["Category Summary", 1, 3, last, 3],
                "fill": {"color": "#4F81BD"},
            }
        )
        chart.set_title({"name": "Spend and income by category"})
        chart.set_x_axis({"name": "Category", "num_font": {"rotation": -45}})
        chart.set_y_axis({"name": "Amount (INR)"})
        chart.set_size({"width": 900, "height": 420})
        category_sheet.insert_chart("G2", chart)

        pie = workbook.add_chart({"type": "pie"})
        pie.add_series(
            {
                "name": "Debit by category",
                "categories": ["Category Summary", 1, 0, last, 0],
                "values": ["Category Summary", 1, 2, last, 2],
            }
        )
        pie.set_title({"name": "Debit distribution"})
        pie.set_size({"width": 720, "height": 420})
        category_sheet.insert_chart("G26", pie)

    month_sheet = workbook.add_worksheet("Monthly Summary")
    month_sheet.set_tab_color("#5D2F8A")
    month_sheet.set_column("A:A", 14)
    month_sheet.set_column("B:E", 18)
    month_headers = ["Month", "Total Credit", "Total Debit", "Net", "Closing Balance"]
    for column, header in enumerate(month_headers):
        month_sheet.write(0, column, header, formats["header"])
    for index, row in enumerate(month_rows, start=1):
        month_sheet.write(index, 0, row["month"], formats["text"])
        month_sheet.write_number(index, 1, _as_float(row["credit"]), formats["money"])
        month_sheet.write_number(index, 2, _as_float(row["debit"]), formats["money"])
        month_sheet.write_number(index, 3, _as_float(row["net"]), formats["money"])
        if row["closing"] is None:
            month_sheet.write(index, 4, "", formats["text"])
        else:
            month_sheet.write_number(index, 4, _as_float(row["closing"]), formats["money"])
    month_sheet.freeze_panes(1, 0)
    if month_rows:
        last = len(month_rows)
        chart = workbook.add_chart({"type": "column"})
        chart.add_series(
            {
                "name": "Credit",
                "categories": ["Monthly Summary", 1, 0, last, 0],
                "values": ["Monthly Summary", 1, 1, last, 1],
                "fill": {"color": "#4F81BD"},
            }
        )
        chart.add_series(
            {
                "name": "Debit",
                "categories": ["Monthly Summary", 1, 0, last, 0],
                "values": ["Monthly Summary", 1, 2, last, 2],
                "fill": {"color": "#C0504D"},
            }
        )
        chart.set_title({"name": "Monthly cash flow"})
        chart.set_y_axis({"name": "Amount (INR)"})
        chart.set_size({"width": 900, "height": 380})
        month_sheet.insert_chart("G2", chart)

        line = workbook.add_chart({"type": "line"})
        line.add_series(
            {
                "name": "Closing balance",
                "categories": ["Monthly Summary", 1, 0, last, 0],
                "values": ["Monthly Summary", 1, 4, last, 4],
                "line": {"color": "#2F8A5D", "width": 2.25},
            }
        )
        line.set_title({"name": "Closing balance trend"})
        line.set_size({"width": 900, "height": 320})
        month_sheet.insert_chart("G22", line)


def export_xlsx(
    job: Any,
    transactions: list[Any],
    path: str | Path,
    *,
    merged_jobs: list[Any] | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(str(path), {"nan_inf_to_errors": True})
    try:
        formats = _base_formats(workbook)
        statements = merged_jobs if merged_jobs is not None else [job]
        merged = merged_jobs is not None
        _write_account_sheet(workbook, formats, statements, merged)
        _write_categories_sheet(workbook, formats)
        _write_transactions_sheet(
            workbook,
            formats,
            transactions,
            {statement.id: statement for statement in statements},
            merged,
        )
        _write_summary_sheets(workbook, formats, transactions)
    finally:
        workbook.close()
    return path
