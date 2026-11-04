"""Punjab National Bank profile."""
from app.core.bank_profiles.base import BankProfile

PROFILE = BankProfile(
    id="pnb",
    name="Punjab National Bank",
    ifsc_prefixes=("PUNB",),
    name_keywords=("PUNJAB NATIONAL BANK", "PNB"),
    date_formats=("DD/MM/YYYY", "DD-MM-YYYY", "DD-MMM-YYYY"),
    amount_style="separate",
    extra_aliases={
        "description": ("particulars",),
        "ref": ("chq no", "cheque no"),
        "debit": ("withdrawal",),
        "credit": ("deposit",),
        "balance": ("balance",),
    },
)
