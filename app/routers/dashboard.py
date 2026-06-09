"""Dashboard: at-a-glance counts and low-stock alerts for the print shop."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Customer, FinishingType, Machine, StockItem, Supplier
from ..web import templates

router = APIRouter()


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

    stats = [
        {"label": "Customers", "value": count(Customer, Customer.active == True), "icon": "bi-people", "url": "/customers"},
        {"label": "Suppliers", "value": count(Supplier, Supplier.active == True), "icon": "bi-truck", "url": "/suppliers"},
        {"label": "Stock Items", "value": count(StockItem), "icon": "bi-box-seam", "url": "/stock"},
        {"label": "Finishing Types", "value": count(FinishingType), "icon": "bi-scissors", "url": "/finishing"},
        {"label": "Machines", "value": count(Machine, Machine.active == True), "icon": "bi-gear-wide-connected", "url": "/machines"},
    ]
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"active_nav": "dashboard", "stats": stats, "low_stock": low_stock},
    )
