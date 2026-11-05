"""The browser UI's web app: static pages + a read-only JSON API, for this machine only.

Health data, so the server is strict even though it only listens on 127.0.0.1:
- the Host header must be 127.0.0.1/localhost — a page on another site can't reach the API by
  pointing its own domain at 127.0.0.1 (DNS rebinding);
- every /api request carries the session token printed at start-up, so another local process
  or browser tab without it gets 403;
- GET only, a strict Content-Security-Policy, no external scripts, fonts or requests.
"""
from __future__ import annotations

import contextlib
import functools
import hmac
import json
import tomllib
from datetime import date, datetime
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from core.db import engine
from web.overview import overview as read_overview

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web" / "static"
TOKEN_HEADER = "x-health-os-token"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SECURITY_HEADERS = {
    "content-security-policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'none'; frame-ancestors 'none'"),
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    # other sites can't load our files as subresources (and so can't tell the UI is running)
    "cross-origin-resource-policy": "same-origin",
    "cross-origin-opener-policy": "same-origin",
}


class SecurityHeaders:
    """Adds SECURITY_HEADERS to every response. API responses are never cached; pages and static
    files are revalidated on every load (ETag → 304), so an edited or updated file is never served
    stale from the browser cache — there is no build step to give them hashed names."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                extra = dict(SECURITY_HEADERS)
                extra["cache-control"] = ("no-store" if scope["path"].startswith("/api/")
                                          else "no-cache")
                headers += [(k.encode(), v.encode()) for k, v in extra.items()]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


class RequireToken:
    """/api/* answers 403 unless the request carries the session token."""

    def __init__(self, app, token: str):
        self.app, self.token = app, token.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            sent = dict(scope.get("headers", [])).get(TOKEN_HEADER.encode(), b"")
            if not hmac.compare_digest(sent, self.token):
                return await JSONResponse({"error": "missing or wrong session token"},
                                          status_code=403)(scope, receive, send)
        await self.app(scope, receive, send)


@functools.cache
def _version() -> str:
    # pyproject.toml first: the UI runs from a checkout (the wheel doesn't package web/), where
    # installed metadata is stale until the next `uv sync` and the Docker image has none at all
    try:
        with open(ROOT / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        pass
    try:
        return version("health-os")
    except PackageNotFoundError:
        return "dev"


async def index(request):
    return FileResponse(STATIC / "index.html")


async def health(request):
    return JSONResponse({"ok": True, "version": _version()})


def _plain(value):
    """What the driver returns but JSON has no type for."""
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, date | datetime):
        return value.isoformat()  # keeps the offset, so the date part is what the summary prints
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


class ApiResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, default=_plain, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode()


@contextlib.contextmanager
def read_only_snapshot():
    """One consistent view of the database that Postgres refuses to write through. On the main
    login, like get_health_summary: the profile and the critical thresholds are base tables, which
    the read-only login can't read."""
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        yield conn


def overview(request):  # not async: Starlette runs it in a thread, so the query can't block others
    lang = request.query_params.get("lang", "en")
    try:
        with read_only_snapshot() as conn:
            return ApiResponse(read_overview(conn, lang))
    except OperationalError:
        return JSONResponse({"error": "database unreachable"}, status_code=503)


def create_app(token: str) -> Starlette:
    if not token:
        raise ValueError("a session token is required")
    routes = [
        Route("/", index, methods=["GET"]),
        Route("/api/v1/health", health, methods=["GET"]),
        Route("/api/v1/overview", overview, methods=["GET"]),
        Mount("/static", StaticFiles(directory=STATIC), name="static"),
    ]
    return Starlette(routes=routes, middleware=[
        Middleware(SecurityHeaders),  # outermost, so the Host check's 400 gets the headers too
        Middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS, www_redirect=False),
        Middleware(RequireToken, token=token),
    ])
