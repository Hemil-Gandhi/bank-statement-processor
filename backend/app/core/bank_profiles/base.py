"""Data-driven bank profile definitions.

Adding a bank means adding a profile dict/module with aliases and signals — no new
table-reconstruction algorithm is required.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Canonical column -> header phrases. Longest phrases are matched first.
COMMON_ALIASES: dict[str, tuple[str, ...]] = {
    "date": (
        "transaction date",
        "posting date",
        "post date",
        "txn date",
        "tran date",
        "book date",
        "date",
    ),
    "value_date": (
        "value date",
        "value dt",
        "val date",
        "val dt",
    ),
    "description": (
        "transaction description",
        "transaction details",
        "transaction remarks",
        "narration",
        "particulars",
        "description",
        "details",
        "remarks",
        "narrative",
    ),
    "ref": (
        "chq/ref no",
        "cheque ref no",
        "instrument no",
        "instrument id",
        "reference no",
        "cheque no",
        "chq no",
        "ref no",
        "reference",
        "utr no",
        "ref",
    ),
    "debit": (
        "withdrawal amount",
        "withdrawal amt",
        "debit amount",
        "amount debit",
        "withdrawals",
        "withdrawal",
        "payments",
        "paid out",
        "debit",
        "dr",
    ),
    "credit": (
        "deposit amount",
        "deposit amt",
        "credit amount",
        "amount credit",
        "deposits",
        "deposit",
        "receipts",
        "paid in",
        "credit",
        "cr",
    ),
    "balance": (
        "closing balance",
        "running balance",
        "balance amount",
        "balance",
        "bal",
    ),
    "amount": (
        "transaction amount",
        "amount inr",
        "amount",
        "amt",
    ),
    "drcr": (
        "dr/cr",
        "cr/dr",
        "dr cr",
        "cr dr",
        "txn type",
        "type",
    ),
    "serial": (
        "serial no",
        "sr no",
        "sl no",
        "s no",
        "no",
        "#",
    ),
}

SUMMARY_PATTERNS: tuple[str, ...] = (
    r"^opening balance",
    r"^closing balance",
    r"^balance b/?f",
    r"^balance c/?f",
    r"^brought forward",
    r"^carried forward",
    r"^grand total",
    r"^total\b",
    r"^debit total",
    r"^credit total",
    r"^statement summary",
    r"^summary\b",
)

FOOTER_PATTERNS: tuple[str, ...] = (
    r"^page\s+\d+\s*(of\s+\d+)?$",
    r"^page\s+\d+\s*/\s*\d+$",
    r"^generated on",
    r"^this is a (?:computer|system) generated",
    r"^this is an? electronically generated",
    r"^registered office",
    r"^customer care",
    r"^please examine",
    r"^subject to",
    r"^for any queries",
    r"^end of statement",
    r"^continued",
    r"^\(?contd",
    r"^statement of account$",
)


@dataclass(frozen=True, slots=True)
class BankProfile:
    id: str
    name: str
    ifsc_prefixes: tuple[str, ...] = ()
    name_keywords: tuple[str, ...] = ()
    date_formats: tuple[str, ...] = ()
    amount_style: str = "auto"  # auto | separate | single_marker
    extra_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    summary_patterns: tuple[str, ...] = SUMMARY_PATTERNS
    footer_patterns: tuple[str, ...] = FOOTER_PATTERNS
    reverse_chronological: bool | None = None
    notes: str = ""

    def aliases(self) -> dict[str, tuple[str, ...]]:
        merged = {key: list(value) for key, value in COMMON_ALIASES.items()}
        for key, values in self.extra_aliases.items():
            merged.setdefault(key, [])
            for value in values:
                if value not in merged[key]:
                    merged[key].append(value)
        return {key: tuple(values) for key, values in merged.items()}

    def alias_entries(self) -> list[tuple[str, str, int]]:
        entries: list[tuple[str, str, int]] = []
        for canonical, phrases in self.aliases().items():
            for phrase in phrases:
                normalized = " ".join(phrase.replace("/", " ").replace("-", " ").lower().split())
                entries.append((normalized, canonical, len(normalized.split())))
        entries.sort(key=lambda item: (-item[2], -len(item[0])))
        return entries


# Fallback names for IFSC prefixes that do not have a dedicated profile yet.
IFSC_BANK_NAMES: dict[str, str] = {
    "SBIN": "State Bank of India",
    "HDFC": "HDFC Bank",
    "ICIC": "ICICI Bank",
    "UTIB": "Axis Bank",
    "KKBK": "Kotak Mahindra Bank",
    "PUNB": "Punjab National Bank",
    "BARB": "Bank of Baroda",
    "CNRB": "Canara Bank",
    "UBIN": "Union Bank of India",
    "IDIB": "Indian Bank",
    "YESB": "Yes Bank",
    "INDB": "IndusInd Bank",
    "BKID": "Bank of India",
    "MAHB": "Bank of Maharashtra",
    "IOBA": "Indian Overseas Bank",
    "FDRL": "Federal Bank",
    "RATN": "RBL Bank",
    "KVBL": "Karur Vysya Bank",
    "CIUB": "City Union Bank",
    "TMBL": "Tamilnad Mercantile Bank",
    "DCBL": "DCB Bank",
    "JAKA": "Jammu & Kashmir Bank",
    "PSIB": "Punjab & Sind Bank",
    "SIBL": "South Indian Bank",
    "UCBA": "UCO Bank",
    "ANDB": "Andhra Bank",
    "CORP": "Corporation Bank",
    "VIJB": "Vijaya Bank",
    "SYNB": "Syndicate Bank",
    "ALLA": "Allahabad Bank",
    "GSCB": "Gujarat State Co-operative Bank",
    "HDFC0": "HDFC Bank",
    "IDFB": "IDFC FIRST Bank",
    "BDBL": "Bandhan Bank",
    "ESFB": "Equitas Small Finance Bank",
    "UJVN": "Ujjivan Small Finance Bank",
    "AUBL": "AU Small Finance Bank",
}


# Header/name aliases for banks that may not have a dedicated table profile.
# Longest alias wins, so "SOUTH INDIAN BANK" beats "INDIAN BANK".
BANK_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "State Bank of India": ("STATE BANK OF INDIA", "SBI", "S.B.I", "STATE BANK"),
    "HDFC Bank": ("HDFC BANK", "HDFC LTD"),
    "ICICI Bank": ("ICICI BANK", "ICICI"),
    "Axis Bank": ("AXIS BANK", "AXIS"),
    "Kotak Mahindra Bank": ("KOTAK MAHINDRA BANK", "KOTAK MAHINDRA", "KOTAK BANK", "KOTAK"),
    "Punjab National Bank": ("PUNJAB NATIONAL BANK", "PNB"),
    "Bank of Baroda": ("BANK OF BARODA", "BARODA"),
    "Canara Bank": ("CANARA BANK",),
    "Union Bank of India": ("UNION BANK OF INDIA", "UNION BANK"),
    "IDBI Bank": ("IDBI BANK", "IDBI"),
    "Yes Bank": ("YES BANK",),
    "IndusInd Bank": ("INDUSIND BANK", "INDUSIND"),
    "IDFC FIRST Bank": ("IDFC FIRST BANK", "IDFC FIRST", "IDFC BANK", "IDFC"),
    "Federal Bank": ("FEDERAL BANK",),
    "RBL Bank": ("RBL BANK",),
    "Bandhan Bank": ("BANDHAN BANK",),
    "Indian Bank": ("INDIAN BANK",),
    "Bank of India": ("BANK OF INDIA",),
    "Central Bank of India": ("CENTRAL BANK OF INDIA", "CENTRAL BANK"),
    "UCO Bank": ("UCO BANK",),
    "Indian Overseas Bank": ("INDIAN OVERSEAS BANK",),
    "Punjab & Sind Bank": ("PUNJAB AND SIND BANK", "PUNJAB & SIND BANK"),
    "Bank of Maharashtra": ("BANK OF MAHARASHTRA",),
    "South Indian Bank": ("SOUTH INDIAN BANK",),
    "Karur Vysya Bank": ("KARUR VYSYA BANK",),
    "City Union Bank": ("CITY UNION BANK",),
    "DCB Bank": ("DCB BANK",),
    "Jammu & Kashmir Bank": ("JAMMU AND KASHMIR BANK", "JAMMU & KASHMIR BANK", "J&K BANK"),
    "AU Small Finance Bank": ("AU SMALL FINANCE BANK", "AU BANK"),
    "Equitas Small Finance Bank": ("EQUITAS SMALL FINANCE BANK", "EQUITAS BANK"),
    "Ujjivan Small Finance Bank": ("UJJIVAN SMALL FINANCE BANK", "UJJIVAN BANK"),
    "SBM Bank India": ("SBM BANK",),
    "Standard Chartered": ("STANDARD CHARTERED",),
    "HSBC": ("HSBC",),
    "Citibank": ("CITIBANK", "CITI BANK"),
    "Deutsche Bank": ("DEUTSCHE BANK",),
    "DBS Bank": ("DBS BANK",),
}
