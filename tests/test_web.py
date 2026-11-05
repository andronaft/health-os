"""web/: the local browser UI server — Host check, session token, CSP, GET only (#50) — and the
frame every page shares: its files, tokens, words and the vendored ECharts (#53)."""
import hashlib
import re
import shutil
import socket
import stat
import subprocess
import sys
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest
import uvicorn
from starlette.testclient import TestClient

import web.__main__
import web.app
from analytics.screening import _rules
from web.app import ROOT, STATIC, create_app
from web.overview import TILES

BASE = "http://127.0.0.1:8765"
ECHARTS = STATIC / "vendor" / "echarts"
OUR_FILES = sorted(p for p in STATIC.rglob("*") if p.is_file() and "vendor" not in p.parts)
OUR_SCRIPTS = [p for p in OUR_FILES if p.suffix == ".js"]


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


def test_frame_has_navigation_and_the_disclaimer(client):
    html = client.get("/").text
    assert 'id="nav"' in html and 'id="main"' in html
    assert "Not a medical device" in html  # in the page itself: it shows even if a script fails


def test_theme_is_set_before_the_first_paint():
    # a module runs after the first paint, which would flash the other theme
    html = (STATIC / "index.html").read_text()
    assert '<script src="/static/theme-init.js"></script>' in html
    for name in ("theme-init.js", "theme.js"):
        assert '"health-os-theme"' in (STATIC / name).read_text(), name


def test_every_local_file_the_ui_refers_to_is_served(client):
    html = (STATIC / "index.html").read_text()
    urls = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    for script in OUR_SCRIPTS:
        for rel in re.findall(r"""(?:from\s+|import\()"(\.[^"<]+)\"""", script.read_text()):
            urls.append("/static/" + (script.parent / rel).resolve().relative_to(STATIC).as_posix())
    assert "/static/vendor/echarts/echarts.esm.min.js" in urls
    for url in urls:
        r = client.get(url)
        assert r.status_code == 200, url
        if url.endswith(".js"):  # with nosniff, anything else is blocked
            assert "javascript" in r.headers["content-type"], url
        if url.endswith(".css"):
            assert r.headers["content-type"].startswith("text/css"), url


def test_our_files_name_nothing_external():
    for path in OUR_FILES:
        text = path.read_text()
        assert not re.search(r"https?://(?!127\.0\.0\.1)", text), path
        assert not re.search(r"""(?:src|href)=["']//""", text), path
    css = (STATIC / "styles.css").read_text()
    assert "@import" not in css and "url(" not in css


def test_csp_stays_strict(client):
    # ECharts works without these (checked in the browser), so nothing should ever loosen it
    csp = client.get("/").headers["content-security-policy"]
    assert "unsafe" not in csp and "http" not in csp and "*" not in csp


def test_scripts_never_parse_records_as_html_or_set_a_style_attribute():
    for script in OUR_SCRIPTS:
        text = script.read_text()
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", 'setAttribute("style"'):
            assert banned not in text, f"{script.name}: {banned}"


def test_css_tokens_are_defined_and_have_both_themes():
    css = (STATIC / "styles.css").read_text()
    defined = set(re.findall(r"(--[\w-]+):", css))
    assert set(re.findall(r"var\((--[\w-]+)", css)) <= defined
    chart = (STATIC / "chart.js").read_text()
    assert set(re.findall(r'"(--[\w-]+)"', chart)) <= defined
    assert not re.search(r"--[\w-]+:\s*#", css)  # a bare colour would be the same in both themes
    for theme in ("light", "dark"):
        assert f':root[data-theme="{theme}"]' in css


def test_every_word_the_ui_uses_is_in_the_table():
    table = (STATIC / "strings.js").read_text()
    keys = set(re.findall(r'^\s*"([\w.]+)":', table, re.M))
    prefixes = "nav|theme|status|table|empty|error|connection|overview"
    used = set()
    for script in OUR_SCRIPTS:
        if script.name != "strings.js":
            used |= set(re.findall(rf'"((?:{prefixes})\.[\w.]+)"', script.read_text()))
    assert used and used <= keys
    # built with a template
    assert {f"theme.{c}" for c in ("auto", "light", "dark")} <= keys
    assert {f"overview.tile.{tile}" for tile, _, _ in TILES} <= keys
    assert {f"overview.profile.missing.{field}" for field in ("date_of_birth", "sex")} <= keys
    assert {f"overview.screening.code.{rule['code']}" for rule in _rules()} <= keys
    assert {f"overview.kind.{kind}" for kind in ("diagnosis", "visit", "procedure", "panel",
                                                 "medication_start", "medication_stop", "hospital",
                                                 "vaccination")} <= keys


def test_the_ui_never_says_everything_is_normal():
    for path in OUR_FILES:
        text = path.read_text().lower()
        for phrase in ("everything is normal", "all normal", "all good", "no problems"):
            assert phrase not in text, f"{path.name}: {phrase}"


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_ui_logic():
    # sorting, filtering, statuses, routes: everything in the UI's scripts that needs no browser
    r = subprocess.run(["node", "--test", str(ROOT / "tests" / "web_ui.test.mjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_echarts_is_vendored_with_its_licences(client):
    assert "Apache License" in (ECHARTS / "LICENSE").read_text()
    assert "Apache ECharts" in (ECHARTS / "NOTICE").read_text()
    assert "Redistribution" in (ECHARTS / "licenses" / "LICENSE-d3").read_text()  # named by LICENSE
    r = client.get("/static/vendor/echarts/echarts.esm.min.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]


def test_echarts_is_the_untouched_release_and_requests_nothing():
    readme = (STATIC / "vendor" / "README.md").read_text()
    bundle = (ECHARTS / "echarts.esm.min.js").read_bytes()
    assert hashlib.sha256(bundle).hexdigest() == re.search(r"sha256: ([0-9a-f]{64})", readme)[1]
    assert b"XMLHttpRequest" not in bundle and not re.search(rb"[^\w.]fetch\(", bundle)


def test_chart_tooltips_are_painted_not_parsed_as_html():
    # the default HTML tooltip breaks under the CSP (checked in the browser: 21 violations from one
    # hover) and would parse whatever a record holds
    assert 'renderMode: "richText"' in (STATIC / "chart.js").read_text()


def test_the_frame_does_not_load_echarts_until_a_chart_needs_it():
    # 1 MB on every page otherwise
    assert "vendor" not in (STATIC / "index.html").read_text()
    assert "chart.js" not in (STATIC / "app.js").read_text()


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
