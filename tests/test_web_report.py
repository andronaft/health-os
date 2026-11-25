"""GET /api/v1/report (#60): the doctor-visit report's data, in the report's language, from approved
values only, with "what changed" since a date. The endpoint runs on the test's own connection, so
everything stays in its rolled-back transaction. Made-up values and the fictional demo patient only."""
import contextlib
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

import web.app
import web.report
from analytics import rcv
from core import queries as q
from core.services import (
    add_diagnosis,
    add_medication,
    approve_staged,
    stage_panel,
    stop_medication,
)
from seed.demo import load_demo
from web.report import DEFAULT_SINCE_DAYS, TREND_CHARTS, TREND_MIN_POINTS

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
    def fetch(query=""):
        r = client.get(f"/api/v1/report{query}", headers=HEADERS)
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        return r.json()

    return fetch


def _today(conn) -> date:
    return conn.execute(text("SELECT now()::date")).scalar()


def _panel(conn, uid, day: date, rows: list[tuple]):
    staged = stage_panel(conn, uid, day, [{"raw_name": n, "value": v, "unit": u, "ref_min": lo,
                                          "ref_max": hi} for n, v, u, lo, hi in rows])
    approve_staged(conn, uid, staged["source_id"])


# ------------------------------------------------------------------ the demo patient


def test_the_demo_patient_in_spanish(conn, get):
    load_demo(conn, today=date.today())
    data = get("?lang=es")
    assert data["lang"] == "es" and data["empty"] is False
    assert data["profile"]["sex"] == "female" and data["profile"]["blood_type"] == "A"
    assert data["allergies"] == [{"allergen": "penicillin", "reaction": "rash",
                                  "severity": "moderate", "verified": True}]
    assert [m["name"] for m in data["medications"]] == ["Vitamin D3"]
    [diagnosis] = data["diagnoses"]
    assert diagnosis["verification_status"] == "suspected" and diagnosis["icd10"] == "E78.0"
    # marker names in the report's language, not the UI's
    out = {r["code"]: r for r in data["out_of_range"]["rows"]}
    assert out["ldl"]["name"] == "Colesterol LDL"
    assert {"ldl", "cholesterol_total", "vitamin_d"} <= set(out)


def test_the_out_of_range_list_is_what_prepare_doctor_visit_calls_still_out_of_range(conn, get):
    # prepare_doctor_visit's still_out_of_range is q.open_results; the tool opens its own
    # connection, which can't see this test's transaction, so compare with the query itself
    uid = load_demo(conn, today=date.today())
    data = get()
    assert ({r["code"] for r in data["out_of_range"]["rows"]}
            == {r["type_code"] for r in q.open_results(conn, uid)["open"]})
    assert data["out_of_range"]["lab_markers_seen"] >= len(data["out_of_range"]["rows"])


def test_pending_values_are_counted_but_never_shown(conn, get):
    uid = load_demo(conn, today=date.today())
    data = get()
    approved = conn.execute(text("SELECT count(*) FROM v_observations WHERE user_id=:u"),
                            {"u": uid}).scalar()
    assert data["approved_values"] == approved
    assert data["pending_values"] == 2  # the demo's unapproved panel: vitamin D 27, ferritin 35
    # the newer vitamin D is pending: the report says so, but shows the approved 22
    vitamin_d = next(r for r in data["out_of_range"]["rows"] if r["code"] == "vitamin_d")
    assert vitamin_d["newer_pending"] is True and vitamin_d["value"] == 22
    body = json.dumps(data)
    assert "ferritin" not in body
    assert all(r["code"] != "vitamin_d" for r in data["changes"]["results"])  # 27 is not a result


def test_trend_charts_are_few_and_out_of_range_markers_come_first(conn, get):
    load_demo(conn, today=date.today())
    trends = get()["trends"]
    assert 0 < len(trends) <= TREND_CHARTS
    assert all(len(t["points"]) >= TREND_MIN_POINTS for t in trends)
    assert trends[0]["code"] in {"ldl", "cholesterol_total"}
    dates = [p["at"] for p in trends[0]["points"]]
    assert dates == sorted(dates)  # oldest first
    ldl = next(t for t in trends if t["code"] == "ldl")
    assert ldl["ref_max"] == 3.0 and ldl["unit"] == "mmol/L"
    assert ldl["change"]["rcv"] == 22.9 and ldl["change"]["significant"] is False


# ------------------------------------------------------------------ the since date


def test_since_defaults_to_six_months_without_a_visit(conn, user_id, get):
    changes = get()["changes"]
    assert changes["since_source"] == "default" and changes["last_visit"] is None
    assert changes["since"] == (_today(conn) - timedelta(days=DEFAULT_SINCE_DAYS)).isoformat()


def test_since_defaults_to_the_last_visit_on_record(conn, user_id, get):
    today = _today(conn)
    for days_ago in (200, 40):
        conn.execute(text("INSERT INTO doctor_visits (user_id, visit_date) VALUES (:u, :d)"),
                     {"u": user_id, "d": today - timedelta(days=days_ago)})
    # a visit booked for later is not the last visit
    conn.execute(text("INSERT INTO doctor_visits (user_id, visit_date) VALUES (:u, :d)"),
                 {"u": user_id, "d": today + timedelta(days=10)})
    changes = get()["changes"]
    assert changes["since_source"] == "visit"
    assert changes["since"] == changes["last_visit"] == (today - timedelta(days=40)).isoformat()


def test_a_chosen_since_date_wins(conn, user_id, get):
    changes = get("?since=2026-01-15")["changes"]
    assert changes["since"] == "2026-01-15" and changes["since_source"] == "chosen"


@pytest.mark.parametrize("since", ["yesterday", "2026-13-01", "15.01.2026"])
def test_a_since_that_is_no_date_is_refused(conn, client, since):
    r = client.get(f"/api/v1/report?since={since}", headers=HEADERS)
    assert r.status_code == 400


def test_what_changed_since_a_date(conn, user_id, get):
    today = _today(conn)
    since = today - timedelta(days=30)
    _panel(conn, user_id, today - timedelta(days=90), [
        ("LDL", 2.8, "mmol/L", 0, 3.0),            # in range → out of range
        ("Vitamin D", 18, "ng/mL", 30, 100),       # out of range → back in range
        ("Glucose", 4.4, "mmol/L", 3.9, 5.6),      # in range → in range, +27 %: past the RCV
    ])
    _panel(conn, user_id, today - timedelta(days=5), [
        ("LDL", 3.4, "mmol/L", 0, 3.0),
        ("Vitamin D", 41, "ng/mL", 30, 100),
        ("Glucose", 5.6, "mmol/L", 3.9, 5.6),
        ("TSH", 2.0, "mIU/L", 0.4, 4.0),           # first measurement
    ])
    old = add_medication(conn, user_id, "Made-up statin", start_date=today - timedelta(days=400))
    stop_medication(conn, user_id, old, end_date=today - timedelta(days=10))
    add_medication(conn, user_id, "Made-up supplement", start_date=today - timedelta(days=3),
                   product_type="supplement")
    add_medication(conn, user_id, "Long-standing tablet", start_date=today - timedelta(days=900))
    add_diagnosis(conn, user_id, "Made-up condition", diagnosed_at=today - timedelta(days=2))
    add_diagnosis(conn, user_id, "Old condition", diagnosed_at=today - timedelta(days=700))

    changes = get(f"?since={since.isoformat()}")["changes"]
    by_code = {r["code"]: r for r in changes["results"]}
    assert set(by_code) == {"ldl", "vitamin_d", "glucose", "tsh"}
    assert by_code["ldl"]["moved"] == "out_of_range"
    assert by_code["ldl"]["before"]["value"] == 2.8 and by_code["ldl"]["value"] == 3.4
    assert by_code["vitamin_d"]["moved"] == "into_range"
    assert by_code["tsh"]["before"] is None and by_code["tsh"]["moved"] is None
    # what crossed its range comes first
    assert {r["code"] for r in changes["results"][:2]} == {"ldl", "vitamin_d"}
    # a change is judged only where a CVi is cited
    assert by_code["glucose"]["change"]["significant"] is True
    assert by_code["ldl"]["change"]["significant"] is False  # +21.4 %, under the RCV of 22.9 %
    assert by_code["vitamin_d"]["change"] is None and by_code["tsh"]["change"] is None

    meds = changes["medications"]
    assert [m["name"] for m in meds["started"]] == ["Made-up supplement"]
    assert [m["name"] for m in meds["stopped"]] == ["Made-up statin"]
    assert meds["stopped"][0]["end_date"] == (today - timedelta(days=10)).isoformat()
    assert [d["name"] for d in changes["diagnoses"]] == ["Made-up condition"]


def test_values_before_the_since_date_are_not_new_results(conn, user_id, get):
    today = _today(conn)
    _panel(conn, user_id, today - timedelta(days=90), [("HDL", 1.4, "mmol/L", 1.2, None)])
    changes = get(f"?since={(today - timedelta(days=30)).isoformat()}")["changes"]
    assert changes["results"] == []


def test_a_database_without_a_user_is_an_empty_report(conn, get, monkeypatch):
    monkeypatch.setattr(web.report.q, "user_id", lambda conn: None)
    data = get()
    assert data["empty"] is True and data["approved_values"] == 0


# ------------------------------------------------------------------ the reference change value


def test_rcv_from_the_cited_within_subject_cv():
    # √2 · 1.96 · √(7.4² + 3.7²) = 22.9 %
    assert round(rcv.rcv_percent(7.4), 1) == 22.9
    assert round(rcv.rcv_percent(5.3), 1) == 16.4
    assert round(rcv.rcv_percent(4.6, cva=0), 1) == round(2 ** 0.5 * 1.96 * 4.6, 1)


def test_a_change_is_judged_only_with_a_cited_number():
    assert rcv.compare("ldl", 3.5, 3.8)["significant"] is False      # +8.6 %
    assert rcv.compare("ldl", 3.0, 3.8)["significant"] is True       # +26.7 %
    assert rcv.compare("ldl", 3.8, 3.0)["percent"] == -21.1
    assert rcv.compare("ferritin", 30, 90) is None                   # no cited CVi: no verdict
    assert rcv.compare("ldl", None, 3.8) is None
    assert rcv.compare("ldl", 0, 3.8) is None
    for code, (cvi, source) in rcv.WITHIN_SUBJECT_CV.items():
        assert 0 < cvi < 50 and "EFLM" in source, code
