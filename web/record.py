"""The medical-record pages' data (#57): timeline, medications, diagnoses, habits.

Plain data from the record, no model output. A lab panel with a value still under review says so
(it must not read as a finished result), and the only computed figure is arithmetic on what was
recorded: the days a medication or a habit ran, and the recorded paracetamol per day — the same
deterministic sum check_medication_safety does, never an interaction or safety verdict.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from sqlalchemy import text

from core import queries as q
from mcp_server.tools import _dose_mg
from safety.critical_values import LANGUAGES
from safety.interactions import (
    PARACETAMOL_MAX_DAILY_MG,
    check_paracetamol_load,
    is_paracetamol,
)

# a diagnosis that is still active but has had no change recorded for this long is worth a look
REVIEW_AFTER_DAYS = 730
ACTIVE_CLINICAL = ("active", "recurrence", "relapse")
VERIFICATION_ORDER = ("confirmed", "provisional", "differential", "suspected", "refuted")

# health_timeline kind → the lane it is drawn in. Medications come from their own table as
# periods (start → stop), so their start and stop events are not points here.
LANES = {
    "diagnosis": "diagnoses",
    "visit": "care",
    "procedure": "care",
    "hospital": "care",
    "panel": "labs",
    "vaccination": "vaccinations",
    "document": "documents",
}


def _number(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _today(conn) -> date:
    return conn.execute(text("SELECT current_date")).scalar()


def _born(conn, uid) -> date | None:
    return conn.execute(text("SELECT date_of_birth FROM user_profile WHERE user_id=:u"),
                        {"u": uid}).scalar()


def _medication_rows(conn, uid) -> list[dict]:
    rows = conn.execute(text(
        """SELECT id, medication_name AS name, product_type, dose_amount, dose_unit, route,
                  times_per_day, dosing_pattern, atc_code, start_date, end_date, status,
                  prescribed_for, stop_reason, side_effects
           FROM medications WHERE user_id=:u AND deleted_at IS NULL
           ORDER BY start_date DESC, medication_name, id"""), {"u": uid}).mappings().all()
    return [{**r, "id": str(r["id"]), "dose_amount": _number(r["dose_amount"]),
             "times_per_day": _number(r["times_per_day"])} for r in rows]


def _habit_rows(conn, uid) -> list[dict]:
    rows = conn.execute(text(
        """SELECT id, habit_type, status, frequency, cigarettes_per_day, smoking_years,
                  drinks_per_week, start_date, end_date, notes
           FROM v_habits WHERE user_id=:u
           ORDER BY status = 'current' DESC, start_date DESC NULLS LAST, habit_type, id"""),
        {"u": uid}).mappings().all()
    return [{**r, "id": str(r["id"]), "drinks_per_week": _number(r["drinks_per_week"])}
            for r in rows]


def _allergies(conn, uid) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        """SELECT allergen, allergen_type, reaction, severity, verified, notes FROM v_allergies
           WHERE user_id=:u ORDER BY verified DESC, allergen, id"""), {"u": uid}).mappings()]


# ------------------------------------------------------------------------------------- timeline

def _events(conn, uid, names: dict) -> list[dict]:
    """Every point event: the timeline view (minus medication starts and stops) plus documents,
    each with what its own table adds."""
    rows = conn.execute(text(
        """SELECT t.kind, t.id, (t.at AT TIME ZONE 'UTC')::date AS date, t.title,
                  d.icd10_code, d.verification_status, d.clinical_status,
                  v.disease, v.dose_number,
                  h.discharge_date,
                  pr.procedure_type,
                  vf.name AS facility,
                  p.facility AS panel_facility,
                  p.n_values, p.n_pending, p.n_out, p.codes
           FROM health_timeline t
           LEFT JOIN diagnoses d ON t.kind = 'diagnosis' AND d.id = t.id
           LEFT JOIN vaccinations v ON t.kind = 'vaccination' AND v.id = t.id
           LEFT JOIN hospital_stays h ON t.kind = 'hospital' AND h.id = t.id
           LEFT JOIN procedures pr ON t.kind = 'procedure' AND pr.id = t.id
           LEFT JOIN doctor_visits dv ON t.kind = 'visit' AND dv.id = t.id
           LEFT JOIN facilities vf ON vf.id = COALESCE(dv.facility_id, h.facility_id,
                                                       pr.facility_id, v.facility_id)
           LEFT JOIN LATERAL (
               SELECT f.name AS facility,
                      count(*) AS n_values,
                      count(*) FILTER (WHERE o.review_status = 'pending') AS n_pending,
                      count(*) FILTER (WHERE o.review_status = 'approved'
                                         AND o.status IN ('low', 'high', 'critical')) AS n_out,
                      array_agg(DISTINCT ot.code ORDER BY ot.code)
                          FILTER (WHERE o.review_status = 'approved') AS codes
               FROM panels pp
               JOIN observations o ON o.panel_id = pp.id AND o.deleted_at IS NULL
               LEFT JOIN observation_types ot ON ot.id = o.type_id
               LEFT JOIN facilities f ON f.id = pp.facility_id
               WHERE t.kind = 'panel' AND pp.id = t.id
               GROUP BY f.name) p ON true
           WHERE t.user_id = :u AND t.kind NOT IN ('medication_start', 'medication_stop')
           ORDER BY t.at, t.kind, t.id"""), {"u": uid}).mappings().all()
    events = []
    for r in rows:
        kind = r["kind"]
        event = {"kind": kind, "lane": LANES.get(kind, "care"), "id": str(r["id"]),
                 "date": r["date"], "title": r["title"]}
        if kind == "diagnosis":
            event |= {"icd10": r["icd10_code"], "verification": r["verification_status"],
                      "clinical": r["clinical_status"]}
        elif kind == "vaccination":
            event |= {"disease": r["disease"], "dose_number": r["dose_number"]}
        elif kind == "hospital":
            event |= {"end": r["discharge_date"]}
        elif kind == "procedure":
            event |= {"procedure_type": r["procedure_type"]}
        elif kind == "panel":
            # values under review are not facts: the panel says how many, and links only to the
            # markers that have an approved value in it
            event |= {"values": r["n_values"] or 0, "pending": r["n_pending"] or 0,
                      "out_of_range": r["n_out"] or 0,
                      "markers": [{"code": c, "name": names.get(c, c)} for c in r["codes"] or []],
                      "facility": r["panel_facility"]}
        if kind != "panel":
            event["facility"] = r["facility"]
        events.append(event)
    docs = conn.execute(text(
        """SELECT id, document_date AS date, COALESCE(title, doc_type) AS title, doc_type
           FROM documents WHERE user_id=:u AND deleted_at IS NULL AND document_date IS NOT NULL
           ORDER BY document_date, id"""), {"u": uid}).mappings().all()
    events += [{"kind": "document", "lane": "documents", "id": str(d["id"]), "date": d["date"],
                "title": d["title"], "doc_type": d["doc_type"]} for d in docs]
    events.sort(key=lambda e: (e["date"], e["kind"], e["id"]))
    return events


def timeline(conn, lang: str = "en") -> dict:
    lang = lang if lang in LANGUAGES else "en"
    uid = q.user_id(conn)
    today = _today(conn)
    if uid is None:
        return {"today": today, "born": None, "events": [], "periods": [], "undated_habits": 0}
    periods = [{"kind": "medication", "lane": "medications", "id": m["id"], "title": m["name"],
                "start": m["start_date"], "end": m["end_date"],
                "ongoing": m["status"] == "taking" and m["end_date"] is None,
                "status": m["status"], "product_type": m["product_type"],
                "detail": _dose_text(m), "stop_reason": m["stop_reason"]}
               for m in _medication_rows(conn, uid)]
    habits = [h for h in _habit_rows(conn, uid) if h["status"] in ("current", "former")]
    periods += [{"kind": "habit", "lane": "habits", "id": h["id"], "title": h["habit_type"],
                 "start": h["start_date"], "end": h["end_date"],
                 "ongoing": h["status"] == "current" and h["end_date"] is None,
                 "status": h["status"], "detail": h["frequency"]}
                for h in habits if h["start_date"]]
    periods.sort(key=lambda p: (p["lane"], p["start"], p["title"]))
    return {"today": today, "born": _born(conn, uid), "events": _events(conn, uid, q.marker_names(conn, lang)),
            "periods": periods,
            # a habit without a start date has no place on an axis: say how many are left out
            "undated_habits": sum(1 for h in habits if not h["start_date"])}


def _dose_text(m: dict) -> str | None:
    """"500 mg × 2/day, oral" — only what was recorded."""
    dose = " ".join(x for x in (_plain_number(m["dose_amount"]), m["dose_unit"]) if x)
    if dose and m["times_per_day"]:
        dose += f" × {_plain_number(m['times_per_day'])}/day"
    return ", ".join(x for x in (dose, m["route"]) if x) or None


def _plain_number(value) -> str | None:
    if value is None:
        return None
    return f"{value:g}"


# ---------------------------------------------------------------------------------- medications

def paracetamol(current: list[dict]) -> dict | None:
    """The recorded paracetamol per day across current medications: the same products, dose
    conversion (mg or g) and sum check_medication_safety uses, so the page and the MCP tool give
    one number. A product without a dose it can convert is named, never counted as 0 (that would
    read as less than it is). None when no current medication is paracetamol. No verdict below
    the limit: a sum, not reassurance."""
    products = [m for m in current if is_paracetamol(m["name"], m["atc_code"])]
    if not products:
        return None
    load = check_paracetamol_load([
        {"name": m["name"], "mg_per_dose": _dose_mg(m), "doses_per_day": m["times_per_day"]}
        for m in products])
    return {"products": load.products, "mg_per_day": round(load.total_mg_per_day) or None,
            "missing_dose": load.missing_dose, "limit_mg": PARACETAMOL_MAX_DAILY_MG,
            "over_limit": load.level == "exceeded"}


def medications(conn, lang: str = "en") -> dict:
    uid = q.user_id(conn)
    today = _today(conn)
    if uid is None:
        return {"today": today, "allergies": [], "current": [], "past": [], "paracetamol": None}
    rows = _medication_rows(conn, uid)
    for m in rows:
        # only a medication still taken runs to today; a stopped one with no end date has no
        # known length
        end = m["end_date"] or (today if m["status"] == "taking" else None)
        m["days"] = (end - m["start_date"]).days if end else None
    current = [m for m in rows if m["status"] == "taking"]
    past = sorted((m for m in rows if m["status"] != "taking"),
                  key=lambda m: (m["end_date"] or m["start_date"]), reverse=True)
    return {"today": today, "allergies": _allergies(conn, uid), "current": current, "past": past,
            "paracetamol": paracetamol(current)}


# ------------------------------------------------------------------------------------ diagnoses

def needs_review(d: dict, today: date) -> bool:
    """Active, believed (not refuted) and with nothing recorded about it for 2+ years. A diagnosis
    is never updated in place (there is no tool for it), so its date is when it last changed."""
    return (d["clinical_status"] in ACTIVE_CLINICAL and d["verification_status"] != "refuted"
            and d["resolved_at"] is None
            and d["diagnosed_at"] <= today - timedelta(days=REVIEW_AFTER_DAYS))


def diagnoses(conn, lang: str = "en") -> dict:
    uid = q.user_id(conn)
    today = _today(conn)
    if uid is None:
        return {"today": today, "review_after_days": REVIEW_AFTER_DAYS, "groups": []}
    rows = conn.execute(text(
        """SELECT id, diagnosis_name AS name, icd10_code, diagnosed_at, resolved_at,
                  clinical_status, verification_status, severity, notes
           FROM diagnoses WHERE user_id=:u AND deleted_at IS NULL
           ORDER BY diagnosed_at DESC, diagnosis_name, id"""), {"u": uid}).mappings().all()
    groups: dict[str, list] = {}
    for r in rows:
        d = {**r, "id": str(r["id"])}
        d["review_hint"] = needs_review(d, today)
        groups.setdefault(r["verification_status"] or "unknown", []).append(d)
    order = [*VERIFICATION_ORDER, *sorted(k for k in groups if k not in VERIFICATION_ORDER)]
    return {"today": today, "review_after_days": REVIEW_AFTER_DAYS,
            "groups": [{"verification": k, "rows": groups[k]} for k in order if k in groups]}


# --------------------------------------------------------------------------------------- habits

def habits(conn, lang: str = "en") -> dict:
    uid = q.user_id(conn)
    today = _today(conn)
    if uid is None:
        return {"today": today, "born": None, "habits": []}
    rows = _habit_rows(conn, uid)
    for h in rows:
        start, end = h["start_date"], h["end_date"]
        # days it ran, and for a habit that ended, the days since: plain date arithmetic
        # only a current habit runs to today; a former one with no end date has no known length
        until = end or (today if h["status"] == "current" else None)
        h["days"] = (until - start).days if start and until else None
        h["days_since_end"] = (today - end).days if end else None
    return {"today": today, "born": _born(conn, uid), "habits": rows}
