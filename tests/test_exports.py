"""CSV export tests."""
import csv
import io

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Invoice, Quotation


def _rows(resp):
    return list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))


def _seed_invoice(client):
    client.post("/quotations/new", data={"customer_id": 1, "date": "2026-06-09",
                                         "status": "Approved", "tax_pct": 6})
    with SessionLocal() as db:
        qid = db.execute(select(Quotation).order_by(Quotation.id.desc())).scalars().first().id
    client.post(f"/quotations/{qid}/items/new", data={
        "title": "Job", "quantity": 1000, "finished_width_mm": 100, "finished_height_mm": 100,
        "paper_id": 2, "machine_id": 1, "colors_front": 4, "colors_back": 0,
        "wastage_pct": 5, "markup_pct": 30})
    client.post(f"/invoices/from-quotation/{qid}")


def test_report_exports_are_valid_csv(client):
    _seed_invoice(client)
    expected_headers = {
        "/trial-balance.csv": ["Code", "Account", "Type", "Debit", "Credit"],
        "/profit-loss.csv": ["Section", "Account", "Amount"],
        "/balance-sheet.csv": ["Section", "Account", "Amount"],
        "/reports/sales.csv": ["Date", "Invoice", "Customer", "Status", "Total", "Paid", "Balance"],
        "/reports/stock-valuation.csv": ["Code", "Name", "Category", "Unit", "On Hand", "Unit Cost", "Value"],
        "/ar.csv": ["Customer", "Invoice", "Date", "Due", "Aging", "Balance"],
        "/export/customers.csv": ["Code", "Name", "Company", "Phone", "Email", "Address",
                                  "City", "SST", "TIN", "RegNo", "CreditLimit", "Terms"],
        "/export/stock.csv": ["ItemCode", "Description", "Category", "UOM", "GSM", "Cost",
                              "SellingPrice", "BalanceQty", "ReorderLevel"],
    }
    for url, header in expected_headers.items():
        r = client.get(url, follow_redirects=False)
        assert r.status_code == 200, url
        assert "text/csv" in r.headers["content-type"], url
        rows = _rows(r)
        assert rows[0] == header, url


def test_trial_balance_csv_totals_balance(client):
    _seed_invoice(client)
    rows = _rows(client.get("/trial-balance.csv"))
    total_row = rows[-1]                       # ["", "TOTAL", "", debit, credit]
    assert total_row[1] == "TOTAL"
    assert float(total_row[3]) == float(total_row[4])   # debits == credits


def test_customer_export_roundtrips_through_import(client):
    # Export, then re-import the same CSV — should update, not duplicate.
    from app.models import Customer
    with SessionLocal() as db:
        before = db.query(Customer).count()
    data = client.get("/export/customers.csv").content
    client.post("/import/customers", files={"file": ("customers.csv", data, "text/csv")})
    with SessionLocal() as db:
        assert db.query(Customer).count() == before   # upserted, no duplicates


def test_audit_csv_is_admin_only(client, anon):
    assert client.get("/audit-log.csv", follow_redirects=False).status_code == 200
    client.post("/users/new", data={"username": "ali3", "role": "staff", "password": "pw12345"})
    anon.post("/login", data={"username": "ali3", "password": "pw12345"})
    assert anon.get("/audit-log.csv", follow_redirects=False).status_code == 303
