"""Input the tools used to accept, crash on or misread — each test pins the fixed behaviour.

Covers: paracetamol from recorded medications + brand names, case-insensitive biotin tests,
the MCP error guard and argument checks, profile/diagnosis/allergy validation, impossible meal
values, template amounts, empty panels, per-user search/crisis contact and the review-queue cap.
"""
import json
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError

from core import queries as q
from core.services import (
    add_allergy,
    add_diagnosis,
    add_food_log,
    log_from_template,
    manual_source,
    save_meal_template,
    stage_panel,
    update_meal,
    upsert_profile,
)
from mcp_server import server
from mcp_server.tools import medication_safety
from safety.interactions import is_paracetamol


def _paracetamol(name, amount=1, unit="g", times=4, atc=None):
    return {"medication_name": name, "dose_amount": amount, "dose_unit": unit,
            "times_per_day": times, "atc_code": atc}


# ------------------------------------------------------------------ paracetamol
def test_explicit_products_add_to_recorded_paracetamol():
    # explicit products used to REPLACE the current list: 1950 mg "ok" instead of 5950 mg
    current = [_paracetamol("Paracetamol", 1000, "mg", 4)]
    p = medication_safety(current, paracetamol_products=[
        {"name": "Frenadol", "mg_per_dose": 650, "doses_per_day": 3}])["paracetamol"]
    assert p["total_mg_per_day"] == 5950 and p["level"] == "exceeded"
    assert p["source"] == "provided+current_medications"
    assert p["from_current_medications"] == ["Paracetamol"]


def test_explicit_product_replaces_the_recorded_entry_of_the_same_name():
    current = [_paracetamol("Gelocatil 1 g", 1000, "mg", 4)]
    p = medication_safety(current, paracetamol_products=[
        {"name": "gelocatil 1g", "mg_per_dose": 1000, "doses_per_day": 2}])["paracetamol"]
    assert p["total_mg_per_day"] == 2000 and p["source"] == "provided"


@pytest.mark.parametrize("name", ["Gelocatil 1 g", "Panadol", "Efferalgan 1g", "Dafalgan",
                                  "Termalgin", "Tylenol", "Apiretal", "Acetaminofén",
                                  "acetaminofen", "Paracetamolo", "PARACETAMOL", "Calpol",
                                  "Xumadol", "Perfalgan", "Frenadol Complex", "Panadol500",
                                  "парацетамол 500", "Парацетамолу таблетки",
                                  "таблетки парацетамолу", "Paracetamolratiopharm"])
def test_paracetamol_brands_and_spellings_are_counted(name):
    out = medication_safety([_paracetamol(name)])
    assert out["paracetamol"]["total_mg_per_day"] == 4000


@pytest.mark.parametrize("name", ["Ibuprofen 400", "Metamizol", "Nolotil", ""])
def test_other_medications_are_not_paracetamol(name):
    assert not is_paracetamol(name)


def test_paracetamol_by_atc_code():
    out = medication_safety([_paracetamol("Some combination", 500, "mg", 3, atc="n02be51")])
    assert out["paracetamol"]["total_mg_per_day"] == 1500


def test_biotin_planned_tests_any_case():
    meds = [{"medication_name": "Biotin", "dose_amount": 10, "dose_unit": "mg",
             "times_per_day": 1}]
    out = medication_safety(meds, planned_tests=["TSH", "Troponin", "Vitamin D"])
    assert "tsh" in out["biotin"] and "troponin" in out["biotin"] and "vitamin_d" in out["biotin"]


# ------------------------------------------------------------------ MCP error guard / arguments
def test_guard_returns_db_errors_without_sql():
    def boom():
        raise DataError("INSERT INTO allergies (secret) VALUES (%(x)s)", {},
                        Exception("value too long for type character varying(20)\n"
                                  "LINE 1: INSERT INTO allergies"))
    out = json.loads(server._db_guard(boom)())
    assert out == {"error": "invalid value",
                   "detail": "value too long for type character varying(20)"}


def test_guard_turns_value_errors_into_json():
    def bad():
        raise ValueError("diagnosis_name is required")
    assert json.loads(server._db_guard(bad)()) == {"error": "invalid input",
                                                   "detail": "diagnosis_name is required"}


@pytest.mark.parametrize("call", [
    lambda: server.approve_staged_source("not-a-uuid"),
    lambda: server.map_pending_observation("not-a-uuid", "glucose"),
])
def test_non_uuid_ids_are_refused_before_the_database(call):
    assert "is not an id" in json.loads(call())["error"]


@pytest.mark.parametrize("call, expected", [
    (lambda: server.log_meal("x", eaten_at="yesterday 13:00"), "eaten_at yesterday 13:00"),
    (lambda: server.log_from_template("whatever", eaten_at="today"), "eaten_at today"),
    (lambda: server.record_medication("m", start_date="last week"),
     "start_date last week is not a date"),
    (lambda: server.set_profile("1990-13-01", "male"), "date_of_birth 1990-13-01 is not a date"),
    (lambda: server.set_profile("2999-01-01", "male"), "in the future"),
    (lambda: server.set_profile("1990-01-01", "yes"), "male or female"),
])
def test_bad_arguments_get_a_clear_error(call, expected):
    assert expected in json.loads(call())["error"]


@pytest.mark.integration
def test_bad_values_reaching_the_service_get_a_clear_error():
    out = json.loads(server.record_diagnosis("dx", diagnosed_at="2026-02-30"))
    assert out == {"error": "diagnosed_at 2026-02-30 is not a date (YYYY-MM-DD)"}
    out = json.loads(server.record_allergy("pollen", severity="severe, life-threatening"))
    assert "longer than 20" in out["error"]
    # a column overflow the code doesn't check by hand still comes back as JSON, not a crash
    out = json.loads(server.record_medication("m", start_date="2026-01-01",
                                              dose_unit="milligrams per square metre"))
    assert out["error"] == "invalid value" and "character varying" in out["detail"]
    assert "INSERT" not in out["detail"]


# ------------------------------------------------------------------ profile / diagnoses / allergies
@pytest.mark.parametrize("given", ["Male", " M ", "hombre", "чоловіча"])
def test_sex_spellings_keep_male_screenings(conn, user_id, given):
    from analytics.screening import for_user
    upsert_profile(conn, user_id, date_of_birth=date(2000, 1, 1), sex=given)
    stored = conn.execute(text("SELECT sex FROM user_profile WHERE user_id=:u"),
                          {"u": user_id}).scalar()
    assert stored == "male"
    assert "testicular" in {r["code"] for r in for_user(conn, user_id)["recommendations"]}


def test_profile_rejects_unknown_sex_and_future_birth(conn, user_id):
    with pytest.raises(ValueError, match="male or female"):
        upsert_profile(conn, user_id, date_of_birth=date(2000, 1, 1), sex="other")
    with pytest.raises(ValueError, match="in the future"):
        upsert_profile(conn, user_id, date_of_birth=date(2090, 1, 1), sex="female")


def test_screening_reads_old_profiles_case_insensitively(conn, user_id):
    from analytics.screening import for_user
    conn.execute(text("""INSERT INTO user_profile (user_id, date_of_birth, sex)
                         VALUES (:u, '2000-01-01', 'Male')
                         ON CONFLICT (user_id) DO UPDATE SET sex='Male',
                             date_of_birth='2000-01-01'"""), {"u": user_id})
    assert "testicular" in {r["code"] for r in for_user(conn, user_id)["recommendations"]}
    conn.execute(text("UPDATE user_profile SET date_of_birth='2090-01-01' WHERE user_id=:u"),
                 {"u": user_id})
    assert "in the future" in for_user(conn, user_id)["error"]


@pytest.mark.parametrize("kwargs, match", [
    ({"diagnosis_name": "", "diagnosed_at": "2020-01-01"}, "diagnosis_name is required"),
    ({"diagnosis_name": "GERD", "diagnosed_at": "2099-01-01"}, "in the future"),
    ({"diagnosis_name": "GERD", "diagnosed_at": "2020-01-01", "clinical_status": "yes"},
     "clinical_status"),
    ({"diagnosis_name": "GERD", "diagnosed_at": "2020-01-01", "verification_status": "sure"},
     "verification_status"),
])
def test_diagnosis_rejects_bad_input(conn, user_id, kwargs, match):
    name = kwargs.pop("diagnosis_name")
    with pytest.raises(ValueError, match=match):
        add_diagnosis(conn, user_id, name, **kwargs)


def test_diagnosis_status_case_is_normalised(conn, user_id):
    did = add_diagnosis(conn, user_id, "GERD", diagnosed_at="2020-01-01",
                        clinical_status="Active", verification_status="Confirmed")
    row = conn.execute(text("SELECT clinical_status, verification_status FROM diagnoses "
                            "WHERE id=:i"), {"i": did}).one()
    assert tuple(row) == ("active", "confirmed")


def test_blank_allergen_is_rejected(conn, user_id):
    with pytest.raises(ValueError, match="allergen is required"):
        add_allergy(conn, user_id, "   ")


# ------------------------------------------------------------------ food diary
def test_future_meal_is_refused_but_a_little_ahead_is_fine(conn, user_id):
    out = add_food_log(conn, user_id, "typo year", eaten_at=datetime.now() + timedelta(days=400),
                       nutrients={"protein": 500})
    assert "in the future" in out["error"]
    ok = add_food_log(conn, user_id, "dinner", eaten_at=datetime.now() + timedelta(hours=3))
    assert "error" not in ok


def test_nutrition_ignores_meals_dated_far_ahead(conn, user_id):
    # a meal stored before the check (or by another writer) must not count in every window
    from analytics.nutrition import summarize
    sid = manual_source(conn, user_id)
    fid = conn.execute(text("""INSERT INTO food_log (user_id, eaten_at, description, source_id)
                               VALUES (:u, now() + interval '400 days', 'future', :s)
                               RETURNING id"""), {"u": user_id, "s": sid}).scalar()
    conn.execute(text("""INSERT INTO food_nutrients (food_log_id, nutrient_id, amount)
                         SELECT :f, id, 500 FROM nutrient_types WHERE code='protein'"""),
                 {"f": fid})
    s = summarize(conn, user_id, days=7)
    assert all(n["nutrient"] != "protein" or n["avg_per_day"] < 500 for n in s["nutrients"])


@pytest.mark.parametrize("kwargs, match", [
    ({"nutrients": {"protein": -300}}, "≥ 0"),
    ({"nutrients": {"protein": "12 g"}}, "≥ 0"),
    ({"glycemic_index": 250}, "0–100"),
    ({"glycemic_load": -1}, "glycemic_load"),
])
def test_impossible_meal_values_are_refused(conn, user_id, kwargs, match):
    out = add_food_log(conn, user_id, "x", eaten_at=datetime(2026, 11, 1, 12), **kwargs)
    assert match in out["error"]
    fid = add_food_log(conn, user_id, "ok", eaten_at=datetime(2026, 11, 1, 12))["id"]
    out = update_meal(conn, user_id, fid, {k: v for k, v in kwargs.items() if k != "nutrients"},
                      nutrients=kwargs.get("nutrients"))
    assert match in out["error"]


def test_template_portion_factor_must_be_positive(conn, user_id):
    save_meal_template(conn, user_id, "t_pf", nutrients={"energy_kcal": 400})
    for pf in (-2, 0):
        out = log_from_template(conn, user_id, "t_pf", eaten_at=datetime(2026, 11, 1, 13),
                                portion_factor=pf)
        assert "portion_factor" in out["error"]


def test_template_rejects_unknown_codes_and_bad_amounts(conn, user_id):
    with pytest.raises(ValueError, match="protien"):
        save_meal_template(conn, user_id, "t_typo", nutrients={"protien": 20})
    with pytest.raises(ValueError, match="≥ 0"):
        save_meal_template(conn, user_id, "t_neg", nutrients={"protein": -5})


def test_template_null_or_text_amounts_are_skipped_not_crashing(conn, user_id):
    # templates saved before amounts were checked: null crashed (TypeError), text (ValueError)
    conn.execute(text("""INSERT INTO meal_templates (user_id, name, nutrients)
                         VALUES (:u, 't_old', CAST(:n AS jsonb))"""),
                 {"u": user_id, "n": json.dumps({"protein": 10, "fiber": None, "iron": "12 g"})})
    out = log_from_template(conn, user_id, "t_old", eaten_at=datetime(2026, 11, 1, 9))
    assert out["nutrients_saved"] == 1
    assert {s["nutrient"] for s in out["skipped"]} == {"fiber", "iron"}


# ------------------------------------------------------------------ staging
def test_empty_panel_is_refused_before_anything_is_written(conn, user_id):
    before = conn.execute(text("SELECT count(*) FROM panels")).scalar()
    out = stage_panel(conn, user_id, "2026-11-02", [])
    assert "rows is empty" in out["error"]
    assert conn.execute(text("SELECT count(*) FROM panels")).scalar() == before


# ------------------------------------------------------------------ review queue cap
def test_pending_list_is_newest_first_and_says_when_truncated(conn, user_id):
    sid = manual_source(conn, user_id, channel="mcp", review_status="pending")
    base = datetime(2026, 1, 1)
    for i in range(201):  # inserted oldest → newest
        conn.execute(text(
            """INSERT INTO observations (user_id, type_id, raw_name, effective_at, value_numeric,
                   unit, review_status, source_id)
               VALUES (:u, NULL, :n, :e, 1, 'x', 'pending', :s)"""),
            {"u": user_id, "n": f"qcap_{i}", "e": base + timedelta(days=i), "s": sid})
    out = q.view_rows(conn, user_id, "pending")
    assert len(out["rows"]) == 200 and out["truncated"] is True
    assert out["rows"][0]["raw_name"] == "qcap_200"            # the newest is kept
    assert "qcap_0" not in {r["raw_name"] for r in out["rows"]}  # the oldest is the one cut
    assert q.view_rows(conn, user_id, "pending", limit=500)["truncated"] is False


def test_medications_list_newest_start_first(conn, user_id):
    from core.services import add_medication
    add_medication(conn, user_id, "old", start_date="2020-01-01")
    add_medication(conn, user_id, "new", start_date="2026-01-01")
    names = [r["medication_name"] for r in q.view_rows(conn, user_id, "medications")["rows"]]
    assert names.index("new") < names.index("old")


# ------------------------------------------------------------------ per-user scoping
@pytest.mark.integration
def test_search_and_crisis_contact_stay_with_the_current_user():
    from core.db import engine
    from core.services import get_or_create_user
    with engine.begin() as c:
        me = get_or_create_user(c)
        other = c.execute(text("INSERT INTO users DEFAULT VALUES RETURNING id")).scalar()
        doc = c.execute(text(
            """INSERT INTO documents (user_id, title, file_path, file_sha256)
               VALUES (:u, 'other user doc', '/x', :sha) RETURNING id"""),
            {"u": other, "sha": uuid.uuid4().hex * 2}).scalar()
        c.execute(text("INSERT INTO document_chunks (document_id, chunk_index, content) "
                       "VALUES (:d, 0, 'zzqotheruser finding')"), {"d": doc})
        c.execute(text("""INSERT INTO user_profile (user_id, date_of_birth, sex, emergency_contact)
                          VALUES (:u, '1980-01-01', 'female', 'zzq other contact')"""),
                  {"u": other})
    try:
        assert str(other) != me
        out = json.loads(server.search("zzqotheruser"))
        assert out["results"] == []
        assert "zzq other contact" not in json.loads(server.crisis_resources("help"))["response"]
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM user_profile WHERE user_id=:u"), {"u": other})
            c.execute(text("DELETE FROM document_chunks WHERE document_id=:d"), {"d": doc})
            c.execute(text("DELETE FROM documents WHERE id=:d"), {"d": doc})
            c.execute(text("DELETE FROM users WHERE id=:u"), {"u": other})
