"""Expenses & bank reconciliation (Module 12).

Expenses are stored documents that auto-post to the GL (Dr expense + SST input,
Cr cash/bank). The reconciliation worksheet lists every posting to a chosen
bank/cash account and lets the user tick which have cleared the bank statement;
cleared marks persist (ReconciledTxn) keyed by each posting's stable key.
"""
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import gl
from ..database import get_db
from ..models import Account, Expense, ReconciledTxn
from ..web import flash, templates
from .quotations import _f, get_settings

router = APIRouter()


def _next_number(db: Session) -> str:
    n = (db.query(Expense).count() or 0) + 1
    while db.query(Expense).filter(Expense.number == f"EXP-{n:04d}").first():
        n += 1
    return f"EXP-{n:04d}"


def _asset_accounts(db):
    return db.execute(select(Account).where(Account.type == "Asset", Account.active == True)
                      .order_by(Account.code)).scalars().all()


def _expense_accounts(db):
    return db.execute(select(Account).where(Account.type == "Expense", Account.active == True)
                      .order_by(Account.code)).scalars().all()


# --------------------------------------------------------------------------- #
# Expenses
# --------------------------------------------------------------------------- #
@router.get("/expenses", response_class=HTMLResponse)
def list_expenses(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(select(Expense).order_by(Expense.id.desc())).scalars().all()
    total = round(sum(e.total for e in rows), 2)
    return templates.TemplateResponse(
        request, "expenses/list.html",
        {"active_nav": "expenses", "rows": rows, "settings": get_settings(db), "total": total})


@router.get("/expenses/new", response_class=HTMLResponse)
def new_expense(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "expenses/form.html",
        {"active_nav": "expenses", "settings": get_settings(db),
         "paid_from": _asset_accounts(db), "categories": _expense_accounts(db),
         "today": date.today().isoformat()})


@router.post("/expenses/new")
async def create_expense(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    if not form.get("paid_from_account_id") or not form.get("expense_account_id"):
        flash(request, "Choose both the paid-from and expense accounts.", "warning")
        return RedirectResponse("/expenses/new", status_code=303)
    ex = Expense(
        number=_next_number(db),
        date=date.fromisoformat(form.get("date") or date.today().isoformat()),
        paid_from_account_id=int(form["paid_from_account_id"]),
        expense_account_id=int(form["expense_account_id"]),
        payee=form.get("payee") or "",
        description=form.get("description") or "",
        amount=_f(form, "amount", float, 0),
        tax_pct=_f(form, "tax_pct", float, 0),
        reference=form.get("reference") or "",
    )
    if ex.amount <= 0:
        flash(request, "Amount must be greater than zero.", "warning")
        return RedirectResponse("/expenses/new", status_code=303)
    db.add(ex)
    db.commit()
    flash(request, f"Expense {ex.number} recorded and posted to the ledger.", "success")
    return RedirectResponse("/expenses", status_code=303)


@router.post("/expenses/{eid}/delete")
def delete_expense(eid: int, request: Request, db: Session = Depends(get_db)):
    ex = db.get(Expense, eid)
    if ex:
        db.delete(ex)
        db.commit()
        flash(request, f"Expense {ex.number} deleted.", "success")
    return RedirectResponse("/expenses", status_code=303)


# --------------------------------------------------------------------------- #
# Bank / cash reconciliation
# --------------------------------------------------------------------------- #
@router.get("/reconcile", response_class=HTMLResponse)
def reconcile_index(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "expenses/reconcile_index.html",
        {"active_nav": "reconcile", "accounts": _asset_accounts(db)})


@router.get("/reconcile/{aid}", response_class=HTMLResponse)
def reconcile_account(aid: int, request: Request, db: Session = Depends(get_db)):
    acc = db.get(Account, aid)
    if not acc:
        return RedirectResponse("/reconcile", status_code=303)
    # Optional statement balance entered by the user (live, not persisted).
    try:
        statement = float(request.query_params.get("statement", "") or 0)
    except ValueError:
        statement = 0.0

    postings = [p for p in gl.iter_postings(db) if p.account_id == aid]
    postings.sort(key=lambda p: (p.date, p.source))
    cleared_keys = {r.txn_key for r in db.execute(
        select(ReconciledTxn).where(ReconciledTxn.account_id == aid)).scalars()}

    book = cleared = 0.0
    rows = []
    for p in postings:
        signed = round((p.debit - p.credit) if acc.is_debit_normal else (p.credit - p.debit), 2)
        book += signed
        is_cleared = p.key in cleared_keys
        if is_cleared:
            cleared += signed
        rows.append({"p": p, "signed": signed, "cleared": is_cleared})
    book = round(book, 2)
    cleared = round(cleared, 2)
    difference = round(statement - cleared, 2)
    return templates.TemplateResponse(
        request, "expenses/reconcile.html",
        {"active_nav": "reconcile", "settings": get_settings(db), "acc": acc, "rows": rows,
         "book": book, "cleared": cleared, "statement": statement, "difference": difference,
         "uncleared": round(book - cleared, 2)})


@router.post("/reconcile/{aid}/toggle")
async def reconcile_toggle(aid: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    key = form.get("key")
    statement = form.get("statement") or ""
    if key:
        existing = db.execute(select(ReconciledTxn).where(
            ReconciledTxn.account_id == aid, ReconciledTxn.txn_key == key)).scalar_one_or_none()
        if existing:
            db.delete(existing)
        else:
            db.add(ReconciledTxn(account_id=aid, txn_key=key))
        db.commit()
    suffix = f"?statement={statement}" if statement else ""
    return RedirectResponse(f"/reconcile/{aid}{suffix}", status_code=303)
