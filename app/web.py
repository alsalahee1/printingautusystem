"""Shared web helpers: the Jinja templates object and a tiny flash system.

Flash messages are stashed on Starlette's request.session (SessionMiddleware)
so they survive the POST -> redirect -> GET pattern used by the CRUD screens.
A context processor binds `get_flashes()` to the active request inside every
template, so base.html can render and clear pending messages.
"""
from fastapi import Request
from fastapi.templating import Jinja2Templates


def flash(request: Request, message: str, category: str = "info") -> None:
    request.session.setdefault("_flashes", []).append((category, message))


def _flash_context(request: Request) -> dict:
    return {"get_flashes": lambda: request.session.pop("_flashes", [])}


templates = Jinja2Templates(
    directory="app/templates",
    context_processors=[_flash_context],
)

# Default empty dynamic-options map; per-request context (extra_context on an
# EntityConfig) overrides this when a form needs DB-driven select choices.
templates.env.globals["dyn_options"] = {}
