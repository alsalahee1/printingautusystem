"""Functional-area permissions (Module 15).

Access is granted per functional area. Admins implicitly have every area; other
users are granted a subset (stored on the user and copied into the session).
The auth middleware calls `can_access` for each request; templates gate nav
sections with the same area keys.
"""

# (key, label, url-prefixes that belong to this area)
PERMISSION_AREAS = [
    ("sales", "Sales — quotations, jobs, delivery orders",
     ["/quotations", "/jobs", "/delivery-orders", "/api"]),
    ("invoicing", "Invoicing & receivables", ["/invoices", "/ar"]),
    ("purchasing", "Purchasing, bills & expenses",
     ["/purchase-orders", "/bills", "/ap", "/expenses"]),
    ("banking", "Bank reconciliation", ["/reconcile"]),
    ("inventory", "Inventory & master data",
     ["/customers", "/suppliers", "/stock", "/stock-movements", "/finishing", "/machines"]),
    ("accounting", "General ledger & SST",
     ["/accounts", "/journals", "/trial-balance", "/profit-loss", "/balance-sheet", "/reports/sst02"]),
    ("reports", "Business reports", ["/reports"]),
    ("import", "Data import", ["/import"]),
]
AREA_KEYS = [k for k, _, _ in PERMISSION_AREAS]

# Always restricted to admins, regardless of granted areas.
ADMIN_ONLY_PREFIXES = ["/users", "/audit-log", "/settings"]
# Open to any authenticated user (no area required).
OPEN_PATHS = {"/", "/login", "/logout", "/health"}
OPEN_PREFIXES = ["/static"]


def _matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def area_for_path(path: str) -> str | None:
    """Return the area key owning `path`, or None if it is not area-restricted.

    Areas are tested in declaration order so more specific prefixes (e.g.
    /reports/sst02 under accounting) win over broader ones (/reports)."""
    for key, _, prefixes in PERMISSION_AREAS:
        if any(_matches(path, p) for p in prefixes):
            return key
    return None


def can_access(path: str, role: str, perms: list[str]) -> bool:
    if role == "admin":
        return True
    if any(_matches(path, p) for p in ADMIN_ONLY_PREFIXES):
        return False
    if path in OPEN_PATHS or any(path.startswith(p) for p in OPEN_PREFIXES):
        return True
    area = area_for_path(path)
    return area is None or area in (perms or [])
