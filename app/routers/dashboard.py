"""Dashboard: at-a-glance counts, low-stock alerts, and active production jobs."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Customer,
    FinishingType,
    Job,
    Machine,
    Quotation,
    StockItem,
    Supplier,
)
from ..web import templates

router = APIRouter()

ACTIVE_JOB_STATUSES = ["Pre-press", "Printing", "Post-press", "Ready"]


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    def count(model, *where):
        stmt = select(func.count()).select_from(model)
        for w in where:
            stmt = stmt.where(w)
        return db.execute(stmt).scalar_one()

    low_stock = db.execute(
        select(StockItem)
        .where(StockItem.reorder_level > 0)
        .where(StockItem.qty_on_hand <= StockItem.reorder_level)
        .order_by(StockItem.qty_on_hand)
    ).scalars().all()

    active_jobs = db.execute(
        select(Job)
        .where(Job.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(Job.due_date.is_(None), Job.due_date)
    ).scalars().all()

    soon = date.today() + timedelta(days=3)
    stats = [
        {"label": "Customers", "value": count(Customer, Customer.active == True), "icon": "bi-people", "url": "/customers"},
        {"label": "Stock Items", "value": count(StockItem), "icon": "bi-box-seam", "url": "/stock"},
        {"label": "Open Quotations", "value": count(Quotation, Quotation.status.in_(["Draft", "Sent"])), "icon": "bi-file-earmark-text", "url": "/quotations"},
        {"label": "Active Jobs", "value": count(Job, Job.status.in_(ACTIVE_JOB_STATUSES)), "icon": "bi-kanban", "url": "/jobs"},
        {"label": "Due ≤ 3 days", "value": count(Job, Job.status.in_(ACTIVE_JOB_STATUSES), Job.due_date.isnot(None), Job.due_date <= soon), "icon": "bi-alarm", "url": "/jobs"},
    ]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"active_nav": "dashboard", "stats": stats, "low_stock": low_stock, "active_jobs": active_jobs},
    )
