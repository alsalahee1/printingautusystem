"""PrintSys — offset-printing management system.

FastAPI application entrypoint. Mounts the dashboard and master-data routers,
creates database tables on startup, and wires session + static-file support.
"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .database import Base, engine
from .routers import (
    accounting,
    dashboard,
    jobs,
    master_data,
    purchasing,
    quotations,
    reports,
)

app = FastAPI(title="PrintSys — Offset Printing Management")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("PRINTSYS_SECRET", "dev-secret-change-me"),
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(dashboard.router)
app.include_router(quotations.router)
app.include_router(jobs.router)
app.include_router(accounting.router)
app.include_router(purchasing.router)
app.include_router(reports.router)
for r in master_data.routers:
    app.include_router(r)


@app.on_event("startup")
def on_startup() -> None:
    # Import models so their tables are registered before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}
