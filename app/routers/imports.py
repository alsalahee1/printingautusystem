"""CSV import (Module 10).

Bulk-load Customers and Stock items from a CSV exported by another system
(e.g. AutoCount). Column headers are matched flexibly against a list of common
aliases (case/spacing/punctuation-insensitive), and rows are upserted by code
so re-importing updates existing records rather than duplicating them.
"""
import csv
import io
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..exporting import csv_response
from ..models import STOCK_CATEGORIES, STOCK_UNITS, Customer, StockItem
from ..web import flash, templates

router = APIRouter()


@router.get("/export/customers.csv")
def export_customers(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(select(Customer).order_by(Customer.code)).scalars().all()
    data = [[c.code, c.name, c.company, c.phone, c.email, c.address, c.city,
             c.tax_no, c.tin, c.reg_no, f"{c.credit_limit:g}", c.payment_terms_days]
            for c in rows]
    return csv_response("customers.csv",
                        ["Code", "Name", "Company", "Phone", "Email", "Address", "City",
                         "SST", "TIN", "RegNo", "CreditLimit", "Terms"], data)


@router.get("/export/stock.csv")
def export_stock(request: Request, db: Session = Depends(get_db)):
    rows = db.execute(select(StockItem).order_by(StockItem.code)).scalars().all()
    data = [[s.code, s.name, s.category, s.unit, s.gsm or "", f"{s.cost_price:g}",
             f"{s.sell_price:g}", f"{s.qty_on_hand:g}", f"{s.reorder_level:g}"]
            for s in rows]
    return csv_response("stock.csv",
                        ["ItemCode", "Description", "Category", "UOM", "GSM", "Cost",
                         "SellingPrice", "BalanceQty", "ReorderLevel"], data)


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _pick(row: dict, aliases: list[str], default=""):
    for a in aliases:
        if a in row and str(row[a]).strip() != "":
            return str(row[a]).strip()
    return default


def _num(val, default=0.0):
    if val in (None, ""):
        return default
    try:
        return float(str(val).replace(",", "").strip())
    except ValueError:
        return default


CUSTOMER_MAP = {
    "code": ["code", "accountno", "account", "custno", "customercode", "accno", "customerno", "debtorcode"],
    "name": ["name", "customername", "contact", "contactname", "debtorname"],
    "company": ["company", "companyname", "customercompany"],
    "phone": ["phone", "phone1", "tel", "telephone", "mobile", "contactno", "hp"],
    "email": ["email", "emailaddress", "e-mail"],
    "address": ["address", "address1", "billingaddress", "addr"],
    "city": ["city", "town"],
    "tax_no": ["sst", "sstno", "taxno", "gstno", "gst"],
    "tin": ["tin", "tinno", "taxidentificationno"],
    "reg_no": ["regno", "brn", "registrationno", "businessregistrationno", "roc"],
    "credit_limit": ["creditlimit", "credit"],
    "payment_terms_days": ["terms", "paymentterms", "creditterms", "term"],
}

STOCK_MAP = {
    "code": ["code", "itemcode", "stockcode", "item", "productcode"],
    "name": ["name", "description", "itemname", "desc", "productname"],
    "category": ["category", "group", "itemgroup", "type", "stockgroup"],
    "unit": ["unit", "uom", "baseuom"],
    "gsm": ["gsm", "grammage", "weight"],
    "cost_price": ["cost", "costprice", "purchaseprice", "unitcost", "averagecost"],
    "sell_price": ["sell", "sellprice", "sellingprice", "price", "unitprice"],
    "qty_on_hand": ["qty", "balanceqty", "qtyonhand", "onhand", "balance", "stockbalance", "balqty"],
    "reorder_level": ["reorder", "reorderlevel", "minqty", "minimum", "minlevel"],
}


def _read_rows(data: bytes):
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        yield {_norm(k): (v or "") for k, v in raw.items() if k}


@router.get("/import", response_class=HTMLResponse)
def import_index(request: Request):
    return templates.TemplateResponse(request, "import/index.html", {"active_nav": "import"})


@router.post("/import/customers", response_class=HTMLResponse)
async def import_customers(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    upload = form.get("file")
    if not upload:
        flash(request, "Choose a CSV file first.", "warning")
        return RedirectResponse("/import", status_code=303)
    created = updated = 0
    errors = []
    for n, row in enumerate(_read_rows(await upload.read()), start=2):
        code = _pick(row, CUSTOMER_MAP["code"])
        name = _pick(row, CUSTOMER_MAP["name"]) or _pick(row, CUSTOMER_MAP["company"])
        if not code or not name:
            errors.append((n, "missing code or name"))
            continue
        obj = db.execute(select(Customer).where(Customer.code == code)).scalar_one_or_none()
        is_new = obj is None
        if is_new:
            obj = Customer(code=code)
            db.add(obj)
        obj.name = name
        obj.company = _pick(row, CUSTOMER_MAP["company"])
        obj.phone = _pick(row, CUSTOMER_MAP["phone"])
        obj.email = _pick(row, CUSTOMER_MAP["email"])
        obj.address = _pick(row, CUSTOMER_MAP["address"])
        obj.city = _pick(row, CUSTOMER_MAP["city"])
        obj.tax_no = _pick(row, CUSTOMER_MAP["tax_no"])
        obj.tin = _pick(row, CUSTOMER_MAP["tin"])
        obj.reg_no = _pick(row, CUSTOMER_MAP["reg_no"])
        obj.credit_limit = _num(_pick(row, CUSTOMER_MAP["credit_limit"]))
        obj.payment_terms_days = int(_num(_pick(row, CUSTOMER_MAP["payment_terms_days"]), 30))
        created += is_new
        updated += not is_new
    db.commit()
    return templates.TemplateResponse(
        request, "import/result.html",
        {"active_nav": "import", "kind": "Customers", "created": created,
         "updated": updated, "errors": errors},
    )


@router.post("/import/stock", response_class=HTMLResponse)
async def import_stock(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    upload = form.get("file")
    if not upload:
        flash(request, "Choose a CSV file first.", "warning")
        return RedirectResponse("/import", status_code=303)
    created = updated = 0
    errors = []
    cat_lookup = {c.lower(): c for c in STOCK_CATEGORIES}
    unit_lookup = {u.lower(): u for u in STOCK_UNITS}
    for n, row in enumerate(_read_rows(await upload.read()), start=2):
        code = _pick(row, STOCK_MAP["code"])
        name = _pick(row, STOCK_MAP["name"])
        if not code or not name:
            errors.append((n, "missing code or name"))
            continue
        obj = db.execute(select(StockItem).where(StockItem.code == code)).scalar_one_or_none()
        is_new = obj is None
        if is_new:
            obj = StockItem(code=code)
            db.add(obj)
        obj.name = name
        obj.category = cat_lookup.get(_pick(row, STOCK_MAP["category"]).lower(), "Other")
        obj.unit = unit_lookup.get(_pick(row, STOCK_MAP["unit"]).lower(), "Pcs")
        obj.gsm = int(_num(_pick(row, STOCK_MAP["gsm"])))
        obj.cost_price = _num(_pick(row, STOCK_MAP["cost_price"]))
        obj.sell_price = _num(_pick(row, STOCK_MAP["sell_price"]))
        obj.qty_on_hand = _num(_pick(row, STOCK_MAP["qty_on_hand"]))
        obj.reorder_level = _num(_pick(row, STOCK_MAP["reorder_level"]))
        created += is_new
        updated += not is_new
    db.commit()
    return templates.TemplateResponse(
        request, "import/result.html",
        {"active_nav": "import", "kind": "Stock items", "created": created,
         "updated": updated, "errors": errors},
    )
