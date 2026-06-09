"""General Ledger tests: auto-postings, report integrity, manual journals."""
from sqlalchemy import select

from app import gl
from app.database import SessionLocal
from app.models import Account, Invoice, JournalEntry, Quotation, Supplier, SupplierBill


def _invoice_and_pay(client, pay):
    client.post("/quotations/new", data={"customer_id": 1, "date": "2026-06-09",
                                         "status": "Approved", "tax_pct": 6})
    with SessionLocal() as db:
        qid = db.execute(select(Quotation).order_by(Quotation.id.desc())).scalars().first().id
    client.post(f"/quotations/{qid}/items/new", data={
        "title": "Job", "quantity": 1000, "finished_width_mm": 100, "finished_height_mm": 100,
        "paper_id": 2, "machine_id": 1, "colors_front": 4, "colors_back": 0,
        "wastage_pct": 5, "markup_pct": 30})
    client.post(f"/invoices/from-quotation/{qid}")
    with SessionLocal() as db:
        inv = db.execute(select(Invoice).order_by(Invoice.id.desc())).scalars().first()
        iid = inv.id
    client.post(f"/invoices/{iid}/payments/add",
                data={"date": "2026-06-09", "amount": pay, "method": "Cash"})
    return iid


def test_reports_render(client):
    for p in ["/accounts", "/journals", "/journals/new",
              "/trial-balance", "/profit-loss", "/balance-sheet"]:
        assert client.get(p, follow_redirects=False).status_code == 200


def test_trial_balance_balances_and_postings_correct(client):
    _invoice_and_pay(client, pay=100)
    with SessionLocal() as db:
        rows, td, tc = gl.trial_balance(db)
        assert abs(td - tc) < 0.005 and td > 0          # debits == credits
        tags = {r["account"].system_tag: r for r in rows if r["account"].system_tag}
        # Sales is credit-normal and must have a credit balance from the invoice.
        assert tags["SALES"]["credit"] > 0
        assert tags["SST_OUTPUT"]["credit"] > 0          # 6% output tax posted
        assert tags["BANK"]["debit"] == 100              # the receipt hit Bank


def test_balance_sheet_balances(client):
    _invoice_and_pay(client, pay=100)
    with SessionLocal() as db:
        bs = gl.balance_sheet(db)
        assert abs(bs["total_assets"] - bs["total_liab_equity"]) < 0.05


def test_supplier_bill_posts_to_ap_and_purchases(client):
    with SessionLocal() as db:
        supid = db.execute(select(Supplier)).scalars().first().id
    client.post("/bills/new", data={"supplier_id": supid, "date": "2026-06-09", "tax_pct": 6})
    with SessionLocal() as db:
        bid = db.execute(select(SupplierBill).order_by(SupplierBill.id.desc())).scalars().first().id
    client.post(f"/bills/{bid}/items/add", data={"description": "Paper", "quantity": 1, "unit_price": 500})
    with SessionLocal() as db:
        bals = gl.account_balances(db)
        sa = gl.system_accounts(db)
        assert bals[sa["PURCHASES"].id]["balance"] == 500     # expense debit
        assert bals[sa["AP"].id]["balance"] == 530            # 500 + 6% credit


def test_manual_journal_must_balance(client):
    with SessionLocal() as db:
        rent = db.execute(select(Account).where(Account.code == "6100")).scalars().one().id
        bank = db.execute(select(Account).where(Account.code == "1000")).scalars().one().id
        before = db.query(JournalEntry).count()

    # Balanced -> posted.
    client.post("/journals/new", data={
        "date": "2026-06-09", "reference": "Rent", "narration": "June",
        "account_id": [str(rent), str(bank)], "debit": ["1200", ""], "credit": ["", "1200"]})
    with SessionLocal() as db:
        assert db.query(JournalEntry).count() == before + 1

    # Unbalanced -> rejected (count unchanged).
    client.post("/journals/new", data={
        "date": "2026-06-09", "account_id": [str(rent), str(bank)],
        "debit": ["100", ""], "credit": ["", "50"]})
    with SessionLocal() as db:
        assert db.query(JournalEntry).count() == before + 1
