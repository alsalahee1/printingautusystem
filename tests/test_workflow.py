"""End-to-end tests of the document chain, PDF, e-Invoice and CSV import."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Invoice, Job, Quotation, StockItem


def _new_quotation_with_item(client, tax_pct=6):
    client.post("/quotations/new", data={"customer_id": 1, "date": "2026-06-09",
                                         "status": "Approved", "tax_pct": tax_pct})
    with SessionLocal() as db:
        qid = db.execute(select(Quotation).order_by(Quotation.id.desc())).scalars().first().id
    client.post(f"/quotations/{qid}/items/new", data={
        "title": "A4 Flyer", "quantity": 5000, "finished_width_mm": 210,
        "finished_height_mm": 297, "paper_id": 2, "machine_id": 1,
        "colors_front": 4, "colors_back": 4, "wastage_pct": 8, "markup_pct": 30,
        "finishing_ids": 1})
    return qid


def test_quote_to_job_carries_spec(client):
    qid = _new_quotation_with_item(client)
    assert client.post(f"/jobs/from-quotation/{qid}", follow_redirects=False).status_code == 303
    with SessionLocal() as db:
        job = db.execute(select(Job).order_by(Job.id.desc())).scalars().first()
        assert job.items[0].ups == 9
        assert len(job.stages) == 6
        assert job.items[0].finishing_summary == "Lamination Gloss"


def test_invoice_payment_status_transitions(client):
    qid = _new_quotation_with_item(client)
    client.post(f"/invoices/from-quotation/{qid}")
    with SessionLocal() as db:
        inv = db.execute(select(Invoice).order_by(Invoice.id.desc())).scalars().first()
        iid, total = inv.id, inv.total
        assert inv.status == "Unpaid" and total > 0

    client.post(f"/invoices/{iid}/payments/add",
                data={"date": "2026-06-09", "amount": round(total / 2, 2), "method": "Cash"})
    with SessionLocal() as db:
        assert db.get(Invoice, iid).status == "Partial"

    with SessionLocal() as db:
        bal = db.get(Invoice, iid).balance
    client.post(f"/invoices/{iid}/payments/add", data={"date": "2026-06-09", "amount": bal})
    with SessionLocal() as db:
        inv = db.get(Invoice, iid)
        assert inv.status == "Paid" and inv.balance == 0


def test_pdf_and_einvoice_endpoints(client):
    qid = _new_quotation_with_item(client)
    client.post(f"/invoices/from-quotation/{qid}")
    with SessionLocal() as db:
        iid = db.execute(select(Invoice).order_by(Invoice.id.desc())).scalars().first().id

    pdf = client.get(f"/invoices/{iid}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get(f"/quotations/{qid}/pdf").content[:4] == b"%PDF"

    ej = client.get(f"/invoices/{iid}/einvoice").json()
    doc = ej["document"]["Invoice"][0]
    assert doc["DocumentCurrencyCode"][0]["_"] == "MYR"
    assert doc["LegalMonetaryTotal"][0]["PayableAmount"][0]["_"] > 0


def test_csv_import_upserts_by_code(client):
    csv1 = ("Account No,Company Name,Phone1,City\r\n"
            "IMP-001,Imported Co,03-1,Penang\r\n,No Code,x,y\r\n")
    r = client.post("/import/customers",
                    files={"file": ("c.csv", csv1, "text/csv")}, follow_redirects=False)
    assert r.status_code == 200 and "Import Result" in r.text

    # Re-import updates instead of duplicating.
    csv2 = "Account No,Company Name,Phone1\r\nIMP-001,Imported Co,03-9999\r\n"
    client.post("/import/customers", files={"file": ("c2.csv", csv2, "text/csv")})
    from app.models import Customer
    with SessionLocal() as db:
        rows = db.execute(select(Customer).where(Customer.code == "IMP-001")).scalars().all()
        assert len(rows) == 1 and rows[0].phone == "03-9999"


def test_stock_import_maps_columns(client):
    csv = ("Item Code,Description,Item Group,UOM,GSM,Cost,Balance Qty\r\n"
           "IMP-PPR,Test Paper 100g,Paper,Sheet,100,0.25,3000\r\n")
    client.post("/import/stock", files={"file": ("s.csv", csv, "text/csv")})
    with SessionLocal() as db:
        item = db.execute(select(StockItem).where(StockItem.code == "IMP-PPR")).scalars().one()
        assert item.category == "Paper" and item.gsm == 100 and item.qty_on_hand == 3000
