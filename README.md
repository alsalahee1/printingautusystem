# PrintSys — Offset Printing Management System

A web-based management and accounting system **built specifically for offset
printing companies**. It covers the workflow a general accounting package
(like AutoCount) cannot model well: paper/GSM stock, print-job estimation,
plates and make-ready costing, post-press finishing, and job tracking — on top
of standard sales, invoicing and accounts-receivable.

> This is an original system. It is **not** a copy of any proprietary
> accounting software; it re-implements the *modules a print shop needs* in a
> clean, printing-first design.

## Status — built module by module

| # | Module | Status |
|---|--------|--------|
| **1** | **Foundation + Master Data** — Customers, Suppliers, Stock & Paper (GSM/sheet size/cost), Finishing types, Machines (rates) | ✅ Done |
| **2** | **Job Estimation + Quotation** — imposition, plate/make-ready/press/paper/ink/finishing costing, live price preview, printable quotes | ✅ Done |
| **3** | **Work-Order / Job tracking** — convert quote → job card, production stages (pre-press → delivery), progress, due dates, priorities | ✅ Done |
| 4 | Core accounting (Sales Order → Delivery Order → Invoice → Receipt + AR) | ⏳ Next |
| 4 | Core accounting (Sales Order → Delivery Order → Invoice → Receipt + AR) | ⏳ Planned |
| 5 | Inventory + Purchasing (stock movements, AP) | ⏳ Planned |
| 6 | Reports + GL (sales, AR aging, job profitability) | ⏳ Planned |

## Quick start

```bash
./run.sh
```

Then open <http://127.0.0.1:8000>. The first run installs dependencies and
seeds realistic sample data (papers, inks, plates, finishing operations,
presses and a few customers/suppliers).

To run manually:

```bash
pip3 install -r requirements.txt
python3 -m app.seed          # optional: load sample data
uvicorn app.main:app --reload
```

## Tech stack

- **FastAPI** + **Uvicorn** (Python web app, single command, no build step)
- **SQLAlchemy** ORM over **SQLite** by default
- **Jinja2** server-rendered templates + **Bootstrap 5** UI

### Production database

SQLite is the zero-config default. Point at PostgreSQL / SQL Server by setting
an environment variable — no code change:

```bash
export PRINTSYS_DB_URL="postgresql+psycopg://user:pass@host/printsys"
export PRINTSYS_SECRET="a-long-random-string"   # signs session cookies
```

## Project layout

```
app/
  main.py            FastAPI app + startup (table creation)
  database.py        Engine / session (PRINTSYS_DB_URL)
  models.py          SQLAlchemy models (grows per module)
  web.py             Jinja templates + flash messages
  crud.py            Config-driven CRUD factory (EntityConfig)
  seed.py            Sample offset-printing data
  routers/
    dashboard.py     Home dashboard + low-stock alerts
    master_data.py   EntityConfig definitions for the 5 master screens
  templates/         base.html, dashboard.html, crud/{list,form}.html
  static/style.css
```

## Module 1 — what's included

**Master data every other module builds on:**

- **Customers** — code, contact, company, credit limit, payment terms, SST no.
- **Suppliers** — for paper/ink/plate purchasing.
- **Stock & Paper** — category (Paper/Ink/Plate/Consumable), unit, and for
  paper: **GSM** and **parent sheet size (mm)**, cost/sell price, on-hand qty,
  reorder level, preferred supplier.
- **Finishing types** — lamination, UV, die-cut, binding, folding, numbering —
  each with a pricing method (per sheet / piece / job / m²), rate and setup cost.
- **Machines** — presses, CTP, cutter, laminator, folder — with **hourly rate**,
  **make-ready cost/time** and **run rate (sheets/hour)** used later for costing.

The **dashboard** shows live counts and **low-stock alerts** (items at or below
reorder level).

## Module 2 — Estimation & Quotations

The printing-specific costing engine and quoting workflow.

- **Estimation engine** (`app/estimating.py`, pure & unit-testable) models a job
  the way a print shop actually costs it:
  1. **Imposition** — pieces per parent sheet, both orientations, with bleed +
     gripper allowance.
  2. **Sheets** — net + spoilage (wastage %).
  3. **Plates** — one CTP plate per colour, per side.
  4. **Make-ready** — per press run (one run per printed side).
  5. **Press time** — impressions ÷ press speed + make-ready minutes × hourly rate.
  6. **Paper & ink** — sheets × cost; ink by colour-impressions.
  7. **Finishing** — per piece / sheet / job / m².
  8. **Margin** — overhead %, then markup % → selling price & unit price.
- **Quotations** — a header (customer, dates, status, tax) plus one or more
  costed print-job line items. Statuses: Draft → Sent → Approved / Rejected /
  Expired.
- **Live price preview** — a JSON `/api/estimate` endpoint recomputes the full
  cost breakdown as you fill the job form, so you see the price update live.
- **Printable quotation** — clean A4 layout with your company header, ready to
  print or save as PDF.
- **Settings** — company details (for the quote header) plus costing defaults
  (plate cost, ink rate, default wastage/markup, overhead, tax, validity).

## Module 3 — Work-Orders / Job Cards

Turns sales into production tracking.

- **Convert quotation → job card** — one click on a quotation copies every line's
  spec (paper, size, colours, ups, sheets, plates, finishing) onto a job card.
- **Production stages** — each job is seeded with a checklist (Pre-press → CTP /
  Plates → Printing → Finishing → Cutting & QC → Delivery). The shop floor ticks
  stages off; each records a completion timestamp and the job's progress %.
- **Status & priority** — Pre-press / Printing / Post-press / Ready / Delivered /
  On Hold / Cancelled, with Low–Urgent priority and **overdue** highlighting.
- **Job board** — filter jobs by status, see progress bars and due dates.
- **Manual jobs** — create a job card directly (with editable production items)
  when there's no originating quotation.
- The **dashboard** now surfaces active jobs, jobs due within 3 days, and open
  quotations alongside low-stock alerts.
