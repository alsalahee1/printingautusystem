"""Accounting screens (Module 4): Invoices, Payments/Receipts, AR, Delivery Orders.

Invoices can be raised from an approved quotation, from a job (pulling pricing
from the job's originating quotation), or blank. Payments are receipts recorded
against an invoice; the invoice status (Unpaid / Partial / Paid) and the
Accounts-Receivable aging are derived from invoice totals minus payments.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import einvoice, pdf
from ..database import get_db
from ..exporting import csv_response
from ..mailer import send_email
from ..models import (
    PAYMENT_METHODS,
    Customer,
    DeliveryOrder,
    DeliveryOrderItem,
    Invoice,
    InvoiceItem,
    Job,
    Payment,
    Quotation,
)
from ..web import flash, templates
from .quotations import _f, get_settings

router = APIRouter()


def _next_number(db: Session, model, prefix: str) -> str:
    """Sequential document number (PREFIX-0001) that skips any taken value."""
    n = (db.query(model).count() or 0) + 1
    while db.query(model).filter(model.number == f"{prefix}-{n:04d}").first():
        n += 1
    return f"{prefix}-{n:04d}"


def _customers(db: Session):
    return db.execute(
        select(Customer).where(Customer.active == True).order_by(Customer.name)
    ).scalars().all()


# --------------------------------------------------------------------------- #
# Invoices
# --------------------------------------------------------------------------- #
@router.get("/invoices", response_class=HTMLResponse)
def list_invoices(request: Request, db: Session = Depends(get_db), status: str | None = None):
    invoices = db.execute(select(Invoice).order_by(Invoice.id.desc())).scalars().all()
    if status:
        invoices = [i for i in invoices if i.status == status]
    settings = get_settings(db)
    total_out = round(sum(i.balance for i in invoices if not i.cancelled), 2)
    return templates.TemplateResponse(
        request, "invoices/list.html",
        {"active_nav": "invoices", "rows": invoices, "settings": settings,
         "active_status": status, "total_out": total_out},
    )


@router.get("/invoices/new", response_class=HTMLResponse)
def new_invoice(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    return templates.TemplateResponse(
        request, "invoices/form.html",
        {"active_nav": "invoices", "obj": None, "customers": _customers(db),
         "settings": settings, "today": date.today().isoformat(),
         "due_date": (date.today() + timedelta(days=30)).isoformat()},
    )


@router.post("/invoices/new")
async def create_invoice(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    settings = get_settings(db)
    inv = Invoice(
        number=_next_number(db, Invoice, "INV"),
        date=date.fromisoformat(form.get("date") or date.today().isoformat()),
        due_date=date.fromisoformat(form["due_date"]) if form.get("due_date") else None,
        customer_id=int(form["customer_id"]),
        tax_pct=_f(form, "tax_pct", float, settings.tax_pct),
        notes=form.get("notes") or "",
        terms=form.get("terms") or "",
    )
    db.add(inv)
    db.commit()
    flash(request, f"Invoice {inv.number} created — add line items.", "success")
    return RedirectResponse(f"/invoices/{inv.id}", status_code=303)


def _invoice_from_lines(db, customer_id, lines, *, job_id=None, quotation_id=None):
    """Create an invoice with the given (description, qty, unit_price) lines."""
    settings = get_settings(db)
    cust = db.get(Customer, customer_id)
    terms_days = cust.payment_terms_days if cust else 30
    inv = Invoice(
        number=_next_number(db, Invoice, "INV"),
        date=date.today(),
        due_date=date.today() + timedelta(days=terms_days),
        customer_id=customer_id,
        job_id=job_id,
        quotation_id=quotation_id,
        tax_pct=settings.tax_pct,
        terms=settings.quotation_terms,
    )
    for i, (desc, qty, price) in enumerate(lines, start=1):
        inv.items.append(InvoiceItem(line_no=i, description=desc, quantity=qty, unit_price=price))
    db.add(inv)
    db.commit()
    return inv


@router.post("/invoices/from-quotation/{qid}")
def invoice_from_quotation(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q or not q.items:
        flash(request, "Quotation has no items to invoice.", "warning")
        return RedirectResponse(f"/quotations/{qid}", status_code=303)
    lines = [
        (f"{it.title} ({it.finished_width_mm:g}×{it.finished_height_mm:g}mm, "
         f"{it.colors_front}/{it.colors_back})", it.quantity, it.unit_price)
        for it in q.items
    ]
    inv = _invoice_from_lines(db, q.customer_id, lines, quotation_id=q.id)
    inv.tax_pct = q.tax_pct
    db.commit()
    flash(request, f"Invoice {inv.number} created from {q.number}.", "success")
    return RedirectResponse(f"/invoices/{inv.id}", status_code=303)


@router.post("/invoices/from-job/{jid}")
def invoice_from_job(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if not job:
        return RedirectResponse("/jobs", status_code=303)
    # Pull pricing from the originating quotation when available.
    price_by_line = {}
    if job.quotation and job.quotation.items:
        price_by_line = {qi.line_no: qi.unit_price for qi in job.quotation.items}
    lines = [
        (f"{it.title} ({it.finished_width_mm:g}×{it.finished_height_mm:g}mm, "
         f"{it.colors_front}/{it.colors_back})", it.quantity, price_by_line.get(it.line_no, 0.0))
        for it in job.items
    ] or [(job.title or job.number, 1, 0.0)]
    inv = _invoice_from_lines(db, job.customer_id, lines, job_id=job.id,
                              quotation_id=job.quotation_id)
    flash(request, f"Invoice {inv.number} created from {job.number}.", "success")
    return RedirectResponse(f"/invoices/{inv.id}", status_code=303)


@router.get("/invoices/{iid}", response_class=HTMLResponse)
def view_invoice(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        flash(request, "Invoice not found.", "danger")
        return RedirectResponse("/invoices", status_code=303)
    return templates.TemplateResponse(
        request, "invoices/view.html",
        {"active_nav": "invoices", "inv": inv, "settings": get_settings(db),
         "methods": PAYMENT_METHODS, "today": date.today().isoformat()},
    )


@router.get("/invoices/{iid}/edit", response_class=HTMLResponse)
def edit_invoice(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        return RedirectResponse("/invoices", status_code=303)
    return templates.TemplateResponse(
        request, "invoices/form.html",
        {"active_nav": "invoices", "obj": inv, "customers": _customers(db),
         "settings": get_settings(db),
         "today": inv.date.isoformat(),
         "due_date": inv.due_date.isoformat() if inv.due_date else ""},
    )


@router.post("/invoices/{iid}/edit")
async def update_invoice(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        return RedirectResponse("/invoices", status_code=303)
    form = await request.form()
    inv.date = date.fromisoformat(form.get("date") or inv.date.isoformat())
    inv.due_date = date.fromisoformat(form["due_date"]) if form.get("due_date") else None
    inv.customer_id = int(form["customer_id"])
    inv.tax_pct = _f(form, "tax_pct", float, inv.tax_pct)
    inv.notes = form.get("notes") or ""
    inv.terms = form.get("terms") or ""
    db.commit()
    flash(request, "Invoice updated.", "success")
    return RedirectResponse(f"/invoices/{inv.id}", status_code=303)


@router.post("/invoices/{iid}/cancel")
def cancel_invoice(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if inv:
        inv.cancelled = not inv.cancelled
        db.commit()
        flash(request, f"Invoice {'cancelled' if inv.cancelled else 'reopened'}.", "success")
    return RedirectResponse(f"/invoices/{iid}", status_code=303)


@router.post("/invoices/{iid}/delete")
def delete_invoice(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if inv:
        db.delete(inv)
        db.commit()
        flash(request, f"Invoice {inv.number} deleted.", "success")
    return RedirectResponse("/invoices", status_code=303)


@router.get("/invoices/{iid}/print", response_class=HTMLResponse)
def print_invoice(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        return RedirectResponse("/invoices", status_code=303)
    return templates.TemplateResponse(
        request, "invoices/print.html", {"inv": inv, "settings": get_settings(db)}
    )


def _pdf_response(data: bytes, filename: str) -> Response:
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/invoices/{iid}/pdf")
def invoice_pdf_view(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        return RedirectResponse("/invoices", status_code=303)
    return _pdf_response(pdf.invoice_pdf(inv, get_settings(db)), f"{inv.number}.pdf")


@router.post("/invoices/{iid}/email")
async def invoice_email(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        return RedirectResponse("/invoices", status_code=303)
    settings = get_settings(db)
    form = await request.form()
    to = (form.get("to") or inv.customer.email or "").strip()
    data = pdf.invoice_pdf(inv, settings)
    ok, msg = send_email(
        settings, to,
        subject=f"Invoice {inv.number} from {settings.company_name}",
        body=f"Dear {inv.customer.name},\n\nPlease find attached invoice {inv.number} "
             f"for {settings.currency} {inv.total:,.2f}.\n\nThank you.\n{settings.company_name}",
        attachment=data, attachment_name=f"{inv.number}.pdf")
    flash(request, msg, "success" if ok else "danger")
    return RedirectResponse(f"/invoices/{iid}", status_code=303)


@router.get("/invoices/{iid}/einvoice")
def invoice_einvoice(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if not inv:
        return RedirectResponse("/invoices", status_code=303)
    settings = get_settings(db)
    return JSONResponse({
        "warnings": einvoice.validation_warnings(inv, settings),
        "document": einvoice.build_einvoice(inv, settings),
    })


@router.get("/delivery-orders/{did}/pdf")
def do_pdf_view(did: int, request: Request, db: Session = Depends(get_db)):
    do = db.get(DeliveryOrder, did)
    if not do:
        return RedirectResponse("/delivery-orders", status_code=303)
    return _pdf_response(pdf.delivery_order_pdf(do, get_settings(db)), f"{do.number}.pdf")


# --- invoice line items (inline add / edit / delete) --- #
@router.post("/invoices/{iid}/items/add")
async def add_invoice_item(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if inv:
        form = await request.form()
        inv.items.append(InvoiceItem(
            line_no=len(inv.items) + 1,
            description=form.get("description") or "",
            quantity=_f(form, "quantity", float, 1),
            unit_price=_f(form, "unit_price", float, 0),
        ))
        db.commit()
    return RedirectResponse(f"/invoices/{iid}", status_code=303)


@router.post("/invoices/{iid}/items/{item_id}/edit")
async def edit_invoice_item(iid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    it = db.get(InvoiceItem, item_id)
    if it and it.invoice_id == iid:
        form = await request.form()
        it.description = form.get("description") or ""
        it.quantity = _f(form, "quantity", float, it.quantity)
        it.unit_price = _f(form, "unit_price", float, it.unit_price)
        db.commit()
    return RedirectResponse(f"/invoices/{iid}", status_code=303)


@router.post("/invoices/{iid}/items/{item_id}/delete")
def delete_invoice_item(iid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    it = db.get(InvoiceItem, item_id)
    if it and it.invoice_id == iid:
        db.delete(it)
        db.commit()
    return RedirectResponse(f"/invoices/{iid}", status_code=303)


# --- payments / receipts --- #
@router.post("/invoices/{iid}/payments/add")
async def add_payment(iid: int, request: Request, db: Session = Depends(get_db)):
    inv = db.get(Invoice, iid)
    if inv:
        form = await request.form()
        amount = _f(form, "amount", float, 0)
        if amount > 0:
            inv.payments.append(Payment(
                date=date.fromisoformat(form.get("date") or date.today().isoformat()),
                amount=amount,
                method=form.get("method") or "Cash",
                reference=form.get("reference") or "",
                notes=form.get("notes") or "",
            ))
            db.commit()
            flash(request, "Payment recorded.", "success")
        else:
            flash(request, "Payment amount must be greater than zero.", "warning")
    return RedirectResponse(f"/invoices/{iid}", status_code=303)


@router.post("/invoices/{iid}/payments/{pid}/delete")
def delete_payment(iid: int, pid: int, request: Request, db: Session = Depends(get_db)):
    p = db.get(Payment, pid)
    if p and p.invoice_id == iid:
        db.delete(p)
        db.commit()
        flash(request, "Payment removed.", "success")
    return RedirectResponse(f"/invoices/{iid}", status_code=303)


# --------------------------------------------------------------------------- #
# Accounts Receivable — aging report
# --------------------------------------------------------------------------- #
AGING_BUCKETS = ["Current", "1–30", "31–60", "61–90", "90+"]


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


@router.get("/ar.csv")
def ar_csv(request: Request, db: Session = Depends(get_db)):
    open_invoices = [i for i in db.execute(select(Invoice)).scalars().all()
                     if not i.cancelled and i.balance > 0.005]
    rows = []
    for inv in sorted(open_invoices, key=lambda x: (x.customer.name, x.date)):
        ref = inv.due_date or inv.date
        rows.append([inv.customer.name, inv.number, inv.date.isoformat(),
                     (inv.due_date or inv.date).isoformat(), _bucket((date.today() - ref).days),
                     f"{inv.balance:.2f}"])
    return csv_response("accounts-receivable.csv",
                        ["Customer", "Invoice", "Date", "Due", "Aging", "Balance"], rows)


@router.get("/ar", response_class=HTMLResponse)
def ar_report(request: Request, db: Session = Depends(get_db)):
    open_invoices = [
        i for i in db.execute(select(Invoice)).scalars().all()
        if not i.cancelled and i.balance > 0.005
    ]
    # Group by customer with per-bucket balances.
    rows: dict[int, dict] = {}
    totals = {b: 0.0 for b in AGING_BUCKETS}
    grand = 0.0
    for inv in open_invoices:
        ref = inv.due_date or inv.date
        bucket = _bucket((date.today() - ref).days)
        r = rows.setdefault(inv.customer_id, {
            "customer": inv.customer, "total": 0.0,
            "buckets": {b: 0.0 for b in AGING_BUCKETS}, "invoices": [],
        })
        r["buckets"][bucket] += inv.balance
        r["total"] += inv.balance
        r["invoices"].append((inv, bucket))
        totals[bucket] += inv.balance
        grand += inv.balance
    customer_rows = sorted(rows.values(), key=lambda r: -r["total"])
    return templates.TemplateResponse(
        request, "ar.html",
        {"active_nav": "ar", "settings": get_settings(db), "buckets": AGING_BUCKETS,
         "customer_rows": customer_rows, "totals": totals, "grand": round(grand, 2)},
    )


# --------------------------------------------------------------------------- #
# Delivery Orders
# --------------------------------------------------------------------------- #
@router.get("/delivery-orders", response_class=HTMLResponse)
def list_dos(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(select(DeliveryOrder).order_by(DeliveryOrder.id.desc())).scalars().all()
    return templates.TemplateResponse(
        request, "deliveries/list.html", {"active_nav": "deliveries", "rows": rows}
    )


@router.post("/delivery-orders/from-job/{jid}")
def do_from_job(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if not job:
        return RedirectResponse("/jobs", status_code=303)
    do = DeliveryOrder(
        number=_next_number(db, DeliveryOrder, "DO"),
        date=date.today(), customer_id=job.customer_id, job_id=job.id,
        delivered_to=job.customer.address if job.customer else "",
    )
    for it in job.items:
        do.items.append(DeliveryOrderItem(
            line_no=it.line_no,
            description=f"{it.title} ({it.finished_width_mm:g}×{it.finished_height_mm:g}mm)",
            quantity=it.quantity,
        ))
    db.add(do)
    db.commit()
    flash(request, f"Delivery Order {do.number} created from {job.number}.", "success")
    return RedirectResponse(f"/delivery-orders/{do.id}", status_code=303)


@router.get("/delivery-orders/new", response_class=HTMLResponse)
def new_do(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "deliveries/form.html",
        {"active_nav": "deliveries", "obj": None, "customers": _customers(db),
         "today": date.today().isoformat()},
    )


@router.post("/delivery-orders/new")
async def create_do(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    do = DeliveryOrder(
        number=_next_number(db, DeliveryOrder, "DO"),
        date=date.fromisoformat(form.get("date") or date.today().isoformat()),
        customer_id=int(form["customer_id"]),
        delivered_to=form.get("delivered_to") or "",
        notes=form.get("notes") or "",
    )
    db.add(do)
    db.commit()
    flash(request, f"Delivery Order {do.number} created.", "success")
    return RedirectResponse(f"/delivery-orders/{do.id}", status_code=303)


@router.get("/delivery-orders/{did}", response_class=HTMLResponse)
def view_do(did: int, request: Request, db: Session = Depends(get_db)):
    do = db.get(DeliveryOrder, did)
    if not do:
        return RedirectResponse("/delivery-orders", status_code=303)
    return templates.TemplateResponse(
        request, "deliveries/view.html",
        {"active_nav": "deliveries", "do": do, "settings": get_settings(db)},
    )


@router.post("/delivery-orders/{did}/items/add")
async def add_do_item(did: int, request: Request, db: Session = Depends(get_db)):
    do = db.get(DeliveryOrder, did)
    if do:
        form = await request.form()
        do.items.append(DeliveryOrderItem(
            line_no=len(do.items) + 1,
            description=form.get("description") or "",
            quantity=_f(form, "quantity", float, 1),
        ))
        db.commit()
    return RedirectResponse(f"/delivery-orders/{did}", status_code=303)


@router.post("/delivery-orders/{did}/items/{item_id}/delete")
def delete_do_item(did: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    it = db.get(DeliveryOrderItem, item_id)
    if it and it.do_id == did:
        db.delete(it)
        db.commit()
    return RedirectResponse(f"/delivery-orders/{did}", status_code=303)


@router.post("/delivery-orders/{did}/delete")
def delete_do(did: int, request: Request, db: Session = Depends(get_db)):
    do = db.get(DeliveryOrder, did)
    if do:
        db.delete(do)
        db.commit()
        flash(request, f"Delivery Order {do.number} deleted.", "success")
    return RedirectResponse("/delivery-orders", status_code=303)


@router.get("/delivery-orders/{did}/print", response_class=HTMLResponse)
def print_do(did: int, request: Request, db: Session = Depends(get_db)):
    do = db.get(DeliveryOrder, did)
    if not do:
        return RedirectResponse("/delivery-orders", status_code=303)
    return templates.TemplateResponse(
        request, "deliveries/print.html", {"do": do, "settings": get_settings(db)}
    )
