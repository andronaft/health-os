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


def _port(value: str) -> int:
    port = int(value)
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be 0–65535 (0 = any free port)")
    return port


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m web",
                                     description="health-os browser UI (local only)")
    parser.add_argument("--port", type=_port, default=settings.ui_port,
                        help="port on 127.0.0.1 (default: UI_PORT; 0 = any free port)")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = parser.parse_args()

    token = secrets.token_urlsafe(24)
    config = uvicorn.Config(create_app(token), host=HOST, port=args.port, log_level="warning",
                            server_header=False)
    # bind first: if the port is taken, exit before the link (with its token) goes to whatever
    # else is listening there
    sock = config.bind_socket()
    port = sock.getsockname()[1]  # the real one when --port 0
    # the token travels in the URL fragment: browsers never send it to the server or log it
    url = f"http://{HOST}:{port}/#token={token}"
    print(f"health-os UI: {url}\n(local only; the link works until this process stops)",
          flush=True)
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        uvicorn.Server(config).run(sockets=[sock])
    except KeyboardInterrupt:  # Ctrl+C: uvicorn has already shut down cleanly
        pass


if __name__ == "__main__":
    main()
