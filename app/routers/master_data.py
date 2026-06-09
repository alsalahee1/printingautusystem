"""Entity configurations for the master-data CRUD screens.

Each EntityConfig declares the list columns and form fields for one entity.
The generic factory in app.crud turns these into full CRUD routers, so adding
a field to a screen means editing one list here, not writing HTML.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..crud import Column, EntityConfig, Field, build_router
from ..models import (
    FINISHING_METHODS,
    FINISHING_METHOD_LABELS,
    MACHINE_TYPES,
    STOCK_CATEGORIES,
    STOCK_UNITS,
    Customer,
    FinishingType,
    Machine,
    StockItem,
    Supplier,
)


def _supplier_options(db: Session):
    rows = db.execute(select(Supplier).order_by(Supplier.name)).scalars().all()
    return {"dyn_options": {"supplier_choices": [(s.id, f"{s.code} — {s.name}") for s in rows]}}


customer_cfg = EntityConfig(
    slug="customers", model=Customer, singular="Customer", plural="Customers",
    nav="customers", icon="bi-people",
    columns=[
        Column("code", "Code"),
        Column("name", "Name"),
        Column("company", "Company"),
        Column("phone", "Phone"),
        Column("credit_limit", "Credit Limit", "money"),
        Column("active", "Active", "bool"),
    ],
    fields=[
        Field("code", "Code", required=True, group="Identity"),
        Field("name", "Contact / Name", required=True),
        Field("company", "Company"),
        Field("phone", "Phone"),
        Field("email", "Email", type="email"),
        Field("city", "City"),
        Field("address", "Address", type="textarea"),
        Field("tax_no", "SST No."),
        Field("tin", "TIN (e-Invoice)", help="LHDN Tax Identification Number."),
        Field("reg_no", "Business/IC Reg. No."),
        Field("credit_limit", "Credit Limit", type="number", group="Terms"),
        Field("payment_terms_days", "Payment Terms (days)", type="number", default=30),
        Field("notes", "Notes", type="textarea"),
        Field("active", "Active", type="checkbox", default=True),
    ],
)

supplier_cfg = EntityConfig(
    slug="suppliers", model=Supplier, singular="Supplier", plural="Suppliers",
    nav="suppliers", icon="bi-truck",
    columns=[
        Column("code", "Code"),
        Column("name", "Name"),
        Column("phone", "Phone"),
        Column("email", "Email"),
        Column("active", "Active", "bool"),
    ],
    fields=[
        Field("code", "Code", required=True, group="Identity"),
        Field("name", "Name", required=True),
        Field("phone", "Phone"),
        Field("email", "Email", type="email"),
        Field("address", "Address", type="textarea"),
        Field("tax_no", "Tax / SST No."),
        Field("payment_terms_days", "Payment Terms (days)", type="number", default=30, group="Terms"),
        Field("notes", "Notes", type="textarea"),
        Field("active", "Active", type="checkbox", default=True),
    ],
)

stock_cfg = EntityConfig(
    slug="stock", model=StockItem, singular="Stock Item", plural="Stock & Paper",
    nav="stock", icon="bi-box-seam",
    columns=[
        Column("code", "Code"),
        Column("name", "Name"),
        Column("category", "Category", "badge"),
        Column("gsm", "GSM", accessor=lambda o: o.gsm or "—"),
        Column("sheet_size", "Sheet Size", accessor=lambda o: o.sheet_size_label or "—"),
        Column("cost_price", "Cost", "money"),
        Column("qty_on_hand", "On Hand", "number"),
    ],
    fields=[
        Field("code", "Code", required=True, group="Item"),
        Field("name", "Name", required=True),
        Field("category", "Category", type="select",
              options=[(c, c) for c in STOCK_CATEGORIES], default="Paper"),
        Field("unit", "Unit", type="select",
              options=[(u, u) for u in STOCK_UNITS], default="Sheet"),
        Field("gsm", "Paper GSM", type="number", group="Paper attributes",
              help="Grammage in g/m². Leave 0 for non-paper items."),
        Field("sheet_width_mm", "Sheet Width (mm)", type="number"),
        Field("sheet_height_mm", "Sheet Height (mm)", type="number"),
        Field("cost_price", "Cost Price", type="number", group="Pricing & stock"),
        Field("sell_price", "Sell Price", type="number"),
        Field("qty_on_hand", "Quantity On Hand", type="number"),
        Field("reorder_level", "Reorder Level", type="number"),
        Field("supplier_id", "Preferred Supplier", type="select", options_key="supplier_choices"),
        Field("notes", "Notes", type="textarea"),
        Field("active", "Active", type="checkbox", default=True),
    ],
    extra_context=_supplier_options,
)

finishing_cfg = EntityConfig(
    slug="finishing", model=FinishingType, singular="Finishing Type", plural="Finishing Types",
    nav="finishing", icon="bi-scissors",
    columns=[
        Column("code", "Code"),
        Column("name", "Name"),
        Column("method", "Pricing", "badge", accessor=lambda o: o.method_label),
        Column("unit_rate", "Unit Rate", "money"),
        Column("setup_cost", "Setup Cost", "money"),
        Column("active", "Active", "bool"),
    ],
    fields=[
        Field("code", "Code", required=True, group="Operation"),
        Field("name", "Name", required=True),
        Field("pricing_method", "Pricing Method", type="select",
              options=[(m, FINISHING_METHOD_LABELS[m]) for m in FINISHING_METHODS],
              default="per_piece"),
        Field("unit_rate", "Unit Rate", type="number", group="Rates",
              help="Charge per the unit chosen above."),
        Field("setup_cost", "Setup / Minimum Cost", type="number"),
        Field("notes", "Notes", type="textarea"),
        Field("active", "Active", type="checkbox", default=True),
    ],
)

machine_cfg = EntityConfig(
    slug="machines", model=Machine, singular="Machine", plural="Machines",
    nav="machines", icon="bi-gear-wide-connected",
    columns=[
        Column("code", "Code"),
        Column("name", "Name"),
        Column("type", "Type", "badge"),
        Column("max_colors", "Colors", "number"),
        Column("hourly_rate", "Hourly Rate", "money"),
        Column("run_rate_per_hour", "Sheets/Hr", "number"),
    ],
    fields=[
        Field("code", "Code", required=True, group="Machine"),
        Field("name", "Name", required=True),
        Field("type", "Type", type="select",
              options=[(t, t) for t in MACHINE_TYPES], default="Press"),
        Field("max_colors", "Max Colors", type="number", default=4),
        Field("max_sheet_width_mm", "Max Sheet Width (mm)", type="number"),
        Field("max_sheet_height_mm", "Max Sheet Height (mm)", type="number"),
        Field("hourly_rate", "Hourly Rate", type="number", group="Costing rates",
              help="Costed machine + operator rate per hour."),
        Field("makeready_cost", "Make-ready Cost", type="number",
              help="Plate mounting / wash-up cost charged once per job."),
        Field("makeready_minutes", "Make-ready Minutes", type="number"),
        Field("run_rate_per_hour", "Run Rate (sheets/hour)", type="number"),
        Field("notes", "Notes", type="textarea"),
        Field("active", "Active", type="checkbox", default=True),
    ],
)

ALL_CONFIGS = [customer_cfg, supplier_cfg, stock_cfg, finishing_cfg, machine_cfg]

routers = [build_router(cfg) for cfg in ALL_CONFIGS]
