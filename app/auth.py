"""Authentication: password hashing, session helpers and access middleware.

Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library only — no extra
dependency) and stored as ``salt$hash`` hex. Login state lives on the Starlette
session; a small middleware redirects anonymous users to /login for everything
except the login page, health check and static assets.
"""
import hashlib
import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse

_ITERATIONS = 240_000
PUBLIC_PREFIXES = ("/static",)
PUBLIC_PATHS = {"/login", "/health"}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt_hex, hash_hex = stored.split("$", 1)
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return hmac.compare_digest(dk.hex(), hash_hex)


def login_user(request: Request, user) -> None:
    request.session["user"] = {
        "id": user.id, "username": user.username,
        "full_name": user.full_name, "role": user.role,
        "permissions": [p for p in (user.permissions or "").split(",") if p],
    }


def logout_user(request: Request) -> None:
    request.session.pop("user", None)


def current_user(request: Request) -> dict | None:
    return request.session.get("user")


class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated requests to the login page.

    Added *inside* SessionMiddleware (see app.main) so request.session is
    populated by the time this runs.
    """

    async def dispatch(self, request: Request, call_next):
        from .audit import current_user_var
        from .permissions import can_access

        path = request.url.path
        is_public = path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES)
        user = request.session.get("user")
        if not is_public and not user:
            return RedirectResponse("/login", status_code=303)
        # Enforce functional-area permissions for authenticated, non-public paths.
        if user and not is_public and not can_access(path, user.get("role", ""), user.get("permissions", [])):
            request.session.setdefault("_flashes", []).append(
                ("danger", "You don't have access to that section."))
            return RedirectResponse("/", status_code=303)
        # Tag DB writes during this request with the acting user (for the audit log).
        token = current_user_var.set(user["username"] if user else "system")
        try:
            return await call_next(request)
        finally:
            current_user_var.reset(token)
