"""Audit-log tests: automatic capture, user tagging, skips, and gating."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import AuditLog, Customer, Quotation


def _latest(entity, action):
    with SessionLocal() as db:
        return db.execute(
            select(AuditLog).where(AuditLog.entity == entity, AuditLog.action == action)
            .order_by(AuditLog.id.desc())).scalars().first()


def test_create_update_delete_are_logged_with_user_and_id(client):
    client.post("/customers/new", data={"code": "AUD-T", "name": "Audit", "active": "on",
                                        "payment_terms_days": "30"})
    with SessionLocal() as db:
        cid = db.execute(select(Customer).where(Customer.code == "AUD-T")).scalars().one().id

    created = _latest("customers", "create")
    assert created.username == "admin" and created.entity_id == cid and created.summary == "AUD-T"

    client.post(f"/customers/{cid}/edit", data={"code": "AUD-T", "name": "Renamed",
                                                "active": "on", "payment_terms_days": "30"})
    assert _latest("customers", "update").entity_id == cid

    client.post(f"/customers/{cid}/delete")
    assert _latest("customers", "delete").entity_id == cid


def test_line_items_are_not_audited(client):
    client.post("/quotations/new", data={"customer_id": 1, "date": "2026-06-09",
                                         "status": "Approved", "tax_pct": 6})
    with SessionLocal() as db:
        qid = db.execute(select(Quotation).order_by(Quotation.id.desc())).scalars().first().id
    client.post(f"/quotations/{qid}/items/new", data={
        "title": "Job", "quantity": 1000, "finished_width_mm": 100, "finished_height_mm": 100,
        "paper_id": 2, "machine_id": 1, "colors_front": 4, "colors_back": 0,
        "wastage_pct": 5, "markup_pct": 30})
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(entity="quotation_items").count() == 0
        assert db.query(AuditLog).filter_by(entity="quotations").count() >= 1


def test_audit_log_is_admin_only(client, anon):
    assert client.get("/audit-log", follow_redirects=False).status_code == 200
    client.post("/users/new", data={"username": "ali2", "full_name": "Ali",
                                    "role": "staff", "password": "pw12345"})
    anon.post("/login", data={"username": "ali2", "password": "pw12345"})
    assert anon.get("/audit-log", follow_redirects=False).status_code == 303
