"""Work-Order / Job-Card screens (Module 3).

A job card is the production view of an order. It is normally created by
converting an approved quotation (carrying every line's spec onto the floor),
then tracked through a checklist of production stages (pre-press -> CTP ->
printing -> finishing -> cutting/QC -> delivery) until delivered.
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    DEFAULT_JOB_STAGES,
    JOB_PRIORITIES,
    JOB_STATUSES,
    Customer,
    Job,
    JobItem,
    JobStage,
    Machine,
    Quotation,
    StockItem,
)
from ..web import flash, templates
from .quotations import _f, get_settings

router = APIRouter()


def _next_job_number(db: Session) -> str:
    # Derive the next sequence from the current job count, then bump past any
    # number already taken so deletions can't cause a unique-constraint clash.
    n = (db.query(Job).count() or 0) + 1
    while db.query(Job).filter(Job.number == f"JOB-{n:04d}").first():
        n += 1
    return f"JOB-{n:04d}"


def _seed_stages(job: Job) -> None:
    for i, name in enumerate(DEFAULT_JOB_STAGES, start=1):
        job.stages.append(JobStage(seq=i, name=name))


def _machine_paper_choices(db: Session) -> dict:
    papers = db.execute(
        select(StockItem).where(StockItem.category == "Paper").order_by(StockItem.name)
    ).scalars().all()
    machines = db.execute(
        select(Machine).where(Machine.active == True).order_by(Machine.name)
    ).scalars().all()
    return {"papers": papers, "machines": machines}


# --------------------------------------------------------------------------- #
# List & dashboard-style board
# --------------------------------------------------------------------------- #
@router.get("/jobs", response_class=HTMLResponse)
def list_jobs(request: Request, db: Session = Depends(get_db), status: str | None = None):
    stmt = select(Job).order_by(Job.id.desc())
    if status:
        stmt = stmt.where(Job.status == status)
    rows = db.execute(stmt).scalars().all()
    counts = {s: db.query(Job).filter(Job.status == s).count() for s in JOB_STATUSES}
    return templates.TemplateResponse(
        request, "jobs/list.html",
        {"active_nav": "jobs", "rows": rows, "statuses": JOB_STATUSES,
         "counts": counts, "active_status": status},
    )


# --------------------------------------------------------------------------- #
# Convert an approved quotation into a job
# --------------------------------------------------------------------------- #
@router.post("/jobs/from-quotation/{qid}")
def convert_quotation(qid: int, request: Request, db: Session = Depends(get_db)):
    q = db.get(Quotation, qid)
    if not q:
        flash(request, "Quotation not found.", "danger")
        return RedirectResponse("/quotations", status_code=303)
    if not q.items:
        flash(request, "Add line items to the quotation before converting.", "warning")
        return RedirectResponse(f"/quotations/{qid}", status_code=303)

    job = Job(
        number=_next_job_number(db),
        quotation_id=q.id,
        customer_id=q.customer_id,
        title=q.items[0].title if q.items else q.number,
        status="Pre-press",
        order_date=date.today(),
    )
    for it in q.items:
        job.items.append(JobItem(
            line_no=it.line_no, title=it.title, quantity=it.quantity,
            paper_id=it.paper_id, finished_width_mm=it.finished_width_mm,
            finished_height_mm=it.finished_height_mm, colors_front=it.colors_front,
            colors_back=it.colors_back, machine_id=it.machine_id, ups=it.ups,
            total_sheets=it.total_sheets, num_plates=it.num_plates,
            finishing_summary=", ".join(f.finishing.name for f in it.finishings),
        ))
    _seed_stages(job)
    db.add(job)
    db.commit()
    flash(request, f"Job {job.number} created from {q.number}.", "success")
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


# --------------------------------------------------------------------------- #
# Manual create / edit header
# --------------------------------------------------------------------------- #
@router.get("/jobs/new", response_class=HTMLResponse)
def new_job(request: Request, db: Session = Depends(get_db)):
    customers = db.execute(
        select(Customer).where(Customer.active == True).order_by(Customer.name)
    ).scalars().all()
    return templates.TemplateResponse(
        request, "jobs/form.html",
        {"active_nav": "jobs", "obj": None, "customers": customers,
         "statuses": JOB_STATUSES, "priorities": JOB_PRIORITIES,
         "order_date": date.today().isoformat(),
         "due_date": (date.today() + timedelta(days=7)).isoformat()},
    )


@router.post("/jobs/new")
async def create_job(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    job = Job(
        number=_next_job_number(db),
        customer_id=int(form["customer_id"]),
        title=form.get("title") or "",
        status=form.get("status") or "Pre-press",
        priority=form.get("priority") or "Normal",
        order_date=date.fromisoformat(form.get("order_date") or date.today().isoformat()),
        due_date=date.fromisoformat(form["due_date"]) if form.get("due_date") else None,
        assigned_to=form.get("assigned_to") or "",
        notes=form.get("notes") or "",
    )
    _seed_stages(job)
    db.add(job)
    db.commit()
    flash(request, f"Job {job.number} created.", "success")
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@router.get("/jobs/{jid}", response_class=HTMLResponse)
def view_job(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if not job:
        flash(request, "Job not found.", "danger")
        return RedirectResponse("/jobs", status_code=303)
    ctx = {"active_nav": "jobs", "job": job, "statuses": JOB_STATUSES}
    ctx.update(_machine_paper_choices(db))
    return templates.TemplateResponse(request, "jobs/view.html", ctx)


@router.get("/jobs/{jid}/edit", response_class=HTMLResponse)
def edit_job(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if not job:
        return RedirectResponse("/jobs", status_code=303)
    customers = db.execute(
        select(Customer).where(Customer.active == True).order_by(Customer.name)
    ).scalars().all()
    return templates.TemplateResponse(
        request, "jobs/form.html",
        {"active_nav": "jobs", "obj": job, "customers": customers,
         "statuses": JOB_STATUSES, "priorities": JOB_PRIORITIES,
         "order_date": job.order_date.isoformat(),
         "due_date": job.due_date.isoformat() if job.due_date else ""},
    )


@router.post("/jobs/{jid}/edit")
async def update_job(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if not job:
        return RedirectResponse("/jobs", status_code=303)
    form = await request.form()
    job.customer_id = int(form["customer_id"])
    job.title = form.get("title") or ""
    job.status = form.get("status") or job.status
    job.priority = form.get("priority") or job.priority
    job.order_date = date.fromisoformat(form.get("order_date") or job.order_date.isoformat())
    job.due_date = date.fromisoformat(form["due_date"]) if form.get("due_date") else None
    job.assigned_to = form.get("assigned_to") or ""
    job.notes = form.get("notes") or ""
    db.commit()
    flash(request, "Job updated.", "success")
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@router.post("/jobs/{jid}/status")
async def set_job_status(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if job:
        form = await request.form()
        job.status = form.get("status") or job.status
        db.commit()
        flash(request, f"Job marked {job.status}.", "success")
    return RedirectResponse(f"/jobs/{jid}", status_code=303)


@router.post("/jobs/{jid}/delete")
def delete_job(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if job:
        db.delete(job)
        db.commit()
        flash(request, f"Job {job.number} deleted.", "success")
    return RedirectResponse("/jobs", status_code=303)


# --------------------------------------------------------------------------- #
# Production stage tracking
# --------------------------------------------------------------------------- #
@router.post("/jobs/{jid}/stages/{sid}/toggle")
async def toggle_stage(jid: int, sid: int, request: Request, db: Session = Depends(get_db)):
    stage = db.get(JobStage, sid)
    if stage and stage.job_id == jid:
        stage.done = not stage.done
        stage.completed_at = datetime.utcnow() if stage.done else None
        form = await request.form()
        if form.get("note") is not None:
            stage.note = form.get("note")
        db.commit()
    return RedirectResponse(f"/jobs/{jid}", status_code=303)


# --------------------------------------------------------------------------- #
# Job items (production spec lines)
# --------------------------------------------------------------------------- #
def _apply_job_item(item: JobItem, form):
    item.title = form.get("title") or ""
    item.quantity = int(_f(form, "quantity", int, 0))
    item.paper_id = int(form["paper_id"]) if form.get("paper_id") else None
    item.finished_width_mm = _f(form, "finished_width_mm", float, 0)
    item.finished_height_mm = _f(form, "finished_height_mm", float, 0)
    item.colors_front = int(_f(form, "colors_front", int, 0))
    item.colors_back = int(_f(form, "colors_back", int, 0))
    item.machine_id = int(form["machine_id"]) if form.get("machine_id") else None
    item.ups = int(_f(form, "ups", int, 0))
    item.total_sheets = int(_f(form, "total_sheets", int, 0))
    item.num_plates = int(_f(form, "num_plates", int, 0))
    item.finishing_summary = form.get("finishing_summary") or ""
    item.notes = form.get("notes") or ""


@router.get("/jobs/{jid}/items/new", response_class=HTMLResponse)
def new_job_item(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if not job:
        return RedirectResponse("/jobs", status_code=303)
    ctx = {"active_nav": "jobs", "job": job, "obj": None}
    ctx.update(_machine_paper_choices(db))
    return templates.TemplateResponse(request, "jobs/item_form.html", ctx)


@router.post("/jobs/{jid}/items/new")
async def create_job_item(jid: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    if not job:
        return RedirectResponse("/jobs", status_code=303)
    form = await request.form()
    item = JobItem(job_id=job.id, line_no=len(job.items) + 1)
    _apply_job_item(item, form)
    db.add(item)
    db.commit()
    flash(request, "Job item added.", "success")
    return RedirectResponse(f"/jobs/{jid}", status_code=303)


@router.get("/jobs/{jid}/items/{item_id}/edit", response_class=HTMLResponse)
def edit_job_item(jid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    job = db.get(Job, jid)
    item = db.get(JobItem, item_id)
    if not job or not item:
        return RedirectResponse(f"/jobs/{jid}", status_code=303)
    ctx = {"active_nav": "jobs", "job": job, "obj": item}
    ctx.update(_machine_paper_choices(db))
    return templates.TemplateResponse(request, "jobs/item_form.html", ctx)


@router.post("/jobs/{jid}/items/{item_id}/edit")
async def update_job_item(jid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(JobItem, item_id)
    if not item:
        return RedirectResponse(f"/jobs/{jid}", status_code=303)
    form = await request.form()
    _apply_job_item(item, form)
    db.commit()
    flash(request, "Job item updated.", "success")
    return RedirectResponse(f"/jobs/{jid}", status_code=303)


@router.post("/jobs/{jid}/items/{item_id}/delete")
def delete_job_item(jid: int, item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.get(JobItem, item_id)
    if item:
        db.delete(item)
        db.commit()
        flash(request, "Job item removed.", "success")
    return RedirectResponse(f"/jobs/{jid}", status_code=303)
