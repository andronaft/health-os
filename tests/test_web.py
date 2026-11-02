"""web/: the local browser UI server — Host check, session token, CSP, GET only (#50)."""
import re
import shutil
import socket
import stat
import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest
import uvicorn
from starlette.testclient import TestClient

import web.__main__
import web.app
from web.app import ROOT, STATIC, create_app

BASE = "http://127.0.0.1:8765"


@pytest.fixture()
def client():
    return TestClient(create_app("t"), base_url=BASE)


def test_index_is_html_with_a_strict_csp(client):
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "<title>health-os</title>" in r.text


def test_page_has_no_inline_scripts_or_styles():
    # the CSP blocks them, so they would silently do nothing
    html = (STATIC / "index.html").read_text()
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html and " style=" not in html


def test_static_module_is_served_as_javascript(client):
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]  # with nosniff, anything else is blocked


def test_api_needs_the_session_token(client):
    assert client.get("/api/v1/health").status_code == 403
    assert client.get("/api/v1/health", headers={"X-Health-OS-Token": "wrong"}).status_code == 403
    r = client.get("/api/v1/health", headers={"X-Health-OS-Token": "t"})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["version"]
    assert r.headers["cache-control"] == "no-store"


def test_version_comes_from_pyproject(monkeypatch, client):
    # installed metadata lags behind until `uv sync`, and the Docker image has none at all
    def not_installed(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr(web.app, "version", not_installed)
    web.app._version.cache_clear()
    with open(ROOT / "pyproject.toml", "rb") as f:
        expected = tomllib.load(f)["project"]["version"]
    try:
        r = client.get("/api/v1/health", headers={"X-Health-OS-Token": "t"})
        assert r.json()["version"] == expected
    finally:
        web.app._version.cache_clear()


def test_api_errors_are_not_cached_either(client):
    assert client.get("/api/v1/health").headers["cache-control"] == "no-store"


def test_pages_and_static_files_are_revalidated(client):
    # no build step, no hashed file names: without this an edited or updated app.js is served
    # stale from the browser cache for hours (heuristic freshness from Last-Modified)
    assert client.get("/").headers["cache-control"] == "no-cache"
    r = client.get("/static/app.js")
    assert r.headers["cache-control"] == "no-cache"
    again = client.get("/static/app.js", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304


def test_other_sites_cannot_load_our_files(client):
    for path in ("/", "/static/app.js", "/static/styles.css", "/api/v1/health"):
        h = client.get(path).headers
        assert h["cross-origin-resource-policy"] == "same-origin", path
        assert h["cross-origin-opener-policy"] == "same-origin", path


@pytest.mark.parametrize("base", ["http://evil.example", "http://127.0.0.1.evil.example:8765"])
def test_foreign_host_is_rejected(base):
    # DNS rebinding: another site's name pointed at 127.0.0.1 arrives with its own Host
    c = TestClient(create_app("t"), base_url=base)
    r = c.get("/")
    assert r.status_code == 400
    assert "default-src 'self'" in r.headers["content-security-policy"]  # headers on every reply
    assert r.headers["x-content-type-options"] == "nosniff"
    assert c.get("/api/v1/health", headers={"X-Health-OS-Token": "t"}).status_code == 400


def test_localhost_is_allowed():
    assert TestClient(create_app("t"), base_url="http://localhost:8765").get("/").status_code == 200


def test_get_only(client):
    assert client.post("/api/v1/health", headers={"X-Health-OS-Token": "t"}).status_code == 405
    assert client.post("/").status_code == 405


def test_app_refuses_to_start_without_a_token():
    with pytest.raises(ValueError):
        create_app("")


def test_server_binds_to_loopback_only():
    assert web.__main__.HOST == "127.0.0.1"


def test_busy_port_exits_before_the_link_is_shown(monkeypatch, capsys):
    # otherwise the browser would open the token link on whatever else holds the port
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        port = other.getsockname()[1]
        monkeypatch.setattr(sys, "argv", ["web", "--port", str(port), "--no-browser"])
        with pytest.raises(SystemExit) as exc:
            web.__main__.main()
    assert exc.value.code != 0
    assert "token=" not in capsys.readouterr().out


def test_ctrl_c_exits_quietly_and_the_link_has_the_real_port(monkeypatch, capsys):
    seen = {}

    def ctrl_c(self, sockets=None):
        seen["config"] = self.config
        for s in sockets:
            s.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(uvicorn.Server, "run", ctrl_c)
    monkeypatch.setattr(sys, "argv", ["web", "--port", "0", "--no-browser"])
    try:
        web.__main__.main()
    except KeyboardInterrupt:  # pytest would take it as the user aborting the whole run
        pytest.fail("Ctrl+C escaped main(): the user sees a traceback")
    port = int(re.search(r"http://127\.0\.0\.1:(\d+)/#token=", capsys.readouterr().out)[1])
    assert port > 0  # --port 0: the port actually bound, not ":0"
    assert seen["config"].server_header is False


@pytest.mark.parametrize("port", ["70000", "-1", "abc"])
def test_bad_port_is_a_usage_error(monkeypatch, port):
    monkeypatch.setattr(sys, "argv", ["web", "--port", port, "--no-browser"])
    with pytest.raises(SystemExit) as exc:
        web.__main__.main()
    assert exc.value.code == 2  # argparse, not an OverflowError traceback


def test_browser_gets_the_link_directly_on_macos(monkeypatch):
    opened = []
    monkeypatch.setattr(web.__main__.webbrowser, "open", opened.append)
    monkeypatch.setattr(sys, "platform", "darwin")  # osascript reads the URL from stdin
    web.__main__.open_browser("http://127.0.0.1:1/#token=secret")
    assert opened == ["http://127.0.0.1:1/#token=secret"]


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_elsewhere_the_token_stays_off_the_command_line(monkeypatch, platform):
    # a browser started with the URL as an argument shows the token to every user in `ps`
    opened = []
    monkeypatch.setattr(web.__main__.webbrowser, "open", opened.append)
    monkeypatch.setattr(sys, "platform", platform)
    url = "http://127.0.0.1:1/#token=secret"
    web.__main__.open_browser(url)
    [arg] = opened
    assert arg.startswith("file://") and "secret" not in arg
    page = Path(arg.removeprefix("file://"))
    assert f'content="0;url={url}"' in page.read_text()
    assert stat.S_IMODE(page.stat().st_mode) == 0o600
    assert stat.S_IMODE(page.parent.stat().st_mode) == 0o700
    shutil.rmtree(page.parent)
