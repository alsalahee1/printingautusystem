"""SQLAlchemy models for the printing management system.

Module 1 (Foundation + Master Data) covers the entities every other module
references: Customers, Suppliers, Stock items (paper/ink/plates/consumables),
Finishing operations, and Machines. Later modules (quotation, job, invoicing,
inventory) add their tables to this file.
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    company: Mapped[str] = mapped_column(String(150), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    tax_no: Mapped[str] = mapped_column(String(40), default="")
    credit_limit: Mapped[float] = mapped_column(Float, default=0.0)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    address: Mapped[str] = mapped_column(Text, default="")
    tax_no: Mapped[str] = mapped_column(String(40), default="")
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    stock_items: Mapped[list["StockItem"]] = relationship(back_populates="supplier")


# Stock categories relevant to an offset print shop.
STOCK_CATEGORIES = ["Paper", "Ink", "Plate", "Consumable", "Other"]
STOCK_UNITS = ["Sheet", "Ream", "Kg", "Litre", "Pcs", "Roll", "Box"]


class StockItem(Base):
    """Paper, ink, CTP plates and other consumables.

    Paper-specific fields (gsm, sheet size) are optional and only filled for
    the Paper category; the estimation module uses them to compute how many
    finished pieces fit on a parent sheet and the paper cost per job.
    """
    __tablename__ = "stock_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(20), default="Paper")
    unit: Mapped[str] = mapped_column(String(20), default="Sheet")

    # Paper attributes (nullable for non-paper items).
    gsm: Mapped[int] = mapped_column(Integer, default=0)
    sheet_width_mm: Mapped[float] = mapped_column(Float, default=0.0)
    sheet_height_mm: Mapped[float] = mapped_column(Float, default=0.0)

    cost_price: Mapped[float] = mapped_column(Float, default=0.0)
    sell_price: Mapped[float] = mapped_column(Float, default=0.0)
    qty_on_hand: Mapped[float] = mapped_column(Float, default=0.0)
    reorder_level: Mapped[float] = mapped_column(Float, default=0.0)

    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    supplier: Mapped["Supplier | None"] = relationship(back_populates="stock_items")

    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def sheet_size_label(self) -> str:
        if self.sheet_width_mm and self.sheet_height_mm:
            return f"{self.sheet_width_mm:g}×{self.sheet_height_mm:g} mm"
        return ""


# How a finishing operation is priced.
FINISHING_METHODS = ["per_sheet", "per_piece", "per_job", "per_sqm"]
FINISHING_METHOD_LABELS = {
    "per_sheet": "Per printed sheet",
    "per_piece": "Per finished piece",
    "per_job": "Flat per job",
    "per_sqm": "Per square metre",
}


class FinishingType(Base):
    """Post-press operations: lamination, UV, die-cut, binding, folding, etc."""
    __tablename__ = "finishing_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    pricing_method: Mapped[str] = mapped_column(String(20), default="per_piece")
    unit_rate: Mapped[float] = mapped_column(Float, default=0.0)
    setup_cost: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def method_label(self) -> str:
        return FINISHING_METHOD_LABELS.get(self.pricing_method, self.pricing_method)


MACHINE_TYPES = ["Press", "CTP", "Cutter", "Laminator", "Folder", "Binder", "Other"]


class Machine(Base):
    """Production equipment with the rates used for job costing.

    `makeready_cost` covers plate mounting / wash-up per job; `run_rate_per_hour`
    is sheets (impressions) per hour at full speed; `hourly_rate` is the costed
    machine + operator rate used to turn run time into money.
    """
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    type: Mapped[str] = mapped_column(String(20), default="Press")
    max_colors: Mapped[int] = mapped_column(Integer, default=4)
    max_sheet_width_mm: Mapped[float] = mapped_column(Float, default=0.0)
    max_sheet_height_mm: Mapped[float] = mapped_column(Float, default=0.0)
    hourly_rate: Mapped[float] = mapped_column(Float, default=0.0)
    makeready_cost: Mapped[float] = mapped_column(Float, default=0.0)
    makeready_minutes: Mapped[int] = mapped_column(Integer, default=0)
    run_rate_per_hour: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Module 2: Estimation & Quotations
# ---------------------------------------------------------------------------

QUOTATION_STATUSES = ["Draft", "Sent", "Approved", "Rejected", "Expired"]
QUOTATION_STATUS_COLORS = {
    "Draft": "secondary", "Sent": "info", "Approved": "success",
    "Rejected": "danger", "Expired": "warning",
}


class Settings(Base):
    """Single-row company + costing defaults used across estimation/quotes."""
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_name: Mapped[str] = mapped_column(String(150), default="My Printing Press")
    company_address: Mapped[str] = mapped_column(Text, default="")
    company_phone: Mapped[str] = mapped_column(String(40), default="")
    company_email: Mapped[str] = mapped_column(String(120), default="")
    company_reg_no: Mapped[str] = mapped_column(String(40), default="")
    company_tax_no: Mapped[str] = mapped_column(String(40), default="")
    currency: Mapped[str] = mapped_column(String(8), default="RM")

    # Costing defaults — used to pre-fill estimates.
    plate_cost: Mapped[float] = mapped_column(Float, default=12.0)
    ink_cost_per_1000: Mapped[float] = mapped_column(Float, default=4.0)
    default_wastage_pct: Mapped[float] = mapped_column(Float, default=8.0)
    default_markup_pct: Mapped[float] = mapped_column(Float, default=30.0)
    overhead_pct: Mapped[float] = mapped_column(Float, default=15.0)
    tax_pct: Mapped[float] = mapped_column(Float, default=0.0)

    quotation_validity_days: Mapped[int] = mapped_column(Integer, default=30)
    quotation_terms: Mapped[str] = mapped_column(
        Text, default="Prices valid for 30 days. 50% deposit required to confirm order."
    )
    next_quotation_no: Mapped[int] = mapped_column(Integer, default=1)


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    date: Mapped[date] = mapped_column(Date, default=date.today)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(20), default="Draft")
    tax_pct: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    terms: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship()
    items: Mapped[list["QuotationItem"]] = relationship(
        back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationItem.line_no"
    )

    @property
    def status_color(self) -> str:
        return QUOTATION_STATUS_COLORS.get(self.status, "secondary")

    @property
    def subtotal(self) -> float:
        return round(sum(i.line_total for i in self.items), 2)

    @property
    def tax_amount(self) -> float:
        return round(self.subtotal * self.tax_pct / 100, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax_amount, 2)


class QuotationItem(Base):
    """One estimated print product on a quotation.

    Stores both the input spec and a snapshot of the computed costs so the
    quote total is stable even if master-data rates change later.
    """
    __tablename__ = "quotation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quotation_id: Mapped[int] = mapped_column(ForeignKey("quotations.id"))
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200), default="")

    quantity: Mapped[int] = mapped_column(Integer, default=0)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("stock_items.id"), nullable=True)
    finished_width_mm: Mapped[float] = mapped_column(Float, default=0.0)
    finished_height_mm: Mapped[float] = mapped_column(Float, default=0.0)
    colors_front: Mapped[int] = mapped_column(Integer, default=4)
    colors_back: Mapped[int] = mapped_column(Integer, default=0)
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("machines.id"), nullable=True)
    wastage_pct: Mapped[float] = mapped_column(Float, default=8.0)
    markup_pct: Mapped[float] = mapped_column(Float, default=30.0)
    notes: Mapped[str] = mapped_column(Text, default="")

    # Computed snapshot.
    ups: Mapped[int] = mapped_column(Integer, default=0)
    net_sheets: Mapped[int] = mapped_column(Integer, default=0)
    total_sheets: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    num_plates: Mapped[int] = mapped_column(Integer, default=0)
    paper_cost: Mapped[float] = mapped_column(Float, default=0.0)
    ink_cost: Mapped[float] = mapped_column(Float, default=0.0)
    plate_cost: Mapped[float] = mapped_column(Float, default=0.0)
    makeready_cost: Mapped[float] = mapped_column(Float, default=0.0)
    press_cost: Mapped[float] = mapped_column(Float, default=0.0)
    finishing_cost: Mapped[float] = mapped_column(Float, default=0.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    line_total: Mapped[float] = mapped_column(Float, default=0.0)

    quotation: Mapped["Quotation"] = relationship(back_populates="items")
    paper: Mapped["StockItem | None"] = relationship()
    machine: Mapped["Machine | None"] = relationship()
    finishings: Mapped[list["QuotationItemFinishing"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class QuotationItemFinishing(Base):
    """A finishing operation applied to a quotation line, with its costed amount."""
    __tablename__ = "quotation_item_finishings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("quotation_items.id"))
    finishing_id: Mapped[int] = mapped_column(ForeignKey("finishing_types.id"))
    amount: Mapped[float] = mapped_column(Float, default=0.0)

    item: Mapped["QuotationItem"] = relationship(back_populates="finishings")
    finishing: Mapped["FinishingType"] = relationship()
