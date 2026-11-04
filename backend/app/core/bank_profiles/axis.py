"""Axis Bank profile."""
from app.core.bank_profiles.base import BankProfile

PROFILE = BankProfile(
    id="axis",
    name="Axis Bank",
    ifsc_prefixes=("UTIB",),
    name_keywords=("AXIS BANK", "AXIS"),
    date_formats=("DD-MM-YYYY", "DD/MM/YYYY"),
    amount_style="separate",
    extra_aliases={
        "date": ("tran date", "transaction date"),
        "description": ("particulars",),
        "ref": ("chq no", "ref no"),
        "debit": ("debit",),
        "credit": ("credit",),
        "balance": ("balance",),
    },
    notes="Axis-style Tran Date / Particulars / Debit / Credit / Balance layout.",
)
