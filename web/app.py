"""The browser UI's web app: static pages + a read-only JSON API, for this machine only.

Health data, so the server is strict even though it only listens on 127.0.0.1:
- the Host header must be 127.0.0.1/localhost — a page on another site can't reach the API by
  pointing its own domain at 127.0.0.1 (DNS rebinding);
- every /api request carries the session token printed at start-up, so another local process
  or browser tab without it gets 403;
- GET only, a strict Content-Security-Policy, no external scripts, fonts or requests.
"""
from __future__ import annotations

import hmac
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

STATIC = Path(__file__).resolve().parent / "static"
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
}


class SecurityHeaders:
    """Adds SECURITY_HEADERS to every response; API responses are never cached."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                extra = dict(SECURITY_HEADERS)
                if scope["path"].startswith("/api/"):
                    extra["cache-control"] = "no-store"
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


def _version() -> str:
    try:
        return version("health-os")
    except PackageNotFoundError:
        return "dev"


async def index(request):
    return FileResponse(STATIC / "index.html")


async def health(request):
    return JSONResponse({"ok": True, "version": _version()})


def create_app(token: str) -> Starlette:
    if not token:
        raise ValueError("a session token is required")
    routes = [
        Route("/", index, methods=["GET"]),
        Route("/api/v1/health", health, methods=["GET"]),
        Mount("/static", StaticFiles(directory=STATIC), name="static"),
    ]
    return Starlette(routes=routes, middleware=[
        Middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS, www_redirect=False),
        Middleware(SecurityHeaders),
        Middleware(RequireToken, token=token),
    ])
