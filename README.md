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
| 2 | Job Estimation + Quotation | ⏳ Next |
| 3 | Work-Order / Job tracking (pre-press → press → post-press) | ⏳ Planned |
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
