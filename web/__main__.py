"""`python -m web` / `make ui`: start the browser UI on 127.0.0.1 and open it."""
from __future__ import annotations

import argparse
import atexit
import html
import os
import secrets
import shutil
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path

import uvicorn

from core.config import settings
from web.app import create_app

HOST = "127.0.0.1"  # never configurable: the UI shows health data
REDIRECT = """<!doctype html>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={url}">
<title>health-os</title>
<p><a href="{url}">Open health-os</a></p>
"""


def _port(value: str) -> int:
    port = int(value)
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError("must be 0–65535 (0 = any free port)")
    return port


def open_browser(url: str) -> None:
    """Open the link without putting the token on a command line.

    macOS hands the URL to the browser through osascript's stdin. Elsewhere the browser gets it
    as a command-line argument, which other users of the machine can read in `ps` for as long as
    that browser runs — so it opens a private redirect file instead, as Jupyter does. A file
    left behind (the process was killed) holds a dead token: every run makes a new one.
    """
    if sys.platform == "darwin":
        webbrowser.open(url)
        return
    folder = Path(tempfile.mkdtemp(prefix="health-os-ui-"))  # 0700
    atexit.register(shutil.rmtree, folder, ignore_errors=True)
    page = folder / "open.html"
    with os.fdopen(os.open(page, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        f.write(REDIRECT.format(url=html.escape(url)))
    webbrowser.open(page.as_uri())


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
        threading.Timer(1.0, open_browser, args=(url,)).start()
    try:
        uvicorn.Server(config).run(sockets=[sock])
    except KeyboardInterrupt:  # Ctrl+C: uvicorn has already shut down cleanly
        pass


if __name__ == "__main__":
    main()
