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
    tin: Mapped[str] = mapped_column(String(40), default="")        # LHDN Tax Identification No.
    reg_no: Mapped[str] = mapped_column(String(40), default="")     # business/IC registration no.
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

    # Outgoing email (SMTP) — used to email PDF quotes/invoices.
    smtp_host: Mapped[str] = mapped_column(String(120), default="")
    smtp_port: Mapped[int] = mapped_column(Integer, default=587)
    smtp_user: Mapped[str] = mapped_column(String(120), default="")
    smtp_pass: Mapped[str] = mapped_column(String(255), default="")
    smtp_from: Mapped[str] = mapped_column(String(120), default="")
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)

    # Malaysian e-Invoice (LHDN MyInvois) identity fields.
    company_tin: Mapped[str] = mapped_column(String(40), default="")
    company_brn: Mapped[str] = mapped_column(String(40), default="")     # business registration no.
    company_msic: Mapped[str] = mapped_column(String(10), default="")    # MSIC industry code
    company_activity: Mapped[str] = mapped_column(String(200), default="")
    einvoice_classification: Mapped[str] = mapped_column(String(10), default="022")  # default item class code


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


# ---------------------------------------------------------------------------
# Module 3: Work-Orders / Job Cards
# ---------------------------------------------------------------------------

JOB_STATUSES = ["Pre-press", "Printing", "Post-press", "Ready", "Delivered", "On Hold", "Cancelled"]
JOB_STATUS_COLORS = {
    "Pre-press": "secondary", "Printing": "primary", "Post-press": "info",
    "Ready": "success", "Delivered": "dark", "On Hold": "warning", "Cancelled": "danger",
}
JOB_PRIORITIES = ["Low", "Normal", "High", "Urgent"]
JOB_PRIORITY_COLORS = {"Low": "secondary", "Normal": "info", "High": "warning", "Urgent": "danger"}

# Production stages every new job card is seeded with (the shop floor ticks
# these off as the work progresses).
DEFAULT_JOB_STAGES = ["Pre-press", "CTP / Plates", "Printing", "Finishing", "Cutting & QC", "Delivery"]


class Job(Base):
    """A production work order — usually created from an approved quotation."""
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    quotation_id: Mapped[int | None] = mapped_column(ForeignKey("quotations.id"), nullable=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="Pre-press")
    priority: Mapped[str] = mapped_column(String(10), default="Normal")
    order_date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    assigned_to: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship()
    quotation: Mapped["Quotation | None"] = relationship()
    items: Mapped[list["JobItem"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobItem.line_no"
    )
    stages: Mapped[list["JobStage"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobStage.seq"
    )

    @property
    def status_color(self) -> str:
        return JOB_STATUS_COLORS.get(self.status, "secondary")

    @property
    def priority_color(self) -> str:
        return JOB_PRIORITY_COLORS.get(self.priority, "secondary")

    @property
    def progress(self) -> int:
        if not self.stages:
            return 0
        done = sum(1 for s in self.stages if s.done)
        return round(done * 100 / len(self.stages))

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.due_date
            and self.due_date < date.today()
            and self.status not in ("Delivered", "Cancelled")
        )


class JobItem(Base):
    """A print product on a job card — production spec carried from the quote."""
    __tablename__ = "job_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    paper_id: Mapped[int | None] = mapped_column(ForeignKey("stock_items.id"), nullable=True)
    finished_width_mm: Mapped[float] = mapped_column(Float, default=0.0)
    finished_height_mm: Mapped[float] = mapped_column(Float, default=0.0)
    colors_front: Mapped[int] = mapped_column(Integer, default=0)
    colors_back: Mapped[int] = mapped_column(Integer, default=0)
    machine_id: Mapped[int | None] = mapped_column(ForeignKey("machines.id"), nullable=True)
    ups: Mapped[int] = mapped_column(Integer, default=0)
    total_sheets: Mapped[int] = mapped_column(Integer, default=0)
    num_plates: Mapped[int] = mapped_column(Integer, default=0)
    finishing_summary: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    job: Mapped["Job"] = relationship(back_populates="items")
    paper: Mapped["StockItem | None"] = relationship()
    machine: Mapped["Machine | None"] = relationship()


class JobStage(Base):
    """A production stage on a job card with completion status & timestamp."""
    __tablename__ = "job_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    seq: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(60))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(200), default="")

    job: Mapped["Job"] = relationship(back_populates="stages")


# ---------------------------------------------------------------------------
# Module 4: Accounting — Invoices, Payments (Receipts), Delivery Orders, AR
# ---------------------------------------------------------------------------

PAYMENT_METHODS = ["Cash", "Bank Transfer", "Cheque", "Card", "Online", "Other"]
INVOICE_STATUS_COLORS = {
    "Unpaid": "danger", "Partial": "warning", "Paid": "success", "Cancelled": "secondary",
}


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    quotation_id: Mapped[int | None] = mapped_column(ForeignKey("quotations.id"), nullable=True)
    tax_pct: Mapped[float] = mapped_column(Float, default=0.0)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    terms: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship()
    job: Mapped["Job | None"] = relationship()
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceItem.line_no"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="Payment.date"
    )

    @property
    def subtotal(self) -> float:
        return round(sum(i.amount for i in self.items), 2)

    @property
    def tax_amount(self) -> float:
        return round(self.subtotal * self.tax_pct / 100, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax_amount, 2)

    @property
    def paid_amount(self) -> float:
        return round(sum(p.amount for p in self.payments), 2)

    @property
    def balance(self) -> float:
        return round(self.total - self.paid_amount, 2)

    @property
    def status(self) -> str:
        if self.cancelled:
            return "Cancelled"
        if self.balance <= 0 and self.total > 0:
            return "Paid"
        if self.paid_amount > 0:
            return "Partial"
        return "Unpaid"

    @property
    def status_color(self) -> str:
        return INVOICE_STATUS_COLORS.get(self.status, "secondary")

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.due_date and self.due_date < date.today()
            and self.balance > 0 and not self.cancelled
        )

    @property
    def days_overdue(self) -> int:
        ref = self.due_date or self.date
        return max((date.today() - ref).days, 0) if self.balance > 0 else 0


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)

    invoice: Mapped["Invoice"] = relationship(back_populates="items")

    @property
    def amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)


class Payment(Base):
    """A receipt of money against an invoice (partial payments allowed)."""
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(20), default="Cash")
    reference: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    invoice: Mapped["Invoice"] = relationship(back_populates="payments")


class DeliveryOrder(Base):
    __tablename__ = "delivery_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    date: Mapped[date] = mapped_column(Date, default=date.today)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    delivered_to: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    customer: Mapped["Customer"] = relationship()
    job: Mapped["Job | None"] = relationship()
    items: Mapped[list["DeliveryOrderItem"]] = relationship(
        back_populates="delivery_order", cascade="all, delete-orphan",
        order_by="DeliveryOrderItem.line_no",
    )


class DeliveryOrderItem(Base):
    __tablename__ = "delivery_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    do_id: Mapped[int] = mapped_column(ForeignKey("delivery_orders.id"))
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[float] = mapped_column(Float, default=1.0)

    delivery_order: Mapped["DeliveryOrder"] = relationship(back_populates="items")


# ---------------------------------------------------------------------------
# Module 5: Inventory movements & Purchasing (PO, goods receipt, AP)
# ---------------------------------------------------------------------------

# Movement types. Quantity is signed: positive = into stock, negative = out.
MOVEMENT_TYPES = ["Receipt", "Issue", "Adjustment", "Job Usage", "PO Receipt"]

PO_STATUSES = ["Draft", "Ordered", "Received", "Cancelled"]
PO_STATUS_COLORS = {"Draft": "secondary", "Ordered": "info", "Received": "success", "Cancelled": "danger"}

BILL_STATUS_COLORS = {"Unpaid": "danger", "Partial": "warning", "Paid": "success", "Cancelled": "secondary"}


class StockMovement(Base):
    """A single in/out/adjustment against a stock item (the inventory ledger)."""
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_item_id: Mapped[int] = mapped_column(ForeignKey("stock_items.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    type: Mapped[str] = mapped_column(String(20), default="Adjustment")
    quantity: Mapped[float] = mapped_column(Float, default=0.0)   # signed
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    reference: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    stock_item: Mapped["StockItem"] = relationship()


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    expected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="Draft")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    supplier: Mapped["Supplier"] = relationship()
    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="po", cascade="all, delete-orphan", order_by="PurchaseOrderItem.line_no"
    )

    @property
    def status_color(self) -> str:
        return PO_STATUS_COLORS.get(self.status, "secondary")

    @property
    def total(self) -> float:
        return round(sum(i.amount for i in self.items), 2)


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    po_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"))
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    stock_item_id: Mapped[int | None] = mapped_column(ForeignKey("stock_items.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)

    po: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    stock_item: Mapped["StockItem | None"] = relationship()

    @property
    def amount(self) -> float:
        return round(self.quantity * self.unit_cost, 2)


class SupplierBill(Base):
    """A supplier invoice (the AP mirror of a customer Invoice)."""
    __tablename__ = "supplier_bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    supplier_ref: Mapped[str] = mapped_column(String(60), default="")   # supplier's own invoice no.
    po_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), nullable=True)
    date: Mapped[date] = mapped_column(Date, default=date.today)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tax_pct: Mapped[float] = mapped_column(Float, default=0.0)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    supplier: Mapped["Supplier"] = relationship()
    items: Mapped[list["SupplierBillItem"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="SupplierBillItem.line_no"
    )
    payments: Mapped[list["SupplierPayment"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="SupplierPayment.date"
    )

    @property
    def subtotal(self) -> float:
        return round(sum(i.amount for i in self.items), 2)

    @property
    def tax_amount(self) -> float:
        return round(self.subtotal * self.tax_pct / 100, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax_amount, 2)

    @property
    def paid_amount(self) -> float:
        return round(sum(p.amount for p in self.payments), 2)

    @property
    def balance(self) -> float:
        return round(self.total - self.paid_amount, 2)

    @property
    def status(self) -> str:
        if self.cancelled:
            return "Cancelled"
        if self.balance <= 0 and self.total > 0:
            return "Paid"
        if self.paid_amount > 0:
            return "Partial"
        return "Unpaid"

    @property
    def status_color(self) -> str:
        return BILL_STATUS_COLORS.get(self.status, "secondary")

    @property
    def is_overdue(self) -> bool:
        return bool(self.due_date and self.due_date < date.today()
                    and self.balance > 0 and not self.cancelled)


class SupplierBillItem(Base):
    __tablename__ = "supplier_bill_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("supplier_bills.id"))
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)

    bill: Mapped["SupplierBill"] = relationship(back_populates="items")

    @property
    def amount(self) -> float:
        return round(self.quantity * self.unit_price, 2)


class SupplierPayment(Base):
    __tablename__ = "supplier_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("supplier_bills.id"))
    date: Mapped[date] = mapped_column(Date, default=date.today)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    method: Mapped[str] = mapped_column(String(20), default="Bank Transfer")
    reference: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    bill: Mapped["SupplierBill"] = relationship(back_populates="payments")


# ---------------------------------------------------------------------------
# Module 7: Users & authentication
# ---------------------------------------------------------------------------

USER_ROLES = ["admin", "staff"]


class User(Base):
    """An application login. Passwords are stored as PBKDF2 hashes (salt$hash)."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    full_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20), default="staff")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# ---------------------------------------------------------------------------
# Module 11: General Ledger (double-entry)
# ---------------------------------------------------------------------------

ACCOUNT_TYPES = ["Asset", "Liability", "Equity", "Income", "Expense"]
# Account types whose normal (increasing) balance is on the debit side.
DEBIT_NORMAL_TYPES = {"Asset", "Expense"}


class Account(Base):
    """A chart-of-accounts entry. `system_tag` links standard accounts to the
    automatic postings made from invoices, bills and payments."""
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    type: Mapped[str] = mapped_column(String(20), default="Asset")
    system_tag: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def is_debit_normal(self) -> bool:
        return self.type in DEBIT_NORMAL_TYPES


class JournalEntry(Base):
    """A manual double-entry journal. Auto-postings from documents are derived
    on the fly (see app.gl) and are not stored here."""
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    date: Mapped[date] = mapped_column(Date, default=date.today)
    reference: Mapped[str] = mapped_column(String(80), default="")
    narration: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan")

    @property
    def total_debit(self) -> float:
        return round(sum(l.debit for l in self.lines), 2)

    @property
    def total_credit(self) -> float:
        return round(sum(l.credit for l in self.lines), 2)

    @property
    def is_balanced(self) -> bool:
        return abs(self.total_debit - self.total_credit) < 0.005


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    debit: Mapped[float] = mapped_column(Float, default=0.0)
    credit: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str] = mapped_column(String(200), default="")

    entry: Mapped["JournalEntry"] = relationship(back_populates="lines")
    account: Mapped["Account"] = relationship()
