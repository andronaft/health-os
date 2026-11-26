"""Values printed as a limit (">600", "<10"): a number with its comparator, checked for critical
values. As text they skipped the critical check and the "check impossible" flag alike, so a
meter's HI glucose or platelets "<10" reached the review queue as an ordinary value."""
from datetime import date

import pytest

from core import queries as q
from core.health_summary import build as build_summary
from core.health_summary import read_facts
from core.normalize import compute_limit_status
from core.services import _lab_limit, approve_staged, map_pending_observation, stage_panel
from safety.critical_values import Threshold, evaluate_limit

K = [Threshold("potassium", "mmol/L", 2.8, 6.0, "msg")]
PLT = [Threshold("platelets", "10*9/L", 30.0, None, "msg")]


@pytest.mark.parametrize("printed, expected", [
    (">600", (">", 600.0)), ("< 10", ("<", 10.0)), ("≤0,5", ("<=", 0.5)), (">= 1.2", (">=", 1.2)),
    ("≥ 5", (">=", 5.0)), ("=<3", ("<=", 3.0)),
    ("negative", None), ("<", None), ("> abc", None), ("5.4", None), ("<<5", None),
])
def test_a_printed_limit_is_read_as_comparator_and_number(printed, expected):
    assert _lab_limit(printed) == expected


def test_a_limit_wholly_in_a_critical_zone_is_critical():
    hit, uncertain = evaluate_limit("potassium", ">", 6.5, "mmol/L", K)
    assert hit and hit.bound == "high" and not uncertain
    hit, uncertain = evaluate_limit("platelets", "<", 10, "10*9/L", PLT)
    assert hit and hit.bound == "low" and not uncertain


def test_a_limit_that_may_or_may_not_be_critical_is_a_check_impossible():
    # ">5" potassium may be 5.1 or 7; "<50" platelets may be 45 or 10
    assert evaluate_limit("potassium", ">", 5.0, "mmol/L", K) == (None, True)
    assert evaluate_limit("platelets", "<", 50, "10*9/L", PLT) == (None, True)
    # ">2" potassium: may be 2.5 (critical low) or 7 (critical high)
    assert evaluate_limit("potassium", ">", 2.0, "mmol/L", K) == (None, True)


def test_a_limit_that_cannot_reach_a_critical_zone_is_fine():
    # platelets have no high threshold: ">450" can't be critical
    assert evaluate_limit("platelets", ">", 450, "10*9/L", PLT) == (None, False)
    assert evaluate_limit("crp", "<", 0.5, "mg/L", K) == (None, False)  # no thresholds


@pytest.mark.parametrize("comparator, value, low, high, expected", [
    (">", 600, 70, 100, "high"),
    ("<", 10, 150, 400, "low"),
    ("<", 0.5, 0, 5, "normal"),      # "0–5": nothing below 0
    ("<", 0.5, None, 5, "normal"),
    (">", 2, 0, 5, None),            # in range or high: not a guess
    ("<", 160, 150, 400, None),      # low or in range
    (">", 1.5, 1.2, None, "normal"),
    (">", 500, 30, 500, "high"),     # past the top: above it
    (">=", 500, 30, 500, None),      # may be exactly 500, in range
    (">=", 501, 30, 500, "high"),
    ("<", 150, 150, 400, "low"),
    ("<=", 150, 150, 400, None),     # may be exactly 150, in range
    ("<=", 149, 150, 400, "low"),
    (None, 3.0, 1, 5, "normal"),
])
def test_a_limit_has_a_status_only_when_the_limit_decides_it(comparator, value, low, high, expected):
    assert compute_limit_status(comparator, value, low, high) == expected


def test_a_meters_hi_glucose_and_platelets_below_ten_are_critical(conn, user_id):
    alerts = []
    out = stage_panel(conn, user_id, date(2026, 11, 10), [
        {"raw_name": "Glucose", "value": ">600", "unit": "mg/dL", "ref_min": 70, "ref_max": 100},
        {"raw_name": "Platelets", "value": "<10", "unit": "10^9/L", "ref_min": 150, "ref_max": 400},
    ], alerter=lambda title, message: alerts.append(message))
    glucose, platelets = out["rows"]
    assert glucose["critical"] and glucose["comparator"] == ">" and glucose["value"] == 600
    assert glucose["status"] == "critical"
    assert platelets["critical"] and platelets["comparator"] == "<"
    assert len(alerts) == 2
    summary = build_summary(conn, user_id).text
    assert "glucose >600" in summary and "platelets <10" in summary
    assert summary.count("CRITICAL value") == 2


def test_a_limit_that_may_be_critical_is_flagged_everywhere(conn, user_id):
    alerts = []
    out = stage_panel(conn, user_id, date(2026, 11, 10),
                      [{"raw_name": "Potassium", "value": ">5", "unit": "mmol/L"}],
                      alerter=lambda title, message: alerts.append(message))
    [row] = out["rows"]
    assert not row["critical"] and row["critical_unverified"]
    assert "only a limit" in row["note"] and alerts
    [pending] = read_facts(conn, user_id)["pending"]
    assert pending["unverifiable"] and pending["limit_only"]
    summary = build_summary(conn, user_id).text
    assert "potassium >5" in summary and "only a limit on the form" in summary


def test_a_text_result_without_a_limit_stays_text(conn, user_id):
    out = stage_panel(conn, user_id, date(2026, 11, 10),
                      [{"raw_name": "Potassium", "value": "hemolysed", "unit": "mmol/L"}])
    [row] = out["rows"]
    assert row["value"] is None and row["value_text"] == "hemolysed" and "comparator" not in row


def test_a_limit_stays_out_of_the_trend(conn, user_id):
    for i, value in enumerate(["4.0", "4.2", "4.4", "4.6", "4.8", ">600"]):
        staged = stage_panel(conn, user_id, date(2020 + i, 1, 1),
                             [{"raw_name": "Glucose", "value": value, "unit": "mmol/L"}])
        approve_staged(conn, user_id, staged["source_id"])
    trend = q.trend(conn, user_id, "glucose", days=3650)
    assert trend["n"] == 5  # ">600" is not a value to fit a slope through


def test_remapping_a_limit_checks_it_as_a_limit(conn, user_id):
    out = stage_panel(conn, user_id, date(2026, 11, 10),
                      [{"raw_name": "Some unknown sugar", "value": ">600", "unit": "mg/dL"}])
    [row] = out["rows"]
    assert row["matched"] is None
    res = map_pending_observation(conn, user_id, row["observation_id"], "glucose")
    assert res["critical"]
