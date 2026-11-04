"""Generate a realistic, reproducible training set for the classical classifier.

No LLM or external service is used. The script combines:
  * hand-written bank-narration examples for every taxonomy category, and
  * synthetic variations with realistic channels, references, UPI handles,
    dates, merchants and amounts.

Run from the project root:
    python scripts/generate_training_data.py
Then train:
    cd backend && python -m app.classification.train
"""
from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.classification.taxonomy import CATEGORIES  # noqa: E402

OUTPUT = BACKEND / "data" / "training" / "transactions_labeled.csv"

RNG = random.Random(20240501)

MONTHS = [
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
]
CITIES = ["MUMBAI", "DELHI", "BENGALURU", "AHMEDABAD", "PUNE", "CHENNAI", "HYDERABAD", "KOLKATA"]
PEOPLE = [
    "RAHUL SHARMA",
    "PRIYA SHAH",
    "AMIT PATEL",
    "NEHA MEHTA",
    "VIKRAM SINGH",
    "ANJALI GUPTA",
    "ROHAN DESAI",
    "KAVITA JOSHI",
    "ARJUN NAIR",
    "SANA KHAN",
]
UPI_HANDLES = ["okaxis", "okhdfcbank", "okicici", "oksbi", "ybl", "paytm", "ibl", "axl"]
BANKS = ["HDFC", "ICICI", "SBI", "AXIS", "KOTAK", "PNB", "BOB"]
CHANNELS = ["UPI", "NEFT", "IMPS", "RTGS", "POS", "ATM", "NACH", "ECS", "CHQ", "MB", "IB"]


def _ref(prefix: str = "") -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    body = "".join(RNG.choice(alphabet) for _ in range(10))
    return f"{prefix}{body}" if prefix else body


def _vpa(name: str | None = None) -> str:
    name = (name or RNG.choice(PEOPLE)).lower().replace(" ", ".")
    return f"{name}@{RNG.choice(UPI_HANDLES)}"


def _date_text() -> str:
    start = date(2024, 1, 1)
    value = start + timedelta(days=RNG.randint(0, 364))
    return value.strftime(RNG.choice(["%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"]))


def _amount_text() -> str:
    value = Decimal(RNG.choice([49, 99, 149, 250, 499, 750, 1200, 2499, 5000, 12000, 25000]))
    value += Decimal(RNG.randint(0, 99)) / 100
    return f"{value:,.2f}"


# Hand-written, real-looking narrations. These are deliberately messy and cover
# the channel/format variants seen in Indian bank statements.
HAND_LABELED: dict[str, list[str]] = {
    "Salary/Income": [
        "SALARY CREDIT APRIL 2024 EMPLOYER PVT LTD",
        "SAL CR 04/2024 ACME TECHNOLOGIES",
    ],
    "Business Income": [
        "CLIENT PAYMENT INV-2024-118 RAZORPAY SETTLEMENT",
        "MERCHANT SETTLEMENT CR PAYU PAYMENTS",
    ],
    "Interest Earned": [
        "INT.PD:CREDIT INTEREST FOR Q4 2023-24",
        "SB INTEREST CREDIT 31/03/2024",
    ],
    "Refund/Reversal": [
        "REFUND FOR FAILED UPI TXN AMAZON",
        "REVERSAL OF ATM WDL CHARGES",
    ],
    "Cash Withdrawal (ATM)": [
        "ATM CASH WITHDRAWAL SBI ATM AHMEDABAD",
        "NFS ATM WDL HDFC BANK MUMBAI",
    ],
    "Cash Deposit": [
        "CASH DEPOSIT BY CASH CDM AHMEDABAD",
        "CASH ACCEPTED AT BRANCH COUNTER",
    ],
    "Transfer In (Self/Others)": [
        "NEFT CR FROM CLIENT ACME INDUSTRIES",
        "IMPS CR FROM SELF SAVINGS ACCOUNT",
    ],
    "Transfer Out": [
        "NEFT DR TO LANDLORD HOUSE RENT",
        "IMPS OUTWARD REMITTANCE TO SELF",
    ],
    "UPI Payment": [
        "UPI/RAHUL SHARMA/rahul.sharma@okaxis/DINNER",
        "BHIM UPI PAYMENT TO AMIT PATEL",
    ],
    "Food & Dining": [
        "UPI/ZOMATO/412345678901/ZOMATO LTD/zomato@okhdfcbank/FOOD ORDER",
        "POS 1234 SWIGGY BANGALORE",
    ],
    "Groceries": [
        "UPI/BIGBASKET/GROCERY ORDER",
        "POS DMART AHMEDABAD GROCERY",
    ],
    "Shopping/E-commerce": [
        "AMAZON PAY INDIA PRIVATE LIMITED ORDER 123-456",
        "POS 5678 MYNTRA FASHION",
    ],
    "Travel & Transport": [
        "UPI/IRCTC/IRCTC@okicici/TRAIN TICKET",
        "UBER INDIA RIDE PAYMENT",
    ],
    "Fuel": [
        "HPCL PETROL PUMP FUEL",
        "POS BPCL FUEL STATION",
    ],
    "Utilities (Electricity/Water/Gas)": [
        "BESCOM ELECTRICITY BILL APRIL 2024",
        "TORRENT POWER WATER BILL",
    ],
    "Mobile/DTH/Internet": [
        "AIRTEL POSTPAID BILL PAYMENT",
        "TATA PLAY DTH RECHARGE",
    ],
    "Rent": [
        "NEFT/HDFC0000123/HOUSE RENT/LANDLORD",
        "RENT PAYMENT TO LANDLORD",
    ],
    "EMI/Loan Repayment": [
        "NACH/HDFC LTD/HOME LOAN EMI",
        "BAJAJ FINANCE EMI REPAYMENT",
    ],
    "Credit Card Payment": [
        "CREDIT CARD PAYMENT HDFC BANK CARD 1234",
        "BILLDESK CC PAYMENT AXIS CARD",
    ],
    "Insurance": [
        "LIC OF INDIA PREMIUM",
        "HDFC LIFE INSURANCE PREMIUM",
    ],
    "Investments (MF/SIP/Stocks)": [
        "NACH/SIP MUTUAL FUND",
        "ZERODHA BROKING STOCKS PURCHASE",
    ],
    "Taxes (GST/Income Tax)": [
        "GST PAYMENT CHALLAN",
        "ADVANCE INCOME TAX PAYMENT",
    ],
    "Bank Charges & Fees": [
        "SMS ALERT CHARGES QUARTERLY",
        "GST ON BANK CHARGES",
    ],
    "Healthcare": [
        "APOLLO PHARMACY MEDICINES",
        "FORTIS HOSPITAL CONSULTATION",
    ],
    "Education": [
        "SCHOOL FEES APRIL JUNE",
        "COURSERA ONLINE COURSE",
    ],
    "Entertainment/Subscriptions": [
        "NETFLIX SUBSCRIPTION",
        "BOOKMYSHOW MOVIE TICKETS",
    ],
    "Donations": [
        "DONATION TO NGO RELIEF FUND",
        "PM CARES DONATION",
    ],
    "Cheque (Deposit/Issue)": [
        "CHEQUE DEPOSIT CLG",
        "CHQ PAID TO SUPPLIER",
    ],
}


TEMPLATES: dict[str, tuple[str, list[str]]] = {
    "Salary/Income": (
        "credit",
        [
            "SALARY CREDIT {month} 2024",
            "SAL CR {month} ACME TECHNOLOGIES",
            "MONTHLY SALARY PAYROLL {month}",
            "PAYROLL CREDIT {month} 2024",
            "WAGES {month} 2024",
            "STIPEND {month} 2024",
            "SALARY ARREARS {month} 2024",
            "SALARY PAYMENT FROM EMPLOYER",
        ],
    ),
    "Business Income": (
        "credit",
        [
            "BUSINESS INCOME INVOICE PAYMENT {ref}",
            "CLIENT PAYMENT INVOICE {ref}",
            "MERCHANT SETTLEMENT RAZORPAY {ref}",
            "PAYMENT RECEIVED FROM CLIENT {ref}",
            "COLLECTION SETTLEMENT PAYU {ref}",
            "CASHFREE SETTLEMENT CREDIT {ref}",
            "INVOICE PAYMENT FROM ACME INDUSTRIES",
            "SETTLEMENT CREDIT INSTAMOJO {ref}",
        ],
    ),
    "Interest Earned": (
        "credit",
        [
            "INT.PD:CREDIT INTEREST FOR QTR",
            "INTEREST CREDIT {month} 2024",
            "SB INTEREST CREDIT {ref}",
            "FD INTEREST CREDIT {ref}",
            "INT ACCRUED ON SAVINGS",
            "INTEREST PAID ON DEPOSIT",
        ],
    ),
    "Refund/Reversal": (
        "credit",
        [
            "REFUND FOR FAILED UPI TXN",
            "REVERSAL OF ATM CHARGES",
            "CHARGEBACK CREDIT {ref}",
            "CASHBACK CREDIT {ref}",
            "REV-UPI TRANSACTION {ref}",
            "MONEY BACK FOR RETURNED ORDER",
            "FAILED TRANSACTION REVERSAL",
        ],
    ),
    "Cash Withdrawal (ATM)": (
        "debit",
        [
            "ATM CASH WITHDRAWAL {city}",
            "ATM WDL {city}",
            "NFS CASH WITHDRAWAL {city}",
            "ATM-CASH WDL {city}",
            "CASH WDL ATM {city}",
        ],
    ),
    "Cash Deposit": (
        "credit",
        [
            "CASH DEPOSIT AT BRANCH {city}",
            "CASH DEP CDM {city}",
            "CDM CASH ACCEPTED {city}",
            "BY CASH DEPOSIT",
            "CASH RECEIVED AT COUNTER {city}",
        ],
    ),
    "Transfer In (Self/Others)": (
        "credit",
        [
            "NEFT CR FROM CLIENT {ref}",
            "IMPS CR FROM {person}",
            "RTGS CR INWARD REMITTANCE {ref}",
            "INWARD REMITTANCE FROM {person}",
            "SELF TRANSFER CR FROM SAVINGS",
            "FROM SELF ACCOUNT {ref}",
            "CREDIT TRANSFER FROM {person}",
        ],
    ),
    "Transfer Out": (
        "debit",
        [
            "NEFT DR TO {person} {ref}",
            "IMPS DR TO {person}",
            "RTGS DR OUTWARD REMITTANCE {ref}",
            "OUTWARD REMITTANCE TO {person}",
            "SELF TRANSFER TO SAVINGS",
            "TO SELF ACCOUNT {ref}",
            "DEBIT TRANSFER TO {person}",
        ],
    ),
    "UPI Payment": (
        "debit",
        [
            "UPI/{person}/{vpa}/PAYMENT",
            "UPI PAYMENT TO {person}",
            "BHIM UPI TO {person}",
            "GPAY UPI PAYMENT {person}",
            "PHONEPE UPI TO {person}",
            "PAYTM UPI PAYMENT {person}",
            "UPI/{person}/{vpa}/SEND MONEY",
        ],
    ),
    "Food & Dining": (
        "debit",
        [
            "UPI/ZOMATO/{ref}/ZOMATO LTD/{vpa}/FOOD ORDER",
            "SWIGGY ORDER {ref}",
            "DOMINOS PIZZA {city}",
            "MCDONALD RESTAURANT {city}",
            "KFC {city}",
            "PIZZA HUT {city}",
            "CAFE COFFEE DAY {city}",
            "RESTAURANT BILL {city}",
            "BIRYANI HOUSE {city}",
            "STARBUCKS {city}",
        ],
    ),
    "Groceries": (
        "debit",
        [
            "BIGBASKET GROCERY ORDER",
            "BLINKIT GROCERY {city}",
            "ZEPTO GROCERY {city}",
            "DMART GROCERY STORE {city}",
            "RELIANCE FRESH SUPERMARKET",
            "MORE SUPERMARKET GROCERY",
            "KIRANA STORE {city}",
            "INSTAMART GROCERY",
            "JIO MART GROCERY",
        ],
    ),
    "Shopping/E-commerce": (
        "debit",
        [
            "AMAZON SHOPPING {ref}",
            "FLIPKART ORDER {ref}",
            "MYNTRA FASHION {ref}",
            "MEESHO SHOPPING {ref}",
            "AJIO FASHION {ref}",
            "SNAPDEAL ORDER {ref}",
            "NYKAA BEAUTY {ref}",
            "CROMA ELECTRONICS {city}",
            "DECATHLON SPORTS {city}",
        ],
    ),
    "Travel & Transport": (
        "debit",
        [
            "UBER RIDE {city}",
            "OLA CAB {city}",
            "RAPIDO BIKE RIDE {city}",
            "IRCTC TRAIN TICKET {ref}",
            "MAKEMYTRIP FLIGHT BOOKING",
            "REDBUS BUS TICKET {ref}",
            "INDIGO AIRLINES {ref}",
            "METRO RAIL RECHARGE {city}",
            "OYO HOTEL BOOKING {city}",
        ],
    ),
    "Fuel": (
        "debit",
        [
            "HPCL PETROL PUMP {city}",
            "BPCL FUEL STATION {city}",
            "IOCL PETROL {city}",
            "PETROL PUMP FUEL {city}",
            "DIESEL FUEL {city}",
            "SHELL FUEL {city}",
            "NAYARA ENERGY FUEL {city}",
            "CNG FUEL STATION {city}",
        ],
    ),
    "Utilities (Electricity/Water/Gas)": (
        "debit",
        [
            "BESCOM ELECTRICITY BILL {month}",
            "TORRENT POWER ELECTRICITY",
            "ELECTRICITY BILL PAYMENT {city}",
            "WATER BILL MUNICIPAL {city}",
            "GAS BILL INDANE {city}",
            "TATA POWER ELECTRICITY",
            "MSEB POWER BILL {city}",
            "HP GAS CYLINDER BOOKING",
        ],
    ),
    "Mobile/DTH/Internet": (
        "debit",
        [
            "AIRTEL POSTPAID BILL",
            "JIO MOBILE RECHARGE",
            "VODAFONE POSTPAID BILL",
            "BSNL BROADBAND BILL",
            "TATA PLAY DTH RECHARGE",
            "ACT FIBERNET BROADBAND",
            "DISH TV DTH RECHARGE",
            "MOBILE BILL PAYMENT {city}",
            "INTERNET BROADBAND BILL",
        ],
    ),
    "Rent": (
        "debit",
        [
            "HOUSE RENT PAYMENT {month}",
            "RENT PAYMENT TO LANDLORD",
            "LANDLORD RENT {city}",
            "NOBROKER RENT PAYMENT",
            "LEASE RENT PAYMENT",
            "RENTAL PAYMENT {city}",
            "NEFT/HDFC0000123/HOUSE RENT/LANDLORD",
        ],
    ),
    "EMI/Loan Repayment": (
        "debit",
        [
            "LOAN EMI PAYMENT {ref}",
            "HOME LOAN EMI {ref}",
            "CAR LOAN EMI {ref}",
            "PERSONAL LOAN REPAYMENT",
            "BAJAJ FINANCE EMI {ref}",
            "NACH LOAN REPAYMENT {ref}",
            "EMI DEBIT {ref}",
            "HDFC LTD HOME LOAN EMI",
        ],
    ),
    "Credit Card Payment": (
        "debit",
        [
            "CREDIT CARD PAYMENT HDFC CARD",
            "CC PAYMENT AXIS CARD",
            "CARD PAYMENT BILLDESK",
            "CRED CREDIT CARD PAYMENT",
            "AMEX CARD PAYMENT",
            "HDFC CARD PAYMENT {ref}",
            "ICICI CARD PAYMENT {ref}",
            "PAYMENT TO CARD {ref}",
        ],
    ),
    "Insurance": (
        "debit",
        [
            "LIC PREMIUM PAYMENT",
            "INSURANCE PREMIUM {ref}",
            "HDFC LIFE INSURANCE",
            "ICICI PRU POLICY PREMIUM",
            "STAR HEALTH INSURANCE",
            "POLICY PREMIUM PAYMENT",
            "SBI LIFE INSURANCE PREMIUM",
            "MAX LIFE INSURANCE",
        ],
    ),
    "Investments (MF/SIP/Stocks)": (
        "debit",
        [
            "SIP MUTUAL FUND {ref}",
            "MF PURCHASE {ref}",
            "ZERODHA STOCKS PURCHASE",
            "GROWW SIP INVESTMENT",
            "NPS CONTRIBUTION {ref}",
            "PPF DEPOSIT {ref}",
            "ELSS MUTUAL FUND SIP",
            "STOCKS BROKING {ref}",
            "DEMAT ACCOUNT PURCHASE",
        ],
    ),
    "Taxes (GST/Income Tax)": (
        "debit",
        [
            "GST PAYMENT CHALLAN {ref}",
            "INCOME TAX PAYMENT {ref}",
            "ADVANCE TAX PAYMENT",
            "PROPERTY TAX {city}",
            "TDS PAYMENT {ref}",
            "TAX PAYMENT CHALLAN",
            "SALES TAX PAYMENT",
            "ITR CHALLAN PAYMENT",
        ],
    ),
    "Bank Charges & Fees": (
        "debit",
        [
            "SMS ALERT CHARGES QUARTERLY",
            "ANNUAL FEE DEBIT",
            "MIN BAL CHARGES",
            "GST ON BANK CHARGES",
            "SERVICE CHARGE {ref}",
            "NEFT CHARGE {ref}",
            "AMC DEBIT CARD FEE",
            "PROCESSING FEE {ref}",
            "PENALTY CHARGES",
        ],
    ),
    "Healthcare": (
        "debit",
        [
            "APOLLO PHARMACY {city}",
            "FORTIS HOSPITAL {city}",
            "MEDPLUS PHARMACY {city}",
            "1MG MEDICINES",
            "NETMEDS PHARMACY",
            "DOCTOR CONSULTATION {city}",
            "DIAGNOSTIC LAB {city}",
            "DENTAL CLINIC {city}",
            "MAX HOSPITAL MEDICAL",
        ],
    ),
    "Education": (
        "debit",
        [
            "SCHOOL FEES {month}",
            "COLLEGE TUITION FEES",
            "COURSERA ONLINE COURSE",
            "UDEMY COURSE PURCHASE",
            "BYJU LEARNING APP",
            "UNACADEMY SUBSCRIPTION",
            "EXAM FEES {ref}",
            "UNIVERSITY FEES {city}",
            "HOSTEL FEES {city}",
        ],
    ),
    "Entertainment/Subscriptions": (
        "debit",
        [
            "NETFLIX SUBSCRIPTION",
            "SPOTIFY PREMIUM",
            "HOTSTAR SUBSCRIPTION",
            "PRIME VIDEO SUBSCRIPTION",
            "BOOKMYSHOW MOVIE TICKETS",
            "PVR CINEMA {city}",
            "YOUTUBE PREMIUM",
            "SONY LIV SUBSCRIPTION",
            "GAMING STEAM PURCHASE",
        ],
    ),
    "Donations": (
        "debit",
        [
            "DONATION TO NGO {ref}",
            "CHARITY TRUST DONATION",
            "TEMPLE DONATION {city}",
            "PM CARES DONATION",
            "RELIEF FUND DONATION",
            "CHURCH DONATION",
            "MOSQUE DONATION",
            "GURUDWARA DONATION",
        ],
    ),
    "Cheque (Deposit/Issue)": (
        "debit",
        [
            "CHEQUE DEPOSIT CLG {ref}",
            "CHQ PAID TO SUPPLIER",
            "CLEARING CHQ {ref}",
            "ISSUED CHEQUE {ref}",
            "CHQ DEP {ref}",
            "CHEQUE CLEARING {ref}",
        ],
    ),
}


def _channel_wrap(description: str, category: str) -> tuple[str, str]:
    """Add a realistic channel prefix/suffix and return (description, channel)."""
    channel = RNG.choice(CHANNELS)
    ref = _ref()
    if channel == "UPI" and "UPI" not in description.upper():
        description = f"UPI/{ref}/{description}/{_vpa()}"
    elif channel in {"NEFT", "IMPS", "RTGS"} and channel not in description.upper():
        description = f"{channel}/{_ref()}/{description}"
    elif channel == "POS" and "POS" not in description.upper():
        description = f"POS {RNG.randint(1000, 9999)} {description}"
    elif channel == "NACH" and "NACH" not in description.upper():
        description = f"NACH/{_ref()}/{description}"
    elif channel == "CHQ" and "CHQ" not in description.upper() and "CHEQUE" not in description.upper():
        description = f"CHQ/{_ref()}/{description}"
    return description, channel


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    categories = [category for category in CATEGORIES if category != "Uncategorized"]

    for category in categories:
        direction, templates = TEMPLATES[category]

        # Hand-labeled examples first (2 per category).
        for text in HAND_LABELED.get(category, []):
            rows.append(
                {
                    "description": text,
                    "category": category,
                    "direction": direction,
                    "amount": _amount_text(),
                    "channel": "",
                    "source": "hand_labeled",
                }
            )

        # 60 synthetic variations per category, cycling through templates.
        for index in range(60):
            template = templates[index % len(templates)]
            description = template.format(
                month=RNG.choice(MONTHS),
                city=RNG.choice(CITIES),
                person=RNG.choice(PEOPLE),
                ref=_ref(),
                vpa=_vpa(),
            )
            description, channel = _channel_wrap(description, category)
            if RNG.random() < 0.35:
                description = f"{_date_text()} {description}"
            if RNG.random() < 0.30:
                description = f"{description} REF {_ref()}"
            if RNG.random() < 0.25:
                description = f"{description} {_amount_text()}"
            rows.append(
                {
                    "description": description,
                    "category": category,
                    "direction": direction,
                    "amount": _amount_text(),
                    "channel": channel,
                    "source": "synthetic",
                }
            )
    RNG.shuffle(rows)
    return rows


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    with open(OUTPUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["description", "category", "direction", "amount", "channel", "source"],
        )
        writer.writeheader()
        writer.writerows(rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    print(f"wrote {len(rows)} rows to {OUTPUT}")
    print(f"categories: {len(counts)}; min={min(counts.values())}; max={max(counts.values())}")


if __name__ == "__main__":
    main()
