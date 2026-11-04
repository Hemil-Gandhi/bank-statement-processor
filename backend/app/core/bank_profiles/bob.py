"""Bank of Baroda profile."""
from app.core.bank_profiles.base import BankProfile

PROFILE = BankProfile(
    id="bob",
    name="Bank of Baroda",
    ifsc_prefixes=("BARB",),
    name_keywords=("BANK OF BARODA", "BARODA"),
    date_formats=("DD/MM/YYYY", "DD-MM-YYYY", "DD-MMM-YYYY"),
    amount_style="separate",
    extra_aliases={
        "description": ("particulars",),
        "ref": ("chq no", "ref no"),
        "debit": ("debit",),
        "credit": ("credit",),
        "balance": ("balance",),
    },
)
