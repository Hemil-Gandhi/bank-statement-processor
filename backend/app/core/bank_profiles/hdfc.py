"""HDFC Bank profile."""
from app.core.bank_profiles.base import BankProfile

PROFILE = BankProfile(
    id="hdfc",
    name="HDFC Bank",
    ifsc_prefixes=("HDFC",),
    name_keywords=("HDFC BANK", "HDFC LTD"),
    date_formats=("DD/MM/YY", "DD-MM-YY", "DD/MM/YYYY"),
    amount_style="separate",
    extra_aliases={
        "date": ("date",),
        "value_date": ("value dt",),
        "description": ("narration",),
        "ref": ("chq/ref no", "chq no"),
        "debit": ("withdrawal amt", "withdrawal amount"),
        "credit": ("deposit amt", "deposit amount"),
        "balance": ("closing balance",),
    },
    notes="HDFC-style statement with Withdrawal Amt. / Deposit Amt. / Closing Balance.",
)
