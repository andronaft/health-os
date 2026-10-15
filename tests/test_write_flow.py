"""Test of the full interactive extraction cycle: stage → review → approve.
Uses committed data (like the real MCP write-path), cleans up in finally."""
import json

import pytest
from sqlalchemy import text

from core.db import engine
from core.services import get_or_create_user
from mcp_server import tools, write_tools

pytestmark = pytest.mark.integration  # hits the DB via `engine` / MCP tools directly


@pytest.fixture(autouse=True)
def _restricted_sql_login(monkeypatch):
    # the test DB login is a superuser; these tests exercise the layers below sql_query's login
    # check (read-only transaction, view-only role) — the check itself: test_sql_query_login.py
    # still a real query on sql_query's connection, so the transaction flow is exercised
    monkeypatch.setattr(tools, "_login_can_leave_readonly",
                        lambda conn: conn.execute(text("SELECT false")).scalar())


def _cleanup(source_id, panel_id):
    with engine.begin() as conn:
        conn.execute(
            text("""DELETE FROM observation_history WHERE observation_id IN
                    (SELECT id FROM observations WHERE source_id=:s)"""),
            {"s": source_id},
        )
        conn.execute(text("DELETE FROM observations WHERE source_id=:s"), {"s": source_id})
        conn.execute(text("DELETE FROM panels WHERE id=:p"), {"p": panel_id})
        conn.execute(text("DELETE FROM ingestion_sources WHERE id=:s"), {"s": source_id})


def test_stage_review_approve_cycle():
    rows = [
        {"raw_name": "Холестерин общий", "value": 5.8, "unit": "mmol/L",
         "ref_min": 0, "ref_max": 5.2},
        {"raw_name": "калій", "value": 6.9, "unit": "mmol/L"},          # critical
        {"raw_name": "абракадабра", "value": 1.0, "unit": "mmol/L"},    # unknown
    ]
    out = json.loads(write_tools.stage_lab_panel("2024-03-01", rows, facility="Synevo"))
    sid, pid = out["source_id"], out["panel_id"]
    try:
        # staging: cholesterol high, potassium critical, gibberish unknown
        assert out["counts"]["critical"] == 1
        assert out["counts"]["unknown"] == 1
        chol = next(r for r in out["rows"] if r["matched"] == "cholesterol_total")
        assert chol["status"] == "high"

        # before approve — nothing is in the approved-view (checked via sql_query, exact date)
        q = "SELECT value_canonical FROM v_observations WHERE type_code='cholesterol_total'"
        before = json.loads(tools.sql_query(q))
        assert all(float(r["value_canonical"]) != 5.8 for r in before["rows"])
        # but visible in pending
        pending = json.loads(tools.list_pending_reviews())
        assert any(r["type_code"] == "cholesterol_total" for r in pending)

        # explicit approval
        appr = json.loads(write_tools.approve_staged_source(sid))
        assert appr["approved_observations"] == 2  # cholesterol + potassium; gibberish unmapped
        assert [u["raw_name"] for u in appr["left_pending_unmapped"]] == ["абракадабра"]

        # now cholesterol is in the approved-view
        after = json.loads(tools.sql_query(q))
        assert any(float(r["value_canonical"]) == 5.8 for r in after["rows"])
    finally:
        _cleanup(sid, pid)


def test_write_profile_and_summary_roundtrip():
    write_tools.set_profile("1997-05-20", "male", blood_type="A+")
    # the summary must show the profile
    summary = tools.get_health_summary()
    assert "male" in summary
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        conn.execute(text("DELETE FROM user_profile WHERE user_id=:u"), {"u": uid})
