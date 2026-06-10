"""Inventory & Purchasing (Module 5).

Three connected pieces:
  * Stock movements — the inventory ledger. Every Receipt / Issue / Adjustment
    is recorded and the item's on-hand quantity kept in step.
  * Purchase Orders — order materials from a supplier; "Receive" turns the PO
    into stock-in movements and (optionally) a supplier bill.
  * Supplier Bills + Payments — Accounts Payable, the mirror of the customer
    AR in Module 4, with its own aging report.

Jobs can also consume materials: issuing each job item's paper (by total
sheets) and plates straight out of stock.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..exporting import csv_response
from ..models import (
    PAYMENT_METHODS,
    PO_STATUSES,
    Job,
    PurchaseOrder,
    PurchaseOrderItem,
    StockItem,
    StockMovement,
    Supplier,
    SupplierBill,
    SupplierBillItem,
    SupplierPayment,
)
from ..web import flash, templates
from .quotations import _f, get_settings

router = APIRouter()


def _next_number(db: Session, model, prefix: str) -> str:
    n = (db.query(model).count() or 0) + 1
    while db.query(model).filter(model.number == f"{prefix}-{n:04d}").first():
        n += 1
    return f"{prefix}-{n:04d}"


def record_movement(db, item: StockItem, qty: float, mtype: str,
                    *, unit_cost=0.0, reference="", notes="") -> StockMovement:
    """Append a stock movement and keep the item's on-hand quantity in step."""
    mv = StockMovement(stock_item_id=item.id, date=date.today(), type=mtype,
                       quantity=qty, unit_cost=unit_cost, reference=reference, notes=notes)
    db.add(mv)
    item.qty_on_hand = round((item.qty_on_hand or 0) + qty, 3)
    return mv


def _suppliers(db):
    return db.execute(select(Supplier).where(Supplier.active == True).order_by(Supplier.name)).scalars().all()


def _stock_items(db):
    return db.execute(select(StockItem).order_by(StockItem.name)).scalars().all()


# --------------------------------------------------------------------------- #
# Stock movements / inventory ledger
# --------------------------------------------------------------------------- #
@router.get("/stock-movements", response_class=HTMLResponse)
def list_movements(request: Request, db: Session = Depends(get_db), item: int | None = None):
    stmt = select(StockMovement).order_by(StockMovement.date.desc(), StockMovement.id.desc())
    if item:
        stmt = stmt.where(StockMovement.stock_item_id == item)
    rows = db.execute(stmt).scalars().all()
    return templates.TemplateResponse(
        request, "inventory/movements.html",
        {"active_nav": "movements", "rows": rows, "items": _stock_items(db),
         "selected_item": item},
    )


@router.post("/stock-movements/add")
async def add_movement(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    item = db.get(StockItem, int(form["stock_item_id"]))
    if item:
        qty = _f(form, "quantity", float, 0)
        direction = form.get("direction", "in")
        signed = qty if direction == "in" else -qty
        record_movement(db, item, signed, form.get("type") or "Adjustment",
                        unit_cost=_f(form, "unit_cost", float, 0),
                        reference=form.get("reference") or "", notes=form.get("notes") or "")
        db.commit()
        flash(request, f"Stock movement recorded for {item.name}.", "success")
    return RedirectResponse(request.headers.get("referer", "/stock-movements"), status_code=303)


@router.post("/stock-movements/{mid}/delete")
def delete_movement(mid: int, request: Request, db: Session = Depends(get_db)):
    mv = db.get(StockMovement, mid)
    if mv:
        item = db.get(StockItem, mv.stock_item_id)
        if item:
            item.qty_on_hand = round((item.qty_on_hand or 0) - mv.quantity, 3)  # reverse
        db.delete(mv)
        db.commit()
        flash(request, "Movement reversed.", "success")
    return RedirectResponse("/stock-movements", status_code=303)


# --------------------------------------------------------------------------- #
# Consume materials from a job (issue paper + plates)
# --------------------------------------------------------------------------- #
@router.post("/jobs/{jid}/consume")
def consume_job_materials(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if not job:
        return RedirectResponse("/jobs", status_code=303)
    issued = 0
    for it in job.items:
        if it.paper_id and it.total_sheets:
            paper = db.get(StockItem, it.paper_id)
            if paper:
                record_movement(db, paper, -it.total_sheets, "Job Usage",
                                unit_cost=paper.cost_price, reference=job.number, notes=it.title)
                issued += 1
    db.commit()
    if issued:
        flash(request, f"Issued materials for {issued} item(s) from stock.", "success")
    else:
        flash(request, "Nothing to issue — items need a paper and sheet count.", "warning")
    return RedirectResponse(f"/jobs/{jid}", status_code=303)


# --------------------------------------------------------------------------- #
# Purchase Orders
# --------------------------------------------------------------------------- #
@router.get("/purchase-orders", response_class=HTMLResponse)
def list_pos(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(select(PurchaseOrder).order_by(PurchaseOrder.id.desc())).scalars().all()
    return templates.TemplateResponse(
        request, "purchasing/po_list.html",
        {"active_nav": "purchase_orders", "rows": rows, "settings": get_settings(db)},
    )


@router.get("/purchase-orders/new", response_class=HTMLResponse)
def new_po(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "purchasing/po_form.html",
        {"active_nav": "purchase_orders", "suppliers": _suppliers(db),
         "today": date.today().isoformat(),
         "expected": (date.today() + timedelta(days=7)).isoformat()},
    )


@router.post("/purchase-orders/new")
async def create_po(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    po = PurchaseOrder(
        number=_next_number(db, PurchaseOrder, "PO"),
        supplier_id=int(form["supplier_id"]),
        date=date.fromisoformat(form.get("date") or date.today().isoformat()),
        expected_date=date.fromisoformat(form["expected_date"]) if form.get("expected_date") else None,
        notes=form.get("notes") or "",
    )
    db.add(po)
    db.commit()
    flash(request, f"Purchase Order {po.number} created — add items.", "success")
    return RedirectResponse(f"/purchase-orders/{po.id}", status_code=303)


@router.get("/purchase-orders/{pid}", response_class=HTMLResponse)
def view_po(pid: int, request: Request, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, pid)
    if not po:
        return RedirectResponse("/purchase-orders", status_code=303)
    return templates.TemplateResponse(
        request, "purchasing/po_view.html",
        {"active_nav": "purchase_orders", "po": po, "settings": get_settings(db),
         "stock_items": _stock_items(db), "statuses": PO_STATUSES},
    )


@router.post("/purchase-orders/{pid}/items/add")
async def add_po_item(pid: int, request: Request, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, pid)
    if po:
        form = await request.form()
        sid = int(form["stock_item_id"]) if form.get("stock_item_id") else None
        item = db.get(StockItem, sid) if sid else None
        po.items.append(PurchaseOrderItem(
            line_no=len(po.items) + 1,
            stock_item_id=sid,
            description=form.get("description") or (item.name if item else ""),
            quantity=_f(form, "quantity", float, 0),
            unit_cost=_f(form, "unit_cost", float, (item.cost_price if item else 0)),
        ))
        db.commit()
    return RedirectResponse(f"/purchase-orders/{pid}", status_code=303)


@router.post("/purchase-orders/{pid}/items/{item_id}/delete")
def delete_po_item(pid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    it = db.get(PurchaseOrderItem, item_id)
    if it and it.po_id == pid:
        db.delete(it)
        db.commit()
    return RedirectResponse(f"/purchase-orders/{pid}", status_code=303)


@router.post("/purchase-orders/{pid}/status")
async def set_po_status(pid: int, request: Request, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, pid)
    if po:
        form = await request.form()
        po.status = form.get("status") or po.status
        db.commit()
        flash(request, f"PO marked {po.status}.", "success")
    return RedirectResponse(f"/purchase-orders/{pid}", status_code=303)


@router.post("/purchase-orders/{pid}/receive")
def receive_po(pid: int, request: Request, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, pid)
    if not po:
        return RedirectResponse("/purchase-orders", status_code=303)
    if po.status == "Received":
        flash(request, "This PO is already received.", "warning")
        return RedirectResponse(f"/purchase-orders/{pid}", status_code=303)
    received = 0
    for it in po.items:
        if it.stock_item_id and it.quantity:
            item = db.get(StockItem, it.stock_item_id)
            if item:
                record_movement(db, item, it.quantity, "PO Receipt",
                                unit_cost=it.unit_cost, reference=po.number)
                received += 1
    po.status = "Received"
    db.commit()
    flash(request, f"Received {received} line(s) into stock.", "success")
    return RedirectResponse(f"/purchase-orders/{pid}", status_code=303)


@router.post("/purchase-orders/{pid}/bill")
def bill_from_po(pid: int, request: Request, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, pid)
    if not po:
        return RedirectResponse("/purchase-orders", status_code=303)
    sup = po.supplier
    bill = SupplierBill(
        number=_next_number(db, SupplierBill, "BILL"),
        supplier_id=po.supplier_id, po_id=po.id, date=date.today(),
        due_date=date.today() + timedelta(days=sup.payment_terms_days if sup else 30),
        tax_pct=get_settings(db).tax_pct,
    )
    for it in po.items:
        bill.items.append(SupplierBillItem(
            line_no=it.line_no, description=it.description,
            quantity=it.quantity, unit_price=it.unit_cost))
    db.add(bill)
    db.commit()
    flash(request, f"Bill {bill.number} created from {po.number}.", "success")
    return RedirectResponse(f"/bills/{bill.id}", status_code=303)


@router.post("/purchase-orders/{pid}/delete")
def delete_po(pid: int, request: Request, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, pid)
    if po:
        db.delete(po)
        db.commit()
        flash(request, f"PO {po.number} deleted.", "success")
    return RedirectResponse("/purchase-orders", status_code=303)


@router.get("/purchase-orders/{pid}/print", response_class=HTMLResponse)
def print_po(pid: int, request: Request, db: Session = Depends(get_db)):
    po = db.get(PurchaseOrder, pid)
    if not po:
        return RedirectResponse("/purchase-orders", status_code=303)
    return templates.TemplateResponse(
        request, "purchasing/po_print.html", {"po": po, "settings": get_settings(db)}
    )


# --------------------------------------------------------------------------- #
# Supplier Bills (Accounts Payable)
# --------------------------------------------------------------------------- #
@router.get("/bills", response_class=HTMLResponse)
def list_bills(request: Request, db: Session = Depends(get_db), status: str | None = None):
    bills = db.execute(select(SupplierBill).order_by(SupplierBill.id.desc())).scalars().all()
    if status:
        bills = [b for b in bills if b.status == status]
    total_out = round(sum(b.balance for b in bills if not b.cancelled), 2)
    return templates.TemplateResponse(
        request, "purchasing/bill_list.html",
        {"active_nav": "bills", "rows": bills, "settings": get_settings(db),
         "active_status": status, "total_out": total_out},
    )


@router.get("/bills/new", response_class=HTMLResponse)
def new_bill(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "purchasing/bill_form.html",
        {"active_nav": "bills", "obj": None, "suppliers": _suppliers(db),
         "settings": get_settings(db), "today": date.today().isoformat(),
         "due_date": (date.today() + timedelta(days=30)).isoformat()},
    )


@router.post("/bills/new")
async def create_bill(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    bill = SupplierBill(
        number=_next_number(db, SupplierBill, "BILL"),
        supplier_id=int(form["supplier_id"]),
        supplier_ref=form.get("supplier_ref") or "",
        date=date.fromisoformat(form.get("date") or date.today().isoformat()),
        due_date=date.fromisoformat(form["due_date"]) if form.get("due_date") else None,
        tax_pct=_f(form, "tax_pct", float, get_settings(db).tax_pct),
        notes=form.get("notes") or "",
    )
    db.add(bill)
    db.commit()
    flash(request, f"Bill {bill.number} created — add items.", "success")
    return RedirectResponse(f"/bills/{bill.id}", status_code=303)


@router.get("/bills/{bid}", response_class=HTMLResponse)
def view_bill(bid: int, request: Request, db: Session = Depends(get_db)):
    bill = db.get(SupplierBill, bid)
    if not bill:
        return RedirectResponse("/bills", status_code=303)
    return templates.TemplateResponse(
        request, "purchasing/bill_view.html",
        {"active_nav": "bills", "bill": bill, "settings": get_settings(db),
         "methods": PAYMENT_METHODS, "today": date.today().isoformat()},
    )


@router.post("/bills/{bid}/items/add")
async def add_bill_item(bid: int, request: Request, db: Session = Depends(get_db)):
    bill = db.get(SupplierBill, bid)
    if bill:
        form = await request.form()
        bill.items.append(SupplierBillItem(
            line_no=len(bill.items) + 1, description=form.get("description") or "",
            quantity=_f(form, "quantity", float, 1), unit_price=_f(form, "unit_price", float, 0)))
        db.commit()
    return RedirectResponse(f"/bills/{bid}", status_code=303)


@router.post("/bills/{bid}/items/{item_id}/delete")
def delete_bill_item(bid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    it = db.get(SupplierBillItem, item_id)
    if it and it.bill_id == bid:
        db.delete(it)
        db.commit()
    return RedirectResponse(f"/bills/{bid}", status_code=303)


@router.post("/bills/{bid}/payments/add")
async def add_bill_payment(bid: int, request: Request, db: Session = Depends(get_db)):
    bill = db.get(SupplierBill, bid)
    if bill:
        form = await request.form()
        amount = _f(form, "amount", float, 0)
        if amount > 0:
            bill.payments.append(SupplierPayment(
                date=date.fromisoformat(form.get("date") or date.today().isoformat()),
                amount=amount, method=form.get("method") or "Bank Transfer",
                reference=form.get("reference") or "", notes=form.get("notes") or ""))
            db.commit()
            flash(request, "Payment recorded.", "success")
    return RedirectResponse(f"/bills/{bid}", status_code=303)


@router.post("/bills/{bid}/payments/{pid}/delete")
def delete_bill_payment(bid: int, pid: int, request: Request, db: Session = Depends(get_db)):
    p = db.get(SupplierPayment, pid)
    if p and p.bill_id == bid:
        db.delete(p)
        db.commit()
    return RedirectResponse(f"/bills/{bid}", status_code=303)


@router.post("/bills/{bid}/cancel")
def cancel_bill(bid: int, request: Request, db: Session = Depends(get_db)):
    bill = db.get(SupplierBill, bid)
    if bill:
        bill.cancelled = not bill.cancelled
        db.commit()
    return RedirectResponse(f"/bills/{bid}", status_code=303)


@router.post("/bills/{bid}/delete")
def delete_bill(bid: int, request: Request, db: Session = Depends(get_db)):
    bill = db.get(SupplierBill, bid)
    if bill:
        db.delete(bill)
        db.commit()
        flash(request, f"Bill {bill.number} deleted.", "success")
    return RedirectResponse("/bills", status_code=303)


AP_BUCKETS = ["Current", "1–30", "31–60", "61–90", "90+"]


def _bucket(days: int) -> str:
    if days <= 0:
        return "Current"
    if days <= 30:
        return "1–30"
    if days <= 60:
        return "31–60"
    if days <= 90:
        return "61–90"
    return "90+"


@router.get("/ap.csv")
def ap_csv(request: Request, db: Session = Depends(get_db)):
    open_bills = [b for b in db.execute(select(SupplierBill)).scalars().all()
                  if not b.cancelled and b.balance > 0.005]
    rows = []
    for bill in sorted(open_bills, key=lambda x: (x.supplier.name, x.date)):
        ref = bill.due_date or bill.date
        rows.append([bill.supplier.name, bill.number, bill.date.isoformat(),
                     (bill.due_date or bill.date).isoformat(), _bucket((date.today() - ref).days),
                     f"{bill.balance:.2f}"])
    return csv_response("accounts-payable.csv",
                        ["Supplier", "Bill", "Date", "Due", "Aging", "Balance"], rows)


@router.get("/ap", response_class=HTMLResponse)
def ap_report(request: Request, db: Session = Depends(get_db)):
    open_bills = [b for b in db.execute(select(SupplierBill)).scalars().all()
                  if not b.cancelled and b.balance > 0.005]
    rows: dict[int, dict] = {}
    totals = {b: 0.0 for b in AP_BUCKETS}
    grand = 0.0
    for bill in open_bills:
        ref = bill.due_date or bill.date
        bucket = _bucket((date.today() - ref).days)
        r = rows.setdefault(bill.supplier_id, {
            "supplier": bill.supplier, "total": 0.0, "buckets": {b: 0.0 for b in AP_BUCKETS}})
        r["buckets"][bucket] += bill.balance
        r["total"] += bill.balance
        totals[bucket] += bill.balance
        grand += bill.balance
    supplier_rows = sorted(rows.values(), key=lambda r: -r["total"])
    return templates.TemplateResponse(
        request, "purchasing/ap.html",
        {"active_nav": "ap", "settings": get_settings(db), "buckets": AP_BUCKETS,
         "supplier_rows": supplier_rows, "totals": totals, "grand": round(grand, 2)},
    )
