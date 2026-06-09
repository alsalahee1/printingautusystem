"""Database engine, session, and base class.

Uses SQLite for zero-config local/shop deployment. The connection string is
read from the PRINTSYS_DB_URL environment variable so it can be swapped for
PostgreSQL or SQL Server in production without code changes.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_URL = os.environ.get("PRINTSYS_DB_URL", "sqlite:///./printsys.db")

# check_same_thread is only needed for SQLite + FastAPI's threadpool.
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
