"""Automatic audit logging (Module 14).

A SQLAlchemy ``before_flush`` listener captures every create / update / delete of
an audited entity; the matching ``after_flush`` listener writes the audit rows
once primary keys are assigned, via a direct Core insert in the same
transaction. The acting user is carried from the request into the listener via a
context variable set by the auth middleware, so no router needs changing.
"""
import contextvars
from datetime import datetime

from sqlalchemy import event, insert
from sqlalchemy.orm import Session

from .models import AuditLog

# Set per-request by AuthMiddleware; "system" for background/seed operations.
current_user_var: contextvars.ContextVar[str] = contextvars.ContextVar("audit_user", default="system")

# Tables that are *not* audited: the log itself, plus high-volume derived rows
# and line-items (their parent document's create/update already covers them).
_SKIP_TABLES = {
    "audit_logs", "reconciled_txns", "stock_movements",
    "quotation_items", "quotation_item_finishings", "job_items", "job_stages",
    "invoice_items", "delivery_order_items", "purchase_order_items",
    "supplier_bill_items", "journal_lines",
}


def _describe(obj) -> str:
    for attr in ("number", "code", "name", "title", "username"):
        val = getattr(obj, attr, None)
        if val:
            return str(val)
    return ""


def _capture(obj, action: str, user: str) -> dict | None:
    table = obj.__tablename__
    if table in _SKIP_TABLES:
        return None
    return {
        "obj": obj, "username": user, "action": action,
        "entity": table, "entity_id": getattr(obj, "id", None),
        "summary": _describe(obj)[:200],
    }


@event.listens_for(Session, "before_flush")
def _audit_before_flush(session, flush_context, instances):  # noqa: ANN001
    user = current_user_var.get()
    pending = session.info.setdefault("_audit_pending", [])
    for obj in session.new:
        rec = _capture(obj, "create", user)
        if rec:
            pending.append(rec)
    for obj in session.deleted:
        rec = _capture(obj, "delete", user)
        if rec:
            pending.append(rec)
    for obj in session.dirty:
        if session.is_modified(obj, include_collections=False):
            rec = _capture(obj, "update", user)
            if rec:
                pending.append(rec)


@event.listens_for(Session, "after_flush")
def _audit_after_flush(session, flush_context):  # noqa: ANN001
    pending = session.info.get("_audit_pending")
    if not pending:
        return
    now = datetime.utcnow()
    rows = []
    for rec in pending:
        eid = rec["entity_id"]
        if eid is None:
            eid = getattr(rec["obj"], "id", None)   # assigned by the flush
        rows.append({"timestamp": now, "username": rec["username"], "action": rec["action"],
                     "entity": rec["entity"], "entity_id": eid, "summary": rec["summary"]})
    session.info["_audit_pending"] = []
    # Direct Core insert: writes in this transaction without re-entering the ORM flush.
    session.execute(insert(AuditLog), rows)
