"""General Ledger screens (Module 11): chart of accounts, journals, and the
Trial Balance / Profit & Loss / Balance Sheet / account-detail reports."""
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import gl
from ..database import get_db
from ..exporting import csv_response
from ..models import ACCOUNT_TYPES, Account, JournalEntry, JournalLine
from ..web import flash, templates
from .quotations import _f, get_settings

router = APIRouter()


def _date_range(request: Request):
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


# --------------------------------------------------------------------------- #
# Chart of accounts
# --------------------------------------------------------------------------- #
@router.get("/accounts", response_class=HTMLResponse)
def list_accounts(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(select(Account).order_by(Account.code)).scalars().all()
    return templates.TemplateResponse(
        request, "ledger/accounts.html",
        {"active_nav": "accounts", "rows": rows, "types": ACCOUNT_TYPES},
    )


@router.post("/accounts/new")
async def create_account(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    code = (form.get("code") or "").strip()
    name = (form.get("name") or "").strip()
    if not code or not name:
        flash(request, "Code and name are required.", "warning")
    elif db.execute(select(Account).where(Account.code == code)).scalar_one_or_none():
        flash(request, "That account code already exists.", "warning")
    else:
        db.add(Account(code=code, name=name,
                       type=form.get("type") if form.get("type") in ACCOUNT_TYPES else "Asset"))
        db.commit()
        flash(request, "Account created.", "success")
    return RedirectResponse("/accounts", status_code=303)


@router.post("/accounts/{aid}/update")
async def update_account(aid: int, request: Request, db: Session = Depends(get_db)):
    acc = db.get(Account, aid)
    if acc:
        form = await request.form()
        acc.name = form.get("name") or acc.name
        if form.get("type") in ACCOUNT_TYPES:
            acc.type = form.get("type")
        acc.active = form.get("active") is not None
        db.commit()
        flash(request, "Account updated.", "success")
    return RedirectResponse("/accounts", status_code=303)


@router.post("/accounts/{aid}/delete")
def delete_account(aid: int, request: Request, db: Session = Depends(get_db)):
    acc = db.get(Account, aid)
    if acc and acc.system_tag:
        flash(request, "Standard (system) accounts can't be deleted.", "warning")
    elif acc:
        db.delete(acc)
        db.commit()
        flash(request, "Account deleted.", "success")
    return RedirectResponse("/accounts", status_code=303)


# --------------------------------------------------------------------------- #
# Manual journal entries
# --------------------------------------------------------------------------- #
@router.get("/journals", response_class=HTMLResponse)
def list_journals(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(select(JournalEntry).order_by(JournalEntry.id.desc())).scalars().all()
    return templates.TemplateResponse(
        request, "ledger/journals.html", {"active_nav": "journals", "rows": rows})


@router.get("/journals/new", response_class=HTMLResponse)
def new_journal(request: Request, db: Session = Depends(get_db)):
    accounts = db.execute(select(Account).where(Account.active == True).order_by(Account.code)).scalars().all()
    return templates.TemplateResponse(
        request, "ledger/journal_form.html",
        {"active_nav": "journals", "accounts": accounts, "today": date.today().isoformat()})


@router.post("/journals/new")
async def create_journal(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    n = (db.query(JournalEntry).count() or 0) + 1
    while db.query(JournalEntry).filter(JournalEntry.number == f"JV-{n:04d}").first():
        n += 1
    je = JournalEntry(
        number=f"JV-{n:04d}",
        date=date.fromisoformat(form.get("date") or date.today().isoformat()),
        reference=form.get("reference") or "", narration=form.get("narration") or "")
    # Collect parallel line arrays.
    account_ids = form.getlist("account_id")
    debits = form.getlist("debit")
    credits = form.getlist("credit")
    for aid, dr, cr in zip(account_ids, debits, credits):
        if not aid:
            continue
        d = _f({"d": dr}, "d", float, 0)
        c = _f({"c": cr}, "c", float, 0)
        if d == 0 and c == 0:
            continue
        je.lines.append(JournalLine(account_id=int(aid), debit=d, credit=c))
    if not je.lines:
        flash(request, "Add at least one line with an amount.", "warning")
        return RedirectResponse("/journals/new", status_code=303)
    if not je.is_balanced:
        flash(request, f"Entry not balanced: debits {je.total_debit} ≠ credits {je.total_credit}.", "danger")
        return RedirectResponse("/journals/new", status_code=303)
    db.add(je)
    db.commit()
    flash(request, f"Journal {je.number} posted.", "success")
    return RedirectResponse("/journals", status_code=303)


@router.post("/journals/{jid}/delete")
def delete_journal(jid: int, request: Request, db: Session = Depends(get_db)):
    je = db.get(JournalEntry, jid)
    if je:
        db.delete(je)
        db.commit()
        flash(request, f"Journal {je.number} deleted.", "success")
    return RedirectResponse("/journals", status_code=303)


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
@router.get("/trial-balance", response_class=HTMLResponse)
def trial_balance(request: Request, db: Session = Depends(get_db)):
    start, end = _date_range(request)
    rows, td, tc = gl.trial_balance(db, start, end)
    return templates.TemplateResponse(
        request, "ledger/trial_balance.html",
        {"active_nav": "trial_balance", "settings": get_settings(db), "rows": rows,
         "total_debit": td, "total_credit": tc,
         "start": start.isoformat(), "end": end.isoformat()})


@router.get("/trial-balance.csv")
def trial_balance_csv(request: Request, db: Session = Depends(get_db)):
    start, end = _date_range(request)
    rows, td, tc = gl.trial_balance(db, start, end)
    data = [[r["account"].code, r["account"].name, r["account"].type,
             f"{r['debit']:.2f}", f"{r['credit']:.2f}"] for r in rows]
    data.append(["", "TOTAL", "", f"{td:.2f}", f"{tc:.2f}"])
    return csv_response(f"trial-balance_{start}_{end}.csv",
                        ["Code", "Account", "Type", "Debit", "Credit"], data)


@router.get("/profit-loss", response_class=HTMLResponse)
def profit_loss(request: Request, db: Session = Depends(get_db)):
    start, end = _date_range(request)
    data = gl.income_statement(db, start, end)
    return templates.TemplateResponse(
        request, "ledger/profit_loss.html",
        {"active_nav": "profit_loss", "settings": get_settings(db), "d": data,
         "start": start.isoformat(), "end": end.isoformat()})


@router.get("/profit-loss.csv")
def profit_loss_csv(request: Request, db: Session = Depends(get_db)):
    start, end = _date_range(request)
    d = gl.income_statement(db, start, end)
    rows = [["Income", "", ""]]
    rows += [["", r["account"].name, f"{r['balance']:.2f}"] for r in d["income"]]
    rows.append(["", "Total income", f"{d['total_income']:.2f}"])
    rows.append(["Expenses", "", ""])
    rows += [["", r["account"].name, f"{r['balance']:.2f}"] for r in d["expense"]]
    rows.append(["", "Total expenses", f"{d['total_expense']:.2f}"])
    rows.append(["", "Net profit/(loss)", f"{d['net_profit']:.2f}"])
    return csv_response(f"profit-loss_{start}_{end}.csv", ["Section", "Account", "Amount"], rows)


@router.get("/balance-sheet", response_class=HTMLResponse)
def balance_sheet(request: Request, db: Session = Depends(get_db)):
    qp = request.query_params
    try:
        as_of = date.fromisoformat(qp["as_of"]) if qp.get("as_of") else date.today()
    except ValueError:
        as_of = date.today()
    data = gl.balance_sheet(db, as_of)
    return templates.TemplateResponse(
        request, "ledger/balance_sheet.html",
        {"active_nav": "balance_sheet", "settings": get_settings(db), "d": data,
         "as_of": as_of.isoformat()})


@router.get("/balance-sheet.csv")
def balance_sheet_csv(request: Request, db: Session = Depends(get_db)):
    from datetime import date as _date
    qp = request.query_params
    try:
        as_of = _date.fromisoformat(qp["as_of"]) if qp.get("as_of") else _date.today()
    except ValueError:
        as_of = _date.today()
    d = gl.balance_sheet(db, as_of)
    rows = [["Assets", "", ""]]
    rows += [["", r["account"].name, f"{r['balance']:.2f}"] for r in d["assets"]]
    rows.append(["", "Total Assets", f"{d['total_assets']:.2f}"])
    rows.append(["Liabilities", "", ""])
    rows += [["", r["account"].name, f"{r['balance']:.2f}"] for r in d["liabilities"]]
    rows.append(["", "Total Liabilities", f"{d['total_liabilities']:.2f}"])
    rows.append(["Equity", "", ""])
    rows += [["", r["account"].name, f"{r['balance']:.2f}"] for r in d["equity"]]
    rows.append(["", "Current period earnings", f"{d['current_earnings']:.2f}"])
    rows.append(["", "Total Equity", f"{d['total_equity_with_earnings']:.2f}"])
    rows.append(["", "Total Liabilities + Equity", f"{d['total_liab_equity']:.2f}"])
    return csv_response(f"balance-sheet_{as_of}.csv", ["Section", "Account", "Amount"], rows)


@router.get("/accounts/{aid}/ledger", response_class=HTMLResponse)
def account_detail(aid: int, request: Request, db: Session = Depends(get_db)):
    start, end = _date_range(request)
    acc, rows = gl.account_ledger(db, aid, start, end)
    if not acc:
        return RedirectResponse("/accounts", status_code=303)
    return templates.TemplateResponse(
        request, "ledger/account_detail.html",
        {"active_nav": "accounts", "settings": get_settings(db), "acc": acc, "rows": rows,
         "start": start.isoformat(), "end": end.isoformat()})
