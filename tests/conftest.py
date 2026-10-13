"""Shared fixtures. Integration tests run against a separate, freshly created test database.

The test DB is `<POSTGRES_DB>_test` on the same Postgres server (override with
TEST_DATABASE_URL). It is dropped and recreated (migrations + seed) on every pytest run —
the working database is never touched.

Tests that need the DB carry the `integration` marker: added automatically for any test that
uses the `conn`/`user_id` fixtures, and set via `pytestmark` in modules that hit `engine`
directly. Everything else is a pure unit test and never connects to Postgres.
`pytest -m "not integration"` skips DB setup entirely; if the DB is unavailable, integration
tests are skipped (not failed) — unless REQUIRE_DB is set (CI), then it is an error.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from core.config import settings

# ---- redirect everything to the test DB BEFORE core.db creates its engines ----------------
if "core.db" in sys.modules:
    pytest.exit("core.db was imported before tests/conftest.py — engines point at the real DB", 2)
_PROD_URL = make_url(settings.database_url)
_TEST_URL = make_url(
    os.environ.get("TEST_DATABASE_URL")
    or _PROD_URL.set(database=f"{_PROD_URL.database}_test").render_as_string(hide_password=False)
)
if not _TEST_URL.database.endswith("_test") or (
    _TEST_URL.database == _PROD_URL.database and _TEST_URL.host == _PROD_URL.host
    and _TEST_URL.port == _PROD_URL.port
):
    pytest.exit(f"refusing to run tests against non-test database {_TEST_URL.database!r}", 2)

_TEST_URL_STR = _TEST_URL.render_as_string(hide_password=False)
settings.database_url = _TEST_URL_STR
settings.readonly_database_url = ""  # readonly engine falls back to the test engine
os.environ["DATABASE_URL"] = _TEST_URL_STR
os.environ["READONLY_DATABASE_URL"] = ""
# never message the real Telegram chat from a test run (see _no_real_alerts below)
settings.alert_telegram_bot_token = settings.alert_telegram_chat_id = ""

from core.db import engine  # noqa: E402 — must be imported after the redirect above

_ROOT = Path(__file__).resolve().parent.parent


_DB_FIXTURES = {"conn", "user_id"}
_db_down = False


def pytest_collection_modifyitems(items):
    for item in items:
        if _DB_FIXTURES & set(item.fixturenames):
            item.add_marker(pytest.mark.integration)


def _is_integration(item) -> bool:
    return item.get_closest_marker("integration") is not None


@pytest.fixture(scope="session", autouse=True)
def _test_db(request):
    """Drop/create the test DB, apply migrations, load seed.

    No-op if no integration tests were selected or Postgres is down.
    """
    global _db_down
    if not any(_is_integration(i) for i in request.session.items):
        yield
        return
    admin = create_engine(_TEST_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{_TEST_URL.database}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{_TEST_URL.database}"'))
    except OperationalError:
        if os.environ.get("REQUIRE_DB"):
            raise  # CI: a missing DB is a failure, not a silent skip
        _db_down = True  # `_require_seed` will skip integration tests
        yield
        return
    finally:
        admin.dispose()

    from alembic import command
    from alembic.config import Config

    from seed.load import load

    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    command.upgrade(cfg, "head")
    load()
    yield


@pytest.fixture()
def conn():
    try:
        connection = engine.connect()
    except OperationalError:
        pytest.skip("DB unavailable — integration tests skipped")
    trans = connection.begin()
    try:
        # tests run in a transaction with rollback — the DB is not changed
        yield connection
    finally:
        trans.rollback()
        connection.close()


@pytest.fixture()
def user_id(conn):
    from core.services import get_or_create_user
    return get_or_create_user(conn)


@pytest.fixture(autouse=True)
def _no_real_alerts(monkeypatch, tmp_path):
    """Critical values staged by tests (e.g. potassium 6.9 in test_write_flow) go through the
    real send_critical_alert. Without this they were appended to the install's data/alerts.log
    and popped a macOS notification on every run — a real alert would drown among them."""
    from safety import alerts
    monkeypatch.setattr(alerts, "_LOG", tmp_path / "alerts.log")
    monkeypatch.setattr(alerts, "_macos_notify", lambda *a: False)
    monkeypatch.setattr(alerts, "_telegram_send", lambda *a: False)


@pytest.fixture(autouse=True)
def _require_seed(request):
    if not _is_integration(request.node):
        return  # unit test — no DB
    if _db_down:
        pytest.skip("DB unavailable — integration tests skipped")
    with engine.connect() as c:
        n = c.execute(text("SELECT count(*) FROM observation_types")).scalar()
    if not n:
        pytest.skip("seed not loaded — run `python -m seed.load`")
