"""Food log corrections: time sanity check, update_meal, delete_meal."""
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from core.db import engine
from core.services import add_food_log, delete_meal, meal_time_note, update_meal
from mcp_server import tools, write_tools


# ---- the time check is pure: no DB ---------------------------------------------------------
@pytest.mark.parametrize("at, meal_type, expected", [
    (datetime(2026, 9, 25, 23, 30), "lunch", "unusual"),           # logged in the evening
    (datetime(2026, 10, 10, 0, 16), "lunch", "toward 2026-10-10"),  # yesterday's lunch?
    (datetime(2026, 10, 11, 0, 12), "dinner", "eaten on 2026-10-10"),
    (datetime(2026, 9, 20, 15, 0), "breakfast", "unusual"),
    (datetime(2026, 9, 20, 8, 30), "breakfast", None),
    (datetime(2026, 9, 20, 14, 0), "lunch", None),
    (datetime(2026, 9, 20, 22, 30), "dinner", None),                # a Spanish dinner is fine
    (datetime(2026, 9, 20, 1, 0), "snack", None),                   # snacks/drinks: any time
    (datetime(2026, 9, 20, 1, 0), None, None),
    (datetime(2026, 9, 20, 23, 0, tzinfo=UTC), "lunch", "unusual"),  # read back from the DB
])
def test_meal_time_note(at, meal_type, expected):
    note = meal_time_note(at, meal_type)
    if expected is None:
        assert note is None
    else:
        assert expected in note and "update_meal" in note


def test_log_returns_the_time_used_and_flags_odd_ones(conn, user_id):
    ok = add_food_log(conn, user_id, "борщ", eaten_at=datetime(2026, 9, 20, 13, 0),
                      meal_type="lunch")
    assert ok["eaten_at"] == datetime(2026, 9, 20, 13, 0) and "time_check" not in ok
    odd = add_food_log(conn, user_id, "сендвіч", eaten_at=datetime(2026, 10, 10, 0, 16),
                       meal_type="lunch")
    assert "toward 2026-10-10" in odd["time_check"]


# ---- update / delete -------------------------------------------------------------------------
def _day_totals(conn, uid, code):
    return dict(conn.execute(
        text("""SELECT eaten_at::date, sum(amount) FROM v_food_nutrients
                WHERE user_id = :u AND nutrient_code = :c GROUP BY 1"""),
        {"u": uid, "c": code}).all())


def test_moving_a_meal_moves_its_nutrients_to_the_right_day(conn, user_id):
    fid = add_food_log(conn, user_id, "сендвіч з куркою", eaten_at=datetime(2026, 10, 10, 0, 16),
                       meal_type="lunch", nutrients={"sodium": 900, "protein": 30})["id"]
    out = update_meal(conn, user_id, fid, {"eaten_at": "2026-10-09 14:00"})
    assert set(out["changed"]) == {"eaten_at"} and "time_check" not in out
    totals = _day_totals(conn, user_id, "sodium")
    assert totals.get(datetime(2026, 10, 9).date()) == 900
    assert datetime(2026, 10, 10).date() not in totals


def test_nutrients_overwrite_only_the_given_codes(conn, user_id):
    fid = add_food_log(conn, user_id, "паста", eaten_at=datetime(2026, 9, 20, 20, 0),
                       meal_type="dinner",
                       nutrients={"energy_kcal": 800, "sodium": 1200, "protein": 30})["id"]
    out = update_meal(conn, user_id, fid, {"portion": "half a plate"},
                      nutrients={"energy_kcal": 400, "sodium": 600, "bogus": 1})
    assert out["nutrients_saved"] == 2 and out["unknown_codes"] == ["bogus"]
    amounts = dict(conn.execute(
        text("SELECT nutrient_code, amount FROM v_food_nutrients WHERE food_log_id = :i"),
        {"i": fid}).all())
    assert amounts == {"energy_kcal": 400, "sodium": 600, "protein": 30}
    assert conn.execute(text("SELECT portion FROM food_log WHERE id = :i"),
                        {"i": fid}).scalar() == "half a plate"


def test_update_keeps_flagging_a_time_that_is_still_odd(conn, user_id):
    fid = add_food_log(conn, user_id, "скрембл", eaten_at=datetime(2026, 9, 25, 23, 30),
                       meal_type="lunch")["id"]
    assert "unusual" in update_meal(conn, user_id, fid, {"description": "скрембл з фетою"})[
        "time_check"]
    assert "time_check" not in update_meal(conn, user_id, fid, {"meal_type": "dinner"})


@pytest.mark.parametrize("changes, nutrients, error", [
    ({}, None, "nothing to change"),
    ({"user_id": "x"}, None, "can't change user_id"),
    ({"eaten_at": "вчора"}, None, "ISO"),
])
def test_update_rejects_bad_input(conn, user_id, changes, nutrients, error):
    fid = add_food_log(conn, user_id, "кава", eaten_at=datetime(2026, 9, 20, 9, 0),
                       meal_type="drink")["id"]
    assert error in update_meal(conn, user_id, fid, changes, nutrients)["error"]


def test_delete_removes_meal_and_its_nutrients_from_totals(conn, user_id):
    fid = add_food_log(conn, user_id, "дубль", eaten_at=datetime(2026, 9, 21, 13, 0),
                       meal_type="lunch", nutrients={"sodium": 500})["id"]
    out = delete_meal(conn, user_id, fid)
    assert out["deleted"] and out["description"] == "дубль"
    assert conn.execute(text("SELECT count(*) FROM v_food_log WHERE id = :i"),
                        {"i": fid}).scalar() == 0
    assert conn.execute(text("SELECT count(*) FROM v_food_nutrients WHERE food_log_id = :i"),
                        {"i": fid}).scalar() == 0
    assert "no meal" in delete_meal(conn, user_id, fid)["error"]
    assert "no meal" in update_meal(conn, user_id, fid, {"portion": "1"})["error"]


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
def test_unknown_id_is_an_error_not_a_crash(conn, user_id, bad_id):
    assert "no meal" in update_meal(conn, user_id, bad_id, {"portion": "1"})["error"]
    assert "no meal" in delete_meal(conn, user_id, bad_id)["error"]


@pytest.mark.integration
def test_mcp_round_trip_query_food_gives_the_id():
    fid = json.loads(write_tools.log_meal("тестова гречка", "snack",
                                          nutrients={"sodium": 10}))["id"]
    try:
        meals = json.loads(tools.query_food(days=1))["meals"]
        assert any(str(m["id"]) == fid for m in meals)
        out = json.loads(write_tools.update_meal(fid, nutrients={"sodium": 20}))
        assert out["nutrients_saved"] == 1 and out["changed"] == {}
        assert json.loads(write_tools.delete_meal(fid))["deleted"]
        assert not any(str(m["id"]) == fid for m in json.loads(tools.query_food(days=1))["meals"])
    finally:
        with engine.begin() as conn:
            sid = conn.execute(text("SELECT source_id FROM food_log WHERE id = :i"),
                               {"i": fid}).scalar()
            conn.execute(text("DELETE FROM food_log WHERE id = :i"), {"i": fid})
            conn.execute(text("DELETE FROM ingestion_sources WHERE id = :s"), {"s": sid})
