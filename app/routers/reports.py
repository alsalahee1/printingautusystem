"""Reports & business insight (Module 6).

Turns the captured documents into management views:
  * a financial snapshot (AR, AP, sales/purchases this month, stock value),
  * a sales summary by month and by customer over a date range,
  * job profitability (revenue vs estimated cost vs actual paper issued),
  * stock valuation by category,
  * printable per-customer statements.
"""
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Customer,
    Expense,
    Invoice,
    Job,
    StockItem,
    StockMovement,
    SupplierBill,
)
from ..web import templates
from .quotations import get_settings

router = APIRouter()


def _range(request: Request):
    """Parse ?start&end query params; default to the current calendar year."""
    qp = request.query_params
    today = date.today()
    try:
        start = date.fromisoformat(qp["start"]) if qp.get("start") else today.replace(month=1, day=1)
    except ValueError:
        start = today.replace(month=1, day=1)
    try:
        end = date.fromisoformat(qp["end"]) if qp.get("end") else today
    except ValueError:
        end = today
    return start, end


def _active_invoices(db):
    return [i for i in db.execute(select(Invoice)).scalars().all() if not i.cancelled]


def _active_bills(db):
    return [b for b in db.execute(select(SupplierBill)).scalars().all() if not b.cancelled]


# --------------------------------------------------------------------------- #
# Landing — financial snapshot
# --------------------------------------------------------------------------- #
@router.get("/reports", response_class=HTMLResponse)
def reports_index(request: Request, db: Session = Depends(get_db)):
    invoices = _active_invoices(db)
    bills = _active_bills(db)
    today = date.today()
    month_start = today.replace(day=1)

    ar = round(sum(i.balance for i in invoices), 2)
    ap = round(sum(b.balance for b in bills), 2)
    sales_month = round(sum(i.total for i in invoices if i.date >= month_start), 2)
    purch_month = round(sum(b.total for b in bills if b.date >= month_start), 2)
    stock_value = round(sum((s.qty_on_hand or 0) * (s.cost_price or 0)
                            for s in db.execute(select(StockItem)).scalars()), 2)

    kpis = [
        {"label": "Accounts Receivable", "value": ar, "icon": "bi-cash-coin", "url": "/ar", "color": "danger"},
        {"label": "Accounts Payable", "value": ap, "icon": "bi-cash-stack", "url": "/ap", "color": "warning"},
        {"label": "Sales this month", "value": sales_month, "icon": "bi-graph-up-arrow", "url": "/reports/sales", "color": "success"},
        {"label": "Purchases this month", "value": purch_month, "icon": "bi-bag", "url": "/reports/sales", "color": "info"},
        {"label": "Stock value", "value": stock_value, "icon": "bi-box-seam", "url": "/reports/stock-valuation", "color": "primary"},
    ]
    return templates.TemplateResponse(
        request, "reports/index.html",
        {"active_nav": "reports", "settings": get_settings(db), "kpis": kpis},
    )


# --------------------------------------------------------------------------- #
# Sales summary
# --------------------------------------------------------------------------- #
@router.get("/reports/sales", response_class=HTMLResponse)
def sales_report(request: Request, db: Session = Depends(get_db)):
    start, end = _range(request)
    invoices = [i for i in _active_invoices(db) if start <= i.date <= end]

    by_month: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "paid": 0.0, "count": 0})
    by_customer: dict[int, dict] = defaultdict(lambda: {"name": "", "total": 0.0, "balance": 0.0, "count": 0})
    for i in invoices:
        key = i.date.strftime("%Y-%m")
        by_month[key]["total"] += i.total
        by_month[key]["paid"] += i.paid_amount
        by_month[key]["count"] += 1
        c = by_customer[i.customer_id]
        c["name"] = i.customer.name
        c["total"] += i.total
        c["balance"] += i.balance
        c["count"] += 1

    months = sorted(by_month.items())
    customers = sorted(by_customer.values(), key=lambda r: -r["total"])
    totals = {
        "total": round(sum(i.total for i in invoices), 2),
        "paid": round(sum(i.paid_amount for i in invoices), 2),
        "balance": round(sum(i.balance for i in invoices), 2),
        "count": len(invoices),
    }
    return templates.TemplateResponse(
        request, "reports/sales.html",
        {"active_nav": "reports", "settings": get_settings(db),
         "start": start.isoformat(), "end": end.isoformat(),
         "months": months, "customers": customers, "totals": totals},
    )


# --------------------------------------------------------------------------- #
# Job profitability
# --------------------------------------------------------------------------- #
@router.get("/reports/profitability", response_class=HTMLResponse)
def profitability_report(request: Request, db: Session = Depends(get_db)):
    jobs = db.execute(select(Job).order_by(Job.id.desc())).scalars().all()
    invoices = _active_invoices(db)
    inv_by_job: dict[int, float] = defaultdict(float)
    for i in invoices:
        if i.job_id:
            inv_by_job[i.job_id] += i.total

    # Actual paper issued per job (Job Usage movements, by job number reference).
    usage = db.execute(
        select(StockMovement).where(StockMovement.type == "Job Usage")
    ).scalars().all()
    actual_by_ref: dict[str, float] = defaultdict(float)
    for m in usage:
        actual_by_ref[m.reference] += abs(m.quantity) * (m.unit_cost or 0)

    rows = []
    tot = {"revenue": 0.0, "cost": 0.0, "margin": 0.0}
    for job in jobs:
        q = job.quotation
        quoted_rev = round(sum(it.line_total for it in q.items), 2) if q else 0.0
        est_cost = round(sum(
            it.paper_cost + it.ink_cost + it.plate_cost + it.makeready_cost
            + it.press_cost + it.finishing_cost for it in q.items), 2) if q else 0.0
        invoiced = round(inv_by_job.get(job.id, 0.0), 2)
        revenue = invoiced if invoiced > 0 else quoted_rev
        actual_paper = round(actual_by_ref.get(job.number, 0.0), 2)
        margin = round(revenue - est_cost, 2)
        margin_pct = round(margin / revenue * 100, 1) if revenue else 0.0
        rows.append({
            "job": job, "revenue": revenue, "invoiced": invoiced, "quoted": quoted_rev,
            "est_cost": est_cost, "actual_paper": actual_paper,
            "margin": margin, "margin_pct": margin_pct,
        })
        tot["revenue"] += revenue
        tot["cost"] += est_cost
        tot["margin"] += margin
    for k in tot:
        tot[k] = round(tot[k], 2)
    tot["margin_pct"] = round(tot["margin"] / tot["revenue"] * 100, 1) if tot["revenue"] else 0.0
    return templates.TemplateResponse(
        request, "reports/profitability.html",
        {"active_nav": "reports", "settings": get_settings(db), "rows": rows, "tot": tot},
    )


# --------------------------------------------------------------------------- #
# Stock valuation
# --------------------------------------------------------------------------- #
@router.get("/reports/stock-valuation", response_class=HTMLResponse)
def stock_valuation(request: Request, db: Session = Depends(get_db)):
    items = db.execute(select(StockItem).order_by(StockItem.category, StockItem.name)).scalars().all()
    groups: dict[str, dict] = defaultdict(lambda: {"items": [], "value": 0.0})
    grand = 0.0
    for s in items:
        value = round((s.qty_on_hand or 0) * (s.cost_price or 0), 2)
        groups[s.category]["items"].append((s, value))
        groups[s.category]["value"] += value
        grand += value
    return templates.TemplateResponse(
        request, "reports/stock_valuation.html",
        {"active_nav": "reports", "settings": get_settings(db),
         "groups": sorted(groups.items()), "grand": round(grand, 2)},
    )


# --------------------------------------------------------------------------- #
# Customer statements
# --------------------------------------------------------------------------- #
@router.get("/reports/statements", response_class=HTMLResponse)
def statements_index(request: Request, db: Session = Depends(get_db)):
    invoices = _active_invoices(db)
    bal_by_customer: dict[int, float] = defaultdict(float)
    for i in invoices:
        bal_by_customer[i.customer_id] += i.balance
    customers = db.execute(select(Customer).order_by(Customer.name)).scalars().all()
    rows = [(c, round(bal_by_customer.get(c.id, 0.0), 2)) for c in customers]
    return templates.TemplateResponse(
        request, "reports/statements.html",
        {"active_nav": "reports", "settings": get_settings(db), "rows": rows},
    )


@router.get("/reports/statements/{cid}", response_class=HTMLResponse)
def customer_statement(cid: int, request: Request, db: Session = Depends(get_db)):
    cust = db.get(Customer, cid)
    if not cust:
        return RedirectResponse("/reports/statements", status_code=303)
    invoices = sorted(
        [i for i in _active_invoices(db) if i.customer_id == cid],
        key=lambda i: i.date,
    )
    total = round(sum(i.total for i in invoices), 2)
    paid = round(sum(i.paid_amount for i in invoices), 2)
    balance = round(sum(i.balance for i in invoices), 2)
    return templates.TemplateResponse(
        request, "reports/statement.html",
        {"settings": get_settings(db), "cust": cust, "invoices": invoices,
         "total": total, "paid": paid, "balance": balance, "today": date.today()},
    )


def _sst_period(today: date):
    """The Malaysian bi-monthly SST taxable period containing `today`
    (Jan-Feb, Mar-Apr, May-Jun, Jul-Aug, Sep-Oct, Nov-Dec)."""
    start_month = ((today.month - 1) // 2) * 2 + 1
    start = date(today.year, start_month, 1)
    if start_month + 2 > 12:
        end = date(today.year, 12, 31)
    else:
        end = date(today.year, start_month + 2, 1) - timedelta(days=1)
    return start, end


@router.get("/reports/sst02", response_class=HTMLResponse)
def sst02_report(request: Request, db: Session = Depends(get_db)):
    qp = request.query_params
    ds, de = _sst_period(date.today())
    try:
        start = date.fromisoformat(qp["start"]) if qp.get("start") else ds
    except ValueError:
        start = ds
    try:
        end = date.fromisoformat(qp["end"]) if qp.get("end") else de
    except ValueError:
        end = de

    # Output tax (sales tax collected) from customer invoices, grouped by rate.
    out_by_rate: dict[float, dict] = defaultdict(lambda: {"taxable": 0.0, "tax": 0.0})
    output_tax = taxable_sales = 0.0
    for inv in _active_invoices(db):
        if not (start <= inv.date <= end) or inv.tax_pct <= 0:
            continue
        out_by_rate[inv.tax_pct]["taxable"] += inv.subtotal
        out_by_rate[inv.tax_pct]["tax"] += inv.tax_amount
        taxable_sales += inv.subtotal
        output_tax += inv.tax_amount

    # Input tax (sales tax paid) from supplier bills and direct expenses.
    input_tax = taxable_purchases = 0.0
    for b in _active_bills(db):
        if start <= b.date <= end and b.tax_pct > 0:
            taxable_purchases += b.subtotal
            input_tax += b.tax_amount
    for ex in db.execute(select(Expense)).scalars():
        if start <= ex.date <= end and ex.tax_pct > 0:
            taxable_purchases += ex.amount
            input_tax += ex.tax_amount

    output_tax = round(output_tax, 2)
    input_tax = round(input_tax, 2)
    rate_rows = [{"rate": r, "taxable": round(v["taxable"], 2), "tax": round(v["tax"], 2)}
                 for r, v in sorted(out_by_rate.items())]
    return templates.TemplateResponse(
        request, "reports/sst02.html",
        {"active_nav": "sst02", "settings": get_settings(db),
         "start": start.isoformat(), "end": end.isoformat(),
         "rate_rows": rate_rows,
         "taxable_sales": round(taxable_sales, 2), "output_tax": output_tax,
         "taxable_purchases": round(taxable_purchases, 2), "input_tax": input_tax,
         "net_payable": round(output_tax - input_tax, 2)},
    )
