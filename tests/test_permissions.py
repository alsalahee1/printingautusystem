"""Granular role-based permission tests."""
from app.permissions import area_for_path, can_access


def test_area_resolution_prefers_specific_prefix():
    assert area_for_path("/quotations/5/edit") == "sales"
    assert area_for_path("/reports/sales") == "reports"
    assert area_for_path("/reports/sst02") == "accounting"   # specific wins over /reports
    assert area_for_path("/") is None                         # dashboard is open


def test_can_access_rules():
    # Admin: everything.
    assert can_access("/accounts", "admin", [])
    assert can_access("/users", "admin", [])
    # Staff: only granted areas; admin-only always denied.
    assert can_access("/quotations", "staff", ["sales"])
    assert not can_access("/accounts", "staff", ["sales"])
    assert not can_access("/users", "staff", ["accounting"])
    assert can_access("/", "staff", [])                       # dashboard open to all


def _make_staff(admin_client, areas):
    admin_client.post("/users/new", data={
        "username": "sara", "full_name": "Sara", "role": "staff",
        "password": "pw12345", "permissions": areas})


def test_staff_is_blocked_from_ungranted_areas(client, anon):
    _make_staff(client, ["sales", "invoicing"])
    anon.post("/login", data={"username": "sara", "password": "pw12345"})

    assert anon.get("/quotations", follow_redirects=False).status_code == 200   # granted
    assert anon.get("/invoices", follow_redirects=False).status_code == 200     # granted
    assert anon.get("/accounts", follow_redirects=False).status_code == 303     # not granted
    assert anon.get("/customers", follow_redirects=False).status_code == 303    # not granted
    assert anon.get("/settings", follow_redirects=False).status_code == 303     # admin only
    assert anon.get("/", follow_redirects=False).status_code == 200             # dashboard open


def test_nav_only_shows_granted_sections(client, anon):
    _make_staff(client, ["sales"])
    anon.post("/login", data={"username": "sara", "password": "pw12345"})
    nav = anon.get("/").text
    assert "Quotations" in nav
    assert "Chart of Accounts" not in nav
    assert ">Settings<" not in nav
