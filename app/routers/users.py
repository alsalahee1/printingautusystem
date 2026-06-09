"""Login / logout and user administration (Module 7).

Login and logout are open to any visitor (login validates credentials); the
user-management screens are restricted to admins via _require_admin.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, hash_password, login_user, logout_user, verify_password
from ..database import get_db
from ..models import USER_ROLES, User
from ..web import flash, templates

router = APIRouter()


def _require_admin(request: Request) -> bool:
    u = current_user(request)
    return bool(u and u.get("role") == "admin")


# --------------------------------------------------------------------------- #
# Login / logout
# --------------------------------------------------------------------------- #
@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"hide_chrome": True})


@router.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if not user or not user.active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html",
            {"hide_chrome": True, "error": "Invalid username or password.", "username": username},
        )
    login_user(request, user)
    flash(request, f"Welcome back, {user.full_name or user.username}.", "success")
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)


# --------------------------------------------------------------------------- #
# User administration (admin only)
# --------------------------------------------------------------------------- #
@router.get("/users", response_class=HTMLResponse)
def list_users(request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        flash(request, "Admins only.", "danger")
        return RedirectResponse("/", status_code=303)
    rows = db.execute(select(User).order_by(User.username)).scalars().all()
    return templates.TemplateResponse(
        request, "users/list.html", {"active_nav": "users", "rows": rows, "roles": USER_ROLES}
    )


@router.post("/users/new")
async def create_user(request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return RedirectResponse("/", status_code=303)
    form = await request.form()
    username = (form.get("username") or "").strip()
    if not username or not form.get("password"):
        flash(request, "Username and password are required.", "warning")
        return RedirectResponse("/users", status_code=303)
    if db.execute(select(User).where(User.username == username)).scalar_one_or_none():
        flash(request, "That username already exists.", "warning")
        return RedirectResponse("/users", status_code=303)
    db.add(User(
        username=username,
        full_name=form.get("full_name") or "",
        role=form.get("role") if form.get("role") in USER_ROLES else "staff",
        password_hash=hash_password(form.get("password")),
    ))
    db.commit()
    flash(request, f"User {username} created.", "success")
    return RedirectResponse("/users", status_code=303)


@router.post("/users/{uid}/update")
async def update_user(uid: int, request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return RedirectResponse("/", status_code=303)
    user = db.get(User, uid)
    if user:
        form = await request.form()
        user.full_name = form.get("full_name") or ""
        if form.get("role") in USER_ROLES:
            user.role = form.get("role")
        user.active = form.get("active") is not None
        if form.get("password"):
            user.password_hash = hash_password(form.get("password"))
        db.commit()
        flash(request, f"User {user.username} updated.", "success")
    return RedirectResponse("/users", status_code=303)


@router.post("/users/{uid}/delete")
def delete_user(uid: int, request: Request, db: Session = Depends(get_db)):
    if not _require_admin(request):
        return RedirectResponse("/", status_code=303)
    user = db.get(User, uid)
    me = current_user(request)
    if user and me and user.id == me["id"]:
        flash(request, "You cannot delete your own account.", "warning")
        return RedirectResponse("/users", status_code=303)
    if user:
        db.delete(user)
        db.commit()
        flash(request, "User deleted.", "success")
    return RedirectResponse("/users", status_code=303)
