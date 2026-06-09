"""PrintSys — offset-printing management system.

FastAPI application entrypoint. Mounts the routers, creates database tables on
startup, seeds a default admin user, and wires session, auth and static files.
"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import AuthMiddleware, hash_password
from .database import Base, SessionLocal, engine
from .routers import (
    accounting,
    dashboard,
    imports,
    jobs,
    master_data,
    purchasing,
    quotations,
    reports,
    users,
)

app = FastAPI(title="PrintSys — Offset Printing Management")

# Middleware runs outermost-first. AuthMiddleware is added BEFORE SessionMiddleware
# so that Session ends up outermost and request.session is ready when auth runs.
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("PRINTSYS_SECRET", "dev-secret-change-me"),
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(users.router)
app.include_router(dashboard.router)
app.include_router(quotations.router)
app.include_router(jobs.router)
app.include_router(accounting.router)
app.include_router(purchasing.router)
app.include_router(reports.router)
app.include_router(imports.router)
for r in master_data.routers:
    app.include_router(r)


def _seed_admin() -> None:
    """Create a default admin (admin / admin) on a fresh database."""
    from .models import User

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            db.add(User(
                username="admin", full_name="Administrator", role="admin",
                password_hash=hash_password(os.environ.get("PRINTSYS_ADMIN_PASS", "admin")),
            ))
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    # Import models so their tables are registered before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _seed_admin()


@app.get("/health")
def health():
    return {"status": "ok"}
