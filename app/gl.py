"""General Ledger engine (Module 11).

PrintSys uses the subledgers (invoices, bills, payments) as the source of truth
and *derives* the double-entry postings from them on the fly, combined with any
manually-entered journal entries. This keeps the GL always consistent with the
documents without a separate posting/sync step.

Standard postings:
  Invoice           Dr AR (total)        Cr Sales (subtotal)  Cr SST Output (tax)
  Customer payment  Dr Bank (amount)     Cr AR (amount)
  Supplier bill     Dr Purchases (sub)   Dr SST Input (tax)   Cr AP (total)
  Supplier payment  Dr AP (amount)       Cr Bank (amount)
  Manual journal    user-defined balanced lines

Accounts are matched by `system_tag`; if a tag is missing the related lines are
simply skipped (so the ledger still works on a partial chart of accounts).
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Account,
    Expense,
    Invoice,
    JournalEntry,
    Payment,
    SupplierBill,
    SupplierPayment,
)


@dataclass
class Posting:
    date: date
    account_id: int
    debit: float
    credit: float
    ref: str
    source: str

    @property
    def key(self) -> str:
        """Stable identifier for a posting, used by bank reconciliation."""
        return f"{self.source}|{self.ref}|{self.date}|{self.debit:.2f}|{self.credit:.2f}"


def system_accounts(db: Session) -> dict[str, Account]:
    rows = db.execute(select(Account).where(Account.system_tag.isnot(None))).scalars().all()
    return {a.system_tag: a for a in rows}


def iter_postings(db: Session, start: date | None = None, end: date | None = None):
    """Yield every GL posting (derived document postings + manual journal lines)."""
    sa = system_accounts(db)

    def tag(t):
        a = sa.get(t)
        return a.id if a else None

    def in_range(d):
        return (start is None or d >= start) and (end is None or d <= end)

    AR, BANK, SALES, SST_OUT = tag("AR"), tag("BANK"), tag("SALES"), tag("SST_OUTPUT")
    AP, PURCH, SST_IN = tag("AP"), tag("PURCHASES"), tag("SST_INPUT")

    # --- Customer invoices ---
    for inv in db.execute(select(Invoice)).scalars():
        if inv.cancelled or not in_range(inv.date):
            continue
        if AR and inv.total:
            yield Posting(inv.date, AR, inv.total, 0, inv.number, "Invoice")
        if SALES and inv.subtotal:
            yield Posting(inv.date, SALES, 0, inv.subtotal, inv.number, "Invoice")
        if SST_OUT and inv.tax_amount:
            yield Posting(inv.date, SST_OUT, 0, inv.tax_amount, inv.number, "Invoice")

    # --- Customer payments (receipts) ---
    for p in db.execute(select(Payment)).scalars():
        inv = p.invoice
        if not inv or inv.cancelled or not in_range(p.date):
            continue
        if BANK and p.amount:
            yield Posting(p.date, BANK, p.amount, 0, inv.number, "Receipt")
        if AR and p.amount:
            yield Posting(p.date, AR, 0, p.amount, inv.number, "Receipt")

    # --- Supplier bills ---
    for b in db.execute(select(SupplierBill)).scalars():
        if b.cancelled or not in_range(b.date):
            continue
        if PURCH and b.subtotal:
            yield Posting(b.date, PURCH, b.subtotal, 0, b.number, "Bill")
        if SST_IN and b.tax_amount:
            yield Posting(b.date, SST_IN, b.tax_amount, 0, b.number, "Bill")
        if AP and b.total:
            yield Posting(b.date, AP, 0, b.total, b.number, "Bill")

    # --- Supplier payments ---
    for p in db.execute(select(SupplierPayment)).scalars():
        bill = p.bill
        if not bill or bill.cancelled or not in_range(p.date):
            continue
        if AP and p.amount:
            yield Posting(p.date, AP, p.amount, 0, bill.number, "Pay Bill")
        if BANK and p.amount:
            yield Posting(p.date, BANK, 0, p.amount, bill.number, "Pay Bill")

    # --- Direct expenses (Dr expense + SST input, Cr cash/bank) ---
    for ex in db.execute(select(Expense)).scalars():
        if not in_range(ex.date):
            continue
        if ex.amount:
            yield Posting(ex.date, ex.expense_account_id, ex.amount, 0, ex.number, "Expense")
        if SST_IN and ex.tax_amount:
            yield Posting(ex.date, SST_IN, ex.tax_amount, 0, ex.number, "Expense")
        yield Posting(ex.date, ex.paid_from_account_id, 0, ex.total, ex.number, "Expense")

    # --- Manual journals ---
    for je in db.execute(select(JournalEntry)).scalars():
        if not in_range(je.date):
            continue
        for ln in je.lines:
            yield Posting(je.date, ln.account_id, ln.debit, ln.credit,
                          je.number, "Journal")


def account_balances(db: Session, start=None, end=None) -> dict[int, dict]:
    """Per-account totals: {account_id: {'debit','credit','balance'}}.

    balance is signed to the account's normal side (debit-normal positive when
    debits exceed credits; credit-normal positive when credits exceed debits).
    """
    accounts = {a.id: a for a in db.execute(select(Account)).scalars()}
    totals: dict[int, dict] = {}
    for p in iter_postings(db, start, end):
        t = totals.setdefault(p.account_id, {"debit": 0.0, "credit": 0.0})
        t["debit"] += p.debit
        t["credit"] += p.credit
    for aid, t in totals.items():
        acc = accounts.get(aid)
        raw = t["debit"] - t["credit"]
        t["balance"] = round(raw if (acc and acc.is_debit_normal) else -raw, 2)
        t["debit"] = round(t["debit"], 2)
        t["credit"] = round(t["credit"], 2)
    return totals


def trial_balance(db: Session, start=None, end=None):
    """Return (rows, total_debit, total_credit). Rows carry net debit/credit."""
    balances = account_balances(db, start, end)
    accounts = sorted(db.execute(select(Account)).scalars(), key=lambda a: a.code)
    rows, td, tc = [], 0.0, 0.0
    for a in accounts:
        t = balances.get(a.id)
        if not t:
            continue
        net = round(t["debit"] - t["credit"], 2)
        dr = net if net > 0 else 0.0
        cr = -net if net < 0 else 0.0
        if dr == 0 and cr == 0:
            continue
        rows.append({"account": a, "debit": dr, "credit": cr})
        td += dr
        tc += cr
    return rows, round(td, 2), round(tc, 2)


def _by_type(db, start, end):
    balances = account_balances(db, start, end)
    accounts = sorted(db.execute(select(Account)).scalars(), key=lambda a: a.code)
    groups: dict[str, list] = {t: [] for t in ["Asset", "Liability", "Equity", "Income", "Expense"]}
    for a in accounts:
        t = balances.get(a.id)
        bal = t["balance"] if t else 0.0
        groups[a.type].append({"account": a, "balance": round(bal, 2)})
    return groups


def income_statement(db, start=None, end=None):
    g = _by_type(db, start, end)
    income = g["Income"]
    expense = g["Expense"]
    total_income = round(sum(r["balance"] for r in income), 2)
    total_expense = round(sum(r["balance"] for r in expense), 2)
    net = round(total_income - total_expense, 2)
    return {"income": income, "expense": expense, "total_income": total_income,
            "total_expense": total_expense, "net_profit": net}


def balance_sheet(db, as_of=None):
    g = _by_type(db, None, as_of)
    assets = g["Asset"]
    liabilities = g["Liability"]
    equity = g["Equity"]
    total_assets = round(sum(r["balance"] for r in assets), 2)
    total_liab = round(sum(r["balance"] for r in liabilities), 2)
    total_equity = round(sum(r["balance"] for r in equity), 2)
    # Current-period earnings make the sheet balance (income - expense to date).
    pnl = income_statement(db, None, as_of)
    retained = pnl["net_profit"]
    total_equity_with_earnings = round(total_equity + retained, 2)
    return {"assets": assets, "liabilities": liabilities, "equity": equity,
            "total_assets": total_assets, "total_liabilities": total_liab,
            "total_equity": total_equity, "current_earnings": retained,
            "total_equity_with_earnings": total_equity_with_earnings,
            "total_liab_equity": round(total_liab + total_equity_with_earnings, 2)}


def account_ledger(db, account_id, start=None, end=None):
    """Detailed postings for one account with a running balance."""
    acc = db.get(Account, account_id)
    if not acc:
        return None, []
    postings = [p for p in iter_postings(db, start, end) if p.account_id == account_id]
    postings.sort(key=lambda p: (p.date, p.source))
    running = 0.0
    rows = []
    for p in postings:
        delta = (p.debit - p.credit) if acc.is_debit_normal else (p.credit - p.debit)
        running = round(running + delta, 2)
        rows.append({"p": p, "balance": running})
    return acc, rows
