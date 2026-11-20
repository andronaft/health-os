"""Paths where a critical value used to lose its flag (clinical-safety audit, 2026-11-18): recompute
filled a canonical value without the critical check, "G/L" read as grams, approval silenced a
limit, approving twice reported success, and the pending view dropped the comparator.
Made-up values only."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from alembic import command
from sqlalchemy import text

from analytics.weekly_report import build as weekly
from core import queries as q
from core.health_summary import build as summary
from core.health_summary import is_alarming, read_facts
from core.normalize import canonicalize_unit, units_incompatible
from core.recompute import recompute_canonical
from core.services import approve_staged, manual_source, stage_panel
from tests import test_names_per_language as _migrations

scratch_db = _migrations.scratch_db


def _obs(conn, oid):
    return conn.execute(text("SELECT * FROM observations WHERE id=:i"), {"i": oid}).mappings().one()


# ---- recompute runs the critical check ---------------------------------------------------------

def _drop_conversion(conn, code, from_unit):
    conv = conn.execute(text(
        """SELECT uc.* FROM unit_conversions uc JOIN observation_types ot ON ot.id = uc.type_id
           WHERE ot.code=:c AND uc.from_unit=:f"""), {"c": code, "f": from_unit}).mappings().one()
    conn.execute(text("DELETE FROM unit_conversions WHERE id=:i"), {"i": conv["id"]})
    return conv


def _restore_conversion(conn, conv):
    conn.execute(text("""INSERT INTO unit_conversions (type_id, from_unit, to_unit, factor, add_offset)
                         VALUES (:t, :f, :to, :fa, :o)"""),
                 {"t": conv["type_id"], "f": conv["from_unit"], "to": conv["to_unit"],
                  "fa": conv["factor"], "o": conv["add_offset"]})


def test_recompute_flags_a_pending_value_it_fills_as_critical(conn, user_id):
    conv = _drop_conversion(conn, "potassium", "mEq/L")
    out = stage_panel(conn, user_id, date.today(),
                      [{"raw_name": "Potassium", "value": 6.9, "unit": "mEq/L"}])
    assert out["rows"][0]["critical_unverified"] is True
    _restore_conversion(conn, conv)  # the conversion arrives later (a seed update)

    alerts = []
    dry = recompute_canonical(conn, user_id=user_id, alerter=lambda t, m: alerts.append(m))
    assert dry.n_fixed == 1 and len(dry.critical) == 1 and alerts == []  # dry run: no alert

    rep = recompute_canonical(conn, apply=True, user_id=user_id,
                              alerter=lambda t, m: alerts.append(m))
    assert rep.n_fixed == 1 and len(rep.critical) == 1 and rep.n_returned_to_review == 0
    assert len(alerts) == 1 and "potassium" in alerts[0]
    [p] = read_facts(conn, user_id)["pending"]
    assert p["status"] == "critical" and is_alarming(p)
    assert "CRITICAL value" in summary(conn, user_id).text
    assert weekly(conn, user_id)["stable"] is False


def _raw_insert(conn, user_id, code, value, unit):
    """What a custom importer does: an approved row without normalization or a critical check."""
    sid = manual_source(conn, user_id, channel="custom_import")
    return str(conn.execute(text(
        """INSERT INTO observations (user_id, type_id, effective_at, value_numeric, unit,
                                     review_status, source_id)
           SELECT :u, id, now(), :v, :unit, 'approved', :s FROM observation_types WHERE code=:c
           RETURNING id"""), {"u": user_id, "v": value, "unit": unit, "s": sid, "c": code}).scalar())


def test_recompute_returns_an_approved_critical_value_to_review(conn, user_id):
    critical = _raw_insert(conn, user_id, "potassium", 7.0, "mmol/L")
    normal = _raw_insert(conn, user_id, "potassium", 4.2, "mmol/L")
    rep = recompute_canonical(conn, apply=True, user_id=user_id)
    assert rep.n_fixed == 2 and rep.n_returned_to_review == 1

    row = _obs(conn, critical)
    assert row["status"] == "critical" and row["review_status"] == "pending"
    assert "returned to review by recompute" in row["notes"]
    assert _obs(conn, normal)["review_status"] == "approved"
    assert "CRITICAL value" in summary(conn, user_id).text

    # approving it again is the user's explicit acknowledgement
    res = approve_staged(conn, user_id, str(row["source_id"]))
    assert res["approved_observations"] == 1
    assert _obs(conn, critical)["status"] == "critical"


# ---- "G/L" is giga per litre for a count -------------------------------------------------------

def test_giga_and_tera_per_litre_are_counts():
    assert canonicalize_unit("G/L") == "10*9/L" and canonicalize_unit("G/l") == "10*9/L"
    assert canonicalize_unit("T/L") == "10*12/L"
    assert canonicalize_unit("g/L") == "g/L" and canonicalize_unit("g/l") == "g/L"
    # an all-caps form's haemoglobin "G/L" can only mean grams
    assert canonicalize_unit("G/L", "g/L") == "g/L"
    assert canonicalize_unit("G/L", "10*9/L") == "10*9/L"
    assert not units_incompatible("G/L", "10*9/L") and not units_incompatible("G/L", "g/L")


def test_platelets_in_giga_per_litre_are_checked(conn, user_id):
    alerts = []
    out = stage_panel(conn, user_id, date.today(), [
        {"raw_name": "Platelets", "value": 25, "unit": "G/L"},
        {"raw_name": "Hemoglobin", "value": 145, "unit": "G/L"},
    ], alerter=lambda t, m: alerts.append(m))
    plt, hb = out["rows"]
    assert plt["matched"] == "platelets" and plt["critical"] is True and plt["canonical"] == 25
    assert hb["matched"] == "hemoglobin" and hb["canonical"] == 145 and not hb["critical"]
    assert len(alerts) == 1 and "platelets" in alerts[0]


def test_a_watched_analyte_in_a_foreign_unit_is_not_silent(conn, user_id):
    alerts = []
    out = stage_panel(conn, user_id, date.today(),
                      [{"raw_name": "Potassium", "value": 6.9, "unit": "%"}],
                      alerter=lambda t, m: alerts.append(m))
    [row] = out["rows"]
    assert row["matched"] is None and row["rejected_match"] == "potassium"
    assert row["critical_unverified"] is True and "CRITICAL CHECK IMPOSSIBLE" in row["note"]
    assert out["counts"]["critical_unverified"] == 1
    assert len(alerts) == 1 and "critical check impossible" in alerts[0]


# ---- approving a limit keeps it flagged --------------------------------------------------------

def _stage_limit_potassium(conn, user_id):
    return stage_panel(conn, user_id, date.today(),
                       [{"raw_name": "Potassium", "value": ">5", "unit": "mmol/L",
                         "ref_min": 3.5, "ref_max": 5.1}])


def test_approving_a_limit_value_keeps_the_impossible_check_visible(conn, user_id):
    out = _stage_limit_potassium(conn, user_id)
    assert out["rows"][0]["critical_unverified"] is True
    res = approve_staged(conn, user_id, out["source_id"])
    assert res["approved_observations"] == 1
    [u] = res["unverifiable_approved"]
    assert u["code"] == "potassium" and u["comparator"] == ">" and u["value"] == 5.0
    assert "could NOT be checked" in res["warning"]

    rep = weekly(conn, user_id)
    assert [u["code"] for u in rep["unverifiable_approved"]] == ["potassium"]
    assert rep["stable"] is False
    assert "unverifiable_approved" in rep["system_health"]["note"]

    text_out = summary(conn, user_id).text
    assert "Approved, critical check impossible (1)" in text_out
    assert "potassium >5 mmol/L" in text_out and "only a limit on the form" in text_out


def test_approving_an_exact_normal_value_adds_no_warning(conn, user_id):
    out = stage_panel(conn, user_id, date.today(),
                      [{"raw_name": "Potassium", "value": 4.2, "unit": "mmol/L"}])
    res = approve_staged(conn, user_id, out["source_id"])
    assert res["approved_observations"] == 1
    assert "unverifiable_approved" not in res and "warning" not in res
    assert weekly(conn, user_id)["unverifiable_approved"] == []


# ---- approval that does nothing is an error ----------------------------------------------------

def test_approving_twice_is_an_error(conn, user_id):
    out = stage_panel(conn, user_id, date.today(),
                      [{"raw_name": "Potassium", "value": 4.2, "unit": "mmol/L"}])
    assert approve_staged(conn, user_id, out["source_id"])["approved_observations"] == 1
    again = approve_staged(conn, user_id, out["source_id"])
    assert "nothing to approve" in again["error"] and "approved_observations" not in again


def test_approving_a_source_that_was_never_staged_is_an_error(conn, user_id):
    sid = manual_source(conn, user_id)
    assert "nothing to approve" in approve_staged(conn, user_id, sid)["error"]
    assert approve_staged(conn, user_id, "not-a-uuid")["error"] == "source not found"


def test_approving_only_unmapped_rows_is_an_error_that_lists_them(conn, user_id):
    out = stage_panel(conn, user_id, date.today(),
                      [{"raw_name": "Marcador desconocido", "value_text": "negativo"}])
    res = approve_staged(conn, user_id, out["source_id"])
    assert "only unmapped rows" in res["error"]
    assert res["left_pending_unmapped"][0]["raw_name"] == "Marcador desconocido"


# ---- the pending view keeps the comparator -----------------------------------------------------

def test_pending_view_shows_a_limit_as_a_limit(conn, user_id):
    _stage_limit_potassium(conn, user_id)
    [row] = q.view_rows(conn, user_id, "pending")["rows"]  # = list_pending_reviews
    assert row["comparator"] == ">" and float(row["value_numeric"]) == 5.0
    assert "notes" in row


def _columns(c, relation):
    return list(c.execute(text("""SELECT column_name FROM information_schema.columns
                                  WHERE table_name=:r ORDER BY ordinal_position"""),
                          {"r": relation}).scalars())


@pytest.mark.integration
def test_migration_0016_appends_comparator_and_reverts(scratch_db):
    cfg = _migrations._alembic()
    command.upgrade(cfg, "0015")
    with scratch_db.begin() as c:
        before = _columns(c, "v_observations_pending")
    command.upgrade(cfg, "0016")
    with scratch_db.begin() as c:
        assert _columns(c, "v_observations_pending") == [*before, "comparator", "notes"]
        assert c.execute(text("SELECT has_table_privilege('health_readonly', "
                              "'v_observations_pending', 'SELECT')")).scalar()
    command.downgrade(cfg, "0015")
    with scratch_db.begin() as c:
        assert _columns(c, "v_observations_pending") == before
        assert c.execute(text("SELECT has_table_privilege('health_readonly', "
                              "'v_observations_pending', 'SELECT')")).scalar()


# ---- review fixes ------------------------------------------------------------------------------

def test_a_watched_marker_in_a_foreign_unit_stays_alarming_after_staging(conn, user_id):
    """Potassium 7.0 "%" goes in unmapped; the "critical check impossible" flag must outlive the
    staging response: the summary and the weekly report keep it alarming."""
    stage_panel(conn, user_id, date.today(),
                [{"raw_name": "Potassium", "value": 7.0, "unit": "%"}], alerter=lambda *a: None)
    report = weekly(conn, user_id)
    assert report["stable"] is False
    assert [a["code"] for a in report["alarming_pending"]] == ["Potassium"]
    text_out = summary(conn, user_id).text
    assert "“Potassium” 7 %" in text_out and "critical check impossible" in text_out


def test_values_approved_today_are_in_this_week_even_with_unmapped_rows_left(conn, user_id):
    """The weekly window dates an approval by the source's reviewed_at; it was set only once no
    unmapped row was left, so a ">5" potassium approved today counted from its staging day."""
    out = stage_panel(conn, user_id, date.today() - timedelta(days=10),
                      [{"raw_name": "Potassium", "value": ">5", "unit": "mmol/L",
                        "ref_min": 3.5, "ref_max": 5.1},
                       {"raw_name": "Marcador desconocido", "value": 1.0, "unit": "U/L"}],
                      alerter=lambda *a: None)
    conn.execute(text("UPDATE observations SET created_at = now() - interval '10 days' "
                     "WHERE source_id = :s"), {"s": out["source_id"]})
    res = approve_staged(conn, user_id, out["source_id"])
    assert res["left_pending_unmapped"] and res["unverifiable_approved"]
    report = weekly(conn, user_id)
    assert [u["code"] for u in report["unverifiable_approved"]] == ["potassium"]
    assert report["stable"] is False
