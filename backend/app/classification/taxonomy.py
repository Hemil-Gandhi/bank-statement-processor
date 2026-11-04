"""Category taxonomy used by the rule engine, ML model, UI and exports."""
from __future__ import annotations

CATEGORY_TYPES: dict[str, str] = {
    "Salary/Income": "income",
    "Business Income": "income",
    "Interest Earned": "income",
    "Refund/Reversal": "income",
    "Cash Withdrawal (ATM)": "expense",
    "Cash Deposit": "income",
    "Transfer In (Self/Others)": "transfer",
    "Transfer Out": "transfer",
    "UPI Payment": "expense",
    "Food & Dining": "expense",
    "Groceries": "expense",
    "Shopping/E-commerce": "expense",
    "Travel & Transport": "expense",
    "Fuel": "expense",
    "Utilities (Electricity/Water/Gas)": "expense",
    "Mobile/DTH/Internet": "expense",
    "Rent": "expense",
    "EMI/Loan Repayment": "expense",
    "Credit Card Payment": "transfer",
    "Insurance": "expense",
    "Investments (MF/SIP/Stocks)": "transfer",
    "Taxes (GST/Income Tax)": "expense",
    "Bank Charges & Fees": "expense",
    "Healthcare": "expense",
    "Education": "expense",
    "Entertainment/Subscriptions": "expense",
    "Donations": "expense",
    "Cheque (Deposit/Issue)": "transfer",
    "Uncategorized": "neutral",
}

CATEGORIES: list[str] = list(CATEGORY_TYPES.keys())


def is_valid_category(category: str) -> bool:
    return category in CATEGORY_TYPES


def category_type(category: str) -> str:
    return CATEGORY_TYPES.get(category, "neutral")
