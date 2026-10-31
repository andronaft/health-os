"""`python -m web` / `make ui`: start the browser UI on 127.0.0.1 and open it."""
from __future__ import annotations

import argparse
import secrets
import threading
import webbrowser

import uvicorn

from core.config import settings
from web.app import create_app

HOST = "127.0.0.1"  # never configurable: the UI shows health data


def main() -> None:
    parser = argparse.ArgumentParser(description="health-os browser UI (local only)")
    parser.add_argument("--port", type=int, default=settings.ui_port)
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()

    token = secrets.token_urlsafe(24)
    config = uvicorn.Config(create_app(token), host=HOST, port=args.port, log_level="warning")
    # bind first: if the port is taken, exit before the link (with its token) goes to whatever
    # else is listening there
    sock = config.bind_socket()
    # the token travels in the URL fragment: browsers never send it to the server or log it
    url = f"http://{HOST}:{args.port}/#token={token}"
    print(f"health-os UI: {url}\n(local only; the link works until this process stops)",
          flush=True)
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.Server(config).run(sockets=[sock])


if __name__ == "__main__":
    main()
