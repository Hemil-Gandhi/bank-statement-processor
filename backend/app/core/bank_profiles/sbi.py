"""State Bank of India profile."""
from app.core.bank_profiles.base import BankProfile

PROFILE = BankProfile(
    id="sbi",
    name="State Bank of India",
    ifsc_prefixes=("SBIN",),
    name_keywords=("STATE BANK OF INDIA", "SBI", "S.B.I"),
    date_formats=("DD/MM/YYYY", "DD-MM-YYYY", "DD Mon YYYY"),
    amount_style="separate",
    extra_aliases={
        "date": ("txn date", "value date"),
        "description": ("narration",),
        "ref": ("chq/ref no", "ref no"),
        "debit": ("withdrawal", "debit"),
        "credit": ("deposit", "credit"),
        "balance": ("balance",),
    },
    notes="Classic SBI statement with separate withdrawal/deposit columns.",
)
