"""Medication lifecycle: corrections and stops keep history and the timeline (migration 0012)."""
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from core.db import engine
from core.services import add_medication, stop_medication, update_medication
from mcp_server import write_tools


def _med(conn, mid):
    return conn.execute(text("SELECT * FROM medications WHERE id = :i"), {"i": mid}).mappings().one()


def _history(conn, mid):
    return conn.execute(
        text("SELECT reason, old_row FROM medication_history WHERE medication_id = :i ORDER BY id"),
        {"i": mid},
    ).mappings().all()


def _current_ids(conn, uid):
    return {str(r[0]) for r in conn.execute(
        text("SELECT id FROM v_medications_current WHERE user_id = :u"), {"u": uid})}


def test_update_changes_only_given_fields_and_keeps_history(conn, user_id):
    mid = add_medication(conn, user_id, "Minoxidil", start_date=date(2026, 10, 12),
                         product_type="otc")
    out = update_medication(conn, user_id, mid, {"medication_name": "Minoxidil 5%",
                                                 "dose_amount": 1, "dose_unit": "ml",
                                                 "times_per_day": 1, "route": "topical",
                                                 "prescribed_for": None})
    assert set(out["changed"]) == {"medication_name", "dose_amount", "dose_unit",
                                   "times_per_day", "route"}
    row = _med(conn, mid)
    assert row["medication_name"] == "Minoxidil 5%" and row["route"] == "topical"
    assert row["dose_amount"] == 1 and row["product_type"] == "otc"  # untouched
    (h,) = _history(conn, mid)
    assert h["reason"] == "update_medication"
    assert h["old_row"]["medication_name"] == "Minoxidil" and h["old_row"]["route"] is None


@pytest.mark.parametrize("changes, error", [
    ({}, "nothing to change"),
    ({"dose_amount": None}, "nothing to change"),
    ({"status": "stopped"}, "can't change status"),
    ({"start_date": "12.10.2026"}, "YYYY-MM-DD"),
])
def test_update_rejects_bad_input(conn, user_id, changes, error):
    mid = add_medication(conn, user_id, "Atorvastatin", start_date=date(2024, 1, 1))
    assert error in update_medication(conn, user_id, mid, changes)["error"]
    assert _history(conn, mid) == []


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_unknown_id_is_an_error_not_a_crash(conn, user_id, bad_id):
    assert "no medication" in update_medication(conn, user_id, bad_id, {"route": "oral"})["error"]
    assert "no medication" in stop_medication(conn, user_id, bad_id,
                                              end_date=date.today())["error"]


def test_stop_leaves_current_list_and_lands_on_timeline(conn, user_id):
    mid = add_medication(conn, user_id, "Amoxicillin", start_date=date(2026, 9, 1),
                         dose_amount=500, dose_unit="mg", times_per_day=3)
    assert mid in _current_ids(conn, user_id)

    out = stop_medication(conn, user_id, mid, end_date="2026-09-08",
                          stop_reason="course finished", side_effects="nausea")
    assert out["status"] == "stopped" and out["end_date"] == date(2026, 9, 8)
    row = _med(conn, mid)
    assert (row["status"], row["stop_reason"], row["side_effects"]) == \
        ("stopped", "course finished", "nausea")
    assert mid not in _current_ids(conn, user_id)
    assert _history(conn, mid)[0]["old_row"]["status"] == "taking"

    kinds = {r[0] for r in conn.execute(
        text("SELECT kind FROM health_timeline WHERE id = :i"), {"i": mid})}
    assert kinds == {"medication_start", "medication_stop"}

    again = stop_medication(conn, user_id, mid, end_date="2026-09-09")
    assert again["error"] == "already stopped since 2026-09-08"


@pytest.mark.parametrize("end, error", [
    (date.today() + timedelta(days=1), "in the future"),
    (date(2026, 8, 31), "before the start_date"),
    ("yesterday", "YYYY-MM-DD"),
])
def test_stop_rejects_impossible_dates(conn, user_id, end, error):
    mid = add_medication(conn, user_id, "Ibuprofen", start_date=date(2026, 9, 1))
    assert error in stop_medication(conn, user_id, mid, end_date=end)["error"]
    assert _med(conn, mid)["status"] == "taking"


def test_start_date_correction_cannot_pass_the_end_date(conn, user_id):
    mid = add_medication(conn, user_id, "Omeprazole", start_date=date(2026, 9, 1))
    stop_medication(conn, user_id, mid, end_date="2026-09-10")
    assert "after the end_date" in update_medication(
        conn, user_id, mid, {"start_date": "2026-09-20"})["error"]


@pytest.mark.integration
def test_mcp_wrappers_round_trip():
    """The MCP layer: route reaches the row, empty strings mean "keep", end_date defaults to today."""
    start = (date.today() - timedelta(days=10)).isoformat()
    mid = json.loads(write_tools.record_medication(
        "Vitamin D3", start, 2000, "IU", 1, "supplement", route="oral"))["id"]
    try:
        out = json.loads(write_tools.update_medication(mid, dose_amount=4000))
        assert set(out["changed"]) == {"dose_amount"}
        stopped = json.loads(write_tools.stop_medication(mid))
        assert stopped["end_date"] == date.today().isoformat()
        with engine.connect() as conn:
            row = _med(conn, mid)
        assert (row["route"], row["dose_unit"], row["dose_amount"], row["status"]) == \
            ("oral", "IU", 4000, "stopped")
    finally:
        with engine.begin() as conn:
            sid = conn.execute(text("SELECT source_id FROM medications WHERE id = :i"),
                               {"i": mid}).scalar()
            conn.execute(text("DELETE FROM medications WHERE id = :i"), {"i": mid})
            conn.execute(text("DELETE FROM ingestion_sources WHERE id = :s"), {"s": sid})
