"""Audit log viewer (Module 14) — admin only."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..database import get_db
from ..models import AuditLog
from ..web import flash, templates

router = APIRouter()

ACTION_COLORS = {"create": "success", "update": "info", "delete": "danger"}


@router.get("/audit-log", response_class=HTMLResponse)
def view_audit_log(request: Request, db: Session = Depends(get_db),
                   entity: str | None = None, action: str | None = None):
    u = current_user(request)
    if not u or u.get("role") != "admin":
        flash(request, "Admins only.", "danger")
        return RedirectResponse("/", status_code=303)

    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = db.execute(stmt.limit(500)).scalars().all()

    entities = sorted({e for (e,) in db.execute(select(AuditLog.entity).distinct())})
    return templates.TemplateResponse(
        request, "audit_log.html",
        {"active_nav": "audit", "rows": rows, "entities": entities,
         "sel_entity": entity, "sel_action": action, "colors": ACTION_COLORS},
    )
