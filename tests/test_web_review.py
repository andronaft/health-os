"""GET /api/v1/review (#58): every value awaiting review, by staging, flagged like the summary flags
it, and nothing approved. The endpoint runs on the test's own connection, so everything stays in its
rolled-back transaction. Made-up values and the fictional demo patient only."""
import contextlib
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

import web.app
from core.health_summary import read_facts
from core.services import approve_staged, ingest_observation, stage_panel
from seed.demo import load_demo

HEADERS = {"X-Health-OS-Token": "t"}


@pytest.fixture()
def get(conn, monkeypatch):
    @contextlib.contextmanager
    def on_the_test_connection():
        yield conn

    monkeypatch.setattr(web.app, "read_only_snapshot", on_the_test_connection)
    client = TestClient(web.app.create_app("t"), base_url="http://127.0.0.1:8765")

    def fetch(query=""):
        r = client.get(f"/api/v1/review{query}", headers=HEADERS)
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"
        return r.json()

    return fetch


def _yesterday() -> date:
    return date.today() - timedelta(days=1)


def test_the_demo_patients_pending_panel_is_listed_as_one_staging(conn, get):
    load_demo(conn, today=date.today())
    data = get()
    assert data["total"] == 2 and data["alarming"] == 0 and data["unmapped"] == 0
    [source] = data["sources"]
    assert source["facility"] == "Demo Lab" and source["channel"] == "mcp"
    assert source["panel_date"] == (date.today() - timedelta(days=3)).isoformat()
    by_code = {r["code"]: r for r in source["rows"]}
    assert set(by_code) == {"vitamin_d", "ferritin"}
    vitamin_d = by_code["vitamin_d"]
    assert vitamin_d["value"] == 27 and vitamin_d["unit"] == "ng/mL"
    assert vitamin_d["ref_min"] == 30 and vitamin_d["ref_max"] == 100
    assert vitamin_d["name"] and vitamin_d["name"] != "vitamin_d"  # its name, not its code
    assert vitamin_d["critical"] is False and vitamin_d["unmapped"] is False


def test_it_lists_what_the_summary_counts_as_awaiting_review(conn, get):
    uid = load_demo(conn, today=date.today())
    ingest_observation(conn, uid, "Sample marker XYZ", 1.5, "u",
                       effective_at=datetime.now(UTC) - timedelta(days=1), review_status="pending")
    data = get()
    assert data["total"] == len(read_facts(conn, uid)["pending"]) == 3
    assert sum(s["total"] for s in data["sources"]) == 3


def test_approved_values_are_not_in_the_queue(conn, user_id, get):
    staged = stage_panel(conn, user_id, _yesterday(),
                         [{"raw_name": "HDL", "value": 1.3, "unit": "mmol/L"}])
    assert get()["total"] == 1
    approve_staged(conn, user_id, staged["source_id"])
    assert get() == {"total": 0, "alarming": 0, "unmapped": 0, "sources": []}


def test_each_staging_is_its_own_group_with_its_id(conn, user_id, get):
    first = stage_panel(conn, user_id, _yesterday(),
                        [{"raw_name": "HDL", "value": 1.3, "unit": "mmol/L"}], facility="Lab A")
    second = stage_panel(conn, user_id, _yesterday() - timedelta(days=7),
                         [{"raw_name": "LDL", "value": 2.9, "unit": "mmol/L"},
                          {"raw_name": "Glucose", "value": 5.0, "unit": "mmol/L"}],
                         facility="Lab B")
    data = get()
    assert data["total"] == 3
    ids = {s["source_id"]: s for s in data["sources"]}
    assert set(ids) == {str(first["source_id"]), str(second["source_id"])}
    assert ids[str(first["source_id"])]["facility"] == "Lab A"
    assert ids[str(second["source_id"])]["total"] == 2


def test_values_that_cannot_wait_come_first_and_are_counted(conn, user_id, get):
    stage_panel(conn, user_id, _yesterday(), [
        {"raw_name": "HDL", "value": 1.3, "unit": "mmol/L"},
        {"raw_name": "Potassium", "value": 6.9, "unit": "mmol/L", "ref_min": 3.5, "ref_max": 5.1},
        {"raw_name": "Sample marker XYZ", "value": 2, "unit": "u"},
    ])
    data = get()
    assert data["alarming"] == 1 and data["unmapped"] == 1
    [source] = data["sources"]
    assert source["alarming"] == 1 and source["unmapped"] == 1
    first, second, third = source["rows"]
    assert first["code"] == "potassium" and first["critical"] is True
    assert second["unmapped"] is True and second["raw_name"] == "Sample marker XYZ"
    assert second["code"] is None and second["name"] == "Sample marker XYZ"
    assert third["code"] == "hdl"


def test_a_limit_is_sent_as_a_limit_and_flagged(conn, user_id, get):
    stage_panel(conn, user_id, _yesterday(),
                [{"raw_name": "Potassium", "value": ">5", "unit": "mmol/L"}])
    [row] = get()["sources"][0]["rows"]
    assert row["comparator"] == ">" and row["value"] == 5
    assert row["limit"] is True and row["unverifiable"] is True and row["critical"] is False


def test_names_follow_the_language(conn, user_id, get):
    stage_panel(conn, user_id, _yesterday(),
                [{"raw_name": "Potassium", "value": 4.2, "unit": "mmol/L"}])
    assert get("?lang=es")["sources"][0]["rows"][0]["name"].startswith("Potasio")
    assert get("?lang=xx")["sources"][0]["rows"][0]["name"].startswith("Potassium")


def test_deleted_values_are_not_listed(conn, user_id, get):
    stage_panel(conn, user_id, _yesterday(), [{"raw_name": "HDL", "value": 1.3, "unit": "mmol/L"}])
    conn.execute(text("UPDATE observations SET deleted_at = now() WHERE user_id = :u"),
                 {"u": user_id})
    assert get()["total"] == 0


def test_no_user_yet_is_an_empty_queue(conn, get):
    assert get() == {"total": 0, "alarming": 0, "unmapped": 0, "sources": []}


def test_the_page_changes_nothing(conn, user_id, get):
    stage_panel(conn, user_id, _yesterday(), [{"raw_name": "HDL", "value": 1.3, "unit": "mmol/L"}])
    statuses = conn.execute(text("SELECT review_status FROM observations")).scalars().all()
    get()
    assert conn.execute(text("SELECT review_status FROM observations")).scalars().all() == statuses
