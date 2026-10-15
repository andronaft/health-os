"""MCP WRITE tools (plan 4.2) — the interactive extraction cycle via an MCP client.

The key difference from tools.py: these functions write to the DB (read-write engine),
whereas tools.py is read-only. The model in the MCP client reads the PDF with
its eyes and calls stage_panel; critical values are force-alerted. approve_staged is a
SEPARATE explicit action (guardrail: the model must not create+approve in one move).
"""
from __future__ import annotations

import json
from datetime import date, datetime

from core.db import engine
from core.services import (
    add_allergy,
    add_diagnosis,
    add_food_log,
    add_medication,
    approve_staged,
    get_or_create_user,
    stage_panel,
    upsert_profile,
)
from core.services import delete_meal as _svc_delete_meal
from core.services import log_from_template as _svc_log_from_template
from core.services import map_pending_observation as _svc_map_pending
from core.services import save_meal_template as _svc_save_meal_template
from core.services import stop_medication as _svc_stop_medication
from core.services import update_meal as _svc_update_meal
from core.services import update_medication as _svc_update_medication
from safety.alerts import send_critical_alert


def _j(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


def set_profile(date_of_birth: str, sex: str, blood_type: str = "",
                height_cm: float | None = None, emergency_contact: str = "") -> str:
    """Create/update the profile (date of birth YYYY-MM-DD, sex male/female).
    Needed for reference ranges, age-gate calculators, the screening calendar."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        upsert_profile(conn, uid, date_of_birth=date_of_birth, sex=sex,
                       blood_type=blood_type or None, height_cm=height_cm,
                       emergency_contact=emergency_contact or None)
    return _j({"ok": True})


def record_allergy(allergen: str, reaction: str = "", severity: str = "",
                   verified: bool = False, allergen_type: str = "") -> str:
    """Add an allergy (auto-approved). verified=false is still treated as an allergy (fail-safe)."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        aid = add_allergy(conn, uid, allergen, reaction=reaction or None,
                          severity=severity or None, verified=verified,
                          allergen_type=allergen_type or None)
    return _j({"id": aid})


def record_diagnosis(diagnosis_name: str, diagnosed_at: str, icd10_code: str = "",
                     clinical_status: str = "active",
                     verification_status: str = "confirmed", severity: str = "") -> str:
    """Add a diagnosis. verification_status: suspected/differential/provisional/confirmed/refuted.
    Advice is built only on confirmed."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        did = add_diagnosis(conn, uid, diagnosis_name, diagnosed_at=diagnosed_at,
                            icd10_code=icd10_code or None, clinical_status=clinical_status,
                            verification_status=verification_status, severity=severity or None)
    return _j({"id": did})


def record_medication(medication_name: str, start_date: str, dose_amount: float | None = None,
                      dose_unit: str = "", times_per_day: float | None = None,
                      product_type: str = "prescription", prescribed_for: str = "",
                      atc_code: str = "", route: str = "") -> str:
    """Add current medications/supplements. product_type: prescription/otc/supplement/herbal."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        mid = add_medication(conn, uid, medication_name, start_date=start_date,
                             dose_amount=dose_amount, dose_unit=dose_unit or None,
                             route=route or None, times_per_day=times_per_day,
                             product_type=product_type, prescribed_for=prescribed_for or None,
                             atc_code=atc_code or None)
    return _j({"id": mid})


def update_medication(medication_id: str, medication_name: str = "",
                      dose_amount: float | None = None, dose_unit: str = "",
                      times_per_day: float | None = None, route: str = "",
                      product_type: str = "", prescribed_for: str = "", atc_code: str = "",
                      start_date: str = "") -> str:
    """Correct a recorded medication; empty arguments are left unchanged."""
    changes = dict(medication_name=medication_name, dose_amount=dose_amount,
                   dose_unit=dose_unit, times_per_day=times_per_day, route=route,
                   product_type=product_type, prescribed_for=prescribed_for,
                   atc_code=atc_code, start_date=start_date)
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = _svc_update_medication(conn, uid, medication_id,
                                     {k: (None if v == "" else v) for k, v in changes.items()})
    return _j(out)


def stop_medication(medication_id: str, end_date: str = "", stop_reason: str = "",
                    side_effects: str = "") -> str:
    """Mark a medication as stopped (end_date defaults to today)."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = _svc_stop_medication(conn, uid, medication_id,
                                   end_date=end_date or date.today().isoformat(),
                                   stop_reason=stop_reason or None,
                                   side_effects=side_effects or None)
    return _j(out)


def log_meal(description: str, meal_type: str = "", eaten_at: str = "", portion: str = "",
             nutrients: dict | None = None, glycemic_index: int | None = None,
             glycemic_load: float | None = None, symptoms: str = "", wellbeing: str = "",
             nutrient_source: str = "model_estimate", notes: str = "") -> str:
    """Log a meal into the diary (auto-approved).

    description — the meal description (required). meal_type: breakfast/lunch/dinner/snack/drink.
    eaten_at — ISO 'YYYY-MM-DD HH:MM' (default — now).
    nutrients — a dict {code: amount} per the nutrient_types reference, e.g.
    {"energy_kcal":350,"protein":12,"carbs":60,"fat":7,"fiber":5,"vitamin_c":8,"iron":2,
    "sodium":400,"calcium":150,"water":250,...}. The calories+macros+vitamins+minerals estimate
    is made by the model (including from a photo). glycemic_index (0-100)/glycemic_load — per meal.
    symptoms/wellbeing — reaction after eating (good/neutral/bloating/pain/nausea/heartburn).
    Review — query_food; daily norms — query_nutrition. Returns id + unknown_codes (nutrients
    outside the reference)."""
    eat = datetime.fromisoformat(eaten_at) if eaten_at else datetime.now()
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = add_food_log(conn, uid, description, eaten_at=eat, meal_type=meal_type or None,
                           portion=portion or None, nutrients=nutrients,
                           glycemic_index=glycemic_index, glycemic_load=glycemic_load,
                           symptoms=symptoms or None, wellbeing=wellbeing or None,
                           nutrient_source=nutrient_source or "model_estimate",
                           notes=notes or None)
    return _j(out)


def update_meal(food_log_id: str, eaten_at: str = "", meal_type: str = "",
                description: str = "", portion: str = "", nutrients: dict | None = None,
                glycemic_index: int | None = None, glycemic_load: float | None = None,
                symptoms: str = "", wellbeing: str = "", notes: str = "") -> str:
    """Correct a logged meal; empty arguments are left unchanged."""
    changes = dict(eaten_at=eaten_at, meal_type=meal_type, description=description,
                   portion=portion, glycemic_index=glycemic_index, glycemic_load=glycemic_load,
                   symptoms=symptoms, wellbeing=wellbeing, notes=notes)
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = _svc_update_meal(conn, uid, food_log_id,
                               {k: (None if v == "" else v) for k, v in changes.items()},
                               nutrients=nutrients)
    return _j(out)


def delete_meal(food_log_id: str) -> str:
    """Remove a logged meal (soft delete)."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = _svc_delete_meal(conn, uid, food_log_id)
    return _j(out)


def save_meal_template(name: str, meal_type: str = "", description: str = "",
                       nutrients: dict | None = None, glycemic_index: int | None = None) -> str:
    """Save a template for a frequent meal (by name). nutrients — {code: amount} per 1 portion.
    Then logged in one call via log_from_template(name)."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        tid = _svc_save_meal_template(conn, uid, name, meal_type=meal_type or None,
                                      description=description or None, nutrients=nutrients,
                                      glycemic_index=glycemic_index)
    return _j({"id": tid, "name": name})


def log_from_template(name: str, portion_factor: float = 1.0, eaten_at: str = "",
                      wellbeing: str = "", symptoms: str = "") -> str:
    """Log a meal from a saved template (nutrients × portion_factor).
    eaten_at=ISO (default — now). Quick entry of frequent meals in one call."""
    eat = datetime.fromisoformat(eaten_at) if eaten_at else datetime.now()
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = _svc_log_from_template(conn, uid, name, eaten_at=eat,
                                     portion_factor=portion_factor,
                                     wellbeing=wellbeing or None, symptoms=symptoms or None)
    return _j(out)


def stage_lab_panel(panel_date: str, rows: list[dict], panel_type: str = "",
                    facility: str = "") -> str:
    """Stage a lab panel extracted from a form (goes in as PENDING for review).

    rows — a list of objects: {"raw_name": "Холестерол загальний", "value": 5.8,
    "unit": "mmol/L", "ref_min": 0, "ref_max": 5.2}. value_text — for qualitative ('не виявлено').
    Each row is normalized; critical values are alerted immediately. Unknown names / a failed
    unit-gate are marked in note. Then show the user the table and wait for an explicit approve_staged."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = stage_panel(conn, uid, panel_date, rows, panel_type=panel_type or None,
                          facility=facility or None, alerter=send_critical_alert)
    return _j(out)


def map_pending_observation(observation_id: str, type_code: str,
                            learn_synonym: bool = True) -> str:
    """Assign a marker type to a pending row (unmapped or matched to the wrong type), after the
    user confirmed which marker it is. Re-normalizes the value, re-checks critical values and
    saves the printed name as a learned synonym. The row stays pending until approve."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = _svc_map_pending(conn, uid, observation_id, type_code,
                               learn_synonym=learn_synonym, alerter=send_critical_alert)
    return _j(out)


def approve_staged_source(source_id: str, allow_missing_canonical: bool = False) -> str:
    """Approve a staged panel/source (a SEPARATE explicit action — only on a direct instruction
    from the user in the current message). Moves pending → approved."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = approve_staged(conn, uid, source_id,
                             allow_missing_canonical=allow_missing_canonical)
    return _j(out)
