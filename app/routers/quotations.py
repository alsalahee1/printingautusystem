"""Estimation & Quotation screens (Module 2).

A quotation is a header (customer, dates, status, tax) plus one or more line
items, where each item is a fully-costed print-job estimate produced by the
pure engine in app.estimating. The same engine backs a JSON /api/estimate
endpoint that powers the live price preview on the item form.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pdf
from ..database import get_db
from ..mailer import send_email
from ..estimating import EstimateInput, FinishingSpec, estimate
from ..models import (
    QUOTATION_STATUSES,
    Customer,
    FinishingType,
    Machine,
    Quotation,
    QuotationItem,
    QuotationItemFinishing,
    Settings,
    StockItem,
)
from ..web import flash, templates

router = APIRouter()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def get_settings(db: Session) -> Settings:
    """Return the singleton settings row, creating defaults on first use."""
    s = db.get(Settings, 1)
    if not s:
        s = Settings(id=1)
        db.add(s)
        db.commit()
    return s


def _f(form, key, cast=float, default=0):
    raw = form.get(key)
    if raw is None or raw == "":
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError):
        return default


def build_estimate_input(db: Session, settings: Settings, p: dict) -> EstimateInput:
    """Turn raw item parameters + master data into an EstimateInput."""
    paper = db.get(StockItem, p["paper_id"]) if p.get("paper_id") else None
    machine = db.get(Machine, p["machine_id"]) if p.get("machine_id") else None
    finishings = []
    for fid in p.get("finishing_ids", []):
        ft = db.get(FinishingType, fid)
        if ft:
            finishings.append(FinishingSpec(ft.name, ft.pricing_method, ft.unit_rate, ft.setup_cost))

    return EstimateInput(
        quantity=int(p.get("quantity") or 0),
        finished_width_mm=float(p.get("finished_width_mm") or 0),
        finished_height_mm=float(p.get("finished_height_mm") or 0),
        parent_width_mm=paper.sheet_width_mm if paper else 0,
        parent_height_mm=paper.sheet_height_mm if paper else 0,
        paper_cost_per_sheet=paper.cost_price if paper else 0,
        colors_front=int(p.get("colors_front") or 0),
        colors_back=int(p.get("colors_back") or 0),
        run_rate_per_hour=machine.run_rate_per_hour if machine else 0,
        hourly_rate=machine.hourly_rate if machine else 0,
        makeready_cost=machine.makeready_cost if machine else 0,
        makeready_minutes=machine.makeready_minutes if machine else 0,
        plate_cost=settings.plate_cost,
        ink_cost_per_1000=settings.ink_cost_per_1000,
        wastage_pct=float(p.get("wastage_pct") or 0),
        markup_pct=float(p.get("markup_pct") or 0),
        overhead_pct=settings.overhead_pct,
        finishings=finishings,
    )


def _form_choices(db: Session) -> dict:
    papers = db.execute(
        select(StockItem).where(StockItem.category == "Paper").order_by(StockItem.name)
    ).scalars().all()
    machines = db.execute(
        select(Machine).where(Machine.active == True).order_by(Machine.name)
    ).scalars().all()
    finishings = db.execute(
        select(FinishingType).where(FinishingType.active == True).order_by(FinishingType.name)
    ).scalars().all()
    return {"papers": papers, "machines": machines, "finishings": finishings}


# --------------------------------------------------------------------------- #
# Live estimate API
# --------------------------------------------------------------------------- #
@router.post("/api/estimate")
async def api_estimate(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    payload["finishing_ids"] = [int(x) for x in payload.get("finishing_ids", [])]
    settings = get_settings(db)
    result = estimate(build_estimate_input(db, settings, payload))
    return JSONResponse(
        {
            "currency": settings.currency,
            "ups": result.ups,
            "net_sheets": result.net_sheets,
            "spoilage_sheets": result.spoilage_sheets,
            "total_sheets": result.total_sheets,
            "num_runs": result.num_runs,
            "impressions": result.impressions,
            "num_plates": result.num_plates,
            "paper_cost": result.paper_cost,
            "ink_cost": result.ink_cost,
            "plate_cost": result.plate_cost,
            "makeready_cost": result.makeready_cost,
            "press_cost": result.press_cost,
            "finishing_cost": result.finishing_cost,
            "finishing_lines": [
                {"name": fl.name, "amount": fl.amount} for fl in result.finishing_lines
            ],
            "material_cost": result.material_cost,
            "production_cost": result.production_cost,
            "base_cost": result.base_cost,
            "overhead_amount": result.overhead_amount,
            "markup_amount": result.markup_amount,
            "selling_price": result.selling_price,
            "unit_price": result.unit_price,
            "warnings": result.warnings,
        }
    )


# --------------------------------------------------------------------------- #
# Quotation header CRUD
# --------------------------------------------------------------------------- #
@router.get("/quotations", response_class=HTMLResponse)
def list_quotations(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(select(Quotation).order_by(Quotation.id.desc())).scalars().all()
    settings = get_settings(db)
    return templates.TemplateResponse(
        request, "quotations/list.html",
        {"active_nav": "quotations", "rows": rows, "settings": settings},
    )


@router.get("/quotations/new", response_class=HTMLResponse)
def new_quotation(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    customers = db.execute(
        select(Customer).where(Customer.active == True).order_by(Customer.name)
    ).scalars().all()
    return templates.TemplateResponse(
        request, "quotations/form.html",
        {
            "active_nav": "quotations", "obj": None, "customers": customers,
            "statuses": QUOTATION_STATUSES, "settings": settings,
            "today": date.today().isoformat(),
            "valid_until": (date.today() + timedelta(days=settings.quotation_validity_days)).isoformat(),
        },
    )


@router.post("/quotations/new")
async def create_quotation(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    settings = get_settings(db)
    number = f"QT-{settings.next_quotation_no:04d}"
    settings.next_quotation_no += 1
    q = Quotation(
        number=number,
        date=date.fromisoformat(form.get("date") or date.today().isoformat()),
        valid_until=date.fromisoformat(form["valid_until"]) if form.get("valid_until") else None,
        customer_id=int(form["customer_id"]),
        status=form.get("status") or "Draft",
        tax_pct=_f(form, "tax_pct", float, settings.tax_pct),
        notes=form.get("notes") or "",
        terms=form.get("terms") or settings.quotation_terms,
    )
    db.add(q)
    db.commit()
    flash(request, f"Quotation {number} created — now add line items.", "success")
    return RedirectResponse(f"/quotations/{q.id}", status_code=303)


@router.get("/quotations/{qid}", response_class=HTMLResponse)
def view_quotation(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q:
        flash(request, "Quotation not found.", "danger")
        return RedirectResponse("/quotations", status_code=303)
    settings = get_settings(db)
    return templates.TemplateResponse(
        request, "quotations/view.html",
        {"active_nav": "quotations", "q": q, "settings": settings, "statuses": QUOTATION_STATUSES},
    )


@router.get("/quotations/{qid}/edit", response_class=HTMLResponse)
def edit_quotation(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q:
        flash(request, "Quotation not found.", "danger")
        return RedirectResponse("/quotations", status_code=303)
    customers = db.execute(
        select(Customer).where(Customer.active == True).order_by(Customer.name)
    ).scalars().all()
    return templates.TemplateResponse(
        request, "quotations/form.html",
        {
            "active_nav": "quotations", "obj": q, "customers": customers,
            "statuses": QUOTATION_STATUSES, "settings": get_settings(db),
            "today": q.date.isoformat(),
            "valid_until": q.valid_until.isoformat() if q.valid_until else "",
        },
    )


@router.post("/quotations/{qid}/edit")
async def update_quotation(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q:
        return RedirectResponse("/quotations", status_code=303)
    form = await request.form()
    q.date = date.fromisoformat(form.get("date") or q.date.isoformat())
    q.valid_until = date.fromisoformat(form["valid_until"]) if form.get("valid_until") else None
    q.customer_id = int(form["customer_id"])
    q.status = form.get("status") or q.status
    q.tax_pct = _f(form, "tax_pct", float, q.tax_pct)
    q.notes = form.get("notes") or ""
    q.terms = form.get("terms") or ""
    db.commit()
    flash(request, "Quotation updated.", "success")
    return RedirectResponse(f"/quotations/{q.id}", status_code=303)


@router.post("/quotations/{qid}/status")
async def set_status(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if q:
        form = await request.form()
        q.status = form.get("status") or q.status
        db.commit()
        flash(request, f"Quotation marked {q.status}.", "success")
    return RedirectResponse(f"/quotations/{qid}", status_code=303)


@router.post("/quotations/{qid}/delete")
def delete_quotation(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if q:
        db.delete(q)
        db.commit()
        flash(request, f"Quotation {q.number} deleted.", "success")
    return RedirectResponse("/quotations", status_code=303)


# --------------------------------------------------------------------------- #
# Quotation line items (the print-job estimates)
# --------------------------------------------------------------------------- #
def _item_form_ctx(request, db, q, item):
    settings = get_settings(db)
    ctx = {"active_nav": "quotations", "q": q, "obj": item, "settings": settings}
    ctx.update(_form_choices(db))
    return ctx


@router.get("/quotations/{qid}/items/new", response_class=HTMLResponse)
def new_item(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q:
        return RedirectResponse("/quotations", status_code=303)
    return templates.TemplateResponse(
        request, "quotations/item_form.html", _item_form_ctx(request, db, q, None)
    )


@router.get("/quotations/{qid}/items/{item_id}/edit", response_class=HTMLResponse)
def edit_item(qid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    item = db.get(QuotationItem, item_id)
    if not q or not item:
        return RedirectResponse(f"/quotations/{qid}", status_code=303)
    ctx = _item_form_ctx(request, db, q, item)
    ctx["selected_finishings"] = [f.finishing_id for f in item.finishings]
    return templates.TemplateResponse(request, "quotations/item_form.html", ctx)


def _apply_item(db, settings, item: QuotationItem, form):
    """Populate an item's spec from the form, run the estimate, store the snapshot."""
    finishing_ids = [int(x) for x in form.getlist("finishing_ids")]
    item.title = form.get("title") or ""
    item.quantity = int(_f(form, "quantity", int, 0))
    item.paper_id = int(form["paper_id"]) if form.get("paper_id") else None
    item.finished_width_mm = _f(form, "finished_width_mm", float, 0)
    item.finished_height_mm = _f(form, "finished_height_mm", float, 0)
    item.colors_front = int(_f(form, "colors_front", int, 0))
    item.colors_back = int(_f(form, "colors_back", int, 0))
    item.machine_id = int(form["machine_id"]) if form.get("machine_id") else None
    item.wastage_pct = _f(form, "wastage_pct", float, settings.default_wastage_pct)
    item.markup_pct = _f(form, "markup_pct", float, settings.default_markup_pct)
    item.notes = form.get("notes") or ""

    params = {
        "quantity": item.quantity, "paper_id": item.paper_id,
        "finished_width_mm": item.finished_width_mm, "finished_height_mm": item.finished_height_mm,
        "colors_front": item.colors_front, "colors_back": item.colors_back,
        "machine_id": item.machine_id, "wastage_pct": item.wastage_pct,
        "markup_pct": item.markup_pct, "finishing_ids": finishing_ids,
    }
    r = estimate(build_estimate_input(db, settings, params))

    item.ups = r.ups
    item.net_sheets = r.net_sheets
    item.total_sheets = r.total_sheets
    item.impressions = r.impressions
    item.num_plates = r.num_plates
    item.paper_cost = r.paper_cost
    item.ink_cost = r.ink_cost
    item.plate_cost = r.plate_cost
    item.makeready_cost = r.makeready_cost
    item.press_cost = r.press_cost
    item.finishing_cost = r.finishing_cost
    item.unit_price = r.unit_price
    item.line_total = r.selling_price

    # Replace finishing rows with freshly-costed ones.
    item.finishings.clear()
    for fl, fid in zip(r.finishing_lines, finishing_ids):
        item.finishings.append(QuotationItemFinishing(finishing_id=fid, amount=fl.amount))
    return r


@router.post("/quotations/{qid}/items/new")
async def create_item(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q:
        return RedirectResponse("/quotations", status_code=303)
    settings = get_settings(db)
    form = await request.form()
    item = QuotationItem(quotation_id=q.id, line_no=len(q.items) + 1)
    _apply_item(db, settings, item, form)
    db.add(item)
    db.commit()
    flash(request, "Line item added.", "success")
    return RedirectResponse(f"/quotations/{qid}", status_code=303)


@router.post("/quotations/{qid}/items/{item_id}/edit")
async def update_item(qid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(QuotationItem, item_id)
    if not item:
        return RedirectResponse(f"/quotations/{qid}", status_code=303)
    settings = get_settings(db)
    form = await request.form()
    _apply_item(db, settings, item, form)
    db.commit()
    flash(request, "Line item updated.", "success")
    return RedirectResponse(f"/quotations/{qid}", status_code=303)


@router.post("/quotations/{qid}/items/{item_id}/delete")
def delete_item(qid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(QuotationItem, item_id)
    if item:
        db.delete(item)
        db.commit()
        flash(request, "Line item removed.", "success")
    return RedirectResponse(f"/quotations/{qid}", status_code=303)


@router.get("/quotations/{qid}/print", response_class=HTMLResponse)
def print_quotation(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q:
        return RedirectResponse("/quotations", status_code=303)
    return templates.TemplateResponse(
        request, "quotations/print.html", {"q": q, "settings": get_settings(db)}
    )


@router.get("/quotations/{qid}/pdf")
def quotation_pdf_view(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q:
        return RedirectResponse("/quotations", status_code=303)
    data = pdf.quotation_pdf(q, get_settings(db))
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{q.number}.pdf"'})


@router.post("/quotations/{qid}/email")
async def quotation_email(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q:
        return RedirectResponse("/quotations", status_code=303)
    settings = get_settings(db)
    form = await request.form()
    to = (form.get("to") or q.customer.email or "").strip()
    data = pdf.quotation_pdf(q, settings)
    ok, msg = send_email(
        settings, to,
        subject=f"Quotation {q.number} from {settings.company_name}",
        body=f"Dear {q.customer.name},\n\nPlease find attached quotation {q.number} "
             f"for {settings.currency} {q.total:,.2f}.\n\nThank you.\n{settings.company_name}",
        attachment=data, attachment_name=f"{q.number}.pdf")
    flash(request, msg, "success" if ok else "danger")
    return RedirectResponse(f"/quotations/{qid}", status_code=303)


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "settings.html", {"active_nav": "settings", "s": get_settings(db)}
    )


@router.post("/settings")
async def save_settings(request: Request, db: Session = Depends(get_db)):
    s = get_settings(db)
    form = await request.form()
    s.company_name = form.get("company_name") or s.company_name
    s.company_address = form.get("company_address") or ""
    s.company_phone = form.get("company_phone") or ""
    s.company_email = form.get("company_email") or ""
    s.company_reg_no = form.get("company_reg_no") or ""
    s.company_tax_no = form.get("company_tax_no") or ""
    s.currency = form.get("currency") or s.currency
    s.plate_cost = _f(form, "plate_cost", float, s.plate_cost)
    s.ink_cost_per_1000 = _f(form, "ink_cost_per_1000", float, s.ink_cost_per_1000)
    s.default_wastage_pct = _f(form, "default_wastage_pct", float, s.default_wastage_pct)
    s.default_markup_pct = _f(form, "default_markup_pct", float, s.default_markup_pct)
    s.overhead_pct = _f(form, "overhead_pct", float, s.overhead_pct)
    s.tax_pct = _f(form, "tax_pct", float, s.tax_pct)
    s.quotation_validity_days = int(_f(form, "quotation_validity_days", int, s.quotation_validity_days))
    s.quotation_terms = form.get("quotation_terms") or ""
    s.smtp_host = form.get("smtp_host") or ""
    s.smtp_port = int(_f(form, "smtp_port", int, s.smtp_port or 587))
    s.smtp_from = form.get("smtp_from") or ""
    s.smtp_user = form.get("smtp_user") or ""
    if form.get("smtp_pass"):
        s.smtp_pass = form.get("smtp_pass")
    s.smtp_use_tls = form.get("smtp_use_tls") is not None
    db.commit()
    flash(request, "Settings saved.", "success")
    return RedirectResponse("/settings", status_code=303)
