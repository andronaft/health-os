"""Habits: recorded over MCP, readable through v_habits and shown in the summary (migration 0013)."""
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from core.health_summary import build
from core.services import add_habit, update_habit
from mcp_server import tools


def test_add_and_read_through_view(conn, user_id):
    out = add_habit(conn, user_id, " Cannabis ", frequency="about once a week",
                    notes="THC with CBD, no tobacco")
    row = conn.execute(text("SELECT * FROM v_habits WHERE id = :i"), {"i": out["id"]}).mappings().one()
    assert (row["habit_type"], row["status"], row["frequency"]) == \
        ("cannabis", "current", "about once a week")
    assert row["start_date"] is None  # no invented day


@pytest.mark.parametrize("kwargs, error", [
    ({"habit_type": ""}, "habit_type is required"),
    ({"habit_type": "alcohol", "status": "sometimes"}, "status must be"),
    ({"habit_type": "alcohol", "start_date": "07.2026"}, "YYYY-MM-DD"),
    ({"habit_type": "alcohol", "start_date": date.today() + timedelta(days=1)}, "in the future"),
    ({"habit_type": "alcohol", "start_date": "2026-07-01", "end_date": "2026-06-01"},
     "before start_date"),
])
def test_add_rejects_bad_input(conn, user_id, kwargs, error):
    habit_type = kwargs.pop("habit_type")
    assert error in add_habit(conn, user_id, habit_type, **kwargs)["error"]


def test_update_records_quitting(conn, user_id):
    hid = add_habit(conn, user_id, "cannabis_with_tobacco", start_date="2026-07-01")["id"]
    out = update_habit(conn, user_id, hid, {"status": "former", "end_date": "2026-08-15",
                                            "frequency": None})
    assert set(out["changed"]) == {"status", "end_date"}
    row = conn.execute(text("SELECT status, end_date FROM habits WHERE id = :i"),
                       {"i": hid}).one()
    assert tuple(row) == ("former", date(2026, 8, 15))


@pytest.mark.parametrize("habit_id, changes, error", [
    ("not-a-uuid", {"status": "former"}, "no habit"),
    ("00000000-0000-0000-0000-000000000000", {"status": "former"}, "no habit"),
    (None, {}, "nothing to change"),
    (None, {"user_id": "x"}, "can't change"),
    (None, {"end_date": "2026-06-01"}, "before start_date"),
])
def test_update_rejects_bad_input(conn, user_id, habit_id, changes, error):
    hid = add_habit(conn, user_id, "smoking", start_date="2026-07-01")["id"]
    assert error in update_habit(conn, user_id, habit_id or hid, changes)["error"]


def test_summary_lists_current_and_former(conn, user_id):
    add_habit(conn, user_id, "smoking", status="former", cigarettes_per_day=10,
              end_date="2020-01-01")
    add_habit(conn, user_id, "cannabis", frequency="about once a week")
    add_habit(conn, user_id, "alcohol", status="never")
    res = build(conn, user_id)
    assert res.valid, res.issues
    assert res.counts["habits"] == 2
    assert "cannabis — current, about once a week" in res.text
    assert "smoking — former" in res.text and "alcohol" not in res.text


def test_readonly_role_can_read_view(conn, user_id):
    add_habit(conn, user_id, "vaping")
    conn.execute(text("SET LOCAL ROLE health_readonly"))
    n = conn.execute(text("SELECT count(*) FROM v_habits WHERE user_id = :u"),
                     {"u": user_id}).scalar()
    assert n == 1


@pytest.mark.integration
def test_get_habits_tool_does_not_crash():
    assert isinstance(json.loads(tools.get_habits()), (list, dict))
