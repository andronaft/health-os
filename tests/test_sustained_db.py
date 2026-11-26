"""Sustained deviations (#75) read from the database: the Vitals page, get_anomalies, the weekly
report. The rules themselves are tested without a DB in test_sustained.py."""
import contextlib
import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

import web.app
from analytics import sustained
from analytics.weekly_report import build as weekly
from core.db import engine
from core.services import add_medication, get_or_create_channel_source, get_or_create_user
from mcp_server import tools
from seed.demo import WEARABLE_EPISODE, load_demo
from seed.demo import workouts as demo_workouts

HEADERS = {"X-Health-OS-Token": "t"}
UTCZ = ZoneInfo("UTC")


@pytest.fixture()
def get(conn, monkeypatch):
    @contextlib.contextmanager
    def on_the_test_connection():
        yield conn

    monkeypatch.setattr(web.app, "read_only_snapshot", on_the_test_connection)
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")

    def fetch(query=""):
        r = client.get(f"/api/v1/vitals{query}", headers=HEADERS)
        assert r.status_code == 200, r.text
        return r.json()

    return fetch


@pytest.fixture()
def today(conn):
    return conn.execute(text("SELECT current_date")).scalar()


def _value(conn, uid, code, at, value, precision="date"):
    conn.execute(text(
        """INSERT INTO observations (user_id, type_id, effective_at, time_precision,
               value_numeric, value_canonical, review_status, source_id, context)
           SELECT :u, id, :at, :p, :v, :v, 'approved', :s, 'daily_aggregate'
           FROM observation_types WHERE code = :c"""),
        {"u": uid, "at": at, "p": precision, "v": value, "c": code,
         "s": get_or_create_channel_source(conn, uid, "garmin")})


def _resting(conn, uid, today, elevated=(2, 1, 0), base=58, high=67):
    """70 days of resting heart rate (58 ± 1) with `elevated` days ago at `high`."""
    for ago in range(70):
        value = high if ago in elevated else base + (-1, 0, 1, 0)[ago % 4]
        _value(conn, uid, "resting_hr", today - timedelta(days=ago), value)


def _samples(conn, uid, code, start, minutes, value, every=5):
    source = get_or_create_channel_source(conn, uid, "apple_health")
    conn.execute(text(
        """INSERT INTO device_samples (user_id, type_code, ts, value, source_id)
           VALUES (:u, :c, :ts, :v, :s)"""),
        [{"u": uid, "c": code, "ts": start + timedelta(minutes=m), "v": value, "s": source}
         for m in range(0, minutes + 1, every)])


# ---- the Vitals page -----------------------------------------------------------------------------

def test_the_demo_episode_is_found_and_reported_together(conn, get, today):
    load_demo(conn, today=today)
    data = get("?days=30&tz=UTC")
    [finding] = data["sustained"]["findings"]
    assert finding["kind"] == "days"
    assert [m["code"] for m in finding["metrics"]] == ["resting_hr", "hrv"]
    first, last = max(WEARABLE_EPISODE), min(WEARABLE_EPISODE)
    assert finding["first_day"] == (today - timedelta(days=first)).isoformat()
    assert finding["last_day"] == (today - timedelta(days=last)).isoformat()
    assert finding["together_days"] == 3
    episode = (date.fromisoformat(finding["first_day"]), date.fromisoformat(finding["last_day"]))
    assert finding["context"] == [  # the demo's workouts on those days, if any fell there
        {"kind": "workout", "day": at.date().isoformat(), "type": kind, "minutes": minutes}
        for at, kind, minutes in demo_workouts(today) if episode[0] <= at.date() <= episode[1]]
    assert get("?days=7&tz=UTC")["sustained"]["findings"] == []  # it ended before the window
    assert get("?days=365&tz=UTC")["sustained"]["findings"] == [finding]  # once, not once a week


def test_no_watch_data_finds_nothing_and_checks_nothing(conn, user_id, get):
    lasting = get()["sustained"]
    assert lasting["findings"] == []
    assert lasting["days_with_values"] == {"resting_hr": 0, "hrv": 0, "hrv_sdnn": 0}


def test_the_days_are_the_users(conn, user_id, get, today):
    # timed values at 22:30 UTC: the next day in Tokyo
    for ago in range(70):
        value = 67 if ago in (3, 2, 1) else 58 + (-1, 0, 1, 0)[ago % 4]
        at = datetime.combine(today - timedelta(days=ago), datetime.min.time(), UTC) + timedelta(hours=22, minutes=30)
        _value(conn, user_id, "resting_hr", at, value, precision="datetime")
    [in_utc] = get("?days=30&tz=UTC")["sustained"]["findings"]
    [in_tokyo] = get("?days=30&tz=Asia/Tokyo")["sustained"]["findings"]
    assert date.fromisoformat(in_tokyo["first_day"]) - date.fromisoformat(in_utc["first_day"]) == timedelta(days=1)


def test_a_beta_blocker_is_context(conn, user_id, get, today):
    _resting(conn, user_id, today)
    add_medication(conn, user_id, "Bisoprolol", start_date=today - timedelta(days=200), atc_code="C07AB07")
    add_medication(conn, user_id, "Vitamin D3", start_date=today - timedelta(days=200), atc_code="A11CC05")
    [finding] = get("?days=7&tz=UTC")["sustained"]["findings"]
    assert finding["context"] == [{"kind": "beta_blocker", "name": "Bisoprolol", "atc_code": "C07AB07"}]


def test_still_minutes_from_raw_samples(conn, user_id, today):
    _resting(conn, user_id, today, elevated=())
    day = datetime.combine(today - timedelta(days=1), datetime.min.time(), UTC)
    _samples(conn, user_id, "heart_rate", day, 24 * 60 - 5, 62)              # a resting day
    conn.execute(text("DELETE FROM device_samples WHERE ts >= :a AND ts < :b"),
                 {"a": day + timedelta(hours=9), "b": day + timedelta(hours=19)})
    _samples(conn, user_id, "heart_rate", day + timedelta(hours=9), 25, 100)   # still: found
    _samples(conn, user_id, "heart_rate", day + timedelta(hours=9, minutes=30), 10, 60)  # back down
    _samples(conn, user_id, "heart_rate", day + timedelta(hours=11), 30, 110)  # walking
    _samples(conn, user_id, "steps", day + timedelta(hours=11, minutes=10), 0, 40)
    _samples(conn, user_id, "heart_rate", day + timedelta(hours=11, minutes=35), 10, 60)
    _samples(conn, user_id, "heart_rate", day + timedelta(hours=17), 30, 140)  # a workout
    _samples(conn, user_id, "heart_rate", day + timedelta(hours=17, minutes=35), 60, 62)
    conn.execute(text(
        """INSERT INTO physical_activities (user_id, activity_date, activity_type, duration_minutes)
           VALUES (:u, :at, 'cycling', 35)"""), {"u": user_id, "at": day + timedelta(hours=16, minutes=55)})
    out = sustained.find(conn, user_id, today - timedelta(days=6), today, UTCZ)
    [episode] = [f for f in out["findings"] if f["kind"] == "minutes"]
    assert episode["start"] == day + timedelta(hours=9) and episode["minutes"] == 25
    assert episode["mean_hr"] == 100 and episode["usual"] == 58


def test_a_sample_back_near_resting_breaks_the_run_even_when_read_sparsely(conn, user_id, today):
    """The heart rate query reads only high samples and their neighbours: the dip must be among them."""
    _resting(conn, user_id, today, elevated=())
    start = datetime.combine(today - timedelta(days=1), datetime.min.time(), UTC) + timedelta(hours=9)
    _samples(conn, user_id, "heart_rate", start - timedelta(hours=1), 55, 60)
    _samples(conn, user_id, "heart_rate", start, 10, 100)
    _samples(conn, user_id, "heart_rate", start + timedelta(minutes=15), 0, 59)
    _samples(conn, user_id, "heart_rate", start + timedelta(minutes=20), 10, 100)
    assert sustained.find(conn, user_id, today - timedelta(days=6), today, UTCZ)["findings"] == []


# ---- get_anomalies and the weekly report --------------------------------------------------------

def test_the_weekly_report_lists_it_and_the_week_is_not_stable(conn, user_id, today):
    _resting(conn, user_id, today)
    report = weekly(conn, user_id)
    assert len(report["sustained"]["findings"]) == 1 and report["stable"] is False
    assert "No ECG" in report["sustained"]["limits"]


@pytest.mark.integration
def test_get_anomalies_has_a_sustained_section():
    with engine.begin() as c:
        uid = get_or_create_user(c)
        today = c.execute(text("SELECT current_date")).scalar()
        source = get_or_create_channel_source(c, uid, "garmin")
        _resting(c, uid, today)
    try:
        out = json.loads(tools.get_anomalies())
        [finding] = out["sustained"]["findings"]
        assert finding["metrics"][0]["code"] == "resting_hr"
        assert "No ECG" in out["sustained"]["limits"]
        assert len(json.loads(tools.get_anomalies("resting_hr"))["sustained"]["findings"]) == 1
        assert json.loads(tools.get_anomalies("hrv"))["sustained"]["findings"] == []
        assert "note" in json.loads(tools.get_anomalies("glucose"))["sustained"]
        assert "no ECG" in tools.get_anomalies.__doc__
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM observations WHERE source_id = :s"), {"s": source})


# ---- workouts: recorded or not (#75 review) ------------------------------------------------------

def _a_still_hour_of_exercise(conn, uid, today):
    """Resting history, and yesterday 30 min at 120 bpm with no steps (a ride, a row, a gym set)."""
    _resting(conn, uid, today, elevated=())
    start = datetime.combine(today - timedelta(days=1), datetime.min.time(), UTC) + timedelta(hours=18)
    _samples(conn, uid, "heart_rate", start - timedelta(hours=1), 55, 62)
    _samples(conn, uid, "heart_rate", start, 30, 120)
    _samples(conn, uid, "heart_rate", start + timedelta(minutes=35), 30, 62)
    return start


def test_without_any_workout_recorded_the_list_says_so(conn, user_id, today):
    _a_still_hour_of_exercise(conn, user_id, today)
    out = sustained.find(conn, user_id, today - timedelta(days=6), today, UTCZ)
    assert out["minutes_rule"] == "checked" and out["workouts_recorded"] is False
    assert [f["kind"] for f in out["findings"]] == ["minutes"]
    assert "No workouts are recorded" in out["notes"][0]


def test_a_recorded_workout_removes_the_finding_and_the_note(conn, user_id, today):
    start = _a_still_hour_of_exercise(conn, user_id, today)
    conn.execute(text(
        """INSERT INTO physical_activities (user_id, activity_date, activity_type, duration_minutes)
           VALUES (:u, :at, 'rowing', 30)"""), {"u": user_id, "at": start})
    out = sustained.find(conn, user_id, today - timedelta(days=6), today, UTCZ)
    assert out["findings"] == [] and out["notes"] == [] and out["workouts_recorded"] is True


def test_without_raw_samples_the_minutes_rule_says_it_did_not_run(conn, user_id, today):
    _resting(conn, user_id, today, elevated=())
    out = sustained.find(conn, user_id, today - timedelta(days=6), today, UTCZ)
    assert out["minutes_rule"] == "no_samples" and out["notes"] == []


def test_the_demo_records_workouts_and_lists_them_as_context(conn, get, today):
    load_demo(conn, today=today)
    lasting = get("?days=30&tz=UTC")["sustained"]
    assert lasting["workouts_recorded"] is True and lasting["minutes_rule"] == "no_samples"
    [finding] = lasting["findings"]
    first, last = date.fromisoformat(finding["first_day"]), date.fromisoformat(finding["last_day"])
    expected = [{"kind": "workout", "day": at.date().isoformat(), "type": kind, "minutes": minutes}
                for at, kind, minutes in demo_workouts(today) if first <= at.date() <= last]
    assert finding["context"] == expected


def test_apple_resting_hr_and_sdnn_reach_the_page(conn, user_id, get, today):
    for ago in range(70):
        _value(conn, user_id, "hrv_sdnn", today - timedelta(days=ago),
               17 if ago in (2, 1, 0) else 30 + (-2, 0, 2, 0)[ago % 4])
    [finding] = get("?days=7&tz=UTC")["sustained"]["findings"]
    assert [m["code"] for m in finding["metrics"]] == ["hrv_sdnn"]


@pytest.mark.integration
def test_a_failing_sustained_check_keeps_the_rest_of_get_anomalies(monkeypatch):
    def broken(code, days):
        raise RuntimeError("boom")

    with engine.begin() as c:
        get_or_create_user(c)

    monkeypatch.setattr(tools, "_sustained", broken)
    out = json.loads(tools.get_anomalies())
    assert "anomalies" in out and "markers_checked" in out
    assert out["sustained"] == {"findings": [], "error": "the sustained check failed: RuntimeError: boom"}
