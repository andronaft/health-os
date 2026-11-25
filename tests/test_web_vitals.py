"""GET /api/v1/vitals (#56): home blood pressure checked against the ESH home protocol, the
watch's daily values aggregated in the database, a year of heatmap days. The protocol logic is
tested on its own first (no database); the endpoint runs on the test's own connection, so
everything stays in its rolled-back transaction. Made-up values and the fictional demo patient."""
import contextlib
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

import web.app
from core.services import get_or_create_channel_source, ingest_observation
from seed.demo import WEARABLE_GAPS, bp_dated, bp_readings, load_demo
from web.vitals import (
    DEFAULT_WINDOW,
    bucket_for,
    bucket_start,
    diaries,
    pair_readings,
    parse_tz,
    session_of,
    summarize_diary,
    training_load,
    window_days,
)

HEADERS = {"X-Health-OS-Token": "t"}
D0 = date(2026, 3, 2)  # a Monday


# ---- the protocol, without a database --------------------------------------------------------------

def _reading(day: int, hour: int, systolic=130, diastolic=80, minute=0):
    at = datetime(2026, 3, 2, hour, minute, tzinfo=UTC) + timedelta(days=day)
    return {"at": at, "day": at.date(), "session": session_of(hour),
            "systolic": systolic, "diastolic": diastolic,
            "complete": systolic is not None and diastolic is not None}


def _diary(days: int, *, morning=2, evening=2, first=0, **values):
    out = []
    for d in range(first, first + days):
        out += [_reading(d, 7, minute=m, **values) for m in range(morning)]
        out += [_reading(d, 21, minute=m, **values) for m in range(evening)]
    return out


def test_morning_evening_and_other_hours():
    assert [session_of(h) for h in (3, 4, 11, 12, 15, 16, 23)] == [
        "other", "morning", "morning", "other", "other", "evening", "evening"]


def test_a_full_week_is_followed_and_its_first_day_is_left_out_of_the_mean():
    readings = _diary(7)
    for r in readings:
        if r["day"] == D0:  # day one reads high: the reason the protocol discards it
            r["systolic"], r["diastolic"] = 170, 100
    d = summarize_diary(readings)
    assert d["followed"] is True
    assert (d["days"], d["complete_days"], d["counted_days"]) == (7, 7, 6)
    assert d["mean"]["systolic"] == 130 and d["mean"]["diastolic"] == 80
    assert d["mean"]["n"] == 24 and d["mean"]["from_day"] == D0 + timedelta(days=1)
    assert d["mean"]["morning"]["n"] == d["mean"]["evening"]["n"] == 12


def test_three_complete_days_are_not_enough_once_day_one_is_discarded():
    d = summarize_diary(_diary(3))
    assert d["complete_days"] == 3 and d["counted_days"] == 2
    assert d["followed"] is False and d["mean"] is None  # never a mean below the minimum


def test_four_complete_days_are_the_minimum():
    d = summarize_diary(_diary(4))
    assert d["counted_days"] == 3 and d["followed"] is True and d["mean"]["n"] == 12


def test_single_readings_make_no_complete_day():
    d = summarize_diary(_diary(7, morning=1, evening=1))
    assert d["complete_days"] == 0 and d["followed"] is False and d["mean"] is None
    assert d["sessions"] == 14 and d["full_sessions"] == 0


def test_mornings_only_are_not_the_protocol():
    d = summarize_diary(_diary(7, evening=0))
    assert d["complete_days"] == 0 and d["followed"] is False


def test_daytime_readings_are_counted_but_not_averaged():
    readings = _diary(5) + [_reading(2, 14, systolic=200, diastolic=120)]
    d = summarize_diary(readings)
    assert d["other_readings"] == 1 and d["followed"] is True
    assert d["mean"]["systolic"] == 130  # the 200 at 14:00 is not in it


def test_a_long_run_is_summarised_by_its_last_seven_days():
    d = summarize_diary(_diary(10, systolic=140))
    assert d["days"] == 7 and d["earlier_days"] == 3
    assert d["first_day"] == D0 + timedelta(days=3) and d["last_day"] == D0 + timedelta(days=9)


def test_diaries_split_on_gaps_and_a_lone_day_is_no_diary():
    readings = (_diary(5) + _diary(4, first=30)
                + [_reading(60, 9)]                    # a lone check at the doctor's
                + _diary(1, first=80) + _diary(1, first=82))  # one missed day: still one diary
    found = diaries(readings)
    assert [(d["first_day"], d["days"]) for d in found] == [
        (D0 + timedelta(days=80), 2), (D0 + timedelta(days=30), 4), (D0, 5)]  # newest first
    assert diaries([]) == []


MADRID = ZoneInfo("Europe/Madrid")


def test_systolic_and_diastolic_of_one_moment_make_one_reading():
    at = datetime(2026, 3, 2, 7, 5, tzinfo=UTC)
    rows = [("systolic_bp", at, 131, None, "datetime"), ("diastolic_bp", at, 84, None, "datetime"),
            ("systolic_bp", at + timedelta(minutes=2), 129, None, "datetime")]
    readings = pair_readings(rows, UTC)
    assert [(r["systolic"], r["diastolic"], r["complete"]) for r in readings] == [
        (131, 84, True), (129, None, False)]
    assert readings[0]["session"] == "morning"


def test_two_readings_logged_at_the_same_minute_stay_two():
    at = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    rows = [("systolic_bp", at, 131, None, "datetime"), ("systolic_bp", at, 127, None, "datetime"),
            ("diastolic_bp", at, 84, None, "datetime"), ("diastolic_bp", at, 82, None, "datetime")]
    readings = pair_readings(rows, UTC)
    assert len(readings) == 2 and all(r["complete"] for r in readings)
    assert sorted(r["systolic"] for r in readings) == [127, 131]


def test_a_group_id_pairs_values_whatever_their_times():
    at = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)
    rows = [("systolic_bp", at, 131, "g1", "datetime"),
            ("diastolic_bp", at + timedelta(seconds=40), 84, "g1", "datetime"),
            ("systolic_bp", at, 127, "g2", "datetime"), ("diastolic_bp", at, 82, "g2", "datetime")]
    readings = pair_readings(rows, UTC)
    assert sorted((r["systolic"], r["diastolic"]) for r in readings) == [(127, 82), (131, 84)]


def test_morning_and_evening_are_read_in_the_users_zone():
    # 17:30 in Madrid's summer is 15:30 UTC: in UTC it would fall outside the evening
    at = datetime(2026, 7, 1, 17, 30, tzinfo=MADRID)
    rows = [("systolic_bp", at, 130, None, "datetime"), ("diastolic_bp", at, 80, None, "datetime")]
    assert pair_readings(rows, UTC)[0]["session"] == "other"
    assert pair_readings(rows, MADRID)[0]["session"] == "evening"
    # just after midnight in Madrid is still the previous day in UTC
    late = datetime(2026, 7, 2, 0, 30, tzinfo=MADRID)
    rows = [("systolic_bp", late, 130, None, "datetime"), ("diastolic_bp", late, 80, None, "datetime")]
    assert pair_readings(rows, MADRID)[0]["day"] == date(2026, 7, 2)


def test_a_value_entered_per_day_has_no_time_of_day():
    midnight = datetime(2026, 3, 2, tzinfo=UTC)
    rows = [("systolic_bp", midnight, 138, None, "date"), ("diastolic_bp", midnight, 86, None, "date")]
    [reading] = pair_readings(rows, ZoneInfo("America/New_York"), day_zone=UTC)
    assert reading["session"] == "untimed"
    assert reading["day"] == date(2026, 3, 2)  # its own day, not the evening before in New York


def _dated(days: int, per_day=2, first=0):
    return [{"at": D0 + timedelta(days=d), "day": D0 + timedelta(days=d), "session": "untimed",
             "systolic": 130 + k, "diastolic": 80 + k, "complete": True}
            for d in range(first, first + days) for k in range(per_day)]


def test_a_diary_without_times_is_not_judged_but_has_a_plain_mean():
    d = summarize_diary(_dated(5))
    assert d["timing"] == "unrecorded"
    assert d["followed"] is None  # unknown: not "not followed"
    assert d["value_days"] == 5 and d["untimed_readings"] == 10
    assert d["mean"] == {"systolic": 130.5, "diastolic": 80.5, "n": 8,
                         "from_day": D0 + timedelta(days=1), "days": 4}
    assert "complete_days" not in d


def test_values_without_times_in_a_timed_diary_are_counted_not_used():
    d = summarize_diary(_diary(5) + _dated(1, first=2))
    assert d["timing"] == "recorded" and d["followed"] is True and d["untimed_readings"] == 2
    assert d["mean"]["n"] == 16


def test_only_complete_pairs_count():
    readings = _diary(5)
    for r in readings:
        if r["day"] == D0 + timedelta(days=3) and r["session"] == "evening":
            r["diastolic"], r["complete"] = None, False   # the cuff saved only one number
    d = summarize_diary(readings)
    assert d["incomplete_readings"] == 2
    assert d["complete_days"] == 4 and d["counted_days"] == 3 and d["followed"] is True
    assert d["mean"]["n"] == 4 * 4 - 2  # days 2–5, without the two halves


def test_day_one_is_a_day_with_readings():
    # a long run whose last seven days start on a missed day: the first day with readings in them
    # is the one discarded, so something is always discarded
    readings = [r for r in _diary(10) if r["day"] != D0 + timedelta(days=3)]
    d = summarize_diary(readings)
    assert d["first_day"] == D0 + timedelta(days=4) and d["days"] == 6
    assert d["counted_days"] == 5 and d["mean"]["from_day"] == D0 + timedelta(days=5)


def test_time_zones():
    assert parse_tz("Europe/Madrid") == MADRID
    assert parse_tz("") is None and parse_tz(None) is None
    for bad in ("Mars/Olympus", "../etc/passwd"):
        with pytest.raises(ValueError):
            parse_tz(bad)


def test_windows_and_buckets():
    assert window_days("365") == 365
    assert window_days("12") == window_days("x") == window_days(None) == DEFAULT_WINDOW
    assert [bucket_for(d) for d in (7, 30, 90, 365, 1825)] == ["day", "day", "day", "week", "month"]
    assert bucket_start(date(2026, 3, 5), "week") == D0
    assert bucket_start(date(2026, 3, 5), "month") == date(2026, 3, 1)


def test_training_load_needs_half_of_its_days():
    days = {D0 + timedelta(days=i): 30.0 for i in range(4)}  # 4 days of watch, then nothing
    load = training_load(days, D0, D0 + timedelta(days=20))
    assert load[D0 + timedelta(days=3)]["acute"] == 30.0          # 4 of 7 days
    assert load[D0 + timedelta(days=3)]["chronic"] is None        # 4 of 28: unknown, not low
    assert D0 + timedelta(days=11) not in load                    # no value in either span


# ---- the endpoint ------------------------------------------------------------------------------------

@pytest.fixture()
def client(conn, monkeypatch):
    @contextlib.contextmanager
    def on_the_test_connection():
        yield conn

    monkeypatch.setattr(web.app, "read_only_snapshot", on_the_test_connection)
    return TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")


@pytest.fixture()
def get(client):
    def fetch(query=""):
        r = client.get(f"/api/v1/vitals{query}", headers=HEADERS)
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        return r.json()

    return fetch


@pytest.fixture()
def today(conn):
    return conn.execute(text("SELECT current_date")).scalar()


@pytest.fixture()
def demo(conn, today):
    return load_demo(conn, today=today)


def test_needs_the_token(client):
    assert client.get("/api/v1/vitals").status_code == 403


def test_no_data_is_empty_not_zero(user_id, get):
    data = get()
    assert data["window"]["days"] == DEFAULT_WINDOW and data["window"]["bucket"] == "day"
    assert data["blood_pressure"]["readings"] == 0 and data["blood_pressure"]["diaries"] == []
    assert data["wearables"] == [] and data["heatmaps"] == [] and data["load"] is None


def test_demo_diaries_follow_the_seed(demo, get, today):
    bp = get()["blood_pressure"]
    assert bp["protocol"]["threshold"] == {"systolic": 135, "diastolic": 85}
    assert "PMC9904446" in bp["protocol"]["source"]["url"]
    latest, middle, oldest, dated = bp["diaries"]
    assert [d["followed"] for d in (latest, middle, oldest, dated)] == [True, True, False, None]
    assert dated["timing"] == "unrecorded" and dated["value_days"] == 5
    kept = [(s, d) for day, s, d in bp_dated(today) if day != date.fromisoformat(dated["first_day"])]
    assert dated["mean"]["n"] == len(kept) == 8
    assert dated["mean"]["systolic"] == round(sum(s for s, _ in kept) / len(kept), 1)
    assert latest["last_day"] == today.isoformat() and latest["days"] == 7
    assert oldest["mean"] is None
    # the mean is the seed's own readings of the last 6 days, morning and evening
    first = today - timedelta(days=6)
    kept = [(s, d) for at, s, d in bp_readings(today) if first < at.date() <= today]
    assert latest["mean"]["n"] == len(kept) == 24
    assert latest["mean"]["systolic"] == round(sum(s for s, _ in kept) / len(kept), 1)
    assert latest["mean"]["diastolic"] == round(sum(d for _, d in kept) / len(kept), 1)


def test_points_in_the_window_raw_then_weekly(demo, get, today):
    month = get("?days=30")["blood_pressure"]["points"]
    assert all(p["n"] == 1 for p in month)
    since = today - timedelta(days=29)
    assert len(month) == sum(since <= at.date() for at, _, _ in bp_readings(today))
    year = get("?days=365")
    assert year["window"]["bucket"] == "week"
    assert {p["session"] for p in year["blood_pressure"]["points"]} == {"morning", "evening", "other", "untimed"}
    assert all(date.fromisoformat(p["at"]).weekday() == 0 for p in year["blood_pressure"]["points"])


def test_pending_blood_pressure_is_counted_not_shown(user_id, conn, get):
    at = datetime.now(UTC).replace(hour=8) - timedelta(days=1)
    ingest_observation(conn, user_id, "Systolic", 150, "mmHg", effective_at=at,
                       review_status="pending")
    bp = get()["blood_pressure"]
    assert bp["pending_values"] == 1 and bp["readings"] == 0 and bp["points"] == []


def test_wearables_are_daily_in_short_windows_and_weekly_in_a_year(demo, get, today):
    month = {w["code"]: w for w in get("?days=30")["wearables"]}
    assert {"steps", "sleep_score", "hrv", "resting_hr", "stress_avg", "vo2max"} <= set(month)
    missed = sum(g < 30 for g in WEARABLE_GAPS)
    assert month["steps"]["days"] == len(month["steps"]["points"]) == 30 - missed
    assert month["steps"]["unit"] == "steps" and month["hrv"]["unit"] == "ms"
    year = {w["code"]: w for w in get("?days=365")["wearables"]}
    assert len(year["steps"]["points"]) <= 53
    assert sum(p["n"] for p in year["steps"]["points"]) == year["steps"]["days"]


def _daily(conn, uid, code, day, value):
    """A watch's daily value, as the importers write one."""
    conn.execute(text(
        """INSERT INTO observations (user_id, type_id, effective_at, time_precision,
               value_numeric, value_canonical, review_status, source_id, context)
           SELECT :u, id, :d, 'date', :v, :v, 'approved', :s, 'daily_aggregate'
           FROM observation_types WHERE code = :c"""),
        {"u": uid, "d": day, "v": value, "c": code,
         "s": get_or_create_channel_source(conn, uid, "garmin")})


def test_absent_series_are_left_out(user_id, conn, get, today):
    _daily(conn, user_id, "sleep_score", today, 72)
    data = get()
    assert [w["code"] for w in data["wearables"]] == ["sleep_score"]
    assert [h["code"] for h in data["heatmaps"]] == ["sleep_score"]
    assert data["load"] is None


def test_two_step_counts_of_a_day_take_the_larger(user_id, conn, get, today):
    for value in (4000, 6500):
        _daily(conn, user_id, "steps", today, value)
    [steps] = get()["wearables"]
    assert steps["points"] == [{"at": today.isoformat(), "value": 6500, "n": 1}]


def test_heatmaps_are_a_year_whatever_the_window(demo, get, today):
    for query in ("?days=7", "?days=365"):
        heatmaps = {h["code"]: h for h in get(query)["heatmaps"]}
        assert list(heatmaps) == ["steps", "sleep_score", "stress_avg"]
        steps = heatmaps["steps"]
        assert steps["to"] == today.isoformat()
        assert steps["from"] == (today - timedelta(days=364)).isoformat()
        assert len(steps["days"]) == 365 - len(WEARABLE_GAPS)


def test_training_load_from_the_demo(demo, get):
    load = get("?days=90")["load"]
    assert load["acute_days"] == 7 and load["chronic_days"] == 28
    assert [line["key"] for line in load["lines"]] == ["acute", "chronic"]
    assert all(line["points"] for line in load["lines"])


def test_a_bad_time_zone_is_refused(client):
    r = client.get("/api/v1/vitals?tz=Nowhere/Land", headers=HEADERS)
    assert r.status_code == 400


def test_an_evening_reading_in_madrid_is_an_evening_reading(user_id, conn, get):
    at = datetime.now(MADRID).replace(hour=17, minute=30, second=0, microsecond=0) - timedelta(days=1)
    for name, value in (("Systolic", 132), ("Diastolic", 82)):
        ingest_observation(conn, user_id, name, value, "mmHg", effective_at=at)
    bp = get("?tz=Europe/Madrid")["blood_pressure"]
    [point] = bp["points"]
    assert point["session"] == "evening" and point["at"].startswith(at.date().isoformat())
    assert point["at"].endswith(at.isoformat()[-6:])  # sent in the user's own zone
    # the same moment is a morning reading for someone in Los Angeles (8:30 there)
    assert get("?tz=America/Los_Angeles")["blood_pressure"]["points"][0]["session"] == "morning"


def test_today_is_the_users_today(user_id, get):
    tokyo = get("?tz=Asia/Tokyo")["window"]
    assert tokyo["tz"] == "Asia/Tokyo"
    assert tokyo["to"] == datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()
