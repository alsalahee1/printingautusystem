"""Baseline data every deployment needs (independent of sample data).

The standard chart of accounts is required for the General Ledger and the
automatic postings to work, so it is ensured at application startup — not only
when the optional sample data is seeded.
"""
from sqlalchemy.orm import Session

from .models import Account

# (code, name, type, system_tag) — system_tag links the auto-posting accounts.
STANDARD_ACCOUNTS = [
    ("1000", "Cash & Bank", "Asset", "BANK"),
    ("1100", "Accounts Receivable", "Asset", "AR"),
    ("1200", "Inventory", "Asset", None),
    ("1300", "SST Input Tax", "Asset", "SST_INPUT"),
    ("2100", "Accounts Payable", "Liability", "AP"),
    ("2200", "SST Output Tax", "Liability", "SST_OUTPUT"),
    ("3000", "Owner's Capital", "Equity", None),
    ("4000", "Sales", "Income", "SALES"),
    ("4100", "Other Income", "Income", None),
    ("5000", "Cost of Materials / Purchases", "Expense", "PURCHASES"),
    ("6000", "Salaries & Wages", "Expense", None),
    ("6100", "Rent", "Expense", None),
    ("6200", "Utilities", "Expense", None),
    ("6900", "General Expenses", "Expense", None),
]


def ensure_standard_accounts(db: Session) -> int:
    """Create any missing standard accounts. Returns how many were created."""
    created = 0
    existing = {code for (code,) in db.query(Account.code).all()}
    for code, name, atype, tag in STANDARD_ACCOUNTS:
        if code not in existing:
            db.add(Account(code=code, name=name, type=atype, system_tag=tag))
            created += 1
    if created:
        db.commit()
    return created
