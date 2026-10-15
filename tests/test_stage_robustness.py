"""stage_panel survives values as printed and malformed rows (found by e2e probing over MCP)."""
from datetime import date, timedelta

import pytest

from core.services import _lab_number, stage_panel


@pytest.mark.parametrize("raw, num", [
    ("6,4", 6.4), (" 5.4 ", 5.4), ("−3", -3.0), ("1 200", 1200.0), (7, 7.0),
    ("<0.5", None), ("negative", None), ("", None), (None, None), (True, None),
])
def test_lab_number(raw, num):
    assert _lab_number(raw) == num


def _by_name(out):
    return {r["raw_name"]: r for r in out["rows"]}


def test_printed_strings_no_longer_lose_the_panel(conn, user_id):
    alerts = []
    out = stage_panel(conn, user_id, "2026-10-01", [
        {"raw_name": "Калій", "value": "6,4", "unit": "ммоль/л"},       # crashed the call before
        {"raw_name": "Glucose", "value": "5.4", "unit": "mmol/L", "ref_min": "3,9", "ref_max": "5,5"},
        {"raw_name": "CRP", "value": "<0.5", "unit": "mg/L"},
        {"raw_name": "HIV", "value": "negative"},
    ], alerter=lambda *a: alerts.append(a))
    rows = _by_name(out)
    assert all(r["stored"] for r in rows.values()), rows
    assert rows["Калій"]["critical"] and rows["Калій"]["canonical"] == 6.4 and alerts
    assert rows["Glucose"]["value"] == 5.4 and rows["Glucose"]["status"] == "normal"
    assert rows["CRP"]["value_text"] == "<0.5" and "stored as text" in rows["CRP"]["note"]
    assert rows["HIV"]["value_text"] == "negative"


def test_a_bad_row_is_reported_and_the_rest_is_kept(conn, user_id):
    out = stage_panel(conn, user_id, "2026-10-02", [
        {"raw_name": "", "value": 1, "unit": "mmol/L"},
        {"raw_name": "Ferritin", "value": None, "unit": "ng/mL"},
        {"raw_name": "LDL", "value": 3.1, "unit": "mmol/L"},
        {"raw_name": "ЛПНЩ", "value": 3.2, "unit": "mmol/L"},
    ], alerter=lambda *a: None)
    notes = [(r["raw_name"], r["stored"], r["note"]) for r in out["rows"]]
    assert notes[0] == (None, False, "no marker name — not stored")
    # used to say "same marker already in this panel" — it was the has-a-value check
    assert notes[1] == ("Ferritin", False, "no value — not stored")
    assert notes[2][1] is True
    assert notes[3][1] is False and notes[3][2].startswith("same marker already in this panel")


@pytest.mark.parametrize("panel_date, error", [
    ("not-a-date", "YYYY-MM-DD"),
    ("2099-01-01", "in the future"),
    ((date.today() + timedelta(days=5)).isoformat(), "in the future"),
])
def test_panel_date_is_checked_before_anything_is_stored(conn, user_id, panel_date, error):
    out = stage_panel(conn, user_id, panel_date, [{"raw_name": "LDL", "value": 3, "unit": "mmol/L"}],
                      alerter=lambda *a: None)
    assert error in out["error"] and "source_id" not in out


def test_tomorrow_is_allowed_for_time_zones(conn, user_id):
    out = stage_panel(conn, user_id, date.today() + timedelta(days=1),
                      [{"raw_name": "LDL", "value": 3, "unit": "mmol/L"}], alerter=lambda *a: None)
    assert "error" not in out and out["rows"][0]["stored"]
