"""CSV and XLSX export content/structure tests."""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from app.export.csv_exporter import write_csv
from app.export.xlsx_exporter import export_xlsx
from app.models.db_models import StatementJob, TransactionRecord


def _job(job_id: str = "job-1", filename: str = "sbi_statement.pdf") -> StatementJob:
    return StatementJob(
        id=job_id,
        filename=filename,
        status="completed",
        pdf_type="TEXT",
        per_page_types=["TEXT"],
        bank_detected="State Bank of India",
        bank_profile="sbi",
        num_pages=2,
        extraction_confidence=0.97,
        warnings=["sample warning"],
        account_details={
            "account_holder_name": "SAMPLE CUSTOMER",
            "account_number": "12345678901",
            "account_number_masked": "XXXXXX78901",
            "ifsc": "SBIN0001234",
            "statement_period_from": "2024-04-01",
            "statement_period_to": "2024-04-30",
            "opening_balance": 1000.0,
            "closing_balance": 1100.0,
            "currency": "INR",
        },
        stats={"transaction_count": 2},
        created_at=datetime(2024, 5, 1, 10, 0, tzinfo=timezone.utc),
    )


def _transactions(statement_id: str = "job-1") -> list[TransactionRecord]:
    return [
        TransactionRecord(
            id=1,
            statement_id=statement_id,
            page=1,
            txn_date=date(2024, 4, 1),
            description="SALARY CREDIT APRIL",
            reference_no="REF001",
            credit=Decimal("500.00"),
            balance=Decimal("1500.00"),
            category="Salary/Income",
            category_source="rule",
            category_confidence=0.9,
            flags=[],
            sort_index=0,
        ),
        TransactionRecord(
            id=2,
            statement_id=statement_id,
            page=1,
            txn_date=date(2024, 4, 2),
            description="ATM WDL 1234",
            debit=Decimal("400.00"),
            balance=Decimal("1100.00"),
            category="Cash Withdrawal (ATM)",
            category_source="rule",
            category_confidence=0.9,
            flags=["balance_unverified"],
            recurring=True,
            sort_index=1,
        ),
    ]


def test_csv_export_has_bom_headers_and_rows(tmp_path: Path) -> None:
    output = tmp_path / "statement.csv"
    write_csv(_transactions(), output)
    raw = output.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0][0] == "Date"
    assert len(rows) == 3
    assert rows[1][0] == "2024-04-01"
    assert rows[1][4] == ""
    assert rows[1][5] == "500.00"
    assert rows[2][10] == "balance_unverified"


def test_merged_csv_includes_statement_column(tmp_path: Path) -> None:
    output = tmp_path / "merged.csv"
    write_csv(
        _transactions(),
        output,
        include_statement=True,
        statement_names={"job-1": "sbi_statement.pdf"},
    )
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0][0] == "Statement"
    assert rows[1][0] == "sbi_statement.pdf"


def test_xlsx_export_has_expected_sheets_and_values(tmp_path: Path) -> None:
    output = tmp_path / "statement.xlsx"
    export_xlsx(_job(), _transactions(), output)
    assert output.exists() and output.stat().st_size > 1000

    workbook = load_workbook(output, data_only=True)
    try:
        assert {
            "Account Details",
            "Transactions",
            "Category Summary",
            "Monthly Summary",
        }.issubset(set(workbook.sheetnames))
        assert workbook["Categories"].sheet_state == "hidden"
        transactions = workbook["Transactions"]
        assert transactions["A1"].value == "Date"
        assert transactions["C2"].value == "SALARY CREDIT APRIL"
        assert transactions["F2"].value == 500
        assert transactions["H2"].value == "Salary/Income"
        assert transactions["A3"].value.date() == date(2024, 4, 2)

        summary = workbook["Category Summary"]
        categories = {summary.cell(row=index, column=1).value for index in range(2, 4)}
        assert {"Salary/Income", "Cash Withdrawal (ATM)"} == categories

        monthly = workbook["Monthly Summary"]
        assert monthly["A2"].value == "2024-04"
        assert monthly["B2"].value == 500
        assert monthly["C2"].value == 400
    finally:
        workbook.close()


def test_merged_xlsx_adds_statement_column(tmp_path: Path) -> None:
    output = tmp_path / "merged.xlsx"
    job = _job()
    export_xlsx(job, _transactions(), output, merged_jobs=[job])
    workbook = load_workbook(output, data_only=True)
    try:
        transactions = workbook["Transactions"]
        assert transactions["A1"].value == "Statement"
        assert transactions["A2"].value == "sbi_statement.pdf"
        account = workbook["Account Details"]
        assert account["A5"].value == "Statement"
    finally:
        workbook.close()
