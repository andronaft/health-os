"""GET /api/v1/overview (#54): matches get_health_summary, says only what's there, and is read-only.

The endpoint runs on the test's own connection, so everything stays in its rolled-back transaction.
Made-up values and the fictional demo patient only."""
import contextlib
import re
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.testclient import TestClient

import web.app
from analytics.screening import for_user
from core.health_summary import build
from core.services import (
    add_medication,
    approve_staged,
    ingest_observation,
    stage_panel,
    upsert_profile,
)
from safety.critical_values import GENERIC, MESSAGES
from safety.policy import DISCLAIMER
from seed.demo import load_demo
from web.overview import AVERAGE_DAYS, rolling_average

HEADERS = {"X-Health-OS-Token": "t"}


@pytest.fixture()
def get(conn, monkeypatch):
    @contextlib.contextmanager
    def on_the_test_connection():
        yield conn

    monkeypatch.setattr(web.app, "read_only_snapshot", on_the_test_connection)
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")

    def fetch(query=""):
        r = client.get(f"/api/v1/overview{query}", headers=HEADERS)
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        return r.json()

    return fetch


@pytest.fixture()
def demo(conn):
    return load_demo(conn, today=date.today())


def _days_ago(n: int, hour: int = 8) -> datetime:
    day = datetime.now(UTC) - timedelta(days=n)
    return day.replace(hour=hour, minute=0, second=0, microsecond=0)


def _wearable(conn, uid, code: str, value: float, at: datetime, *, ref_max=None, status=None):
    """A daily value as scripts/import_garmin.py writes it: straight in, approved."""
    source = conn.execute(text(
        """INSERT INTO ingestion_sources (user_id, channel, extracted_by, review_status)
           VALUES (:u, 'device', 'test', 'approved') RETURNING id"""), {"u": uid}).scalar()
    conn.execute(text(
        """INSERT INTO observations (user_id, type_id, effective_at, time_precision, value_numeric,
               value_canonical, ref_max, status, review_status, source_id)
           SELECT :u, id, :at, 'date', :v, :v, :max, :st, 'approved', :s
           FROM observation_types WHERE code = :c"""),
        {"u": uid, "c": code, "at": at, "v": value, "max": ref_max, "st": status, "s": source})


def _by_code(rows):
    return {row["code"]: row for row in rows}


def _tile(data, tile):
    return next(t for t in data["tiles"] if t["id"] == tile)


# ---- the demo patient matches get_health_summary ------------------------------------------------

def test_profile_matches_the_summary(conn, demo, get):
    data = get()
    profile = data["profile"]
    line = f"**Profile:** {profile['sex']}, {profile['age']} yr, blood type {profile['blood_type']}"
    assert line in build(conn, demo).text
    assert profile["missing"] == []
    assert profile["rh_factor"] == "+" and profile["height_cm"] == 168


def test_lists_match_the_summary(conn, demo, get):
    data = get()
    summary = build(conn, demo)
    assert summary.valid, summary.issues
    assert summary.counts == {"allergies": len(data["allergies"]),
                              "active_diagnoses": len(data["diagnoses"]),
                              "current_medications": len(data["medications"]),
                              "habits": len(data["habits"])}
    assert f"**{data['allergies'][0]['allergen']}** — {data['allergies'][0]['reaction']}" in summary.text
    diagnosis = data["diagnoses"][0]
    assert (f"{diagnosis['diagnosis_name']} [{diagnosis['icd10_code']}] — ⚠️ "
            f"{diagnosis['verification_status']} (not certain)") in summary.text
    assert data["medications"][0]["medication_name"] in summary.text


def test_pending_and_recency_match_the_summary(conn, demo, get):
    data = get()
    text_out = build(conn, demo).text
    pending = data["attention"]["pending"]
    assert f"Awaiting review ({pending['total']} values, not yet facts)" in text_out
    assert data["attention"]["critical"] == []
    assert f"Last lab panel: {data['coverage']['last_panel']}" in text_out
    assert "Not checked in a long time" not in text_out
    assert data["attention"]["not_checked"]["rows"] == []


def test_screening_matches_the_calendar(conn, demo, get):
    screening = get()["attention"]["screening"]
    calendar = {r["code"]: r["status"] for r in for_user(conn, demo)["recommendations"]}
    assert screening["available"] is True
    assert screening["overdue"] == []
    assert {r["code"] for r in screening["no_record"]} == {
        code for code, status in calendar.items() if status == "due"}
    assert "bp" not in {r["code"] for r in screening["no_record"]}  # the demo has measured it


def test_the_demo_markers_add_up(demo, get):
    data = get()
    # 9 lab markers: LDL, total cholesterol high, vitamin D low, 6 in range; BP and weight no range
    assert data["coverage"] == {"recorded": 12, "in_range": 6, "out_of_range": 3, "no_range": 3,
                                "last_panel": data["coverage"]["last_panel"],
                                "last_panel_pending": True}
    rows = _by_code(data["attention"]["out_of_range"])
    assert {code: row["status"] for code, row in rows.items()} == {
        "ldl": "high", "cholesterol_total": "high", "vitamin_d": "low"}
    assert rows["ldl"]["value"] == 3.8 and rows["ldl"]["unit"] == "mmol/L"
    assert rows["ldl"]["ref_max"] == 3.0
    assert rows["ldl"]["name"] == "LDL cholesterol"  # the English name, not name_uk


# ---- pending values never look like facts --------------------------------------------------------

def test_a_pending_value_reaches_only_the_pending_list(demo, get):
    data = get()
    pending = _by_code(data["attention"]["pending"]["rows"])
    assert set(pending) == {"ferritin", "vitamin_d"}
    assert pending["vitamin_d"]["value"] == 27
    # vitamin D stays at its latest approved value, and ferritin, only ever pending, isn't counted
    assert _by_code(data["attention"]["out_of_range"])["vitamin_d"]["value"] == 22
    assert "ferritin" not in _by_code(data["attention"]["out_of_range"])
    assert data["coverage"]["recorded"] == 12


def test_a_pending_blood_pressure_stays_out_of_the_tile(conn, user_id, get):
    ingest_observation(conn, user_id, "Systolic", 200, "mmHg", effective_at=_days_ago(1),
                       review_status="pending")
    tile = _tile(get(), "blood_pressure")
    assert tile["series"] == [] and tile["values"] == []


def test_a_panel_under_review_is_flagged_on_the_timeline(conn, user_id, get):
    today = date.today()
    rows = [{"raw_name": "HDL", "value": 1.3, "unit": "mmol/L", "ref_min": 1.2, "ref_max": None}]
    approved = stage_panel(conn, user_id, today - timedelta(days=40), rows)
    approve_staged(conn, user_id, approved["source_id"])
    stage_panel(conn, user_id, today - timedelta(days=2), rows)
    events = [e for e in get()["events"] if e["kind"] == "panel"]
    assert [e["pending"] for e in events] == [True, False]
    assert events[0]["date"] == str(today - timedelta(days=2))
    assert get()["coverage"]["last_panel_pending"] is True


# ---- critical values come with the escalation text ----------------------------------------------

@pytest.fixture()
def critical_panel(conn, user_id):
    rows = [{"raw_name": "Potassium", "value": 6.9, "unit": "mmol/L", "ref_min": 3.5, "ref_max": 5.1}]
    return stage_panel(conn, user_id, date.today() - timedelta(days=1), rows)


def test_a_pending_critical_value_shows_with_its_message(conn, user_id, critical_panel, get):
    data = get()
    [row] = data["attention"]["critical"]
    assert row["code"] == "potassium" and row["value"] == 6.9 and row["pending"] is True
    assert row["message"] == MESSAGES["potassium"]["en"]
    assert data["attention"]["disclaimer"] == DISCLAIMER
    assert "CRITICAL value" in build(conn, user_id).text  # the summary says it too
    assert data["attention"]["pending"]["rows"][0]["critical"] is True
    assert data["coverage"]["recorded"] == 0  # still not a fact


def test_an_approved_critical_value_stays_out_of_the_plain_list(conn, user_id, critical_panel, get):
    approve_staged(conn, user_id, critical_panel["source_id"])
    data = get()
    [row] = data["attention"]["critical"]
    assert row["pending"] is False and row["status"] == "critical"
    assert data["attention"]["out_of_range"] == []
    assert data["coverage"]["out_of_range"] == 1 and data["coverage"]["recorded"] == 1


@pytest.mark.parametrize("lang, needle", [("uk", "Критичний калій"), ("es", "Potasio crítico"),
                                          ("en", "Critical potassium"), ("xx", "Critical potassium")])
def test_the_escalation_text_and_names_follow_the_language(critical_panel, get, lang, needle):
    data = get(f"?lang={lang}")
    assert needle in data["attention"]["critical"][0]["message"]
    expected = {"uk": "Калій", "es": "Potasio"}.get(lang, "Potassium")
    assert expected in data["attention"]["critical"][0]["name"]


def test_a_critical_marker_without_its_own_text_gets_the_generic_one(conn, user_id, get):
    _wearable(conn, user_id, "hdl", 9.9, _days_ago(1), status="critical")
    assert get()["attention"]["critical"][0]["message"] == GENERIC["en"]


def test_a_unit_it_cannot_read_is_alarming_too(conn, user_id, get):
    rows = [{"raw_name": "Калій", "value": 6.8, "unit": "mmol per liter"}]
    stage_panel(conn, user_id, date.today() - timedelta(days=1), rows)
    [row] = get()["attention"]["critical"]
    assert row["unverifiable"] is True and row["pending"] is True and row["message"] is None
    assert "critical check impossible" in build(conn, user_id).text


def test_a_marker_it_does_not_recognize_says_so(conn, user_id, get):
    ingest_observation(conn, user_id, "Sample marker XYZ", 1.5, "u", effective_at=_days_ago(1),
                       review_status="pending")
    pending = get()["attention"]["pending"]
    assert pending["unmapped"] == 1
    assert pending["rows"][0]["unmapped"] is True
    assert pending["rows"][0]["raw_name"] == "Sample marker XYZ"


def test_only_some_pending_rows_are_sent_but_never_too_few_alarming_ones(conn, user_id, get):
    for i in range(25):
        ingest_observation(conn, user_id, "HDL", 1.3 + i / 100, "mmol/L", effective_at=_days_ago(1),
                           review_status="pending")
    ingest_observation(conn, user_id, "Potassium", 6.9, "mmol/L", effective_at=_days_ago(30))
    pending = get()["attention"]["pending"]
    assert pending["total"] == 26 and len(pending["rows"]) == 20
    assert pending["rows"][0]["critical"] is True  # first, though it is the oldest


# ---- the tiles -----------------------------------------------------------------------------------

def test_blood_pressure_is_a_seven_day_average(demo, get):
    data = get()
    tile = _tile(data, "blood_pressure")
    assert tile["average_days"] == AVERAGE_DAYS == 7 and tile["unit"] == "mmHg"
    assert tile["readings"] == 7
    # the demo's values, as seed/demo.py writes them: d days ago
    systolic = [128 + (d * 7) % 11 for d in range(7)]
    diastolic = [82 + (d * 5) % 7 for d in range(7)]
    values = _by_code(tile["values"])
    assert values["systolic_bp"]["value"] == round(sum(systolic) / 7, 1)
    assert values["diastolic_bp"]["value"] == round(sum(diastolic) / 7, 1)
    assert values["systolic_bp"]["status"] is None  # an average isn't in or out of a range
    assert [s["code"] for s in tile["series"]] == ["systolic_bp", "diastolic_bp"]
    assert len(tile["series"][0]["points"]) == 14  # one per day


def test_the_average_counts_a_week_of_readings_and_every_reading_of_a_day(conn, user_id, get):
    for days_ago, value in ((0, 130), (0, 150), (6, 120), (7, 500)):
        ingest_observation(conn, user_id, "Systolic", value, "mmHg",
                           effective_at=_days_ago(days_ago, hour=1 + value % 20))
    tile = _tile(get(), "blood_pressure")
    assert tile["values"][0]["value"] == round((130 + 150 + 120) / 3, 1)  # the 8th day back is out
    assert tile["readings"] == 3


def test_points_only_from_the_window_but_the_average_reaches_behind_it(conn, user_id, get):
    ingest_observation(conn, user_id, "Systolic", 100, "mmHg", effective_at=_days_ago(33))
    ingest_observation(conn, user_id, "Systolic", 120, "mmHg", effective_at=_days_ago(29))
    tile = _tile(get(), "blood_pressure")
    assert [p["value"] for p in tile["series"][0]["points"]] == [110.0]  # (100 + 120) / 2


def test_rolling_average():
    at = lambda day: datetime(2026, 1, day, 8, tzinfo=UTC)  # noqa: E731
    points = [(at(1), 10.0), (at(1), 20.0), (at(3), 30.0), (at(9), 40.0)]
    assert rolling_average(points) == [(at(1), 15.0, 2), (at(3), 20.0, 3), (at(9), 35.0, 2)]
    assert rolling_average([]) == []


def test_a_single_value_tile_keeps_its_status_and_raw_points(conn, user_id, get):
    _wearable(conn, user_id, "resting_hr", 58, _days_ago(2), ref_max=59, status="normal")
    _wearable(conn, user_id, "resting_hr", 60, _days_ago(1), ref_max=59, status="high")
    tile = _tile(get(), "resting_hr")
    assert tile["average_days"] is None and tile["readings"] is None
    assert tile["values"] == [{"code": "resting_hr", "value": 60, "status": "high"}]
    assert tile["unit"] == "bpm"  # the marker's own: the importers leave a row's unit empty
    assert [p["value"] for p in tile["series"][0]["points"]] == [58, 60]


def test_a_tile_without_recent_values_says_when_there_last_was_one(conn, user_id, get):
    ingest_observation(conn, user_id, "Weight", 70.5, "kg", effective_at=_days_ago(100))
    tile = _tile(get(), "weight")
    assert tile["series"] == [] and tile["values"] == []
    assert tile["last_recorded"]["values"] == [70.5] and tile["last_recorded"]["unit"] == "kg"


def test_a_tile_with_nothing_at_all_is_empty_not_zero(user_id, get):
    tile = _tile(get(), "hrv")
    assert tile["series"] == [] and tile["values"] == [] and tile["last_recorded"] is None


# ---- what's missing is said -----------------------------------------------------------------------

def test_no_profile_says_what_is_missing(user_id, get):
    data = get()
    assert data["profile"]["missing"] == ["date_of_birth", "sex"]
    assert data["profile"]["age"] is None
    assert data["attention"]["screening"] == {"available": False, "overdue": [], "no_record": []}
    assert data["coverage"]["recorded"] == 0
    # "never" is a fact too, and with nothing measured it holds for everything the check watches
    rows = data["attention"]["not_checked"]["rows"]
    assert len(rows) == data["attention"]["not_checked"]["watched"]
    assert all(row["last"] is None for row in rows)


def test_no_user_yet_still_answers(monkeypatch, get):
    monkeypatch.setattr("core.queries.user_id", lambda conn: None)
    data = get()
    assert data["profile"]["missing"] == ["date_of_birth", "sex"]
    assert data["events"] == [] and data["coverage"]["recorded"] == 0


def test_an_overdue_screening_is_listed(conn, user_id, get):
    upsert_profile(conn, user_id, date_of_birth=date(1985, 1, 1), sex="female")
    ingest_observation(conn, user_id, "Systolic", 120, "mmHg", effective_at=_days_ago(800))
    screening = get()["attention"]["screening"]
    assert [r["code"] for r in screening["overdue"]] == ["bp"]
    assert screening["overdue"][0]["last_done"] == str(_days_ago(800).date())


def test_an_old_check_is_listed_like_in_the_summary(conn, user_id, get):
    ingest_observation(conn, user_id, "Glucose", 5.0, "mmol/L", effective_at=_days_ago(500))
    rows = _by_code(get()["attention"]["not_checked"]["rows"])
    assert rows["glucose"]["months"] == 16
    assert rows["glucose"]["name"] == "Glucose"
    assert "Glucose: last ~16 mo. ago" in build(conn, user_id).text


def test_events_are_past_ones_newest_first(conn, user_id, get):
    today = date.today()
    add_medication(conn, user_id, "Sample A", start_date=today - timedelta(days=5))
    add_medication(conn, user_id, "Sample B", start_date=today - timedelta(days=9))
    add_medication(conn, user_id, "Sample future", start_date=today + timedelta(days=9))
    events = get()["events"]
    assert [e["title"] for e in events] == ["Sample A", "Sample B"]
    assert events[0] == {"kind": "medication_start", "date": str(today - timedelta(days=5)),
                         "title": "Sample A", "pending": False}


# ---- a read-only API ------------------------------------------------------------------------------

def test_overview_needs_the_session_token():
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")
    assert client.get("/api/v1/overview").status_code == 403
    assert client.post("/api/v1/overview", headers=HEADERS).status_code == 405


@pytest.mark.integration
def test_the_snapshot_refuses_writes():
    with web.app.read_only_snapshot() as conn:
        with pytest.raises(DBAPIError, match="read-only transaction"):
            conn.execute(text("INSERT INTO users DEFAULT VALUES"))


@pytest.mark.integration
def test_overview_runs_on_a_real_snapshot():
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")
    r = client.get("/api/v1/overview", headers=HEADERS)
    assert r.status_code == 200 and r.json()["window"]["days"] == 30


def test_an_unreachable_database_is_a_503_that_says_so(monkeypatch):
    class Down:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(web.app, "engine", Down())
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")
    r = client.get("/api/v1/overview", headers=HEADERS)
    assert r.status_code == 503 and r.json() == {"error": "database unreachable"}
    assert "connection refused" not in r.text


def test_nothing_in_the_answer_reassures(demo, get):
    assert not re.search(r"everything is normal|all normal|all good|no problems",
                         str(get()).lower())
