"""MCP tool tests. tools.py reads through separate connections (like the real MCP),
so committed data is needed — we clean up in finally."""
import json

import pytest
from sqlalchemy import text

from core.db import engine
from core.services import get_or_create_user, ingest_observation
from mcp_server import tools

pytestmark = pytest.mark.integration  # hits the DB via `engine` / MCP tools directly


@pytest.fixture(autouse=True)
def _restricted_sql_login(monkeypatch):
    # the test DB login is a superuser; these tests exercise the layers below sql_query's login
    # check (read-only transaction, view-only role) — the check itself: test_sql_query_login.py
    # still a real query on sql_query's connection, so the transaction flow is exercised
    monkeypatch.setattr(tools, "_login_can_leave_readonly",
                        lambda conn: conn.execute(text("SELECT false")).scalar())


def test_sql_query_rejects_writes():
    assert "error" in json.loads(tools.sql_query("UPDATE observations SET status='x'"))
    assert "error" in json.loads(tools.sql_query("DELETE FROM users"))
    assert "error" in json.loads(tools.sql_query("DROP TABLE users"))


def test_sql_query_allows_select():
    out = json.loads(tools.sql_query("SELECT 1 AS one"))
    assert out["rows"][0]["one"] == 1


def test_sql_query_is_read_only_at_db_level():
    # even if the keyword filter let it through — the READ ONLY transaction blocks the write
    out = json.loads(tools.sql_query(
        "WITH x AS (SELECT 1) INSERT INTO users DEFAULT VALUES"
    ))
    assert "error" in out  # rejected (doesn't start with select, or read-only)



def test_sql_query_sees_only_approved_views_without_readonly_url():
    # tests run WITHOUT READONLY_DATABASE_URL, as the owner (a superuser in Docker) — the case
    # that used to expose base tables and server files
    assert "rows" in json.loads(tools.sql_query("SELECT count(*) FROM v_observations"))
    for q in ("SELECT count(*) FROM observations",          # includes pending/unverified rows
              "SELECT count(*) FROM audit_log",
              "SELECT date_of_birth FROM user_profile",
              "SELECT pg_read_file('/etc/hostname')"):      # server files
        out = json.loads(tools.sql_query(q))
        assert "permission denied" in out.get("error", ""), (q, out)

def test_query_observations_roundtrip():
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        res = ingest_observation(conn, uid, "глюкоза", 5.2, "mmol/L",
                                 ref_min=3.9, ref_max=5.5)
        oid = res.observation_id
        sid = conn.execute(
            text("SELECT source_id FROM observations WHERE id=:i"), {"i": oid}
        ).scalar()
    try:
        out = json.loads(tools.query_observations("glucose", days=30))
        assert any(float(r["value_canonical"]) == 5.2 for r in out["rows"])
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM observations WHERE id=:i"), {"i": oid})
            conn.execute(text("DELETE FROM ingestion_sources WHERE id=:i"), {"i": sid})


def test_pending_not_in_approved_view():
    """A critical value (pending) must NOT leak into v_observations."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        res = ingest_observation(conn, uid, "калій", 6.8, "mmol/L")  # critical → pending
        oid = res.observation_id
        sid = conn.execute(
            text("SELECT source_id FROM observations WHERE id=:i"), {"i": oid}
        ).scalar()
    try:
        approved = json.loads(tools.query_observations("potassium", days=30))
        assert all(float(r["value_canonical"]) != 6.8 for r in approved["rows"])
        pending = json.loads(tools.list_pending_reviews())
        assert any(str(r["id"]) == oid for r in pending)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM observations WHERE id=:i"), {"i": oid})
            conn.execute(text("DELETE FROM ingestion_sources WHERE id=:i"), {"i": sid})


def test_crisis_resources_tool():
    out = json.loads(tools.crisis_resources("I want to die"))
    assert out["detected_by_keywords"] is True
    assert "112" in out["response"]
    # always returns the resources, even if keywords don't match (false positive > miss)
    assert "112" in json.loads(tools.crisis_resources("I feel off"))["response"]


def test_check_medication_safety_tool():
    out = json.loads(tools.check_medication_safety(
        paracetamol_products=[{"name": "Paracetamol", "mg_per_dose": 1000, "doses_per_day": 5}]))
    assert out["paracetamol"]["level"] == "exceeded"
    assert "interactions" in out


def test_query_nutrition_does_not_flag_low_sugar_as_deficient():
    from datetime import datetime

    from core.services import add_food_log

    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        fid = add_food_log(conn, uid, "plain rice", eaten_at=datetime.now(),
                           nutrients={"added_sugar": 2, "sodium": 100, "calcium": 50})["id"]
    try:
        flags = {n["nutrient"]: n["flag"]
                 for n in json.loads(tools.query_nutrition(days=1))["nutrients"]}
        assert flags["calcium"] == "deficient"
        assert flags["added_sugar"] is None and flags["sodium"] is None
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM food_nutrients WHERE food_log_id=:i"), {"i": fid})
            conn.execute(text("DELETE FROM food_log WHERE id=:i"), {"i": fid})


def _approved_glucose(effective_at=None):
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        oid = ingest_observation(conn, uid, "глюкоза", 5.2, "mmol/L",
                                 effective_at=effective_at).observation_id
        sid = conn.execute(text("SELECT source_id FROM observations WHERE id=:i"),
                           {"i": oid}).scalar()
    return oid, sid


def _drop(oid, sid):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM observations WHERE id=:i"), {"i": oid})
        conn.execute(text("DELETE FROM ingestion_sources WHERE id=:i"), {"i": sid})


def test_type_code_case_and_unknown_codes_are_explained():
    oid, sid = _approved_glucose()
    try:
        out = json.loads(tools.query_observations(" GLUCOSE ", days=30))
        assert out["type_code"] == "glucose" and out["rows"] and "note" not in out
        # a code with no values at all must not read like "no data for a real marker"
        typo = json.loads(tools.query_observations("glucos", days=30))
        assert "no approved values at all" in typo["note"] and "glucose" in typo["did_you_mean"]
        trend = json.loads(tools.get_trend("Glucos"))
        assert trend["n"] == 0 and "glucose" in trend["did_you_mean"]
    finally:
        _drop(oid, sid)


def test_a_real_code_outside_the_window_says_so():
    from datetime import datetime
    oid, sid = _approved_glucose(effective_at=datetime(2000, 1, 3, 8, 0))
    try:
        out = json.loads(tools.query_observations("glucose", days=30))
        assert out["rows"] == [] and "in this period" in out["note"]
        assert "did_you_mean" not in out
    finally:
        _drop(oid, sid)


def test_huge_day_windows_do_not_crash():
    # make_interval overflowed for ~10^7 days and the tools failed with a bare error
    for call in (lambda: tools.get_timeline(days=10**9),
                 lambda: tools.query_food(days=10**9),
                 lambda: tools.query_nutrition(days=10**9),
                 lambda: tools.query_observations("glucose", days=10**9),
                 lambda: tools.get_trend("glucose", days=10**9),
                 lambda: tools.search("x", days=10**9)):
        out = json.loads(call())
        assert "error" not in out if isinstance(out, dict) else True


def test_timeline_names_panels_without_a_type():
    from core.services import stage_panel
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = stage_panel(conn, uid, "2020-01-02", [{"raw_name": "LDL", "value": 3.0,
                                                    "unit": "mmol/L"}], alerter=lambda *a: None)
    try:
        rows = json.loads(tools.get_timeline(days=36500))
        panels = [r for r in rows if r["kind"] == "panel" and r["at"].startswith("2020-01-02")]
        assert panels and all(r["title"] == "lab panel" for r in panels)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM observations WHERE source_id=:s"),
                         {"s": out["source_id"]})
            conn.execute(text("DELETE FROM panels WHERE id=:p"), {"p": out["panel_id"]})
            conn.execute(text("DELETE FROM ingestion_sources WHERE id=:s"),
                         {"s": out["source_id"]})
