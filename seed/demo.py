"""Synthetic demo patient — lets you try health-os without entering your own data.

Run on a FRESH database, after migrations and `seed.load`:
    uv run python -m seed.demo

Everything here is fictional. The loader refuses to run if the database already holds a
profile or observations, so it can never mix demo values into a real record.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import text

from core.services import (
    add_allergy,
    add_diagnosis,
    add_food_log,
    add_habit,
    add_medication,
    approve_staged,
    get_or_create_user,
    ingest_observation,
    manual_source,
    save_meal_template,
    stage_panel,
    stop_medication,
    upsert_profile,
)

# (months ago, {raw_name: (value, unit, ref_min, ref_max)}) — LDL creeps up, vitamin D stays low
LAB_PANELS = [
    (30, {"Total cholesterol": (4.9, "mmol/L", 0, 5.2), "LDL": (2.9, "mmol/L", 0, 3.0),
          "HDL": (1.5, "mmol/L", 1.2, None), "Glucose": (4.9, "mmol/L", 3.9, 5.6),
          "TSH": (2.1, "mIU/L", 0.4, 4.0), "Creatinine": (72, "umol/L", 45, 90)}),
    (24, {"Total cholesterol": (5.1, "mmol/L", 0, 5.2), "LDL": (3.1, "mmol/L", 0, 3.0),
          "HDL": (1.4, "mmol/L", 1.2, None), "Vitamin D": (18, "ng/mL", 30, 100)}),
    (18, {"Total cholesterol": (5.3, "mmol/L", 0, 5.2), "LDL": (3.3, "mmol/L", 0, 3.0),
          "HDL": (1.4, "mmol/L", 1.2, None), "Glucose": (5.2, "mmol/L", 3.9, 5.6)}),
    (12, {"Total cholesterol": (5.5, "mmol/L", 0, 5.2), "LDL": (3.5, "mmol/L", 0, 3.0),
          "HDL": (1.3, "mmol/L", 1.2, None), "Vitamin D": (22, "ng/mL", 30, 100),
          "Hemoglobin": (132, "g/L", 120, 150), "TSH": (2.4, "mIU/L", 0.4, 4.0)}),
    (2, {"Total cholesterol": (5.8, "mmol/L", 0, 5.2), "LDL": (3.8, "mmol/L", 0, 3.0),
         "HDL": (1.3, "mmol/L", 1.2, None), "Glucose": (5.5, "mmol/L", 3.9, 5.6),
         "HbA1c": (5.6, "%", 4.0, 5.7), "Creatinine": (75, "umol/L", 45, 90)}),
]
# a fresh panel the "user" hasn't approved yet → shows the pending-review guardrail
PENDING_PANEL = (3, {"Vitamin D": (27, "ng/mL", 30, 100), "Ferritin": (35, "ng/mL", 15, 150)})

_B, _L, _D, _S = "breakfast", "lunch", "dinner", "snack"
MEALS = [  # (days ago, hour, meal_type, description, wellbeing, nutrients)
    (0, 8, _B, "Oatmeal with banana and walnuts", "good",
     {"energy_kcal": 420, "protein": 12, "carbs": 68, "sugar": 16, "fiber": 8, "fat": 12,
      "sodium": 90, "potassium": 620, "magnesium": 110, "calcium": 60, "iron": 3}),
    (0, 13, _L, "Chicken salad with olive oil, bread", "good",
     {"energy_kcal": 610, "protein": 38, "carbs": 42, "fiber": 6, "fat": 30,
      "sodium": 980, "potassium": 720, "vitamin_c": 45, "iron": 2}),
    (0, 16, _S, "Apple and a handful of almonds", "good",
     {"energy_kcal": 260, "protein": 6, "carbs": 30, "sugar": 20, "fiber": 7, "fat": 14,
      "potassium": 350, "magnesium": 80, "calcium": 80, "vitamin_c": 8}),
    (0, 19, _D, "Salmon, rice, broccoli", "good",
     {"energy_kcal": 720, "protein": 42, "carbs": 70, "fiber": 5, "fat": 26, "omega3": 2.2,
      "sodium": 520, "potassium": 1100, "vitamin_d": 12, "vitamin_c": 90, "calcium": 90}),
    (1, 8, _B, "Greek yogurt, berries, honey", "good",
     {"energy_kcal": 300, "protein": 18, "carbs": 38, "sugar": 30, "fat": 8,
      "calcium": 250, "vitamin_c": 30, "sodium": 70, "potassium": 380}),
    (1, 13, _L, "Lentil soup, rye bread", "good",
     {"energy_kcal": 520, "protein": 26, "carbs": 78, "fiber": 16, "fat": 9,
      "iron": 6, "folate_b9": 300, "sodium": 1100, "potassium": 900, "magnesium": 90}),
    (1, 19, _D, "Pizza (3 slices), cola", "tired",
     {"energy_kcal": 1050, "protein": 36, "carbs": 130, "sugar": 42, "added_sugar": 35,
      "fat": 40, "saturated_fat": 17, "sodium": 2200, "potassium": 480, "calcium": 350}),
    (2, 8, _B, "Two eggs, toast, tomato", "good",
     {"energy_kcal": 380, "protein": 20, "carbs": 30, "fiber": 3, "fat": 19,
      "sodium": 480, "potassium": 420, "vitamin_b12": 1.1, "vitamin_d": 2, "iron": 2}),
    (2, 13, _L, "Burger and fries", "tired",
     {"energy_kcal": 1100, "protein": 35, "carbs": 105, "fat": 58, "saturated_fat": 18,
      "sodium": 1900, "potassium": 900, "added_sugar": 10}),
    (2, 19, _D, "Vegetable stew with beans", "good",
     {"energy_kcal": 480, "protein": 20, "carbs": 70, "fiber": 15, "fat": 12,
      "sodium": 700, "potassium": 1200, "magnesium": 120, "folate_b9": 250, "vitamin_c": 60}),
]


def _years_ago(today: date, years: float) -> date:
    return today - timedelta(days=round(365.25 * years))


def _ok(result: dict) -> dict:
    """The services answer a refused write with {"error": …}: the demo must not skip one."""
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def _record(conn, uid: str, today: date) -> None:
    """The rest of the medical record, so every timeline lane and record page has something:
    diagnoses of each verification status, a finished medication course, habits, visits,
    a procedure, a hospital stay, vaccinations and a document."""
    add_diagnosis(conn, uid, "Allergic rhinitis due to pollen", icd10_code="J30.1",
                  diagnosed_at=_years_ago(today, 9), verification_status="confirmed",
                  severity="mild")
    add_diagnosis(conn, uid, "Iron deficiency anaemia", icd10_code="D50.9",
                  diagnosed_at=_years_ago(today, 4), clinical_status="resolved",
                  verification_status="confirmed")
    add_diagnosis(conn, uid, "Tension-type headache", icd10_code="G44.2",
                  diagnosed_at=_years_ago(today, 1.5), verification_status="provisional")
    add_diagnosis(conn, uid, "Hypothyroidism", icd10_code="E03.9",
                  diagnosed_at=_years_ago(today, 2.5), clinical_status="inactive",
                  verification_status="refuted", notes="TSH in range on repeat tests")

    iron = add_medication(conn, uid, "Ferrous sulfate", start_date=_years_ago(today, 4),
                          dose_amount=200, dose_unit="mg", route="oral", times_per_day=1,
                          prescribed_for="Iron deficiency anaemia")
    _ok(stop_medication(conn, uid, iron, end_date=_years_ago(today, 3.5),
                        stop_reason="course completed"))
    add_medication(conn, uid, "Cetirizine", start_date=_years_ago(today, 9),
                   product_type="otc", dose_amount=10, dose_unit="mg", route="oral",
                   times_per_day=1, dosing_pattern="seasonal",
                   prescribed_for="Allergic rhinitis due to pollen")
    add_medication(conn, uid, "Paracetamol", start_date=_years_ago(today, 1.5),
                   product_type="otc", dose_amount=500, dose_unit="mg", route="oral",
                   times_per_day=2, dosing_pattern="as_needed",
                   prescribed_for="Tension-type headache")

    _ok(add_habit(conn, uid, "smoking", status="former", cigarettes_per_day=8, smoking_years=10,
                  start_date=_years_ago(today, 22), end_date=_years_ago(today, 12)))
    _ok(add_habit(conn, uid, "alcohol", status="current", frequency="2–3 drinks a week",
                  drinks_per_week=3, start_date=_years_ago(today, 20)))
    _ok(add_habit(conn, uid, "running", status="current", frequency="3 times a week",
                  start_date=_years_ago(today, 3)))

    sid = manual_source(conn, uid)
    clinic = conn.execute(text(
        "INSERT INTO facilities (user_id, name, kind) VALUES (:u, 'Demo Clinic', 'clinic') "
        "RETURNING id"), {"u": uid}).scalar()
    hospital = conn.execute(text(
        "INSERT INTO facilities (user_id, name, kind) VALUES (:u, 'Demo Hospital', 'hospital') "
        "RETURNING id"), {"u": uid}).scalar()
    p = {"u": uid, "s": sid, "c": clinic, "h": hospital}
    for years, reason in ((9, "Sneezing and itchy eyes every spring"), (4, "Tiredness"),
                          (1.5, "Headaches"), (0.1, "Check-up: cholesterol results")):
        conn.execute(text(
            "INSERT INTO doctor_visits (user_id, visit_date, facility_id, reason_for_visit, "
            "source_id) VALUES (:u, :d, :c, :r, :s)"), {**p, "d": _years_ago(today, years),
                                                       "r": reason})
    conn.execute(text(
        "INSERT INTO hospital_stays (user_id, admission_date, discharge_date, facility_id, "
        "department, admission_diagnosis, source_id) "
        "VALUES (:u, :a, :b, :h, 'Surgery', 'Acute appendicitis', :s)"),
        {**p, "a": _years_ago(today, 14), "b": _years_ago(today, 14) + timedelta(days=3)})
    conn.execute(text(
        "INSERT INTO procedures (user_id, procedure_date, procedure_name, procedure_type, "
        "facility_id, outcome, source_id) VALUES (:u, :d, 'Laparoscopic appendectomy', "
        "'surgery', :h, 'recovered', :s)"), {**p, "d": _years_ago(today, 14)})
    for years, vaccine, disease, dose in ((16, "Hepatitis B vaccine", "Hepatitis B", 3),
                                          (7, "Tdap", "Tetanus, diphtheria, pertussis", None),
                                          (0.9, "Influenza vaccine", "Influenza", None)):
        conn.execute(text(
            "INSERT INTO vaccinations (user_id, vaccination_date, vaccine_name, disease, "
            "dose_number, facility_id, source_id) VALUES (:u, :d, :v, :dis, :n, :c, :s)"),
            {**p, "d": _years_ago(today, years), "v": vaccine, "dis": disease, "n": dose})
    conn.execute(text(
        "INSERT INTO documents (user_id, document_date, doc_type, title, file_path, file_sha256, "
        "mime_type) VALUES (:u, :d, 'discharge_summary', 'Discharge summary: appendectomy', "
        "'demo/discharge-summary.pdf', :sha, 'application/pdf')"),
        {"u": uid, "d": _years_ago(today, 14) + timedelta(days=3), "sha": "d" * 64})


def _rows(markers: dict) -> list[dict]:
    return [{"raw_name": name, "value": v, "unit": u, "ref_min": lo, "ref_max": hi}
            for name, (v, u, lo, hi) in markers.items()]


def is_empty(conn) -> bool:
    n = conn.execute(text(
        "SELECT (SELECT count(*) FROM user_profile) + (SELECT count(*) FROM observations)"
    )).scalar()
    return not n


def load_demo(conn, *, today: date | None = None) -> str:
    """Fill an empty database with the demo patient. Returns user_id."""
    if not is_empty(conn):
        raise RuntimeError("database already has a profile or observations — "
                           "the demo only loads into a fresh database")
    today = today or date.today()
    uid = get_or_create_user(conn)

    upsert_profile(conn, uid, date_of_birth=date(1985, 4, 12), sex="female",
                   blood_type="A", rh_factor="+", height_cm=168)
    add_allergy(conn, uid, "penicillin", reaction="rash", severity="moderate", verified=True)
    add_diagnosis(conn, uid, "Hypercholesterolemia", icd10_code="E78.0",
                  diagnosed_at=today - timedelta(days=30), verification_status="suspected")
    add_medication(conn, uid, "Vitamin D3", start_date=today - timedelta(days=300),
                   product_type="supplement", dose_amount=2000, dose_unit="IU", times_per_day=1)
    _record(conn, uid, today)

    # labs go through the same path an MCP client uses: stage → (user) approve
    for months_ago, rows in LAB_PANELS:
        staged = stage_panel(conn, uid, today - timedelta(days=30 * months_ago),
                             _rows(rows), facility="Demo Lab")
        approve_staged(conn, uid, staged["source_id"])
    days_ago, rows = PENDING_PANEL
    stage_panel(conn, uid, today - timedelta(days=days_ago), _rows(rows), facility="Demo Lab")

    for d in range(14):  # two weeks of home blood pressure + weight
        at = datetime.combine(today - timedelta(days=d), datetime.min.time()) + timedelta(hours=8)
        ingest_observation(conn, uid, "Systolic", 128 + (d * 7) % 11, "mmHg", effective_at=at)
        ingest_observation(conn, uid, "Diastolic", 82 + (d * 5) % 7, "mmHg", effective_at=at)
        if d % 7 == 0:
            ingest_observation(conn, uid, "Weight", 68.4 - d * 0.05, "kg", effective_at=at)

    for days_ago, hour, meal_type, desc, wellbeing, nutrients in MEALS:
        at = datetime.combine(today - timedelta(days=days_ago), datetime.min.time())
        add_food_log(conn, uid, desc, eaten_at=at + timedelta(hours=hour), meal_type=meal_type,
                     wellbeing=wellbeing, nutrients=nutrients)
    save_meal_template(conn, uid, "oatmeal", meal_type="breakfast",
                       description="Oatmeal with banana and walnuts", nutrients=MEALS[0][5])
    return uid


def main() -> None:
    from core.db import engine

    try:
        with engine.begin() as conn:
            load_demo(conn)
    except RuntimeError as e:  # a CLI message, not a traceback
        raise SystemExit(f"Demo patient not loaded: {e}. For a throwaway demo database "
                         "run `make demo` (demo/docker-compose.yml).") from None
    print("Demo patient loaded. Connect an MCP client and ask for the health summary.")


if __name__ == "__main__":
    main()
