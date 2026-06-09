"""Expenses and bank-reconciliation tests."""
from sqlalchemy import select

from app import gl
from app.database import SessionLocal
from app.models import Account, Expense, ReconciledTxn


def _accounts():
    with SessionLocal() as db:
        rent = db.execute(select(Account).where(Account.code == "6100")).scalars().one().id
        bank = db.execute(select(Account).where(Account.code == "1000")).scalars().one().id
    return rent, bank


def test_expense_posts_to_ledger(client):
    rent, bank = _accounts()
    r = client.post("/expenses/new", data={
        "date": "2026-06-09", "payee": "Landlord", "reference": "CHQ01",
        "expense_account_id": str(rent), "paid_from_account_id": str(bank),
        "amount": "300", "tax_pct": "6", "description": "June rent"},
        follow_redirects=False)
    assert r.status_code == 303
    with SessionLocal() as db:
        ex = db.execute(select(Expense).order_by(Expense.id.desc())).scalars().first()
        assert ex.amount == 300 and ex.tax_amount == 18 and ex.total == 318
        bals = gl.account_balances(db)
        sa = gl.system_accounts(db)
        assert bals[rent]["balance"] == 300              # expense debit
        assert bals[sa["SST_INPUT"].id]["balance"] == 18  # input tax debit
        assert bals[bank]["balance"] == -318             # bank credited
        rows, td, tc = gl.trial_balance(db)
        assert abs(td - tc) < 0.005                       # still balanced


def test_expense_requires_positive_amount(client):
    rent, bank = _accounts()
    before = SessionLocal().query(Expense).count()
    client.post("/expenses/new", data={
        "date": "2026-06-09", "expense_account_id": str(rent),
        "paid_from_account_id": str(bank), "amount": "0"})
    assert SessionLocal().query(Expense).count() == before


def test_bank_reconciliation_toggle(client):
    rent, bank = _accounts()
    client.post("/expenses/new", data={
        "date": "2026-06-09", "expense_account_id": str(rent),
        "paid_from_account_id": str(bank), "amount": "120", "tax_pct": "0"})
    assert client.get(f"/reconcile/{bank}", follow_redirects=False).status_code == 200

    with SessionLocal() as db:
        key = next(p.key for p in gl.iter_postings(db)
                   if p.account_id == bank and p.source == "Expense")

    client.post(f"/reconcile/{bank}/toggle", data={"key": key})
    with SessionLocal() as db:
        assert db.query(ReconciledTxn).filter_by(account_id=bank, txn_key=key).count() == 1
    client.post(f"/reconcile/{bank}/toggle", data={"key": key})   # toggle off
    with SessionLocal() as db:
        assert db.query(ReconciledTxn).filter_by(account_id=bank, txn_key=key).count() == 0
