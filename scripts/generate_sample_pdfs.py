"""Generate realistic dummy bank statements for testing.

Creates text PDFs in five distinct layouts, an image-only scanned PDF (rotation +
noise), a mixed text+scan PDF, a password-protected PDF and an empty PDF.

Usage:
    python scripts/generate_sample_pdfs.py --out samples
"""
from __future__ import annotations

import argparse
import random
import textwrap
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = A4


@dataclass
class StatementData:
    key: str
    bank_name: str
    address: str
    account_name: str
    account_number: str
    ifsc: str
    branch: str
    customer_id: str
    period_from: date
    period_to: date
    opening: Decimal
    rows: list[dict] = field(default_factory=list)
    date_format: str = "%d/%m/%Y"


def _rows(specs: list[tuple], opening: Decimal) -> list[dict]:
    balance = opening
    rows = []
    for txn_date, description, debit, credit, reference in specs:
        debit_value = Decimal(str(debit)) if debit is not None else None
        credit_value = Decimal(str(credit)) if credit is not None else None
        if debit_value is not None:
            balance -= debit_value
        if credit_value is not None:
            balance += credit_value
        rows.append(
            {
                "date": txn_date,
                "description": description,
                "debit": debit_value,
                "credit": credit_value,
                "reference": reference,
                "balance": balance,
            }
        )
    return rows


def sbi_data() -> StatementData:
    opening = Decimal("100000.00")
    specs = [
        (date(2024, 4, 1), "SALARY CREDIT APRIL 2024", None, "85000.00", "SAL202404"),
        (date(2024, 4, 2), "UPI/ZOMATO/412345678901/ZOMATO LTD/zomato@okhdfcbank/FOOD ORDER", "450.00", None, "412345678901"),
        (date(2024, 4, 3), "ATM CASH WITHDRAWAL SBI ATM AHMEDABAD", "5000.00", None, "ATM001"),
        (date(2024, 4, 5), "UPI/SWIGGY/423456789012/SWIGGY/order@ybl/DINNER", "320.00", None, "423456789012"),
        (date(2024, 4, 7), "NEFT/HDFC0000123/HOUSE RENT/LANDLORD", "18000.00", None, "NEFT7788"),
        (date(2024, 4, 10), "AMAZON PAY INDIA PRIVATE LIMITED ORDER 123-456", "1299.00", None, "AMZ123"),
        (date(2024, 4, 12), "BESCOM ELECTRICITY BILL APRIL 2024", "2100.00", None, "BES0424"),
        (date(2024, 4, 15), "IMPS/SELF TRANSFER TO SAVINGS", "10000.00", None, "IMPS9911"),
        (date(2024, 4, 18), "UPI/RAHUL SHARMA/rahul@okaxis/DINNER", "500.00", None, "RAHUL01"),
        (date(2024, 4, 20), "INT.PD:CREDIT INTEREST FOR Q4", None, "250.00", "INT0420"),
        (date(2024, 4, 25), "SMS ALERT CHARGES QUARTERLY", "25.00", None, "CHG001"),
        (date(2024, 4, 28), "UPI/IRCTC/IRCTC@okicici/TRAIN TICKET", "1450.00", None, "IRCTC01"),
        (date(2024, 4, 30), "REFUND/REVERSAL AMAZON ORDER", None, "499.00", "REF001"),
        (date(2024, 5, 1), "SALARY CREDIT MAY 2024", None, "85000.00", "SAL202405"),
        (date(2024, 5, 3), "UPI/BIGBASKET/GROCERY", "2350.00", None, "BB001"),
        (date(2024, 5, 5), "LIC OF INDIA PREMIUM", "3200.00", None, "LIC001"),
        (date(2024, 5, 7), "NACH/SIP MUTUAL FUND", "5000.00", None, "SIP001"),
        (date(2024, 5, 10), "CREDIT CARD PAYMENT HDFC BANK CARD 1234 BILL DESK PAYMENT FOR MAY 2024", "15000.00", None, "CC001"),
        (date(2024, 5, 12), "HPCL PETROL PUMP FUEL", "2500.00", None, "HP001"),
        (date(2024, 5, 15), "AIRTEL POSTPAID BILL", "799.00", None, "AIR001"),
        (date(2024, 5, 18), "APOLLO PHARMACY MEDICINES", "1250.00", None, "APL001"),
        (date(2024, 5, 20), "SCHOOL FEES APRIL JUNE", "12000.00", None, "SCH001"),
        (date(2024, 5, 22), "DONATION TO NGO RELIEF FUND", "1000.00", None, "NGO001"),
        (date(2024, 5, 25), "CHEQUE DEPOSIT CLG", None, "15000.00", "CHQ001"),
        (date(2024, 5, 28), "CASH DEPOSIT BY CASH", None, "5000.00", "CASH01"),
        (date(2024, 5, 30), "GST PAYMENT CHALLAN", "3000.00", None, "GST001"),
        (date(2024, 6, 1), "SALARY CREDIT JUNE 2024", None, "85000.00", "SAL202406"),
        (date(2024, 6, 5), "UPI/UBER/UBER@okaxis/RIDE", "380.00", None, "UBER01"),
        (date(2024, 6, 7), "BUSINESS INCOME INVOICE PAYMENT", None, "25000.00", "INV001"),
        (date(2024, 6, 10), "UPI/NETFLIX/NETFLIX@okicici/SUBSCRIPTION", "649.00", None, "NFLX01"),
        (date(2024, 6, 12), "TDS ON INTEREST", "25.00", None, "TDS001"),
        (date(2024, 6, 15), "UPI/MYNTRA/MYNTRA@okaxis/SHOPPING", "1899.00", None, "MYN001"),
        (date(2024, 6, 18), "NEFT/OUTWARD REMITTANCE", "7500.00", None, "NEFT002"),
        (date(2024, 6, 20), "UPI/SPOTIFY/SPOTIFY@okaxis", "119.00", None, "SPOT01"),
        (date(2024, 6, 25), "INT.PD:CREDIT INTEREST", None, "300.00", "INT0625"),
        (date(2024, 6, 28), "CLOSING CHARGES", "50.00", None, "CHG002"),
    ]
    return StatementData(
        key="sbi",
        bank_name="STATE BANK OF INDIA",
        address="Ahmedabad Main Branch, Bhadra, Ahmedabad - 380001",
        account_name="MR. SAMPLE CUSTOMER",
        account_number="12345678901",
        ifsc="SBIN0001234",
        branch="AHMEDABAD MAIN",
        customer_id="987654321",
        period_from=date(2024, 4, 1),
        period_to=date(2024, 6, 30),
        opening=opening,
        rows=_rows(specs, opening),
    )


def hdfc_data() -> StatementData:
    opening = Decimal("50000.00")
    specs = [
        (date(2024, 4, 1), "SALARY CREDIT - APRIL 2024", None, "75000.00", "SAL0424"),
        (date(2024, 4, 3), "UPI-ZOMATO-ORDER FOOD", "520.00", None, "ZOM001"),
        (date(2024, 4, 6), "POS 1234 AMAZON INDIA", "2499.00", None, "POS001"),
        (date(2024, 4, 10), "ATM WDL HDFC ATM", "4000.00", None, "ATM002"),
        (date(2024, 4, 15), "NEFT CR FROM CLIENT", None, "20000.00", "NEFT101"),
        (date(2024, 4, 20), "BESCOM ELECTRICITY", "1800.00", None, "BES001"),
        (date(2024, 4, 25), "SIP MUTUAL FUND", "5000.00", None, "SIP002"),
        (date(2024, 5, 1), "SALARY CREDIT - MAY 2024", None, "75000.00", "SAL0524"),
        (date(2024, 5, 5), "UPI-SWIGGY", "350.00", None, "SWG001"),
        (date(2024, 5, 9), "HDFC LIFE INSURANCE PREMIUM", "4500.00", None, "INS001"),
        (date(2024, 5, 15), "IRCTC TRAIN BOOKING", "1650.00", None, "IRCTC02"),
        (date(2024, 5, 20), "REFUND FLIPKART", None, "899.00", "REF002"),
        (date(2024, 5, 28), "CREDIT CARD PAYMENT", "12000.00", None, "CC002"),
        (date(2024, 6, 1), "SALARY CREDIT - JUNE 2024", None, "75000.00", "SAL0624"),
        (date(2024, 6, 10), "UPI-BLINKIT GROCERY", "1250.00", None, "BLK001"),
        (date(2024, 6, 18), "AIRTEL POSTPAID", "999.00", None, "AIR002"),
    ]
    return StatementData(
        key="hdfc",
        bank_name="HDFC BANK",
        address="HDFC Bank House, Senapati Bapat Marg, Mumbai - 400013",
        account_name="MS. PRIYA SHAH",
        account_number="50100123456789",
        ifsc="HDFC0000123",
        branch="SATELLITE AHMEDABAD",
        customer_id="CIF778899",
        period_from=date(2024, 4, 1),
        period_to=date(2024, 6, 30),
        opening=opening,
        rows=_rows(specs, opening),
        date_format="%d/%m/%y",
    )


def icici_data() -> StatementData:
    opening = Decimal("75000.00")
    specs = [
        (date(2024, 4, 1), "SALARY CREDIT", None, "90000.00", "SALIC1"),
        (date(2024, 4, 4), "UPI/ZOMATO/FOOD", "600.00", None, "ZOMIC1"),
        (date(2024, 4, 8), "AMAZON SHOPPING", "3200.00", None, "AMZIC1"),
        (date(2024, 4, 12), "ATM CASH WITHDRAWAL", "6000.00", None, "ATMIC1"),
        (date(2024, 4, 18), "NEFT OUTWARD RENT", "22000.00", None, "NEFIC1"),
        (date(2024, 4, 25), "INTEREST CREDIT", None, "400.00", "INTIC1"),
        (date(2024, 5, 1), "SALARY CREDIT", None, "90000.00", "SALIC2"),
        (date(2024, 5, 6), "UBER RIDE", "450.00", None, "UBERIC1"),
        (date(2024, 5, 12), "BESCOM ELECTRICITY", "2400.00", None, "BESIC1"),
        (date(2024, 5, 20), "SIP MUTUAL FUND", "8000.00", None, "SIPIC1"),
        (date(2024, 5, 28), "REFUND SWIGGY", None, "250.00", "REFIC1"),
        (date(2024, 6, 1), "SALARY CREDIT", None, "90000.00", "SALIC3"),
    ]
    return StatementData(
        key="icici",
        bank_name="ICICI BANK",
        address="ICICI Bank Tower, Bandra Kurla Complex, Mumbai - 400051",
        account_name="MR. ARJUN MEHTA",
        account_number="001234567890",
        ifsc="ICIC0000123",
        branch="BANDRA KURLA",
        customer_id="CIF445566",
        period_from=date(2024, 4, 1),
        period_to=date(2024, 6, 30),
        opening=opening,
        rows=_rows(specs, opening),
        date_format="%d-%b-%Y",
    )


def axis_data() -> StatementData:
    opening = Decimal("60000.00")
    specs = [
        (date(2024, 4, 1), "SALARY CREDIT APRIL", None, "80000.00", "AXS001"),
        (date(2024, 4, 5), "UPI ZOMATO", "480.00", None, "AXS002"),
        (date(2024, 4, 10), "POS AMAZON", "1899.00", None, "AXS003"),
        (date(2024, 4, 15), "ATM WDL", "3000.00", None, "AXS004"),
        (date(2024, 4, 20), "NEFT RENT PAYMENT", "20000.00", None, "AXS005"),
        (date(2024, 5, 1), "SALARY CREDIT MAY", None, "80000.00", "AXS006"),
        (date(2024, 5, 7), "HPCL FUEL", "2200.00", None, "AXS007"),
        (date(2024, 5, 12), "NETFLIX SUBSCRIPTION", "649.00", None, "AXS008"),
        (date(2024, 5, 20), "LIC INSURANCE", "3500.00", None, "AXS009"),
        (date(2024, 5, 28), "CASH DEPOSIT", None, "10000.00", "AXS010"),
    ]
    return StatementData(
        key="axis",
        bank_name="AXIS BANK",
        address="Axis Bank Ltd, Trishul, Law Garden, Ahmedabad - 380006",
        account_name="MRS. NEHA PATEL",
        account_number="918020012345678",
        ifsc="UTIB0000456",
        branch="LAW GARDEN",
        customer_id="CIF112233",
        period_from=date(2024, 4, 1),
        period_to=date(2024, 5, 31),
        opening=opening,
        rows=_rows(specs, opening),
        date_format="%d-%m-%Y",
    )


def generic_data() -> StatementData:
    opening = Decimal("40000.00")
    specs = [
        (date(2024, 4, 1), "SALARY CREDIT", None, "70000.00", "GEN001"),
        (date(2024, 4, 4), "UPI ZOMATO FOOD", "550.00", None, "GEN002"),
        (date(2024, 4, 9), "AMAZON SHOPPING", "1500.00", None, "GEN003"),
        (date(2024, 4, 14), "ATM CASH WITHDRAWAL", "2500.00", None, "GEN004"),
        (date(2024, 4, 19), "BESCOM ELECTRICITY", "1700.00", None, "GEN005"),
        (date(2024, 4, 25), "INTEREST CREDIT", None, "200.00", "GEN006"),
        (date(2024, 5, 1), "SALARY CREDIT", None, "70000.00", "GEN007"),
        (date(2024, 5, 6), "SIP MUTUAL FUND", "3000.00", None, "GEN008"),
    ]
    return StatementData(
        key="generic",
        bank_name="GENERIC BANK LTD",
        address="12 Somewhere Street, Ahmedabad - 380009",
        account_name="MR. SAMPLE CUSTOMER",
        account_number="999888777666",
        ifsc="GENX0000001",
        branch="GENERIC BRANCH",
        customer_id="CIF999888",
        period_from=date(2024, 4, 1),
        period_to=date(2024, 5, 31),
        opening=opening,
        rows=_rows(specs, opening),
    )


def scanned_data() -> StatementData:
    opening = Decimal("100000.00")
    specs = [
        (date(2024, 4, 1), "SALARY CREDIT APRIL 2024", None, "85000.00", "SAL202404"),
        (date(2024, 4, 2), "UPI/ZOMATO/FOOD ORDER", "450.00", None, "412345678901"),
        (date(2024, 4, 3), "ATM CASH WITHDRAWAL", "5000.00", None, "ATM001"),
        (date(2024, 4, 10), "AMAZON PAY INDIA", "1299.00", None, "AMZ123"),
        (date(2024, 4, 12), "BESCOM ELECTRICITY BILL", "2100.00", None, "BES0424"),
        (date(2024, 4, 20), "INT.PD:CREDIT INTEREST", None, "250.00", "INT0420"),
        (date(2024, 4, 25), "SMS ALERT CHARGES", "25.00", None, "CHG001"),
        (date(2024, 4, 30), "REFUND/REVERSAL AMAZON", None, "499.00", "REF001"),
    ]
    return StatementData(
        key="scanned",
        bank_name="STATE BANK OF INDIA",
        address="Ahmedabad Main Branch, Bhadra, Ahmedabad - 380001",
        account_name="MR. SAMPLE CUSTOMER",
        account_number="12345678901",
        ifsc="SBIN0001234",
        branch="AHMEDABAD MAIN",
        customer_id="987654321",
        period_from=date(2024, 4, 1),
        period_to=date(2024, 4, 30),
        opening=opening,
        rows=_rows(specs, opening),
    )


LAYOUTS = {
    "sbi": {
        "columns": [
            ("Date", 40, "left"),
            ("Value Date", 95, "left"),
            ("Description", 155, "left"),
            ("Ref No", 340, "left"),
            ("Debit", 450, "right"),
            ("Credit", 505, "right"),
            ("Balance", 559, "right"),
        ],
        "desc_x": 155,
        "desc_chars": 40,
        "date_x": 40,
        "value_x": 95,
        "ref_x": 340,
        "debit_right": 450,
        "credit_right": 505,
        "balance_right": 559,
        "vlines": [36, 90, 150, 335, 400, 458, 515, 559],
        "borders": True,
        "style": "separate",
    },
    "hdfc": {
        "columns": [
            ("Date", 40, "left"),
            ("Narration", 95, "left"),
            ("Chq/Ref No", 300, "left"),
            ("Value Dt", 370, "left"),
            ("Withdrawal Amt.", 455, "right"),
            ("Deposit Amt.", 515, "right"),
            ("Closing Balance", 559, "right"),
        ],
        "desc_x": 95,
        "desc_chars": 34,
        "date_x": 40,
        "value_x": 370,
        "ref_x": 300,
        "debit_right": 455,
        "credit_right": 515,
        "balance_right": 559,
        "vlines": [],
        "borders": False,
        "style": "separate",
    },
    "icici": {
        "columns": [
            ("S.No.", 40, "left"),
            ("Date", 75, "left"),
            ("Description", 145, "left"),
            ("Ref No", 315, "left"),
            ("Amount", 445, "right"),
            ("Dr/Cr", 470, "left"),
            ("Balance", 559, "right"),
        ],
        "desc_x": 145,
        "desc_chars": 30,
        "date_x": 75,
        "value_x": None,
        "ref_x": 315,
        "amount_right": 445,
        "drcr_x": 460,
        "balance_right": 559,
        "vlines": [36, 72, 140, 310, 400, 455, 510, 559],
        "borders": True,
        "style": "single_marker",
    },
    "axis": {
        "columns": [
            ("Tran Date", 40, "left"),
            ("Particulars", 110, "left"),
            ("Debit", 440, "right"),
            ("Credit", 500, "right"),
            ("Balance", 559, "right"),
        ],
        "desc_x": 110,
        "desc_chars": 46,
        "date_x": 40,
        "value_x": None,
        "ref_x": None,
        "debit_right": 440,
        "credit_right": 500,
        "balance_right": 559,
        "vlines": [36, 105, 380, 445, 505, 559],
        "borders": True,
        "style": "separate",
    },
    "generic": {
        "columns": [],
        "desc_x": 110,
        "desc_chars": 48,
        "date_x": 40,
        "value_x": None,
        "ref_x": None,
        "amount_right": 455,
        "balance_right": 559,
        "vlines": [],
        "borders": False,
        "style": "signed_amount",
    },
}


def _draw_header(c: canvas.Canvas, data: StatementData, layout: dict, page: int) -> None:
    c.setFont("Helvetica-Bold", 16)
    c.drawString(36, 800, data.bank_name)
    c.setFont("Helvetica", 8)
    c.drawString(36, 786, data.address)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(36, 764, "Statement of Account")
    c.setFont("Helvetica", 8)
    c.drawString(
        36,
        748,
        f"Statement Period: {data.period_from.strftime(data.date_format)} to "
        f"{data.period_to.strftime(data.date_format)}",
    )
    c.line(36, 738, 559, 738)

    c.setFont("Helvetica-Bold", 8)
    c.drawString(36, 718, "Account Name")
    c.drawString(36, 704, "Account Number")
    c.drawString(36, 690, "IFSC")
    c.drawString(36, 676, "Branch")
    c.drawString(36, 662, "Customer ID")
    c.setFont("Helvetica", 8)
    c.drawString(140, 718, data.account_name)
    c.drawString(140, 704, data.account_number)
    c.drawString(140, 690, data.ifsc)
    c.drawString(140, 676, data.branch)
    c.drawString(140, 662, data.customer_id)

    c.setFont("Helvetica-Bold", 8)
    c.drawString(360, 718, "Opening Balance")
    c.drawString(360, 704, "Closing Balance")
    c.drawString(360, 690, "Currency")
    c.setFont("Helvetica", 8)
    c.drawString(460, 718, f"{data.opening:,.2f}")
    closing = data.rows[-1]["balance"] if data.rows else data.opening
    c.drawString(460, 704, f"{closing:,.2f}")
    c.drawString(460, 690, "INR")
    c.setFont("Helvetica", 7)
    c.drawString(360, 662, f"Page {page}")

    if layout["columns"]:
        c.setFont("Helvetica-Bold", 7.5)
        for label, x, align in layout["columns"]:
            if align == "right":
                c.drawRightString(x, 620, label)
            else:
                c.drawString(x, 620, label)
        c.line(36, 612, 559, 612)


def _draw_footer(c: canvas.Canvas) -> None:
    c.setFont("Helvetica", 7)
    c.drawString(36, 28, "This is a computer generated statement. Please examine and report discrepancies.")
    c.drawRightString(559, 28, "Page")


def _draw_frame(c: canvas.Canvas, layout: dict, bottom_y: float) -> None:
    if layout["borders"]:
        for x in layout["vlines"]:
            c.line(x, max(bottom_y, 40), x, 612)
        c.line(36, max(bottom_y, 40), 559, max(bottom_y, 40))


def _draw_row(c: canvas.Canvas, data: StatementData, layout: dict, row: dict, y: float) -> float:
    style = layout["style"]
    c.setFont("Helvetica", 7.5)
    c.drawString(layout["date_x"], y, row["date"].strftime(data.date_format))
    if layout["value_x"]:
        c.drawString(layout["value_x"], y, row["date"].strftime(data.date_format))
    if layout["ref_x"]:
        c.drawString(layout["ref_x"], y, row["reference"] or "")

    lines = textwrap.wrap(
        row["description"],
        width=layout["desc_chars"],
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]
    for index, line in enumerate(lines):
        c.drawString(layout["desc_x"], y - index * 9, line)

    if style == "separate":
        if row["debit"] is not None:
            c.drawRightString(layout["debit_right"], y, f"{row['debit']:,.2f}")
        if row["credit"] is not None:
            c.drawRightString(layout["credit_right"], y, f"{row['credit']:,.2f}")
    elif style == "single_marker":
        amount = row["debit"] if row["debit"] is not None else row["credit"]
        marker = "Dr" if row["debit"] is not None else "Cr"
        if amount is not None:
            c.drawRightString(layout["amount_right"], y, f"{amount:,.2f}")
        c.drawString(layout["drcr_x"], y, marker)
    else:  # signed_amount
        amount = None
        if row["debit"] is not None:
            amount = -row["debit"]
        elif row["credit"] is not None:
            amount = row["credit"]
        if amount is not None:
            c.drawRightString(layout["amount_right"], y, f"{amount:,.2f}")

    c.drawRightString(layout["balance_right"], y, f"{row['balance']:,.2f}")
    return max(18, 9 * len(lines) + 6)


def draw_statement(data: StatementData, output: Path, *, force_split: int | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    layout = LAYOUTS["sbi" if data.key == "scanned" else data.key]
    c = canvas.Canvas(str(output), pagesize=A4)
    c.setTitle(f"{data.bank_name} Statement")
    page = 0
    row_start = 598

    def new_page() -> float:
        nonlocal page
        if page:
            _draw_footer(c)
            c.showPage()
        page += 1
        _draw_header(c, data, layout, page)
        return row_start

    y = new_page()
    for index, row in enumerate(data.rows):
        lines = textwrap.wrap(
            row["description"],
            width=layout["desc_chars"],
            break_long_words=True,
            break_on_hyphens=False,
        ) or [""]
        row_height = max(18, 9 * len(lines) + 6)
        if force_split is not None and index == force_split and len(lines) >= 2:
            # Draw the first line + amounts on this page, then continue the
            # narration at the top of the next page without a date.
            c.setFont("Helvetica", 7.5)
            c.drawString(layout["date_x"], y, row["date"].strftime(data.date_format))
            if layout["value_x"]:
                c.drawString(layout["value_x"], y, row["date"].strftime(data.date_format))
            if layout["ref_x"]:
                c.drawString(layout["ref_x"], y, row["reference"] or "")
            c.drawString(layout["desc_x"], y, lines[0])
            if layout["style"] == "separate":
                if row["debit"] is not None:
                    c.drawRightString(layout["debit_right"], y, f"{row['debit']:,.2f}")
                if row["credit"] is not None:
                    c.drawRightString(layout["credit_right"], y, f"{row['credit']:,.2f}")
            c.drawRightString(layout["balance_right"], y, f"{row['balance']:,.2f}")
            _draw_frame(c, layout, y - 10)
            y = new_page()
            c.setFont("Helvetica", 7.5)
            c.drawString(layout["desc_x"], y, " ".join(lines[1:]))
            y -= 14
            continue
        if y - row_height < 55:
            _draw_frame(c, layout, y)
            y = new_page()
        y -= _draw_row(c, data, layout, row, y)
    _draw_frame(c, layout, y)
    _draw_footer(c)
    c.showPage()
    c.save()


def make_scanned(source: Path, output: Path, *, rotation: float = 1.3) -> None:
    doc = fitz.open(source)
    page = doc[0]
    pix = page.get_pixmap(dpi=220)
    png = output.with_suffix(".png")
    pix.save(str(png))
    doc.close()

    image = Image.open(png).convert("RGB")
    image = image.rotate(rotation, expand=True, fillcolor=(255, 255, 255))
    array = np.array(image).astype(np.int16)
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 4, array.shape).astype(np.int16)
    array = np.clip(array + noise, 0, 255).astype(np.uint8)
    scanned = Image.fromarray(array)
    scanned.save(png)

    out = fitz.open()
    page = out.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_image(page.rect, filename=str(png))
    out.save(output)
    out.close()
    png.unlink(missing_ok=True)


def make_mixed(text_pdf: Path, output: Path) -> None:
    """Keep page 1 as text and turn page 2 of the same PDF into an image page."""
    source = fitz.open(text_pdf)
    if source.page_count < 2:
        source.close()
        raise ValueError("mixed fixture needs a source PDF with at least two pages")
    page = source[1]
    pix = page.get_pixmap(dpi=220)
    png = output.with_suffix(".page2.png")
    pix.save(str(png))
    source.close()

    image = Image.open(png).convert("RGB")
    image = image.rotate(0.7, expand=True, fillcolor=(255, 255, 255))
    array = np.array(image).astype(np.int16)
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 3, array.shape).astype(np.int16)
    array = np.clip(array + noise, 0, 255).astype(np.uint8)
    Image.fromarray(array).save(png)

    out = fitz.open()
    first = fitz.open(text_pdf)
    out.insert_pdf(first, from_page=0, to_page=0)
    first.close()
    image_page = out.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    image_page.insert_image(image_page.rect, filename=str(png))
    out.save(output)
    out.close()
    png.unlink(missing_ok=True)


def make_password_protected(source: Path, output: Path, password: str = "demo123") -> None:
    doc = fitz.open(source)
    doc.save(
        output,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-demo",
        user_pw=password,
    )
    doc.close()


def make_empty(output: Path) -> None:
    doc = fitz.open()
    doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    doc.save(output)
    doc.close()


def generate_all(output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    produced: dict[str, Path] = {}

    statements = {
        "sbi": (sbi_data(), 17),
        "hdfc": (hdfc_data(), None),
        "icici": (icici_data(), None),
        "axis": (axis_data(), None),
        "generic": (generic_data(), None),
    }
    for key, (data, split) in statements.items():
        path = output / f"{key}_statement.pdf"
        draw_statement(data, path, force_split=split)
        produced[key] = path

    scan_source = output / "_scan_source.pdf"
    draw_statement(scanned_data(), scan_source)
    scanned = output / "scanned_statement.pdf"
    make_scanned(scan_source, scanned)
    scan_source.unlink(missing_ok=True)
    produced["scanned"] = scanned

    mixed = output / "mixed_statement.pdf"
    # Page 1 stays a text layer, page 2 is rendered as a scan of the *same*
    # statement so the combined fixture remains internally consistent and
    # exercises per-page auto-detection without artificial duplicates.
    make_mixed(produced["sbi"], mixed)
    produced["mixed"] = mixed

    protected = output / "password_protected.pdf"
    make_password_protected(produced["sbi"], protected, "demo123")
    produced["password"] = protected

    empty = output / "empty.pdf"
    make_empty(empty)
    produced["empty"] = empty

    return produced


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate realistic sample bank statement PDFs.")
    parser.add_argument("--out", default="samples", help="Output directory")
    args = parser.parse_args()
    random.seed(42)
    produced = generate_all(args.out)
    for key, path in produced.items():
        print(f"{key:20s} -> {path}")


if __name__ == "__main__":
    main()
