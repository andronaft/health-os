"""web/: the local browser UI server — Host check, session token, CSP, GET only (#50)."""
import re
import socket
import sys

import pytest
from starlette.testclient import TestClient

import web.__main__
from web.app import STATIC, create_app

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


def test_api_errors_are_not_cached_either(client):
    assert client.get("/api/v1/health").headers["cache-control"] == "no-store"


@pytest.mark.parametrize("base", ["http://evil.example", "http://127.0.0.1.evil.example:8765"])
def test_foreign_host_is_rejected(base):
    # DNS rebinding: another site's name pointed at 127.0.0.1 arrives with its own Host
    c = TestClient(create_app("t"), base_url=base)
    assert c.get("/").status_code == 400
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
