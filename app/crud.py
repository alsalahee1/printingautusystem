"""Config-driven CRUD for master-data entities.

Each master-data screen (customers, suppliers, stock, finishing, machines) is
described by an EntityConfig: which model it edits, which columns to show in the
list, and which fields to render on the form. A single factory then builds the
list / new / edit / delete routes and renders the shared generic templates.

This keeps the five near-identical maintenance screens DRY while letting each
one declare its own printing-specific fields.
"""
from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .web import flash, templates


@dataclass
class Field:
    name: str
    label: str
    type: str = "text"            # text, number, textarea, select, checkbox, email
    required: bool = False
    options: list = field(default_factory=list)   # for select: list[(value, label)]
    options_key: str = ""         # template context key holding dynamic options
    default: Any = ""
    step: str = "any"             # for number inputs
    help: str = ""
    group: str = ""               # optional fieldset grouping on the form


@dataclass
class Column:
    name: str
    label: str
    kind: str = "text"            # text, number, money, bool, badge
    accessor: Callable | None = None   # optional func(obj) -> display value


@dataclass
class EntityConfig:
    slug: str                     # url segment, e.g. "customers"
    model: type
    singular: str
    plural: str
    nav: str
    icon: str
    columns: list
    fields: list
    order_by: str = "code"
    # Optional hook to provide extra template context (e.g. select options).
    extra_context: Callable[[Session], dict] | None = None


def _coerce(field_def: Field, raw: str | None):
    if field_def.type == "checkbox":
        return raw is not None
    if field_def.type == "number":
        if raw is None or raw == "":
            return 0
        try:
            num = float(raw)
            return int(num) if num.is_integer() else num
        except ValueError:
            return 0
    if raw is None:
        return field_def.default
    raw = raw.strip()
    # Empty foreign-key / optional select -> None
    if raw == "" and field_def.name.endswith("_id"):
        return None
    return raw


def build_router(cfg: EntityConfig) -> APIRouter:
    router = APIRouter()

    def base_ctx(request: Request, db: Session) -> dict:
        ctx = {"request": request, "cfg": cfg, "active_nav": cfg.nav}
        if cfg.extra_context:
            ctx.update(cfg.extra_context(db))
        return ctx

    @router.get(f"/{cfg.slug}", response_class=HTMLResponse)
    def list_view(request: Request, db: Session = Depends(get_db)):
        order_col = getattr(cfg.model, cfg.order_by)
        rows = db.execute(select(cfg.model).order_by(order_col)).scalars().all()
        ctx = base_ctx(request, db)
        ctx["rows"] = rows
        return templates.TemplateResponse(request, "crud/list.html", ctx)

    @router.get(f"/{cfg.slug}/new", response_class=HTMLResponse)
    def new_view(request: Request, db: Session = Depends(get_db)):
        ctx = base_ctx(request, db)
        ctx["obj"] = None
        return templates.TemplateResponse(request, "crud/form.html", ctx)

    @router.post(f"/{cfg.slug}/new")
    async def create(request: Request, db: Session = Depends(get_db)):
        form = await request.form()
        obj = cfg.model()
        for f in cfg.fields:
            setattr(obj, f.name, _coerce(f, form.get(f.name)))
        db.add(obj)
        db.commit()
        flash(request, f"{cfg.singular} created.", "success")
        return RedirectResponse(f"/{cfg.slug}", status_code=303)

    @router.get(f"/{cfg.slug}/{{obj_id}}/edit", response_class=HTMLResponse)
    def edit_view(obj_id: int, request: Request, db: Session = Depends(get_db)):
        obj = db.get(cfg.model, obj_id)
        if not obj:
            flash(request, f"{cfg.singular} not found.", "danger")
            return RedirectResponse(f"/{cfg.slug}", status_code=303)
        ctx = base_ctx(request, db)
        ctx["obj"] = obj
        return templates.TemplateResponse(request, "crud/form.html", ctx)

    @router.post(f"/{cfg.slug}/{{obj_id}}/edit")
    async def update(obj_id: int, request: Request, db: Session = Depends(get_db)):
        obj = db.get(cfg.model, obj_id)
        if not obj:
            flash(request, f"{cfg.singular} not found.", "danger")
            return RedirectResponse(f"/{cfg.slug}", status_code=303)
        form = await request.form()
        for f in cfg.fields:
            setattr(obj, f.name, _coerce(f, form.get(f.name)))
        db.commit()
        flash(request, f"{cfg.singular} updated.", "success")
        return RedirectResponse(f"/{cfg.slug}", status_code=303)

    @router.post(f"/{cfg.slug}/{{obj_id}}/delete")
    def delete(obj_id: int, request: Request, db: Session = Depends(get_db)):
        obj = db.get(cfg.model, obj_id)
        if obj:
            db.delete(obj)
            db.commit()
            flash(request, f"{cfg.singular} deleted.", "success")
        return RedirectResponse(f"/{cfg.slug}", status_code=303)

    return router
