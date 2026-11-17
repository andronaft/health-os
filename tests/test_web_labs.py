"""GET /api/v1/labs and /api/v1/labs/{code} (#55): approved values are the facts, every point
carries the range of its own form, pending values are sent apart and kept out of the trend and the
baseline. The endpoints run on the test's own connection, so everything stays in its rolled-back
transaction. Made-up values and the fictional demo patient only."""
import contextlib
from datetime import UTC, date, datetime, timedelta

import pytest
from starlette.testclient import TestClient

import web.app
from core import queries as q
from core.services import approve_staged, ingest_observation, stage_panel
from seed.demo import load_demo
from web.labs import BASELINE_MIN, MATRIX_DATES, SPARK_POINTS, TREND_MIN_N, band

HEADERS = {"X-Health-OS-Token": "t"}


@pytest.fixture()
def client(conn, monkeypatch):
    @contextlib.contextmanager
    def on_the_test_connection():
        yield conn

    monkeypatch.setattr(web.app, "read_only_snapshot", on_the_test_connection)
    return TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")


@pytest.fixture()
def get(client):
    def fetch(path):
        r = client.get(f"/api/v1/{path}", headers=HEADERS)
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        return r.json()

    return fetch


@pytest.fixture()
def demo(conn):
    return load_demo(conn, today=date.today())


def _days_ago(n: int) -> datetime:
    return (datetime.now(UTC) - timedelta(days=n)).replace(hour=8, minute=0, second=0, microsecond=0)


def _glucose(conn, uid, value, days_ago, *, unit="mmol/L", ref=(3.9, 5.6), review="approved"):
    return ingest_observation(conn, uid, "Glucose", value, unit, effective_at=_days_ago(days_ago),
                              ref_min=ref[0], ref_max=ref[1], review_status=review)


def _by_code(rows):
    return {row["code"]: row for row in rows}


# ---- the marker table -------------------------------------------------------------------------

def test_the_table_lists_lab_markers_with_their_latest_approved_value(demo, get):
    markers = _by_code(get("labs")["markers"])
    # blood pressure and weight are the Vitals page's, not lab markers
    assert "systolic_bp" not in markers and "body_weight" not in markers
    ldl = markers["ldl"]
    assert ldl["value"] == 3.8 and ldl["unit"] == "mmol/L" and ldl["status"] == "high"
    assert ldl["ref_min"] == 0 and ldl["ref_max"] == 3.0
    assert ldl["n"] == 5 and ldl["specimen"] == "serum" and ldl["name"] == "LDL cholesterol"
    assert markers["hemoglobin"]["specimen"] == "whole_blood"


def test_a_pending_value_is_counted_but_never_the_latest(demo, get):
    data = get("labs")
    markers = _by_code(data["markers"])
    vitamin_d = markers["vitamin_d"]
    assert vitamin_d["value"] == 22 and vitamin_d["pending"] == 1  # 27 is under review
    assert all(p["value"] != 27 for p in vitamin_d["spark"])
    # ferritin has nothing approved: no row, but the page still says it waits
    assert "ferritin" not in markers
    assert data["pending"] == 2


def test_the_sparkline_is_the_latest_approved_values_oldest_first(conn, user_id, get):
    for i in range(SPARK_POINTS + 3):
        _glucose(conn, user_id, 4.0 + i / 10, days_ago=100 - i)
    _glucose(conn, user_id, 9.9, days_ago=1, review="pending")
    [row] = get("labs")["markers"]
    values = [p["value"] for p in row["spark"]]
    assert len(values) == SPARK_POINTS and values == sorted(values)
    assert values[-1] == pytest.approx(4.0 + (SPARK_POINTS + 2) / 10)
    assert 9.9 not in values and row["n"] == SPARK_POINTS + 3 and row["pending"] == 1


def test_the_matrix_has_the_latest_days_newest_first_and_no_pending_value(demo, get):
    matrix = get("labs")["matrix"]
    dates = matrix["dates"]
    assert dates == sorted(dates, reverse=True) and len(dates) == 5  # five approved panels
    rows = _by_code(matrix["rows"])
    assert "ferritin" not in rows
    ldl = rows["ldl"]["cells"]
    assert ldl[dates[0]]["value"] == 3.8 and ldl[dates[0]]["status"] == "high"
    pending_day = (date.today() - timedelta(days=3)).isoformat()
    assert pending_day not in dates
    assert dates[-1] not in rows["hemoglobin"]["cells"]  # not measured that day: no cell


def test_the_matrix_keeps_only_the_latest_days(conn, user_id, get):
    for i in range(MATRIX_DATES + 2):
        _glucose(conn, user_id, 5.0, days_ago=200 - 10 * i)
    matrix = get("labs")["matrix"]
    assert len(matrix["dates"]) == MATRIX_DATES and matrix["older_dates"] == 2


def test_nothing_recorded_is_empty_not_zero(user_id, get):
    data = get("labs")
    assert data == {"markers": [], "pending": 0,
                    "matrix": {"dates": [], "older_dates": 0, "rows": []}}


def test_no_user_yet_still_answers(get):
    assert get("labs")["markers"] == []


# ---- one marker -------------------------------------------------------------------------------

def test_each_point_has_the_range_of_its_own_form(conn, user_id, get):
    # two labs, two ranges, and one form in mg/dL: the band is converted like the value
    _glucose(conn, user_id, 5.0, days_ago=60, ref=(3.9, 5.6))
    _glucose(conn, user_id, 5.2, days_ago=30, ref=(4.1, 6.1))
    _glucose(conn, user_id, 95, days_ago=10, unit="mg/dL", ref=(70, 100))
    data = get("labs/glucose")
    assert data["unit"] == "mmol/L"
    first, second, third = data["points"]
    assert first["range"] == {"min": 3.9, "max": 5.6, "unconverted": False}
    assert second["range"] == {"min": 4.1, "max": 6.1, "unconverted": False}
    assert third["value"] == pytest.approx(95 * 0.05551)
    assert third["range"]["min"] == pytest.approx(70 * 0.05551)
    assert third["range"]["max"] == pytest.approx(100 * 0.05551)
    # the tooltip's "on the form" is the form's own value, unit and range
    assert third["original"] == {"value": 95, "comparator": None, "text": None, "unit": "mg/dL",
                                 "ref_min": 70, "ref_max": 100}


def test_a_one_sided_range_keeps_its_open_side(conn, user_id, get):
    ingest_observation(conn, user_id, "HDL", 1.4, "mmol/L", effective_at=_days_ago(5),
                       ref_min=1.2)
    [point] = get("labs/hdl")["points"]
    assert point["range"] == {"min": 1.2, "max": None, "unconverted": False}


def test_a_range_in_a_unit_with_no_conversion_is_unknown_not_guessed():
    row = {"ref_min": 70, "ref_max": 100, "unit": "furlongs"}
    assert band(row, "mmol/L", {"mg/dL": (0.05551, 0)}) == {
        "min": None, "max": None, "unconverted": True}
    assert band({"ref_min": None, "ref_max": None, "unit": "mmol/L"}, "mmol/L", {}) is None
    # a marker without a canonical unit (a ratio) keeps the form's numbers
    assert band({"ref_min": 0.8, "ref_max": 1.2, "unit": None}, None, {})["max"] == 1.2


def test_pending_values_stay_out_of_the_trend_and_the_baseline(conn, user_id, get):
    for i, value in enumerate([4.6, 4.8, 5.0, 5.2, 5.4]):
        _glucose(conn, user_id, value, days_ago=400 - 80 * i)
    _glucose(conn, user_id, 2.0, days_ago=2, review="pending")
    data = get("labs/glucose")
    assert [p["value"] for p in data["points"]] == [4.6, 4.8, 5.0, 5.2, 5.4]
    assert all(not p["pending"] for p in data["points"])
    [pending] = data["pending"]
    assert pending["value"] == 2.0 and pending["pending"] is True
    trend = data["trend"]
    assert trend["n"] == 5 and trend["direction"] == "increasing" and trend["p"] < 0.05
    assert trend["min_n"] == TREND_MIN_N and trend["slope_per_year"] > 0
    assert trend == {**q.trend(conn, user_id, "glucose"), "min_n": TREND_MIN_N,
                     "days": trend["days"]}  # what get_trend says in the chat
    base = data["baseline"]
    assert base["n"] == 5 and base["mean"] == pytest.approx(5.0)
    assert base["low"] < 4.6 and base["high"] > 5.4


def test_too_few_values_give_no_trend_and_no_baseline(conn, user_id, get):
    _glucose(conn, user_id, 5.0, days_ago=30)
    _glucose(conn, user_id, 5.1, days_ago=10)
    data = get("labs/glucose")
    assert data["trend"]["n"] == 2 and data["trend"]["p"] is None
    assert data["baseline"] == {"n": 2, "min_n": BASELINE_MIN, "sigmas": 2,
                                "mean": None, "low": None, "high": None}


def test_a_marker_with_only_pending_values_has_no_facts(demo, get):
    data = get("labs/ferritin")
    assert data["points"] == [] and len(data["pending"]) == 1
    assert data["trend"]["n"] == 0 and data["baseline"]["n"] == 0
    assert "note" not in data["trend"] and "did_you_mean" not in data["trend"]


def test_the_code_is_read_like_get_trend_reads_it(demo, get):
    assert get("labs/LDL")["code"] == "ldl"


def test_a_staged_panel_shows_only_after_approval(conn, user_id, get):
    rows = [{"raw_name": "TSH", "value": 2.2, "unit": "mIU/L", "ref_min": 0.4, "ref_max": 4.0}]
    staged = stage_panel(conn, user_id, date.today() - timedelta(days=1), rows)
    assert get("labs")["markers"] == [] and get("labs")["pending"] == 1
    assert get("labs/tsh")["points"] == []
    approve_staged(conn, user_id, staged["source_id"])
    assert [m["code"] for m in get("labs")["markers"]] == ["tsh"]
    assert get("labs/tsh")["pending"] == []


@pytest.mark.parametrize("code", ["no_such_marker", "systolic_bp"])
def test_an_unknown_or_non_lab_marker_is_a_404(demo, client, code):
    r = client.get(f"/api/v1/labs/{code}", headers=HEADERS)
    assert r.status_code == 404 and r.json() == {"error": "no such marker"}


@pytest.mark.parametrize("path", ["labs", "labs/ldl"])
def test_labs_need_the_session_token(client, path):
    assert client.get(f"/api/v1/{path}").status_code == 403
    assert client.get(f"/api/v1/{path}", headers={"X-Health-OS-Token": "wrong"}).status_code == 403


def test_nothing_in_the_answer_reassures(demo, get):
    text = (str(get("labs")) + str(get("labs/ldl"))).lower()
    for phrase in ("everything is normal", "all normal", "healthy", "no problems"):
        assert phrase not in text
