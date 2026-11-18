"""Unknown / mis-mapped lab rows are kept as pending unmapped rows and can be mapped later (#12)."""
from datetime import date

from sqlalchemy import text

from core.health_summary import build as build_summary
from core.normalize import units_incompatible
from core.services import approve_staged, map_pending_observation, stage_panel


def _row(conn, oid):
    return conn.execute(
        text("""SELECT o.type_id, ot.code, o.raw_name, o.value_canonical, o.status,
                       o.review_status
                FROM observations o LEFT JOIN observation_types ot ON ot.id = o.type_id
                WHERE o.id = :i"""),
        {"i": oid},
    ).mappings().one()


def test_units_incompatible_only_for_known_different_dimensions():
    assert units_incompatible("10^9/L", "%")
    assert units_incompatible("%", "10*9/L")
    assert not units_incompatible("mg/dL", "mmol/L")      # convertible via molar mass
    assert not units_incompatible("уо/л", "mmol/L")      # unrecognized unit → not a verdict
    assert not units_incompatible("mmol/mol", "%")       # HbA1c IFCC vs NGSP: not classified
    assert not units_incompatible(None, "mmol/L")


def test_unknown_name_is_stored_pending_and_listed(conn, user_id):
    out = stage_panel(conn, user_id, date(2026, 9, 15),
                      [{"raw_name": "Glucosa basal ayunas", "value": 99, "unit": "mg/dL",
                        "ref_min": 70, "ref_max": 110}])
    r = out["rows"][0]
    assert r["stored"] and r["matched"] is None
    assert out["counts"]["unknown"] == 1
    assert "map_pending_observation" in out["hint"]

    pending = conn.execute(
        text("SELECT raw_name, unmapped, value_numeric, unit, ref_max FROM v_observations_pending "
             "WHERE id = :i"), {"i": r["observation_id"]},
    ).mappings().one()
    assert pending["unmapped"] and pending["raw_name"] == "Glucosa basal ayunas"
    assert float(pending["value_numeric"]) == 99 and pending["unit"] == "mg/dL"

    summary = build_summary(conn, user_id).text
    assert "unrecognized marker" in summary and "Glucosa basal ayunas" in summary


def test_mapping_renormalizes_and_learns_the_name(conn, user_id):
    out = stage_panel(conn, user_id, date(2026, 9, 15),
                      [{"raw_name": "Glucosa basal ayunas", "value": 99, "unit": "mg/dL"}])
    oid = out["rows"][0]["observation_id"]

    res = map_pending_observation(conn, user_id, oid, "glucose")
    assert res["type_code"] == "glucose" and res["learned_synonym"]["saved"]
    assert abs(res["value_canonical"] - 99 * 0.05551) < 1e-6
    row = _row(conn, oid)
    assert row["code"] == "glucose" and row["review_status"] == "pending"

    # the next panel with the same printed name maps automatically (flagged as learned)
    again = stage_panel(conn, user_id, date(2026, 9, 21),
                        [{"raw_name": "GLUCOSA  basal ayunas", "value": 101, "unit": "mg/dL"}])
    r = again["rows"][0]
    assert r["matched"] == "glucose" and "learned synonym" in r["note"]


def test_mapping_rechecks_critical_values(conn, user_id):
    out = stage_panel(conn, user_id, date(2026, 9, 15),
                      [{"raw_name": "Kalium im Serum", "value": 7.1, "unit": "mmol/L"}])
    oid = out["rows"][0]["observation_id"]
    alerts = []
    res = map_pending_observation(conn, user_id, oid, "potassium",
                                  alerter=lambda t, m: alerts.append(m))
    assert res["critical"] and res["status"] == "critical" and alerts
    assert _row(conn, oid)["status"] == "critical"


def test_mapping_refuses_wrong_dimension_and_unknown_code(conn, user_id):
    out = stage_panel(conn, user_id, date(2026, 9, 15),
                      [{"raw_name": "Linfocitos totales", "value": 2.1, "unit": "10^9/L"}])
    oid = out["rows"][0]["observation_id"]
    assert "error" in map_pending_observation(conn, user_id, oid, "lymphocytes_pct")
    assert "error" in map_pending_observation(conn, user_id, oid, "no_such_marker")
    assert _row(conn, oid)["type_id"] is None
    assert map_pending_observation(conn, user_id, oid, "lymphocytes_abs")["type_code"] \
        == "lymphocytes_abs"


def test_ambiguous_synonym_does_not_block_the_correct_row(conn, user_id):
    # bare "Lymphocytes" is a synonym of the % type; this lab prints the absolute count
    out = stage_panel(conn, user_id, date(2026, 9, 15), [
        {"raw_name": "Lymphocytes", "value": 2.1, "unit": "10^9/L"},
        {"raw_name": "лімфоцити", "value": 30, "unit": "%"},
    ])
    wrong, right = out["rows"]
    assert wrong["stored"] and wrong["matched"] is None
    assert wrong["rejected_match"] == "lymphocytes_pct"
    assert "wrong type" in wrong["note"] and "no unit conversion" not in wrong["note"]
    assert right["stored"] and right["matched"] == "lymphocytes_pct"
    assert out["counts"]["likely_wrong_type"] == 1 and out["counts"]["unit_gate"] == 0

    # the name already means lymphocytes_pct — mapping works but no second meaning is learned
    res = map_pending_observation(conn, user_id, wrong["observation_id"], "lymphocytes_abs")
    assert res["type_code"] == "lymphocytes_abs"
    assert res["learned_synonym"]["saved"] is False


def test_approve_leaves_unmapped_rows_pending(conn, user_id):
    out = stage_panel(conn, user_id, date(2026, 9, 15), [
        {"raw_name": "калій", "value": 4.2, "unit": "mmol/L"},
        {"raw_name": "Marcador desconocido", "value_text": "negativo"},
    ])
    unknown = out["rows"][1]["observation_id"]
    appr = approve_staged(conn, user_id, out["source_id"])
    assert appr["approved_observations"] == 1
    assert appr["left_pending_unmapped"][0]["observation_id"] == unknown
    assert _row(conn, unknown)["review_status"] == "pending"


def test_a_learned_name_with_accents_maps_the_next_panel(conn, user_id):
    # the synonym was saved as typed, but find_type compares the accent-stripped form
    from datetime import date

    from core.services import map_pending_observation, stage_panel
    name = "Glucosa en suero (método enzimático)"
    first = stage_panel(conn, user_id, date(2026, 9, 15),
                        [{"raw_name": name, "value": 99, "unit": "mg/dL"}])
    res = map_pending_observation(conn, user_id, first["rows"][0]["observation_id"], "glucose")
    assert res["learned_synonym"]["saved"] is True
    again = stage_panel(conn, user_id, date(2026, 9, 21),
                        [{"raw_name": name.upper(), "value": 101, "unit": "mg/dL"}])
    assert again["rows"][0]["matched"] == "glucose"
