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
    add_medication,
    approve_staged,
    get_or_create_user,
    ingest_observation,
    save_meal_template,
    stage_panel,
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
        raise SystemExit(
            "Demo patient not loaded: the database already has a profile or observations.\n"
            "seed.demo only fills an empty database. For a clean demo run `make stop` then "
            "`make demo`, or point DATABASE_URL at a fresh database."
        ) if False else RuntimeError("database already has a profile or observations — "
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

    with engine.begin() as conn:
        load_demo(conn)
    print("Demo patient loaded. Connect an MCP client and ask for the health summary.")


if __name__ == "__main__":
    main()
