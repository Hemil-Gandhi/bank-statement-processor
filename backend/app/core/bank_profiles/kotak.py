"""Kotak Mahindra Bank profile."""
from app.core.bank_profiles.base import BankProfile

PROFILE = BankProfile(
    id="kotak",
    name="Kotak Mahindra Bank",
    ifsc_prefixes=("KKBK",),
    name_keywords=("KOTAK MAHINDRA", "KOTAK BANK", "KOTAK"),
    date_formats=("DD/MM/YYYY", "DD-MM-YYYY", "DD MMM YYYY"),
    amount_style="separate",
    extra_aliases={
        "date": ("date",),
        "description": ("description",),
        "ref": ("ref no",),
        "debit": ("debit",),
        "credit": ("credit",),
        "balance": ("balance",),
    },
)
