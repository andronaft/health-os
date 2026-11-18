"""Core services: manual entity entry + ingestion of a single observation.

Manual entry (profile/allergies/diagnoses/medications via a chat with any MCP client) is auto-approved,
but with provenance (channel='manual'). Observations go through normalization,
status computation from the form, and the deterministic critical-value rule-engine (plan 4.5).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from core.health_summary import read_unverifiable_approved
from core.normalize import (
    canonicalize,
    canonicalize_unit,
    compute_limit_status,
    convert_to_canonical,
    find_type,
    normalize,
    units_incompatible,
)
from safety.critical_values import (
    ABOVE,
    BELOW,
    CriticalHit,
    evaluate,
    evaluate_limit,
    load_thresholds,
)


# --------------------------------------------------------------------------- users/profile
def get_or_create_user(conn) -> str:
    row = conn.execute(text("SELECT id FROM users LIMIT 1")).first()
    if row:
        return str(row[0])
    return str(conn.execute(text("INSERT INTO users DEFAULT VALUES RETURNING id")).scalar())


# Sex is stored as "male"/"female": the screening rules compare with exactly these, and "Male"
# silently dropped the male-only screenings. Only spellings that map without guessing.
_SEX = {"male": "male", "m": "male", "чоловіча": "male", "hombre": "male",
        "female": "female", "f": "female", "жіноча": "female", "mujer": "female"}


def normalize_sex(sex) -> str:
    """"Male", " M ", "жіноча" → male/female; anything else is rejected (ValueError) with the
    accepted values, never stored as free text."""
    key = str(sex or "").strip().lower()
    if key not in _SEX:
        raise ValueError(f"sex “{sex}” is not recognised — use male or female "
                         f"(also accepted: {', '.join(k for k in _SEX if k not in _SEX.values())})")
    return _SEX[key]


def _past_date(field: str, value, *, required: bool = True) -> date | None:
    """A date that has already happened: a date object or YYYY-MM-DD. Raises ValueError with a
    message the agent can act on ("diagnosed_at 2026-02-30 is not a date")."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"{field} is required (YYYY-MM-DD)")
        return None
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        try:
            d = date.fromisoformat(str(value).strip())
        except ValueError:
            raise ValueError(f"{field} {value} is not a date (YYYY-MM-DD)") from None
    if d > date.today():
        raise ValueError(f"{field} {d} is in the future")
    return d


def upsert_profile(conn, user_id: str, *, date_of_birth, sex, blood_type=None,
                   rh_factor=None, height_cm=None, emergency_contact=None) -> None:
    """Create or overwrite the profile. A date of birth in the future gave a negative age and a
    screening calendar for it; an unrecognised sex dropped the sex-specific screenings."""
    date_of_birth = _past_date("date_of_birth", date_of_birth)
    sex = normalize_sex(sex)
    conn.execute(
        text(
            """
            INSERT INTO user_profile (user_id, date_of_birth, sex, blood_type, rh_factor,
                                      height_cm, emergency_contact, updated_at)
            VALUES (:uid, :dob, :sex, :bt, :rh, :h, :ec, now())
            ON CONFLICT (user_id) DO UPDATE SET
                date_of_birth=EXCLUDED.date_of_birth, sex=EXCLUDED.sex,
                blood_type=EXCLUDED.blood_type, rh_factor=EXCLUDED.rh_factor,
                height_cm=EXCLUDED.height_cm, emergency_contact=EXCLUDED.emergency_contact,
                updated_at=now()
            """
        ),
        dict(uid=user_id, dob=date_of_birth, sex=sex, bt=blood_type, rh=rh_factor,
             h=height_cm, ec=emergency_contact),
    )


# --------------------------------------------------------------------------- provenance
def get_or_create_channel_source(conn, user_id: str, channel: str) -> str:
    """Stable per-channel source (apple_health/strava): a repeated cumulative import
    reuses source_id so the UNIQUE on device_samples deduplicates (plan 3.9)."""
    row = conn.execute(
        text("SELECT id FROM ingestion_sources WHERE user_id=:u AND channel=:c "
             "ORDER BY created_at ASC LIMIT 1"),
        {"u": user_id, "c": channel},
    ).first()
    if row:
        return str(row[0])
    return manual_source(conn, user_id, channel=channel, review_status="approved")


def manual_source(conn, user_id: str, channel: str = "manual",
                  review_status: str = "approved") -> str:
    return str(
        conn.execute(
            text(
                """
                INSERT INTO ingestion_sources (user_id, channel, extracted_by, review_status)
                VALUES (:uid, :ch, 'human', :rs) RETURNING id
                """
            ),
            dict(uid=user_id, ch=channel, rs=review_status),
        ).scalar()
    )


# --------------------------------------------------------------------------- safety-critical entities
def _required_text(field: str, value, max_len: int) -> str:
    s = str(value or "").strip()
    if not s:
        raise ValueError(f"{field} is required")
    if len(s) > max_len:
        raise ValueError(f"{field} is longer than {max_len} characters")
    return s


def add_allergy(conn, user_id: str, allergen: str, *, allergen_type=None, reaction=None,
                severity=None, verified: bool = False, notes=None) -> str:
    """Record an allergy (auto-approved). A blank allergen used to be stored as an allergy to
    nothing; it is rejected (ValueError) like an over-long severity (the column holds 20)."""
    allergen = _required_text("allergen", allergen, 200)
    if severity is not None and len(str(severity)) > 20:
        raise ValueError("severity is longer than 20 characters — use mild / moderate / severe "
                         "and put the details into reaction")
    sid = manual_source(conn, user_id)
    return str(
        conn.execute(
            text(
                """
                INSERT INTO allergies (user_id, allergen, allergen_type, reaction, severity,
                                       verified, notes, source_id)
                VALUES (:uid, :a, :at, :r, :sev, :v, :n, :sid) RETURNING id
                """
            ),
            dict(uid=user_id, a=allergen, at=allergen_type, r=reaction, sev=severity,
                 v=verified, n=notes, sid=sid),
        ).scalar()
    )


# The two status axes (FHIR Condition). The summary and the views compare with these exact
# lower-case values: "Confirmed" or "yes" stored as typed left a diagnosis on no axis at all.
CLINICAL_STATUSES = ("active", "recurrence", "relapse", "inactive", "remission", "resolved")
VERIFICATION_STATUSES = ("confirmed", "provisional", "suspected", "differential", "refuted")


def _status(field: str, value, allowed: tuple[str, ...]) -> str:
    s = str(value or "").strip().lower()
    if s not in allowed:
        raise ValueError(f"{field} “{value}” is not one of {' / '.join(allowed)}")
    return s


def add_diagnosis(conn, user_id: str, diagnosis_name: str, *, diagnosed_at,
                  icd10_code=None, clinical_status="active",
                  verification_status="confirmed", severity=None, notes=None) -> str:
    """Record a diagnosis (auto-approved). Rejects (ValueError) an empty name, a status outside
    the two axes, and a diagnosis date that is not a real past date."""
    diagnosis_name = _required_text("diagnosis_name", diagnosis_name, 300)
    diagnosed_at = _past_date("diagnosed_at", diagnosed_at)
    clinical_status = _status("clinical_status", clinical_status, CLINICAL_STATUSES)
    verification_status = _status("verification_status", verification_status,
                                  VERIFICATION_STATUSES)
    sid = manual_source(conn, user_id)
    return str(
        conn.execute(
            text(
                """
                INSERT INTO diagnoses (user_id, diagnosed_at, diagnosis_name, icd10_code,
                                       clinical_status, verification_status, severity, notes, source_id)
                VALUES (:uid, :d, :name, :icd, :cs, :vs, :sev, :n, :sid) RETURNING id
                """
            ),
            dict(uid=user_id, d=diagnosed_at, name=diagnosis_name, icd=icd10_code,
                 cs=clinical_status, vs=verification_status, sev=severity, n=notes, sid=sid),
        ).scalar()
    )


def add_medication(conn, user_id: str, medication_name: str, *, start_date,
                   product_type="prescription", dose_amount=None, dose_unit=None,
                   route=None, times_per_day=None, dosing_pattern=None,
                   atc_code=None, prescribed_for=None, status="taking") -> str:
    sid = manual_source(conn, user_id)
    return str(
        conn.execute(
            text(
                """
                INSERT INTO medications (user_id, medication_name, product_type, dose_amount,
                    dose_unit, route, times_per_day, dosing_pattern, atc_code, start_date,
                    status, prescribed_for, source_id)
                VALUES (:uid, :name, :pt, :da, :du, :rt, :tpd, :dp, :atc, :sd, :st, :pf, :sid)
                RETURNING id
                """
            ),
            dict(uid=user_id, name=medication_name, pt=product_type, da=dose_amount,
                 du=dose_unit, rt=route, tpd=times_per_day, dp=dosing_pattern, atc=atc_code,
                 sd=start_date, st=status, pf=prescribed_for, sid=sid),
        ).scalar()
    )


# fields a correction may touch; status/end_date change only through stop_medication
MEDICATION_EDITABLE = ("medication_name", "dose_amount", "dose_unit", "route", "times_per_day",
                       "product_type", "prescribed_for", "atc_code", "start_date")


def _as_date(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _find_medication(conn, user_id: str, medication_id: str):
    try:
        uuid.UUID(str(medication_id))
    except ValueError:
        return None
    return conn.execute(
        text("""SELECT * FROM medications
                WHERE id = CAST(:id AS uuid) AND user_id = :u AND deleted_at IS NULL"""),
        {"id": medication_id, "u": user_id},
    ).mappings().first()


def _set_actor(conn, reason: str) -> None:
    # read by the medication_history trigger (migration 0012)
    conn.execute(text("SELECT set_config('app.actor', 'user', true), "
                      "set_config('app.reason', :r, true)"), {"r": reason})


def update_medication(conn, user_id: str, medication_id: str, changes: dict) -> dict:
    """Correct a recorded medication in place: a typo, a missing dose, unit, frequency or route.

    Only the given fields change (None = keep); the previous row is kept in medication_history.
    A dose the doctor changed is not a correction — stop the old entry and record a new one,
    so the timeline shows when the change happened.
    """
    unknown = sorted(set(changes) - set(MEDICATION_EDITABLE))
    if unknown:
        return {"error": f"can't change {', '.join(unknown)} — editable: "
                         f"{', '.join(MEDICATION_EDITABLE)}"}
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        return {"error": "nothing to change — pass at least one field"}
    row = _find_medication(conn, user_id, medication_id)
    if row is None:
        return {"error": "no medication with this id — take it from get_medications"}
    if "start_date" in changes:
        try:
            changes["start_date"] = _as_date(changes["start_date"])
        except ValueError:
            return {"error": "start_date must be YYYY-MM-DD"}
        if row["end_date"] and changes["start_date"] > row["end_date"]:
            return {"error": f"start_date is after the end_date {row['end_date']}"}

    _set_actor(conn, "update_medication")
    sets = ", ".join(f"{k} = :{k}" for k in changes)  # keys are whitelisted above
    conn.execute(text(f"UPDATE medications SET {sets} WHERE id = :id"),
                 {**changes, "id": row["id"]})
    return {"id": str(row["id"]),
            "changed": {k: {"from": row[k], "to": v} for k, v in changes.items()
                        if row[k] != v}}


def stop_medication(conn, user_id: str, medication_id: str, *, end_date,
                    stop_reason=None, side_effects=None) -> dict:
    """Mark a medication as no longer taken (status 'stopped' + end_date).

    It leaves v_medications_current (get_medications, the health summary, safety checks) and
    stays on the timeline as a medication_stop event. The previous row goes to medication_history.
    """
    row = _find_medication(conn, user_id, medication_id)
    if row is None:
        return {"error": "no medication with this id — take it from get_medications"}
    if row["status"] != "taking":
        return {"error": f"already {row['status']}"
                         + (f" since {row['end_date']}" if row["end_date"] else "")}
    try:
        end = _as_date(end_date)
    except ValueError:
        return {"error": "end_date must be YYYY-MM-DD"}
    if end > date.today():
        return {"error": "end_date is in the future — record the stop when it happens"}
    if end < row["start_date"]:
        return {"error": f"end_date is before the start_date {row['start_date']}"}

    _set_actor(conn, "stop_medication")
    conn.execute(
        text("""UPDATE medications SET status = 'stopped', end_date = :e,
                    stop_reason = COALESCE(:r, stop_reason),
                    side_effects = COALESCE(:se, side_effects)
                WHERE id = :id"""),
        {"e": end, "r": stop_reason, "se": side_effects, "id": row["id"]},
    )
    return {"id": str(row["id"]), "medication_name": row["medication_name"],
            "status": "stopped", "start_date": row["start_date"], "end_date": end}


# --------------------------------------------------------------------------- habits
HABIT_STATUSES = ("current", "former", "never")
# fields a correction may touch (status/end_date included: "I quit" is an update here)
HABIT_EDITABLE = ("habit_type", "status", "frequency", "cigarettes_per_day", "smoking_years",
                  "drinks_per_week", "start_date", "end_date", "notes")


_HABIT_MAX_LEN = {"habit_type": 50, "status": 50, "frequency": 100}  # column sizes


def _check_habit(fields: dict) -> str | None:
    """Validate and coerce habit fields in place; returns an error or None."""
    if fields.get("habit_type") is not None:
        fields["habit_type"] = fields["habit_type"].strip().lower()
    for k, n in _HABIT_MAX_LEN.items():
        if fields.get(k) is not None and len(fields[k]) > n:
            return f"{k} is longer than {n} characters — put details into notes"
    if fields.get("status") is not None and fields["status"] not in HABIT_STATUSES:
        return f"status must be one of {', '.join(HABIT_STATUSES)}"
    for k in ("start_date", "end_date"):
        if fields.get(k) is not None:
            try:
                fields[k] = _as_date(fields[k])
            except ValueError:
                return f"{k} must be YYYY-MM-DD"
            if fields[k] > date.today():
                return f"{k} is in the future"
    return None


def add_habit(conn, user_id: str, habit_type: str, *, status="current", frequency=None,
              cigarettes_per_day=None, smoking_years=None, drinks_per_week=None,
              start_date=None, end_date=None, notes=None) -> dict:
    """Record a habit the user reports: smoking, alcohol, cannabis, vaping… (auto-approved).

    Dates are optional — "since July" without a day is a note, not an invented date.
    """
    if not (habit_type or "").strip():
        return {"error": "habit_type is required (e.g. smoking, alcohol, cannabis)"}
    fields = {"habit_type": habit_type, "status": status, "frequency": frequency,
              "start_date": start_date, "end_date": end_date}
    err = _check_habit(fields)
    if err:
        return {"error": err}
    if fields["start_date"] and fields["end_date"] and fields["end_date"] < fields["start_date"]:
        return {"error": "end_date is before start_date"}
    sid = manual_source(conn, user_id)
    hid = conn.execute(
        text(
            """
            INSERT INTO habits (user_id, habit_type, status, frequency, cigarettes_per_day,
                                smoking_years, drinks_per_week, start_date, end_date, notes,
                                source_id)
            VALUES (:uid, :t, :s, :f, :cpd, :sy, :dpw, :sd, :ed, :n, :sid) RETURNING id
            """
        ),
        dict(uid=user_id, t=fields["habit_type"], s=fields["status"], f=frequency,
             cpd=cigarettes_per_day,
             sy=smoking_years, dpw=drinks_per_week, sd=fields["start_date"],
             ed=fields["end_date"], n=notes, sid=sid),
    ).scalar()
    return {"id": str(hid)}


def update_habit(conn, user_id: str, habit_id: str, changes: dict) -> dict:
    """Correct a habit or record a change in it ("quit in September", "now twice a week").

    Only the given fields change (None = keep).
    """
    unknown = sorted(set(changes) - set(HABIT_EDITABLE))
    if unknown:
        return {"error": f"can't change {', '.join(unknown)} — editable: "
                         f"{', '.join(HABIT_EDITABLE)}"}
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        return {"error": "nothing to change — pass at least one field"}
    try:
        uuid.UUID(str(habit_id))
    except ValueError:
        return {"error": "no habit with this id — take it from get_habits"}
    row = conn.execute(
        text("""SELECT * FROM habits
                WHERE id = CAST(:id AS uuid) AND user_id = :u AND deleted_at IS NULL"""),
        {"id": habit_id, "u": user_id},
    ).mappings().first()
    if row is None:
        return {"error": "no habit with this id — take it from get_habits"}
    err = _check_habit(changes)
    if err:
        return {"error": err}
    start = changes.get("start_date", row["start_date"])
    end = changes.get("end_date", row["end_date"])
    if start and end and end < start:
        return {"error": "end_date is before start_date"}

    sets = ", ".join(f"{k} = :{k}" for k in changes)  # keys are whitelisted above
    conn.execute(text(f"UPDATE habits SET {sets} WHERE id = :id"), {**changes, "id": row["id"]})
    return {"id": str(row["id"]),
            "changed": {k: {"from": row[k], "to": v} for k, v in changes.items()
                        if row[k] != v}}


# --------------------------------------------------------------------------- food diary
def add_food_log(conn, user_id: str, description: str, *, eaten_at, meal_type=None,
                 portion=None, nutrients: dict | None = None, glycemic_index=None,
                 glycemic_load=None, symptoms=None, wellbeing=None,
                 nutrient_source="model_estimate", notes=None) -> dict:
    """Record a meal + nutrients (auto-approved, provenance channel='manual').

    nutrients: {code: amount} per the nutrient_types catalog (energy_kcal/protein/vitamin_c/...).
    The model provides the estimate (including from a photo); the schema is source-agnostic
    (USDA-ready). Unknown codes are skipped and returned in unknown_codes (we don't invent them).
    No unit gate / critical values — hence no staging/approve, like diagnoses/medications.
    Impossible values are rejected before anything is written (see _check_meal).
    """
    err = _check_meal(eaten_at=eaten_at, nutrients=nutrients, glycemic_index=glycemic_index,
                      glycemic_load=glycemic_load)
    if err:
        return {"error": err}
    sid = manual_source(conn, user_id)
    food_id = str(
        conn.execute(
            text(
                """
                INSERT INTO food_log (user_id, eaten_at, meal_type, description, portion,
                    glycemic_index, glycemic_load, symptoms, wellbeing, nutrient_source,
                    notes, source_id)
                VALUES (:uid, :eat, :mt, :d, :p, :gi, :gl, :sym, :wb, :ns, :n, :sid)
                RETURNING id
                """
            ),
            dict(uid=user_id, eat=eaten_at, mt=meal_type, d=description, p=portion,
                 gi=glycemic_index, gl=glycemic_load, sym=symptoms, wb=wellbeing,
                 ns=nutrient_source, n=notes, sid=sid),
        ).scalar()
    )

    saved, unknown = _save_nutrients(conn, food_id, nutrients)
    out = {"id": food_id, "nutrients_saved": saved, "unknown_codes": unknown,
           "eaten_at": eaten_at}
    note = meal_time_note(eaten_at, meal_type)
    if note:
        out["time_check"] = note
    return out


# a meal may be logged a little ahead of the clock (time zones, "dinner at 21:00" said at
# 20:50); further ahead is a typo, and analytics would count it in every window until then
MEAL_FUTURE_SLACK = timedelta(days=1)


def _amount(v) -> float | None:
    """A nutrient amount as a number, or None if it isn't one (None, "12 g", NaN, True)."""
    import math
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _check_meal(*, eaten_at=None, nutrients: dict | None = None, glycemic_index=None,
                glycemic_load=None) -> str | None:
    """Values that can't be true for a meal: a time far in the future, a negative or
    non-numeric nutrient amount, a glycemic index outside 0–100, a negative glycemic load.
    They used to be stored and then summed into the daily totals (−300 g of protein)."""
    if isinstance(eaten_at, datetime):
        now = datetime.now(eaten_at.tzinfo) if eaten_at.tzinfo else datetime.now()
        if eaten_at > now + MEAL_FUTURE_SLACK:
            return (f"eaten_at {eaten_at:%Y-%m-%d %H:%M} is in the future — check the date "
                    "(when was it eaten?)")
    if glycemic_index is not None:
        gi = _amount(glycemic_index)
        if gi is None or not 0 <= gi <= 100:
            return f"glycemic_index {glycemic_index} is outside 0–100"
    if glycemic_load is not None:
        gl = _amount(glycemic_load)
        if gl is None or gl < 0:
            return f"glycemic_load {glycemic_load} must be a number ≥ 0"
    bad = [f"{k}={v}" for k, v in (nutrients or {}).items()
           if v is not None and (_amount(v) is None or _amount(v) < 0)]
    if bad:
        return (f"nutrient amounts must be numbers ≥ 0 (in the nutrient's unit): "
                f"{', '.join(bad)}")
    return None


def _save_nutrients(conn, food_id, nutrients: dict | None) -> tuple[int, list[str]]:
    """Upsert {code: amount} for one meal; unknown codes are returned, never invented."""
    saved, unknown = 0, []
    if nutrients:
        id_map = {c: nid for nid, c in
                  conn.execute(text("SELECT id, code FROM nutrient_types")).all()}
        for code, amount in nutrients.items():
            nid = id_map.get(code)
            if nid is None:
                unknown.append(code)
                continue
            if amount is None:
                continue
            conn.execute(
                text(
                    """INSERT INTO food_nutrients (food_log_id, nutrient_id, amount)
                       VALUES (:f, :nid, :a)
                       ON CONFLICT (food_log_id, nutrient_id) DO UPDATE SET amount=EXCLUDED.amount"""
                ),
                {"f": food_id, "nid": nid, "a": amount},
            )
            saved += 1
    return saved, unknown


# hours a main meal usually falls in; end is exclusive, dinner runs past midnight
_MEAL_HOURS = {"breakfast": (4, 13), "lunch": (10, 19), "dinner": (16, 28)}


def meal_time_note(eaten_at, meal_type) -> str | None:
    """A deterministic check of a main meal's time — daily nutrient totals go by its date.

    Meals logged late at night with "now" as the time land on the wrong day (a lunch at 23:30,
    yesterday's dinner at 00:16). The meal is stored as given; the note asks the model to
    confirm the time with the user and fix it with update_meal if it's wrong.
    """
    if meal_type not in _MEAL_HOURS or not isinstance(eaten_at, datetime):
        return None
    day, hm = eaten_at.date(), eaten_at.strftime("%H:%M")
    if eaten_at.hour < 4:
        return (f"{meal_type} at {hm} counts toward {day} in the daily totals — if it was "
                f"eaten on {day - timedelta(days=1)}, fix eaten_at with update_meal")
    start, end = _MEAL_HOURS[meal_type]
    if not start <= eaten_at.hour < end:
        return (f"{meal_type} at {hm} on {day} is unusual — if the time was just when it was "
                f"logged, ask when it was eaten and fix eaten_at with update_meal")
    return None


MEAL_EDITABLE = ("eaten_at", "meal_type", "description", "portion", "glycemic_index",
                 "glycemic_load", "symptoms", "wellbeing", "notes")


def _find_meal(conn, user_id: str, food_log_id: str):
    try:
        uuid.UUID(str(food_log_id))
    except ValueError:
        return None
    return conn.execute(
        text("""SELECT * FROM food_log
                WHERE id = CAST(:id AS uuid) AND user_id = :u AND deleted_at IS NULL"""),
        {"id": food_log_id, "u": user_id},
    ).mappings().first()


def update_meal(conn, user_id: str, food_log_id: str, changes: dict,
                nutrients: dict | None = None) -> dict:
    """Correct a logged meal: its time/date, type, description, portion, reaction, or the
    amounts of the given nutrients (other nutrients are kept). None = keep the field."""
    unknown = sorted(set(changes) - set(MEAL_EDITABLE))
    if unknown:
        return {"error": f"can't change {', '.join(unknown)} — editable: "
                         f"{', '.join(MEAL_EDITABLE)} and nutrients"}
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes and not nutrients:
        return {"error": "nothing to change — pass at least one field or nutrients"}
    row = _find_meal(conn, user_id, food_log_id)
    if row is None:
        return {"error": "no meal with this id — take it from query_food"}
    if "eaten_at" in changes and not isinstance(changes["eaten_at"], datetime):
        try:
            changes["eaten_at"] = datetime.fromisoformat(str(changes["eaten_at"]))
        except ValueError:
            return {"error": "eaten_at must be ISO 'YYYY-MM-DD HH:MM'"}
    err = _check_meal(eaten_at=changes.get("eaten_at"), nutrients=nutrients,
                      glycemic_index=changes.get("glycemic_index"),
                      glycemic_load=changes.get("glycemic_load"))
    if err:
        return {"error": err}

    if changes:
        sets = ", ".join(f"{k} = :{k}" for k in changes)  # keys are whitelisted above
        conn.execute(text(f"UPDATE food_log SET {sets} WHERE id = :id"),
                     {**changes, "id": row["id"]})
    saved, unknown_codes = _save_nutrients(conn, row["id"], nutrients)
    out = {"id": str(row["id"]),
           "changed": {k: {"from": row[k], "to": v} for k, v in changes.items() if row[k] != v},
           "nutrients_saved": saved, "unknown_codes": unknown_codes}
    note = meal_time_note(changes.get("eaten_at", row["eaten_at"]),
                          changes.get("meal_type", row["meal_type"]))
    if note:
        out["time_check"] = note
    return out


def delete_meal(conn, user_id: str, food_log_id: str) -> dict:
    """Remove a logged meal from the diary and the nutrient totals (soft delete)."""
    row = _find_meal(conn, user_id, food_log_id)
    if row is None:
        return {"error": "no meal with this id — take it from query_food"}
    conn.execute(text("UPDATE food_log SET deleted_at = now() WHERE id = :id"), {"id": row["id"]})
    return {"id": str(row["id"]), "deleted": True, "eaten_at": row["eaten_at"],
            "meal_type": row["meal_type"], "description": row["description"]}


def save_meal_template(conn, user_id: str, name: str, *, meal_type=None, description=None,
                       nutrients: dict | None = None, glycemic_index=None) -> str:
    """Save/update a frequent-meal template (by name, per user).

    Rejected (ValueError), so a typo isn't found only when the template is used: a nutrient
    code outside nutrient_types ("protien" used to be saved and then silently dropped from every
    meal logged from it), a non-numeric or negative amount, a glycemic index outside 0–100.
    A null amount means "not known" and is left out."""
    import json as _json
    name = _required_text("name", name, 200)
    nutrients = {k: v for k, v in (nutrients or {}).items() if v is not None}
    if nutrients:
        known = {c for (c,) in conn.execute(text("SELECT code FROM nutrient_types"))}
        unknown = sorted(set(nutrients) - known)
        if unknown:
            raise ValueError(f"unknown nutrient code(s): {', '.join(unknown)} — use the codes of "
                             f"nutrient_types (as in log_meal: energy_kcal, protein, fiber, …)")
    err = _check_meal(nutrients=nutrients, glycemic_index=glycemic_index)
    if err:
        raise ValueError(err)
    nutr = _json.dumps(nutrients) if nutrients else None
    row = conn.execute(
        text(
            """UPDATE meal_templates
                  SET meal_type=:mt, description=:d, nutrients=CAST(:n AS jsonb),
                      glycemic_index=:gi
                WHERE user_id=:u AND lower(name)=lower(:name) AND deleted_at IS NULL
                RETURNING id"""
        ),
        dict(u=user_id, name=name, mt=meal_type, d=description, n=nutr, gi=glycemic_index),
    ).first()
    if row:
        return str(row[0])
    return str(
        conn.execute(
            text(
                """INSERT INTO meal_templates (user_id, name, meal_type, description,
                       nutrients, glycemic_index)
                   VALUES (:u, :name, :mt, :d, CAST(:n AS jsonb), :gi) RETURNING id"""
            ),
            dict(u=user_id, name=name, mt=meal_type, d=description, n=nutr, gi=glycemic_index),
        ).scalar()
    )


def log_from_template(conn, user_id: str, name: str, *, eaten_at, portion_factor: float = 1.0,
                      wellbeing=None, symptoms=None) -> dict:
    """Log a meal from a template (nutrients × portion_factor). Calls add_food_log.

    A template saved before amounts were checked may hold null or text ("12 g"): those nutrients
    are left out and listed in `skipped` — they used to crash the call (TypeError/ValueError)."""
    pf = _amount(portion_factor)
    if pf is None or pf <= 0:
        return {"error": f"portion_factor {portion_factor} must be a number > 0 "
                         f"(1 = one portion, 0.5 = half)"}
    t = conn.execute(
        text(
            """SELECT meal_type, description, nutrients, glycemic_index
               FROM meal_templates
               WHERE user_id=:u AND lower(name)=lower(:name) AND deleted_at IS NULL"""
        ),
        {"u": user_id, "name": name},
    ).mappings().first()
    if not t:
        return {"error": f"template “{name}” not found"}
    base = t["nutrients"] or {}
    scaled, skipped = {}, []
    for k, v in base.items():
        x = _amount(v)
        if x is None or x < 0:
            skipped.append({"nutrient": k, "stored": v})
        else:
            scaled[k] = round(x * pf, 3)
    out = add_food_log(
        conn, user_id, t["description"] or name, eaten_at=eaten_at, meal_type=t["meal_type"],
        nutrients=scaled, glycemic_index=t["glycemic_index"], wellbeing=wellbeing,
        symptoms=symptoms,
    )
    if "error" in out:
        return out
    out["template"] = name
    out["portion_factor"] = pf
    if skipped:
        out["skipped"] = skipped
        out["skipped_note"] = ("These template amounts are empty, text or negative, so they "
                               "were not logged; fix the template with save_meal_template.")
    return out


# --------------------------------------------------------------------------- observations
@dataclass
class IngestResult:
    observation_id: str | None
    normalized: object                 # NormResult
    status: str | None
    critical: CriticalHit | None
    needs_review: bool
    note: str
    critical_unverified: bool = False  # analyte has critical thresholds, but the unit is unknown
    unmapped: bool = False             # stored pending without a type (map_pending_observation)


def ingest_observation(
    conn, user_id: str, raw_name: str, value: float | None, unit: str | None, *,
    effective_at: datetime | None = None, ref_min: float | None = None,
    ref_max: float | None = None, value_text: str | None = None,
    comparator: str | None = None,
    channel: str = "manual", review_status: str = "approved",
    panel_id: str | None = None, source_id: str | None = None,
    time_precision: str = "datetime", alerter=None,
) -> IngestResult:
    """Normalizes and records one observation; runs the critical-value rule-engine.

    Unknown name / failed unit gate → the record stays pending with a note
    (we don't guess, don't auto-approve). An unknown name, or a unit whose dimension can't belong
    to the matched type (likely a wrong/ambiguous synonym), is stored UNMAPPED: type_id NULL +
    the printed name, so it waits in the review queue for map_pending_observation instead of being
    lost — and doesn't take the matched type's slot in the panel. Critical value → forced flag +
    needs_review.
    `alerter(title, message)` — optional alert-delivery callback (in production:
    safety.alerts.send_critical_alert; not passed in tests).
    """
    effective_at = effective_at or datetime.now()
    nr = normalize(raw_name, value, unit, conn)

    if comparator is not None and comparator not in ABOVE + BELOW:
        comparator = None
    # status — from the form's range (both in the same unit by construction); a limit (">600")
    # only when the limit decides it
    status = compute_limit_status(comparator, value, ref_min, ref_max)

    # critical values — on the canonical value
    critical: CriticalHit | None = None
    limit_unverified = False
    thresholds = load_thresholds(conn) if nr.type_code else []
    if nr.type_code and nr.value_canonical is not None and nr.canonical_unit is not None:
        if comparator:
            critical, limit_unverified = evaluate_limit(
                nr.type_code, comparator, nr.value_canonical, nr.canonical_unit, thresholds)
        else:
            critical = evaluate(nr.type_code, nr.value_canonical, nr.canonical_unit, thresholds)
    # fail-safe: a critical-watch analyte whose unit we can't convert must not pass silently
    # (unless the unit says it isn't that analyte at all — then it's stored unmapped)
    watched = any(t.type_code == nr.type_code for t in thresholds)
    unit_unverified = (critical is None and value is not None and nr.conversion_missing
                       and not nr.dimension_mismatch and watched)
    # the unit says "not this analyte", but the name says a critical-watch one: the row goes in
    # unmapped, and a misread unit spelling must still not hide a critical value
    mismatch_unverified = value is not None and nr.dimension_mismatch and watched
    critical_unverified = unit_unverified or limit_unverified or mismatch_unverified
    unmapped = nr.type_id is None or nr.dimension_mismatch

    needs_review = False
    notes = []
    effective_status = review_status
    if nr.unknown_type:
        needs_review, effective_status = True, "pending"
        notes.append(f"unknown observation “{raw_name}” — stored unmapped; confirm the marker with "
                     f"the user, then map_pending_observation")
    if nr.dimension_mismatch:
        needs_review, effective_status = True, "pending"
        notes.append(f"unit “{unit}” can't belong to {nr.type_code} ({nr.canonical_unit}) — the name "
                     f"likely matched the wrong type (ambiguous synonym); stored unmapped, "
                     f"map_pending_observation to the right type")
    elif nr.conversion_missing:
        needs_review, effective_status = True, "pending"
        notes.append(f"no unit conversion “{unit}” → {nr.canonical_unit} (unit gate)")
    if critical:
        needs_review, effective_status = True, "pending"
        status = "critical"
        notes.append("CRITICAL value — forced display; " + critical.message)
        if alerter is not None:
            alerter("Health OS — critical value",
                    f"{nr.type_code} {critical.value}{critical.unit}: {critical.message}")
    if unit_unverified:
        notes.append(f"CRITICAL CHECK IMPOSSIBLE — unit “{unit}” not recognized for "
                     f"{nr.type_code}; compare the value with the form now")
        if alerter is not None:
            alerter("Health OS — verify a value",
                    f"{nr.type_code} {value} {unit}: unit not recognized, critical check impossible")
    if mismatch_unverified:
        notes.append(f"CRITICAL CHECK IMPOSSIBLE — “{raw_name}” reads as {nr.type_code}, but the "
                     f"unit “{unit}” doesn't fit it; compare the value with the form now")
        if alerter is not None:
            alerter("Health OS — verify a value",
                    f"{nr.type_code}? {value} {unit}: unit doesn't fit the marker, "
                    f"critical check impossible")
    if limit_unverified:
        needs_review, effective_status = True, "pending"
        notes.append(f"CRITICAL CHECK IMPOSSIBLE — the form gives only a limit "
                     f"({comparator}{value:g} {unit or ''}), and a critical value is past it; "
                     f"compare with the form now")
        if alerter is not None:
            alerter("Health OS — verify a value",
                    f"{nr.type_code} {comparator}{value:g} {unit or ''}: only a limit, "
                    f"critical check impossible")
    if nr.synonym_origin == "learned":
        notes.append("mapped via a learned synonym — highlight for review")

    if unmapped and value is None and value_text is None:
        return IngestResult(None, nr, status, critical, True, "; ".join(notes), unmapped=True)

    # shared panel source (source_id) or a new per-observation one
    sid = source_id or manual_source(conn, user_id, channel=channel,
                                     review_status=effective_status)
    oid = conn.execute(
        text(
            """
            INSERT INTO observations (user_id, type_id, raw_name, effective_at, time_precision,
                value_numeric, comparator, value_text, unit, value_canonical, ref_min, ref_max,
                status, review_status, source_id, panel_id, notes)
            VALUES (:uid, :tid, :raw, :eff, :tp, :vn, :cmp, :vt, :u, :vc, :rmin, :rmax, :st, :rs,
                    :sid, :pid, :notes)
            RETURNING id
            """
        ),
        dict(uid=user_id, tid=None if unmapped else nr.type_id, raw=raw_name, eff=effective_at,
             tp=time_precision, vn=value, cmp=comparator if value is not None else None,
             vt=value_text, u=unit,
             vc=None if unmapped else nr.value_canonical, rmin=ref_min, rmax=ref_max,
             st=status, rs=effective_status, sid=sid, pid=panel_id,
             # an unmapped row has no type to check it by later: the flag must live on the row
             # (health_summary.CHECK_IMPOSSIBLE_UNMAPPED_SQL reads it)
             notes="; ".join(notes) if mismatch_unverified else None),
    ).scalar()

    return IngestResult(str(oid), nr, status, critical, needs_review,
                        "; ".join(notes) or "ok", critical_unverified, unmapped)


# --------------------------------------------------------------------------- panel staging
def _get_or_create_facility(conn, user_id: str, name: str | None) -> str | None:
    if not name:
        return None
    row = conn.execute(
        text("SELECT id FROM facilities WHERE user_id=:u AND name=:n LIMIT 1"),
        {"u": user_id, "n": name},
    ).first()
    if row:
        return str(row[0])
    return str(
        conn.execute(
            text("INSERT INTO facilities (user_id, name) VALUES (:u, :n) RETURNING id"),
            {"u": user_id, "n": name},
        ).scalar()
    )


def _lab_number(v) -> float | None:
    """A number from a value or a printed string ("6,4", " 5.4", "−3"); None if it isn't one."""
    import re
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    s = str(v).strip().replace("\u2212", "-").replace(" ", "")
    if re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", s):
        return float(s.replace(",", "."))
    return None


_LIMIT_SIGNS = {"<": "<", ">": ">", "<=": "<=", ">=": ">=", "≤": "<=", "≥": ">=",
                "=<": "<=", "=>": ">="}


def _lab_limit(v: str) -> tuple[str, float] | None:
    """(comparator, number) from a printed limit: ">600", "< 10", "≤0,5", ">= 1.2"."""
    import re
    m = re.fullmatch(r"\s*(<=|>=|=<|=>|≤|≥|<|>)\s*(.+?)\s*", v)
    if not m:
        return None
    num = _lab_number(m.group(2))
    return (_LIMIT_SIGNS[m.group(1)], num) if num is not None else None


def _coerce_lab_row(r: dict) -> tuple[dict, str | None]:
    """Models pass values as printed: "6,4", "negative", "<0.5". A numeric string becomes a
    number; a limit (">600", "≤ 0,5") a number with its comparator; any other text goes to
    value_text (a qualitative result) — a string compared with a float used to crash the whole
    panel, critical rows included."""
    r = dict(r)
    note = None
    v = r.get("value")
    limit = _lab_limit(v) if isinstance(v, str) else None
    if limit:
        # ">600" (a meter's HI), "<10": a number with its comparator, so the critical check
        # runs on it — as text it used to skip the check and the "impossible" flag alike
        r["comparator"], r["value"] = limit
        note = "a limit, not an exact value"
    elif isinstance(v, str):
        num = _lab_number(v)
        if num is not None:
            r["value"] = num
        else:
            r["value"] = None
            if v.strip() and not r.get("value_text"):
                r["value_text"] = v.strip()
                note = "stored as text, not a number"
    for k in ("ref_min", "ref_max"):
        if r.get(k) is not None and not isinstance(r[k], int | float):
            r[k] = _lab_number(r[k])
    return r, note


def _check_panel_date(panel_date) -> str | None:
    from datetime import date, timedelta
    try:
        d = panel_date if isinstance(panel_date, date) else date.fromisoformat(str(panel_date)[:10])
    except ValueError:
        return "panel_date must be YYYY-MM-DD"
    if d > date.today() + timedelta(days=1):
        return f"panel_date {d} is in the future — check the year on the report"
    return None


def stage_panel(conn, user_id: str, panel_date, rows: list[dict], *,
                panel_type: str | None = None, facility: str | None = None,
                alerter=None) -> dict:
    """Stages an extracted lab panel (channel='mcp', review pending).

    rows: list of {raw_name, value?, unit?, ref_min?, ref_max?, value_text?, printed_flag?}.
    Each row goes through normalization + the critical-value rule-engine + computed confidence.
    Returns a staging summary: source_id, panel_id, per-row results, counters,
    a warning about a possible duplicate panel (logical dedup).
    """
    from sqlalchemy.exc import DBAPIError

    from ingestion.confidence import score as _confidence

    # before anything is written: an empty panel used to be created, reported as staged and
    # shown on the timeline as a lab panel with no values
    if not rows or not isinstance(rows, list):
        return {"error": "rows is empty — nothing to stage; pass the report's rows as "
                         "[{raw_name, value, unit, ref_min, ref_max}, …]"}
    date_error = _check_panel_date(panel_date)
    if date_error:
        return {"error": date_error}
    facility_id = _get_or_create_facility(conn, user_id, facility)

    # logical dedup: same date+facility+≥70% codes → warning (not a block)
    dup_warning = _check_panel_duplicate(conn, user_id, panel_date, facility_id, rows)
    source_id = manual_source(conn, user_id, channel="mcp", review_status="pending")
    panel_id = str(
        conn.execute(
            text(
                """INSERT INTO panels (user_id, panel_date, panel_type, facility_id,
                       source_id, row_count_in_document, rows_extracted)
                   VALUES (:u, :d, :pt, :f, :sid, :rc, :re) RETURNING id"""
            ),
            {"u": user_id, "d": panel_date, "pt": panel_type, "f": facility_id,
             "sid": source_id, "rc": len(rows), "re": len(rows)},
        ).scalar()
    )

    results = []
    n_critical = n_unknown = n_unit_gate = n_crit_unverified = n_wrong_type = 0
    for r in rows:
        name = str(r.get("raw_name") or "").strip() if isinstance(r, dict) else ""
        if not name:
            results.append({"raw_name": None, "stored": False,
                            "note": "no marker name — not stored"})
            continue
        r, coerce_note = _coerce_lab_row({**r, "raw_name": name})
        if r.get("value") is None and not r.get("value_text"):
            results.append({"raw_name": name, "value": None, "unit": r.get("unit"),
                            "stored": False, "note": "no value — not stored"})
            continue
        row_eff = r.get("effective_at")
        # an observation from a form is dated with the panel date (historical date, day only)
        eff = row_eff or panel_date
        tp = "datetime" if row_eff else "date"
        try:
            with conn.begin_nested():  # savepoint: one bad row must not lose the whole panel
                res = ingest_observation(
                    conn, user_id, r["raw_name"], r.get("value"), r.get("unit"),
                    ref_min=r.get("ref_min"), ref_max=r.get("ref_max"),
                    value_text=r.get("value_text"), comparator=r.get("comparator"),
                    effective_at=eff, time_precision=tp,
                    channel="mcp", review_status="pending", panel_id=panel_id,
                    source_id=source_id, alerter=alerter,
                )
        except IntegrityError as e:
            constraint = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
            # the same marker twice in one panel (e.g. fasting + 2 h glucose) — uq_obs_in_panel
            note = ("same marker already in this panel — not stored; stage it as a separate "
                    "panel (e.g. with its own time)" if constraint == "uq_obs_in_panel"
                    else f"not stored: {constraint or 'integrity error'}")
            results.append({"raw_name": name, "value": r.get("value"),
                            "unit": r.get("unit"), "stored": False, "note": note})
            continue
        except (TypeError, ValueError, ArithmeticError, DBAPIError) as e:
            # one malformed row must not lose the panel (and the alerts already sent for it)
            results.append({"raw_name": name, "value": r.get("value"),
                            "unit": r.get("unit"), "stored": False,
                            "note": f"not stored: {type(e).__name__}"})
            continue
        if res.critical:
            n_critical += 1
        if res.critical_unverified:
            n_crit_unverified += 1
        if res.normalized.unknown_type:
            n_unknown += 1
        if res.normalized.dimension_mismatch:
            n_wrong_type += 1
        elif res.normalized.conversion_missing:
            n_unit_gate += 1
        conf = _confidence(
            printed_flag=r.get("printed_flag"),
            computed_status=res.status,
            conversion_ok=not res.normalized.conversion_missing and not res.normalized.unknown_type,
            panel_complete=True,
            learned_mapping=(res.normalized.synonym_origin == "learned"),
        )
        results.append({
            "raw_name": r["raw_name"],
            "observation_id": res.observation_id,
            "stored": res.observation_id is not None,
            "matched": None if res.unmapped else res.normalized.type_code,
            **({"rejected_match": res.normalized.type_code}
               if res.normalized.dimension_mismatch else {}),
            "value": r.get("value"),
            **({"comparator": r["comparator"]} if r.get("comparator") else {}),
            **({"value_text": r["value_text"]} if r.get("value_text") else {}),
            "unit": r.get("unit"),
            "canonical": res.normalized.value_canonical,
            "status": res.status,
            "critical": bool(res.critical),
            "critical_unverified": res.critical_unverified,
            "confidence": conf.score,
            "confidence_flags": conf.flags,
            "note": f"{res.note}; {coerce_note}" if coerce_note else res.note,
        })

    hint = ("Review the table. To write to approved — approve_staged(source_id) "
            "as a separate explicit command.")
    if n_unknown or n_wrong_type:
        hint += (f" {n_unknown + n_wrong_type} row(s) are stored UNMAPPED (no marker type): ask the "
                 "user which marker each is, then map_pending_observation(observation_id, "
                 "type_code); approval skips unmapped rows.")
    return {
        "source_id": source_id,
        "panel_id": panel_id,
        "rows": results,
        "counts": {"total": len(rows), "critical": n_critical,
                   "unknown": n_unknown, "likely_wrong_type": n_wrong_type,
                   "unit_gate": n_unit_gate, "critical_unverified": n_crit_unverified},
        "duplicate_warning": dup_warning,
        "hint": hint,
    }


def _check_panel_duplicate(conn, user_id: str, panel_date, facility_id, rows: list[dict]):
    """Logical dedup (plan 3.4): same date+facility+≥70% codes → warning."""
    from core.dedup import find_duplicate
    from core.normalize import find_type

    codes = set()
    for r in rows:
        # a malformed row is reported by the row loop; here it must not lose the whole panel
        name = r.get("raw_name") if isinstance(r, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        t = find_type(name, conn)
        if t:
            codes.add(t["code"])
    if not codes:
        return None
    existing_rows = conn.execute(
        text(
            """SELECT p.id AS panel_id, p.panel_date, p.facility_id,
                      array_agg(DISTINCT ot.code) AS codes
               FROM panels p
               JOIN observations o ON o.panel_id = p.id AND o.deleted_at IS NULL
               JOIN observation_types ot ON ot.id = o.type_id
               WHERE p.user_id = :u AND p.panel_date = :d
               GROUP BY p.id, p.panel_date, p.facility_id"""
        ),
        {"u": user_id, "d": panel_date},
    ).mappings().all()
    existing = [{"panel_id": e["panel_id"], "panel_date": e["panel_date"],
                 "facility_id": str(e["facility_id"]) if e["facility_id"] else None,
                 "codes": set(e["codes"])} for e in existing_rows]
    fid = str(facility_id) if facility_id else None
    dup = find_duplicate(panel_date, fid, codes, existing)
    return {"panel_id": dup.panel_id, "reason": dup.reason} if dup else None


def approve_staged(conn, user_id: str, source_id: str, *,
                   allow_missing_canonical: bool = False) -> dict:
    """Approves a staging (a separate explicit user action, guardrail plan 4.2).

    Moves the source and all its pending typed observations to 'approved' (unmapped rows stay
    pending until map_pending_observation). Critical values
    keep status='critical' but become visible in the approved view after confirmation.

    Numeric rows without a canonical value (unit gate failed) would drop out of trends and
    analytics for good (#11), so they block the approval unless explicitly allowed.

    A source with nothing pending (approved already, or never staged — a manual entry) is an
    error, not "approved_observations: 0": a model reading 0 as success tells the user it's done.
    Approved values the critical check couldn't settle (only a limit on the form, or no canonical
    value) are returned in unverifiable_approved — approval is not a check of them.
    """
    try:
        uuid.UUID(str(source_id))
    except ValueError:
        return {"error": "source not found", "source_id": source_id}
    src = conn.execute(
        text("SELECT id FROM ingestion_sources WHERE id=:sid AND user_id=:u"),
        {"sid": source_id, "u": user_id},
    ).first()
    if not src:
        return {"error": "source not found", "source_id": source_id}
    n_pending = conn.execute(
        text("""SELECT count(*) FILTER (WHERE type_id IS NOT NULL) FROM observations
                WHERE source_id=:sid AND user_id=:u AND review_status='pending'
                  AND deleted_at IS NULL"""),
        {"sid": source_id, "u": user_id},
    ).scalar()
    unmapped = conn.execute(
        text(
            """SELECT id, raw_name FROM observations
               WHERE source_id=:sid AND user_id=:u AND review_status='pending'
                 AND deleted_at IS NULL AND type_id IS NULL"""
        ),
        {"sid": source_id, "u": user_id},
    ).all()
    if not n_pending:
        out = {"error": "nothing to approve: this source has no pending values — it was approved "
                        "already, or it isn't a staged panel", "source_id": source_id}
        if unmapped:
            out["error"] = ("nothing to approve: only unmapped rows are pending — "
                            "map_pending_observation each, then approve again")
            out["left_pending_unmapped"] = [{"observation_id": str(i), "raw_name": rn}
                                            for i, rn in unmapped]
        return out
    missing = conn.execute(
        text(
            """SELECT ot.code, o.value_numeric, o.unit
               FROM observations o JOIN observation_types ot ON ot.id = o.type_id
               WHERE o.source_id=:sid AND o.user_id=:u AND o.review_status='pending'
                 AND o.deleted_at IS NULL AND o.value_numeric IS NOT NULL
                 AND o.value_canonical IS NULL"""
        ),
        {"sid": source_id, "u": user_id},
    ).mappings().all()
    if missing and not allow_missing_canonical:
        return {
            "approved_observations": 0, "source_id": source_id,
            "blocked_without_canonical": [
                f"{m['code']} {m['value_numeric']:g} {m['unit'] or '(no unit)'}" for m in missing],
            "hint": "These values have a unit that can't be converted, so they would never show "
                    "up in trends. Fix the unit (or add a conversion) and re-stage, or approve "
                    "with allow_missing_canonical=true if that's acceptable.",
        }
    n = conn.execute(
        text(
            """UPDATE observations SET review_status='approved'
               WHERE source_id=:sid AND user_id=:u AND review_status='pending'
                 AND deleted_at IS NULL AND type_id IS NOT NULL"""
        ),
        {"sid": source_id, "u": user_id},
    ).rowcount
    # reviewed_at is when values of this source were last approved, even while unmapped rows
    # keep the source itself pending: the weekly report dates an approval by it, and without it
    # values approved today counted from the day they were staged and could fall out of the week
    conn.execute(
        text("UPDATE ingestion_sources SET reviewed_at=now(), reviewed_by='human'"
             + ("" if unmapped else ", review_status='approved'")
             + " WHERE id=:sid AND user_id=:u"),
        {"sid": source_id, "u": user_id},
    )
    out = {"approved_observations": n, "source_id": source_id}
    if missing:
        out["approved_without_canonical"] = len(missing)
    if unmapped:
        out["left_pending_unmapped"] = [{"observation_id": str(i), "raw_name": rn}
                                        for i, rn in unmapped]
        out["hint"] = ("Unmapped rows stay pending: map_pending_observation each, then approve "
                       "this source again.")
    unverifiable = read_unverifiable_approved(conn, user_id, source_id=source_id)
    if unverifiable:
        out["unverifiable_approved"] = [
            {k: u[k] for k in ("observation_id", "code", "value", "comparator", "unit", "why")}
            for u in unverifiable]
        out["warning"] = (f"{len(unverifiable)} approved value(s) could NOT be checked against "
                          "critical thresholds (only a limit on the form, or a unit that couldn't "
                          "be converted) — tell the user to compare them with the form now. They "
                          "stay listed in the health summary, and in the weekly report of the "
                          "week they were approved.")
    return out


# --------------------------------------------------------------------------- mapping unmapped rows
def map_pending_observation(conn, user_id: str, observation_id: str, type_code: str, *,
                            learn_synonym: bool = True, alerter=None) -> dict:
    """Assign a type to a pending row (unmapped, or matched to the wrong type) — #12.

    Re-normalizes the value into the type's canonical unit and re-runs the critical-value check.
    The row stays pending (approval is still a separate step). With learn_synonym the printed name
    is saved as a learned synonym, so future panels map it automatically — unless the name
    already maps to a type (seed/learned): then a second meaning would only add ambiguity.
    """
    row = conn.execute(
        text(
            """SELECT o.id, o.type_id, o.raw_name, o.value_numeric, o.comparator, o.unit,
                      o.ref_min, o.ref_max, o.status, o.panel_id, o.source_id
               FROM observations o
               WHERE o.id = CAST(:id AS uuid) AND o.user_id = :u
                 AND o.review_status = 'pending' AND o.deleted_at IS NULL"""
        ),
        {"id": observation_id, "u": user_id},
    ).mappings().first()
    if row is None:
        return {"error": "no pending observation with this id (approved rows can't be remapped)"}
    t = conn.execute(
        text("SELECT id, code, canonical_unit FROM observation_types WHERE code = :c"),
        {"c": type_code},
    ).mappings().first()
    if t is None:
        return {"error": f"unknown type_code “{type_code}” — look it up in observation_types"}

    value = float(row["value_numeric"]) if row["value_numeric"] is not None else None
    unit = canonicalize_unit(row["unit"], t["canonical_unit"])
    if value is not None and units_incompatible(unit, t["canonical_unit"]):
        return {"error": f"unit “{row['unit']}” can't belong to {type_code} "
                         f"({t['canonical_unit']}) — pick a type with a matching unit"}
    value_canonical = None
    if value is not None:
        if t["canonical_unit"] is None:
            value_canonical = value
        elif unit is not None:
            value_canonical = convert_to_canonical(t["id"], value, unit, t["canonical_unit"], conn)

    comparator = row["comparator"]
    status = compute_limit_status(comparator, value, row["ref_min"], row["ref_max"])
    thresholds = load_thresholds(conn)
    critical = None
    limit_unverified = False
    if value_canonical is not None and t["canonical_unit"] is not None:
        if comparator:
            critical, limit_unverified = evaluate_limit(
                type_code, comparator, value_canonical, t["canonical_unit"], thresholds)
        else:
            critical = evaluate(type_code, value_canonical, t["canonical_unit"], thresholds)
    if critical:
        status = "critical"
    critical_unverified = limit_unverified or (
        value is not None and value_canonical is None
        and any(th.type_code == type_code for th in thresholds))

    conn.execute(text("SELECT set_config('app.actor', 'user', true), "
                      "set_config('app.reason', 'map_pending', true)"))
    try:
        with conn.begin_nested():
            conn.execute(
                text("""UPDATE observations SET type_id = :tid, value_canonical = :vc, status = :st
                        WHERE id = :id"""),
                {"tid": t["id"], "vc": value_canonical, "st": status, "id": row["id"]},
            )
    except IntegrityError:
        return {"error": f"this panel already has a {type_code} value — the row may be a "
                         f"different marker, or a duplicate (then leave it unapproved)"}

    learned = None
    if learn_synonym and row["raw_name"]:
        existing = find_type(row["raw_name"], conn)
        if existing is None:
            conn.execute(
                text("""INSERT INTO observation_synonyms (type_id, synonym, origin, learned_from,
                                                          user_id)
                        VALUES (:tid, :syn, 'learned', :oid, :u)
                        ON CONFLICT DO NOTHING"""),
                # stored as find_type compares it: "Glucosa (método)" with its accents stripped
                # was saved as typed and never matched again
                {"tid": t["id"], "syn": canonicalize(row["raw_name"]), "oid": row["id"],
                 "u": user_id},
            )
            learned = {"saved": True}
        else:
            learned = {"saved": False,
                       "reason": f"“{row['raw_name']}” already maps to {existing['code']} "
                                 f"({existing['origin']}); not adding a second meaning"}

    if alerter is not None and critical:
        alerter("Health OS — critical value",
                f"{type_code} {critical.value}{critical.unit}: {critical.message}")
    elif alerter is not None and critical_unverified:
        alerter("Health OS — verify a value",
                f"{type_code} {value} {row['unit']}: unit not recognized, critical check impossible")

    out = {
        "observation_id": str(row["id"]),
        "type_code": type_code,
        "value": value,
        "unit": row["unit"],
        "value_canonical": value_canonical,
        "canonical_unit": t["canonical_unit"],
        "status": status,
        "critical": bool(critical),
        "critical_unverified": critical_unverified,
        "source_id": str(row["source_id"]),
        "learned_synonym": learned,
        "hint": "Still PENDING — approve via approve_staged_source(source_id) on an explicit "
                "user instruction.",
    }
    if critical:
        out["note"] = "CRITICAL value — forced display; " + critical.message
    if value is not None and value_canonical is None:
        out["note"] = (f"no unit conversion “{row['unit']}” → {t['canonical_unit']} (unit gate); "
                       "approval will ask for allow_missing_canonical")
        if critical_unverified:
            out["note"] = (f"CRITICAL CHECK IMPOSSIBLE — unit “{row['unit']}” not recognized for "
                           f"{type_code}; compare the value with the form now; " + out["note"])
    return out
