"""Pytest fixtures: an isolated SQLite database and ready-to-use clients.

PRINTSYS_DB_URL must be set *before* app modules import (the engine binds at
import time), so it is configured here at the top of conftest, which pytest
loads before the test modules.
"""
import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="printsys-test-")
os.environ["PRINTSYS_DB_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["PRINTSYS_SECRET"] = "test-secret"
os.environ["PRINTSYS_ADMIN_PASS"] = "admin"

from starlette.testclient import TestClient  # noqa: E402

from app import seed as seed_module  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import _seed_admin, app  # noqa: E402


@pytest.fixture(autouse=True)
def _database():
    """Fresh, isolated database for every test (so tests never leak state)."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _seed_admin()
    seed_module.seed()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """A TestClient already logged in as the seeded admin."""
    c = TestClient(app)
    r = c.post("/login", data={"username": "admin", "password": "admin"},
               follow_redirects=False)
    assert r.status_code == 303
    return c


@pytest.fixture
def anon():
    return TestClient(app)
