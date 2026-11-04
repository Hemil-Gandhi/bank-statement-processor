"""Generic heuristic profile used when no bank-specific signal is found."""
from app.core.bank_profiles.base import BankProfile

PROFILE = BankProfile(
    id="generic",
    name="Generic / Unknown Bank",
    ifsc_prefixes=(),
    name_keywords=(),
    date_formats=(),
    amount_style="auto",
    extra_aliases={},
    notes="Heuristic table detection, column clustering and balance-delta inference.",
)
