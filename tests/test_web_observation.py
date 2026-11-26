"""GET /api/v1/observations/{id}: where one value comes from — printed vs canonical, the range and
its source, the review, the notes, the document and the panel. Only the user's own live rows; a
pending value says it is pending. The endpoint runs on the test's own connection, so everything
stays in its rolled-back transaction. Made-up values only."""
import contextlib
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

import web.app
from core import queries as q
from core.services import approve_staged, ingest_observation, stage_panel

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
    def fetch(path, status=200):
        r = client.get(f"/api/v1/{path}", headers=HEADERS)
        assert r.status_code == status, r.text
        assert r.headers["cache-control"] == "no-store"
        return r.json()

    return fetch


def _panel(conn, uid, rows, *, days_ago=10, approve=True, facility="Test Lab"):
    staged = stage_panel(conn, uid, date.today() - timedelta(days=days_ago), rows,
                         panel_type="Biochemistry", facility=facility)
    if approve:
        approve_staged(conn, uid, staged["source_id"], allow_missing_canonical=True)
    return staged


def _id(conn, panel_id, raw_name):
    return str(conn.execute(text("SELECT id FROM observations WHERE panel_id=:p AND raw_name=:n"),
                            {"p": panel_id, "n": raw_name}).scalar())


ROWS = [
    {"raw_name": "Glucose", "value": 99, "unit": "mg/dL", "ref_min": 70, "ref_max": 100},
    {"raw_name": "ALT", "value": 30, "unit": "U/L", "ref_min": 0, "ref_max": 41},
    {"raw_name": "Ferritin", "value": 600, "comparator": ">", "unit": "ng/mL",
     "ref_min": 30, "ref_max": 400},
]


def test_an_approved_value_with_its_conversion_range_review_and_panel(conn, user_id, get):
    staged = _panel(conn, user_id, ROWS)
    oid = _id(conn, staged["panel_id"], "Glucose")
    data = get(f"observations/{oid}")
    assert data["id"] == oid and data["code"] == "glucose" and data["pending"] is False
    assert data["raw_name"] == "Glucose"
    assert data["printed"] == {"value": 99, "comparator": None, "text": None, "unit": "mg/dL"}
    conv = data["canonical"]
    assert conv["state"] == "converted" and conv["unit"] == "mmol/L"
    assert conv["factor"] and conv["value"] == pytest.approx(99 * conv["factor"], rel=1e-6)
    # the form's range, in the form's unit, and the same range in the canonical one
    assert data["range"]["source"] == "form"
    assert (data["range"]["min"], data["range"]["max"], data["range"]["unit"]) == (70, 100, "mg/dL")
    assert data["range"]["canonical"]["max"] == pytest.approx(100 * conv["factor"], rel=1e-4)
    assert data["range"]["defaults"] == []  # the form has one: no catalog hint
    assert data["review"]["status"] == "approved" and data["review"]["channel"] == "mcp"
    assert data["review"]["reviewed_by"] == "human" and data["review"]["reviewed_at"]
    assert data["panel"]["facility"] == "Test Lab" and data["panel"]["type"] == "Biochemistry"
    assert data["panel"]["rows_in_document"] == 3
    others = {o["code"]: o for o in data["panel"]["others"]}
    assert set(others) == {"alt", "ferritin"}  # not itself
    assert others["alt"]["value"] == 30 and others["alt"]["pending"] is False
    assert data["document"] is None  # a staged panel with no document stored


def test_a_pending_value_says_so_and_has_no_review_date(conn, user_id, get):
    first = _panel(conn, user_id, ROWS[:1], days_ago=40)
    staged = _panel(conn, user_id, ROWS[1:2], approve=False)
    oid = _id(conn, staged["panel_id"], "ALT")
    # another source of the same user was approved: its date must not pass for this value's
    assert get(f"observations/{_id(conn, first['panel_id'], 'Glucose')}")["review"]["reviewed_at"]
    data = get(f"observations/{oid}")
    assert data["pending"] is True and data["review"]["status"] == "pending"
    assert data["review"]["reviewed_at"] is None and data["review"]["reviewed_by"] is None
    assert data["status"] == "normal"  # the form's word, sent; the page says it isn't a fact


def test_a_pending_value_of_a_partly_approved_source_has_no_review_date(conn, user_id, get):
    # an unmapped row stays pending while the source gets reviewed_at
    staged = _panel(conn, user_id, [ROWS[0], {"raw_name": "Zqxwy factor", "value": 3,
                                             "unit": "U/L", "ref_min": 1, "ref_max": 5}])
    data = get(f"observations/{_id(conn, staged['panel_id'], 'Zqxwy factor')}")
    assert data["pending"] is True and data["unmapped"] is True and data["code"] is None
    assert data["name"] == "Zqxwy factor"
    assert data["review"]["reviewed_at"] is None
    assert data["canonical"]["state"] == "not_converted"
    # and the panel lists the approved one next to it
    assert [o["code"] for o in data["panel"]["others"]] == ["glucose"]


def test_a_limit_value_keeps_its_comparator(conn, user_id, get):
    staged = _panel(conn, user_id, ROWS)
    data = get(f"observations/{_id(conn, staged['panel_id'], 'Ferritin')}")
    assert data["printed"]["comparator"] == ">" and data["printed"]["value"] == 600
    assert data["status"] == "high"
    assert data["canonical"]["state"] in {"same_unit", "converted"}


def test_an_unconverted_unit_is_said_plainly(conn, user_id, get):
    res = ingest_observation(conn, user_id, "ALT", 0.5, "ukat/L", ref_min=0.1, ref_max=0.7)
    data = get(f"observations/{res.observation_id}")
    assert data["canonical"]["state"] == "not_converted" and data["canonical"]["value"] is None
    assert data["pending"] is True  # the unit gate keeps it under review
    # the range can't be drawn in U/L either: never guessed
    assert data["range"]["canonical"] == {"min": None, "max": None, "unconverted": True}


def test_no_range_on_the_form_sends_the_catalog_default_as_a_hint(conn, user_id, get):
    conn.execute(text("INSERT INTO user_profile (user_id, date_of_birth, sex) VALUES "
                      "(:u, '1990-01-01', 'female') ON CONFLICT (user_id) DO UPDATE SET sex='female'"),
                 {"u": user_id})
    res = ingest_observation(conn, user_id, "Hemoglobin", 131, "g/L")
    data = get(f"observations/{res.observation_id}")
    assert data["range"]["source"] == "none" and data["range"]["canonical"] is None
    assert data["status"] is None  # no range, no status: a default never made one
    defaults = data["range"]["defaults"]
    assert [(d["sex"], d["min"], d["max"]) for d in defaults] == [("female", 120, 155)]
    assert data["review"]["status"] == "approved" and data["review"]["reviewed_at"] is None


def test_notes_and_the_document_are_sent_as_stored(conn, user_id, get):
    staged = _panel(conn, user_id, ROWS)
    oid = _id(conn, staged["panel_id"], "ALT")
    note = "CRITICAL CHECK IMPOSSIBLE — <b>compare</b> with the form"
    conn.execute(text("UPDATE observations SET notes=:n WHERE id=:id"), {"n": note, "id": oid})
    doc = conn.execute(text(
        "INSERT INTO documents (user_id, document_date, doc_type, title, file_path, file_sha256) "
        "VALUES (:u, :d, 'lab_report', 'Blood test <script>', '/x.pdf', :sha) RETURNING id"),
        {"u": user_id, "d": date(2026, 10, 1), "sha": uuid.uuid4().hex * 2}).scalar()
    conn.execute(text("UPDATE panels SET document_id=:d WHERE id=:p"),
                 {"d": doc, "p": staged["panel_id"]})
    data = get(f"observations/{oid}")
    assert data["notes"] == note  # verbatim: the page puts it in as text
    assert data["document"] == {"title": "Blood test <script>", "date": "2026-10-01",
                                "type": "lab_report"}
    conn.execute(text("UPDATE documents SET deleted_at=now() WHERE id=:d"), {"d": doc})
    assert get(f"observations/{oid}")["document"] is None


def test_a_deleted_row_a_malformed_or_unknown_id_is_404(conn, user_id, get):
    staged = _panel(conn, user_id, ROWS)
    oid = _id(conn, staged["panel_id"], "Glucose")
    conn.execute(text("UPDATE observations SET deleted_at=now() WHERE id=:id"), {"id": oid})
    get(f"observations/{oid}", status=404)
    get("observations/not-a-uuid", status=404)
    get(f"observations/{uuid.uuid4()}", status=404)
    # and a deleted row is no longer among the panel's other values
    alt = get(f"observations/{_id(conn, staged['panel_id'], 'ALT')}")
    assert "glucose" not in {o["code"] for o in alt["panel"]["others"]}


def test_another_users_row_is_404(conn, user_id, get, monkeypatch):
    other = str(conn.execute(text("INSERT INTO users DEFAULT VALUES RETURNING id")).scalar())
    theirs = ingest_observation(conn, other, "Glucose", 5.0, "mmol/L", ref_min=3.9, ref_max=5.6)
    mine = ingest_observation(conn, user_id, "Glucose", 5.1, "mmol/L", ref_min=3.9, ref_max=5.6)
    monkeypatch.setattr(q, "user_id", lambda conn: user_id)
    get(f"observations/{theirs.observation_id}", status=404)
    assert get(f"observations/{mine.observation_id}")["canonical"]["state"] == "same_unit"


def test_the_pages_send_the_ids_the_drawer_opens(conn, user_id, get):
    staged = _panel(conn, user_id, ROWS)
    glucose = _id(conn, staged["panel_id"], "Glucose")
    labs = get("labs")
    marker = next(m for m in labs["markers"] if m["code"] == "glucose")
    assert marker["id"] == glucose
    day = labs["matrix"]["dates"][0]
    row = next(r for r in labs["matrix"]["rows"] if r["code"] == "glucose")
    assert row["cells"][day]["id"] == glucose
    pending = _panel(conn, user_id, [{**ROWS[0], "value": 101}], days_ago=1, approve=False)
    detail = get("labs/glucose")
    assert [p["id"] for p in detail["points"]] == [glucose]
    assert [p["id"] for p in detail["pending"]] == [_id(conn, pending["panel_id"], "Glucose")]
    overview = get("overview")
    assert {r["id"] for r in overview["attention"]["pending"]["rows"]} == {
        _id(conn, pending["panel_id"], "Glucose")}
