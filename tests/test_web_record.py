"""GET /api/v1/timeline, /medications, /diagnoses, /habits (#57): the medical record as recorded.
The endpoints run on the test's own connection, so everything stays in its rolled-back transaction.
Made-up values and the fictional demo patient only."""
import contextlib
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

import web.app
from core.services import (
    add_diagnosis,
    add_habit,
    add_medication,
    approve_staged,
    stage_panel,
    stop_medication,
)
from seed.demo import load_demo
from web.record import needs_review, paracetamol

HEADERS = {"X-Health-OS-Token": "t"}
TODAY = date.today()


@pytest.fixture()
def get(conn, monkeypatch):
    @contextlib.contextmanager
    def on_the_test_connection():
        yield conn

    monkeypatch.setattr(web.app, "read_only_snapshot", on_the_test_connection)
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")

    def fetch(page, query=""):
        r = client.get(f"/api/v1/{page}{query}", headers=HEADERS)
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        return r.json()

    return fetch


def _ago(days: int) -> date:
    return TODAY - timedelta(days=days)


# ------------------------------------------------------------------------------------- timeline

def test_the_demo_timeline_shows_every_event_kind_and_a_medication_period(conn, get):
    """The issue's "done when": every event kind, and medications as start → stop periods."""
    load_demo(conn, today=TODAY)
    data = get("timeline")
    assert data["today"] == TODAY.isoformat() and data["born"] == "1985-04-12"
    kinds = {e["kind"] for e in data["events"]}
    assert kinds == {"diagnosis", "visit", "procedure", "hospital", "panel", "vaccination",
                     "document"}
    # medication starts and stops are periods, not points
    assert not {"medication_start", "medication_stop"} & kinds
    meds = {p["title"]: p for p in data["periods"] if p["kind"] == "medication"}
    iron = meds["Ferrous sulfate"]
    assert iron["end"] and iron["start"] < iron["end"] and iron["ongoing"] is False
    assert iron["status"] == "stopped" and iron["stop_reason"] == "course completed"
    assert iron["detail"] == "200 mg × 1/day, oral"
    assert meds["Vitamin D3"]["end"] is None and meds["Vitamin D3"]["ongoing"] is True
    habits = {p["title"]: p for p in data["periods"] if p["kind"] == "habit"}
    assert habits["smoking"]["end"] and habits["alcohol"]["ongoing"] is True
    assert data["undated_habits"] == 0
    # oldest first, each in its lane
    dates = [e["date"] for e in data["events"]]
    assert dates == sorted(dates)
    assert {e["lane"] for e in data["events"]} == {"diagnoses", "care", "labs", "vaccinations",
                                                  "documents"}


def test_a_panel_under_review_says_so_and_links_only_to_approved_markers(conn, get):
    load_demo(conn, today=TODAY)
    panels = [e for e in get("timeline")["events"] if e["kind"] == "panel"]
    pending = [p for p in panels if p["pending"]]
    assert len(pending) == 1  # the demo's unapproved panel
    assert pending[0]["values"] == 2 and pending[0]["markers"] == []
    assert pending[0]["facility"] == "Demo Lab"
    latest = max((p for p in panels if not p["pending"]), key=lambda p: p["date"])
    codes = {m["code"] for m in latest["markers"]}
    assert "ldl" in codes and latest["out_of_range"] >= 1  # LDL 3.8 against ≤ 3.0
    ldl = next(m for m in latest["markers"] if m["code"] == "ldl")
    assert ldl["name"] == "LDL cholesterol"


def test_a_diagnosis_on_the_timeline_carries_its_code_and_certainty(conn, get):
    load_demo(conn, today=TODAY)
    events = {e["title"]: e for e in get("timeline")["events"] if e["kind"] == "diagnosis"}
    assert events["Hypothyroidism"]["verification"] == "refuted"
    assert events["Hypercholesterolemia"] == {**events["Hypercholesterolemia"], "icd10": "E78.0",
                                              "verification": "suspected", "clinical": "active"}


def test_deleted_records_are_not_on_the_timeline(conn, user_id, get):
    med = add_medication(conn, user_id, "Sample med", start_date=_ago(100))
    staged = stage_panel(conn, user_id, _ago(5), [{"raw_name": "HDL", "value": 1.3,
                                                     "unit": "mmol/L"}])
    approve_staged(conn, user_id, staged["source_id"])
    data = get("timeline")
    assert [p["title"] for p in data["periods"]] == ["Sample med"]
    assert [e["kind"] for e in data["events"]] == ["panel"]
    conn.execute(text("UPDATE medications SET deleted_at = now() WHERE id = :id"), {"id": med})
    conn.execute(text("UPDATE observations SET deleted_at = now() WHERE source_id = :s"),
                 {"s": staged["source_id"]})
    data = get("timeline")
    assert data["periods"] == [] and data["events"] == []


def test_a_habit_without_a_start_date_is_counted_not_placed(conn, user_id, get):
    assert "error" not in add_habit(conn, user_id, "smoking", status="current")
    assert "error" not in add_habit(conn, user_id, "alcohol", status="never")
    data = get("timeline")
    assert data["periods"] == [] and data["undated_habits"] == 1  # "never" is no period at all


def test_no_user_yet_is_an_empty_record(conn, get):
    if conn.execute(text("SELECT count(*) FROM users")).scalar():
        pytest.skip("the test database already has a user")
    assert get("timeline")["events"] == []
    assert get("medications")["current"] == []
    assert get("diagnoses")["groups"] == []
    assert get("habits")["habits"] == []


def test_the_record_routes_need_the_token(conn, get):
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")
    for page in ("timeline", "medications", "diagnoses", "habits"):
        assert client.get(f"/api/v1/{page}").status_code == 403


# ---------------------------------------------------------------------------------- medications

def test_medications_split_current_and_past_with_allergies_first(conn, get):
    load_demo(conn, today=TODAY)
    data = get("medications")
    assert [a["allergen"] for a in data["allergies"]] == ["penicillin"]
    assert data["allergies"][0]["verified"] is True
    assert {m["name"] for m in data["current"]} == {"Vitamin D3", "Cetirizine", "Paracetamol"}
    [iron] = data["past"]
    assert iron["name"] == "Ferrous sulfate" and iron["route"] == "oral"
    assert iron["stop_reason"] == "course completed" and iron["prescribed_for"]
    assert iron["days"] == (date.fromisoformat(iron["end_date"])
                            - date.fromisoformat(iron["start_date"])).days
    cetirizine = next(m for m in data["current"] if m["name"] == "Cetirizine")
    assert cetirizine["days"] == (TODAY - date.fromisoformat(cetirizine["start_date"])).days
    assert cetirizine["dose_amount"] == 10 and cetirizine["times_per_day"] == 1


def test_the_recorded_paracetamol_is_summed_from_current_medications_only(conn, get):
    load_demo(conn, today=TODAY)
    p = get("medications")["paracetamol"]
    assert p["products"] == ["Paracetamol"] and p["mg_per_day"] == 1000
    assert p["missing_dose"] == [] and p["over_limit"] is False and p["limit_mg"] == 4000


def test_a_stopped_paracetamol_is_not_counted(conn, user_id, get):
    med = add_medication(conn, user_id, "Paracetamol", start_date=_ago(30), dose_amount=1000,
                         dose_unit="mg", times_per_day=4)
    assert get("medications")["paracetamol"]["mg_per_day"] == 4000
    assert "error" not in stop_medication(conn, user_id, med, end_date=_ago(1))
    assert get("medications")["paracetamol"] is None


def test_paracetamol_sum_names_what_it_cannot_count():
    def med(name, dose=None, unit="mg", times=None, atc=None):
        return {"name": name, "dose_amount": dose, "dose_unit": unit, "times_per_day": times,
                "atc_code": atc}

    assert paracetamol([med("Vitamin D3", 2000, "IU", 1)]) is None
    out = paracetamol([med("Panadol", 1000, "mg", 3), med("Cold remedy", atc="N02BE51"),
                       med("Paracetamol syrup", 5, "ml", 4), med("Paracetamol", 1000, "MG", 2)])
    assert out["mg_per_day"] == 5000 and out["over_limit"] is True
    assert out["missing_dose"] == ["Cold remedy", "Paracetamol syrup"]  # never counted as 0
    assert paracetamol([med("Paracetamol")])["mg_per_day"] is None


# ------------------------------------------------------------------------------------ diagnoses

def test_diagnoses_are_grouped_by_certainty_in_a_fixed_order(conn, get):
    load_demo(conn, today=TODAY)
    data = get("diagnoses")
    assert [g["verification"] for g in data["groups"]] == ["confirmed", "provisional",
                                                           "suspected", "refuted"]
    by_name = {d["name"]: d for g in data["groups"] for d in g["rows"]}
    assert by_name["Allergic rhinitis due to pollen"]["icd10_code"] == "J30.1"
    # active, confirmed and 9 years without a change: the one hint
    assert [n for n, d in by_name.items() if d["review_hint"]] == [
        "Allergic rhinitis due to pollen"]
    assert data["review_after_days"] == 730


def test_the_review_hint_needs_active_believed_and_two_quiet_years(conn, user_id, get):
    old = _ago(800)
    add_diagnosis(conn, user_id, "Sample active", diagnosed_at=old)
    add_diagnosis(conn, user_id, "Sample recent", diagnosed_at=_ago(100))
    add_diagnosis(conn, user_id, "Sample resolved", diagnosed_at=old, clinical_status="resolved")
    add_diagnosis(conn, user_id, "Sample refuted", diagnosed_at=old,
                  verification_status="refuted")
    add_diagnosis(conn, user_id, "Sample suspected", diagnosed_at=old,
                  verification_status="suspected")
    rows = {d["name"]: d for g in get("diagnoses")["groups"] for d in g["rows"]}
    assert {n for n, d in rows.items() if d["review_hint"]} == {"Sample active",
                                                                "Sample suspected"}


def test_needs_review_at_the_edge():
    d = {"clinical_status": "relapse", "verification_status": None, "resolved_at": None,
         "diagnosed_at": TODAY - timedelta(days=730)}
    assert needs_review(d, TODAY)
    assert not needs_review({**d, "diagnosed_at": TODAY - timedelta(days=729)}, TODAY)
    assert not needs_review({**d, "resolved_at": TODAY}, TODAY)


# --------------------------------------------------------------------------------------- habits

def test_habits_say_how_long_they_ran_and_how_long_ago_they_ended(conn, get):
    load_demo(conn, today=TODAY)
    data = get("habits")
    by_type = {h["habit_type"]: h for h in data["habits"]}
    assert [h["status"] for h in data["habits"]][:2] == ["current", "current"]  # current first
    smoking = by_type["smoking"]
    start, end = date.fromisoformat(smoking["start_date"]), date.fromisoformat(smoking["end_date"])
    assert smoking["days"] == (end - start).days
    assert smoking["days_since_end"] == (TODAY - end).days
    assert smoking["cigarettes_per_day"] == 8
    running = by_type["running"]
    assert running["days"] == (TODAY - date.fromisoformat(running["start_date"])).days
    assert running["days_since_end"] is None and running["frequency"] == "3 times a week"
    assert by_type["alcohol"]["drinks_per_week"] == 3
