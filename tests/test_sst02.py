"""SST-02 tax-return summary tests."""
from datetime import date

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Account, Quotation, SupplierBill, Supplier
from app.routers.reports import _sst_period


def test_taxable_period_is_bimonthly():
    assert _sst_period(date(2026, 6, 10)) == (date(2026, 5, 1), date(2026, 6, 30))
    assert _sst_period(date(2026, 1, 5)) == (date(2026, 1, 1), date(2026, 2, 28))
    assert _sst_period(date(2026, 12, 31)) == (date(2026, 11, 1), date(2026, 12, 31))


def _invoice_with_tax(client, tax):
    client.post("/quotations/new", data={"customer_id": 1, "date": "2026-06-09",
                                         "status": "Approved", "tax_pct": tax})
    with SessionLocal() as db:
        qid = db.execute(select(Quotation).order_by(Quotation.id.desc())).scalars().first().id
    client.post(f"/quotations/{qid}/items/new", data={
        "title": "Job", "quantity": 1000, "finished_width_mm": 100, "finished_height_mm": 100,
        "paper_id": 2, "machine_id": 1, "colors_front": 4, "colors_back": 0,
        "wastage_pct": 5, "markup_pct": 30})
    client.post(f"/invoices/from-quotation/{qid}")


def test_sst02_summarises_output_and_input_tax(client):
    _invoice_with_tax(client, 6)        # output tax
    with SessionLocal() as db:
        supid = db.execute(select(Supplier)).scalars().first().id
    client.post("/bills/new", data={"supplier_id": supid, "date": "2026-06-09", "tax_pct": 6})
    with SessionLocal() as db:
        bid = db.execute(select(SupplierBill).order_by(SupplierBill.id.desc())).scalars().first().id
    client.post(f"/bills/{bid}/items/add", data={"description": "Paper", "quantity": 1, "unit_price": 1000})

    with SessionLocal() as db:
        rent = db.execute(select(Account).where(Account.code == "6100")).scalars().one().id
        bank = db.execute(select(Account).where(Account.code == "1000")).scalars().one().id
    client.post("/expenses/new", data={"date": "2026-06-09", "expense_account_id": str(rent),
                                       "paid_from_account_id": str(bank), "amount": "500", "tax_pct": "6"})

    r = client.get("/reports/sst02?start=2026-05-01&end=2026-06-30", follow_redirects=False)
    assert r.status_code == 200
    # Input tax = 60 (bill 6% of 1000) + 30 (expense 6% of 500) = 90.00
    assert "90.00" in r.text
    assert "Net SST payable" in r.text
