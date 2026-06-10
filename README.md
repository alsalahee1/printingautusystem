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
| **4** | **Core accounting** — Invoices (from quote/job/manual), Payments/Receipts, AR aging, Delivery Orders | ✅ Done |
| **5** | **Inventory + Purchasing** — stock movements, Purchase Orders + goods receipt, Supplier Bills, AP aging, job material consumption | ✅ Done |
| **6** | **Reports & Insight** — financial snapshot, sales summary, job profitability, stock valuation, customer statements | ✅ Done |
| **7** | **Users & Authentication** — login, roles (admin/staff), user management, hashed passwords | ✅ Done |
| **8** | **PDF & Email** — server-side PDF quotes/invoices/DOs, email with PDF attachment (SMTP) | ✅ Done |
| **9** | **e-Invoice & SST** — LHDN MyInvois-aligned JSON export, TIN/BRN/MSIC fields | ✅ Done |
| **10** | **CSV Import** — bulk-load customers & stock from AutoCount exports, upsert by code | ✅ Done |
| **11** | **General Ledger** — chart of accounts, auto-postings from documents, manual journals, Trial Balance / P&L / Balance Sheet | ✅ Done |
| **12** | **Expenses & Bank Reconciliation** — quick expense entry (auto-posted to GL), reconcile cash/bank accounts against statements | ✅ Done |
| **13** | **SST-02 Tax Return** — bi-monthly Malaysian SST summary (output vs input tax, by rate), printable | ✅ Done |
| **14** | **Audit Log** — automatic who-changed-what trail across every module (admin only) | ✅ Done |
| **15** | **Role-based permissions** — grant staff access to specific functional areas; enforced in nav and at the request | ✅ Done |
| **16** | **CSV export** — one-click Excel export of the key reports and master data | ✅ Done |

## Quick start

```bash
docker compose up -d     # Docker:  http://localhost:8000  (admin / admin)
# — or, without Docker —
./run.sh                 # local:   http://127.0.0.1:8000
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

Sign in with **admin / admin** on first run and change the password under *Users*.

### Tests & deployment

```bash
pip install -r requirements-dev.txt
pytest                       # isolated temp DB — does not touch your data
```

See **[DEPLOY.md](DEPLOY.md)** for running on a shop PC or production server
(environment variables, PostgreSQL, gunicorn + systemd, backups).

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

## Module 4 — Core Accounting

Where the money gets tracked.

- **Invoices** — raise from an approved **quotation** (pricing carried over),
  from a **job** (pricing pulled from its originating quote), or **manually**.
  Line items are **inline-editable** (description, qty, unit price); subtotal,
  tax and total recompute automatically.
- **Payments / Receipts** — record full or **partial** payments against an
  invoice (cash, bank transfer, cheque, card…). Invoice status derives from the
  balance: **Unpaid → Partial → Paid**, plus Cancel/Reopen.
- **Accounts Receivable** — an **aging report** bucketing every open balance by
  days past due (Current / 1–30 / 31–60 / 61–90 / 90+), grouped per customer
  with column totals.
- **Delivery Orders** — generate a DO from a job (carrying the items) or create
  one manually; printable with sign-off lines. The sales chain is now
  **Quotation → Job → Delivery Order → Invoice → Receipt**.
- **Printable** invoices and delivery orders with your company header.

> Scope note: a separate *Sales Order* document is intentionally omitted — the
> Quotation → Job flow already covers the pre-invoice stage for a print shop.

## Module 5 — Inventory & Purchasing

Closes the loop on materials and what you owe suppliers.

- **Stock movements** — an inventory ledger of every Receipt / Issue /
  Adjustment, keeping each item's on-hand quantity in step. Reversible.
- **Purchase Orders** — order materials from a supplier; "Receive into Stock"
  turns the PO lines into stock-in movements and bumps on-hand quantities.
- **Job material consumption** — one click on a job issues each item's paper
  (by total sheets) out of stock as "Job Usage" movements.
- **Supplier Bills (Accounts Payable)** — create from a received PO or
  manually; inline-editable lines, full/partial supplier **payments**, and
  status Unpaid → Partial → Paid (the AP mirror of customer AR).
- **AP aging report** — open payables bucketed by days past due, per supplier.

## Module 6 — Reports & Business Insight

Turns the captured data into management decisions.

- **Financial snapshot** — AR, AP, sales this month, purchases this month, and
  stock value at a glance.
- **Sales summary** — invoiced / paid / outstanding over a date range, broken
  down by month and by customer.
- **Job profitability** — revenue (actual invoice, or quoted) vs the estimated
  cost snapshot vs actual paper issued, with margin and margin % per job — the
  report that shows which jobs actually make money.
- **Stock valuation** — on-hand inventory value at cost, grouped by category.
- **Customer statements** — printable per-customer account statement with
  invoices, payments and balance due.

## Module 7 — Users & Authentication

- **Login required** — every page is behind a sign-in (session-based); a small
  middleware redirects anonymous visitors to `/login`.
- **Roles** — `admin` (manage users & settings) and `staff` (everything else).
- **User management** — admins add/edit/deactivate users and reset passwords.
- Passwords are stored as PBKDF2-HMAC-SHA256 hashes (standard library only).
- A default **admin / admin** account is created on first run — change it
  immediately (set `PRINTSYS_ADMIN_PASS` to seed a different password).

## Module 8 — PDF & Email

- **PDF documents** — quotations, invoices and delivery orders render to clean
  A4 PDFs server-side with ReportLab (no system libraries needed). "PDF" button
  on each document.
- **Email** — send the PDF straight to the customer from the document screen.
  Configure SMTP (host/port/from/credentials/TLS) under **Settings**; if it's
  left blank, email is disabled but PDF download still works. SMTP errors are
  reported back to the user, never crashing the request.

## Module 9 — e-Invoice & SST (Malaysia / LHDN)

- **Identity fields** — company TIN, BRN, MSIC code and business activity
  (Settings); customer TIN and registration number (customer record).
- **SST** — invoice tax % feeds the e-Invoice tax category (Sales Tax `01`
  when charged, `06` not-applicable when zero).
- **e-Invoice JSON** — each invoice exports a **MyInvois-aligned UBL JSON**
  (`Invoice → e-Invoice`) with supplier/buyer parties, line items + commodity
  classification, tax totals and monetary totals — ready to hand to a MyInvois
  submitter. Pre-submission **warnings** flag missing TIN/MSIC.

> The final transmit step to the IRBM **MyInvois API** (sign + submit) needs
> IRBM credentials and is left as a documented integration point; PrintSys
> prepares the compliant document.

## Module 10 — CSV Import (from AutoCount)

- **Bulk-load Customers and Stock items** from a CSV exported by AutoCount (or
  any system) under **Import Data**.
- **Flexible column matching** — headers are matched against common aliases,
  case/spacing/punctuation-insensitive (e.g. `Account No`, `Company Name`,
  `Phone1`, `Item Code`, `Balance Qty` are all recognised).
- **Upsert by code** — re-importing updates existing records instead of
  duplicating them; rows missing a code or name are skipped and reported.
- An **import result** screen shows created / updated / skipped counts with the
  reason for each skipped row.

## Module 11 — General Ledger (double-entry)

Full bookkeeping on top of the operational data.

- **Chart of accounts** — a standard chart is seeded (Bank, AR, AP, SST in/out,
  Sales, Purchases, expenses…); add your own accounts.
- **Automatic postings** — invoices, receipts, supplier bills and supplier
  payments post to the ledger automatically (Dr/Cr) — no manual entry needed.
  The subledgers are the source of truth and the GL is derived from them, so it
  is always consistent.
- **Manual journals** — for adjustments, opening balances and expenses, with a
  live debit/credit balance check (won't post unless balanced).
- **Financial statements** — **Trial Balance**, **Profit & Loss** and
  **Balance Sheet** over any date range, plus drill-down **account ledgers**
  with running balances.

## Module 12 — Expenses & Bank Reconciliation

- **Expenses** — record a direct expense (date, payee, category, paid-from
  cash/bank account, amount, SST). It auto-posts to the GL (Dr expense + SST
  input, Cr cash/bank), flowing straight into the P&L — no manual journal.
- **Bank reconciliation** — pick a cash/bank account, enter the statement
  closing balance, and tick the transactions that have cleared. The worksheet
  shows book vs cleared vs statement and the remaining difference; cleared
  marks are saved so you can reconcile over multiple sessions.

## Module 13 — SST-02 Tax Return

- **Bi-monthly summary** — output tax collected on sales versus input tax paid
  on purchases and expenses, for the Malaysian SST taxable period (auto-detected
  Jan-Feb, Mar-Apr, … or any custom range).
- **Breakdown by rate** with taxable values, plus the net SST payable.
- Printable, with the registered-person SST number from Settings. Intended as a
  working summary to support filing through the official MyTax / MySST portal.

## Module 14 — Audit Log

- **Automatic, app-wide trail** — every create / update / delete of a main
  record (customers, quotations, jobs, invoices, payments, bills, expenses,
  journals, accounts, users, settings…) is logged with the **acting user**,
  timestamp, entity, record id and a short description.
- Implemented with SQLAlchemy flush listeners, so it covers every module
  without per-router code; noisy line-items and derived rows are excluded.
- **Admin-only viewer** with entity/action filters.

## Module 15 — Role-Based Permissions

- **Functional areas** — Sales, Invoicing, Purchasing, Banking, Inventory &
  master data, Accounting (GL & SST), Reports, Import.
- **Per-user grants** — admins have everything; each staff user is granted a
  subset of areas from the Users screen.
- **Enforced two ways** — nav sections hide what a user can't use, and the auth
  middleware blocks direct access to ungranted areas (redirecting with a
  message). Users, audit log and settings remain admin-only.

## Module 16 — CSV Export

- **One-click "Export CSV"** on Trial Balance, Profit & Loss, Balance Sheet,
  Sales summary, AR aging, AP aging, Stock valuation and the Audit log
  (date-range filters are carried into the export).
- **Master-data export** of Customers and Stock from the Import/Export screen —
  the same column format the importer reads, so it round-trips cleanly with
  AutoCount or a spreadsheet.
- Files are UTF-8 (with a BOM) so Excel opens them with correct names.
