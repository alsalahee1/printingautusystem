"""SQLAlchemy models for the printing management system.

Module 1 (Foundation + Master Data) covers the entities every other module
references: Customers, Suppliers, Stock items (paper/ink/plates/consumables),
Finishing operations, and Machines. Later modules (quotation, job, invoicing,
inventory) add their tables to this file.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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
