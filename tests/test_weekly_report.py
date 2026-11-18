"""The weekly report must never call a week "stable" while a value can't wait, and must see a
panel in the week it was approved. Made-up values only."""
from datetime import date, timedelta

from sqlalchemy import text

from analytics.weekly_report import build
from core.services import approve_staged, ingest_observation, stage_panel


def test_a_pending_critical_value_makes_the_week_unstable(conn, user_id):
    out = stage_panel(conn, user_id, date.today(),
                      [{"raw_name": "Potassium", "value": 6.9, "unit": "mmol/L"}])
    assert out["counts"]["critical"] == 1
    report = build(conn, user_id)
    assert report["stable"] is False
    [row] = report["alarming_pending"]
    assert row["code"] == "potassium" and row["status"] == "critical"
    assert "alarming_pending" in report["system_health"]["note"]


def test_a_pending_value_that_cannot_be_checked_makes_the_week_unstable(conn, user_id):
    stage_panel(conn, user_id, date.today(),
                [{"raw_name": "Potassium", "value": ">5", "unit": "mmol/L"}])
    report = build(conn, user_id)
    assert report["stable"] is False
    assert report["alarming_pending"][0]["critical_check_impossible"] is True


def test_a_panel_staged_earlier_counts_in_the_week_it_was_approved(conn, user_id):
    out = stage_panel(conn, user_id, date.today() - timedelta(days=12),
                      [{"raw_name": "Potassium", "value": 6.9, "unit": "mmol/L"}])
    conn.execute(text("UPDATE observations SET created_at = now() - interval '12 days' "
                      "WHERE source_id = :s"), {"s": out["source_id"]})
    approve_staged(conn, user_id, out["source_id"])
    report = build(conn, user_id)
    assert [r["code"] for r in report["abnormal"]] == ["potassium"]
    assert report["new_values"] == [{"code": "potassium", "n": 1}]
    assert report["stable"] is False


def test_a_quiet_week_is_stable(conn, user_id):
    ingest_observation(conn, user_id, "Potassium", 4.2, "mmol/L", ref_min=3.5, ref_max=5.1)
    report = build(conn, user_id)
    assert report["stable"] is True and report["alarming_pending"] == []
