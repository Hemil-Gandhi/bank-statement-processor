"""ICICI Bank profile (single Amount column with a Dr/Cr marker)."""
from app.core.bank_profiles.base import BankProfile

PROFILE = BankProfile(
    id="icici",
    name="ICICI Bank",
    ifsc_prefixes=("ICIC",),
    name_keywords=("ICICI BANK", "ICICI"),
    date_formats=("DD-MM-YYYY", "DD/MM/YYYY", "DD Mon YYYY"),
    amount_style="single_marker",
    extra_aliases={
        "serial": ("s no", "sr no"),
        "date": ("date",),
        "description": ("description", "transaction remarks"),
        "ref": ("ref no", "cheque no"),
        "amount": ("amount",),
        "drcr": ("dr/cr", "dr cr"),
        "balance": ("balance",),
    },
    notes="ICICI-style single amount + Dr/Cr indicator layout.",
)
