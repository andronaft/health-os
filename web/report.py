"""The doctor-visit report's data (#60): one printable page for the doctor, in the report's own
language (the `lang` asked for, independent of the UI's).

Approved values only: every number comes from v_observations. Pending values are counted (the
report says they are left out) but never shown. The out-of-range list is q.open_results, the same
rows prepare_doctor_visit sends as still_out_of_range. "What changed" compares the latest value of
each lab marker measured since a date with its latest value before it; a change between the two is
called larger than lab noise only for the markers analytics.rcv has a cited number for.
Plain data, no model output. The user's own records (diagnosis and medication names, allergens)
are as entered, not translated.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from sqlalchemy import text

from analytics import rcv
from core import queries as q
from core.health_summary import read_facts
from safety.critical_values import LANGUAGES

DEFAULT_SINCE_DAYS = 182      # no visit on record: the last six months
TREND_CHARTS = 4
TREND_MIN_POINTS = 3
TREND_YEARS = 5
OUT_OF_RANGE = q.OUT_OF_RANGE


def _number(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def parse_since(value: str | None) -> date | None:
    """The `since` query parameter: an ISO date or nothing. ValueError for anything else."""
    if not value:
        return None
    return date.fromisoformat(value)


def _value(r) -> dict:
    return {"value": _number(r["value_numeric"]), "comparator": r["comparator"],
            "text": r["value_text"], "unit": r["unit"], "ref_min": _number(r["ref_min"]),
            "ref_max": _number(r["ref_max"]), "status": r["status"], "at": r["effective_at"]}


def _since(conn, uid, today: date, chosen: date | None) -> dict:
    last_visit = conn.execute(
        text("""SELECT max(visit_date) FROM doctor_visits
                WHERE user_id=:u AND deleted_at IS NULL AND visit_date <= :t"""),
        {"u": uid, "t": today}).scalar()
    if chosen:
        return {"date": chosen, "source": "chosen", "last_visit": last_visit}
    if last_visit:
        return {"date": last_visit, "source": "visit", "last_visit": last_visit}
    return {"date": today - timedelta(days=DEFAULT_SINCE_DAYS), "source": "default",
            "last_visit": None}


def _moved(before: str | None, after: str | None) -> str | None:
    """'into_range' / 'out_of_range' when the status crossed the range; None otherwise."""
    if before is None or after is None:
        return None
    if before in OUT_OF_RANGE and after == "normal":
        return "into_range"
    if before == "normal" and after in OUT_OF_RANGE:
        return "out_of_range"
    return None


def _comparable(r) -> float | None:
    """A value a change can be computed from: numeric, canonical, not a limit (">600")."""
    return None if r["comparator"] is not None else _number(r["value_canonical"])


def _new_results(conn, uid, since: date, names: dict) -> list[dict]:
    rows = conn.execute(
        text("""WITH after AS (
                    SELECT DISTINCT ON (type_code) *, count(*) OVER (PARTITION BY type_code) AS n
                    FROM v_observations
                    WHERE user_id=:u AND category='lab' AND effective_at >= :s
                    ORDER BY type_code, effective_at DESC),
                before AS (
                    SELECT DISTINCT ON (type_code) *
                    FROM v_observations
                    WHERE user_id=:u AND category='lab' AND effective_at < :s
                    ORDER BY type_code, effective_at DESC)
                SELECT a.type_code, a.n,
                       a.effective_at, a.value_numeric, a.comparator, a.value_text, a.unit,
                       a.value_canonical, a.ref_min, a.ref_max, a.status,
                       b.effective_at AS b_effective_at, b.value_numeric AS b_value_numeric,
                       b.comparator AS b_comparator, b.value_text AS b_value_text,
                       b.unit AS b_unit, b.value_canonical AS b_value_canonical,
                       b.ref_min AS b_ref_min, b.ref_max AS b_ref_max, b.status AS b_status
                FROM after a LEFT JOIN before b USING (type_code)"""),
        {"u": uid, "s": since}).mappings().all()
    out = []
    for r in rows:
        code = r["type_code"]
        before = None
        if r["b_effective_at"] is not None:
            before = _value({k[2:]: r[k] for k in r.keys() if k.startswith("b_")})
        change = None
        if before is not None:
            change = rcv.compare(code, _comparable({k[2:]: r[k] for k in r.keys()
                                                     if k.startswith("b_")}), _comparable(r))
        out.append({"code": code, "name": names.get(code, code), "n": r["n"], **_value(r),
                    "before": before, "moved": _moved(before and before["status"], r["status"]),
                    "change": change})
    # what crossed its range first, then out of range, then by name
    return sorted(out, key=lambda x: (x["moved"] is None, x["status"] not in OUT_OF_RANGE,
                                      x["name"].lower()))


def _medication(r) -> dict:
    return {"name": r["medication_name"], "product_type": r["product_type"],
            "dose_amount": _number(r["dose_amount"]), "dose_unit": r["dose_unit"],
            "times_per_day": _number(r["times_per_day"]), "start_date": r["start_date"],
            "end_date": r.get("end_date"), "prescribed_for": r["prescribed_for"]}


def _medication_changes(conn, uid, since: date) -> dict:
    rows = conn.execute(
        text("""SELECT medication_name, product_type, dose_amount, dose_unit, times_per_day,
                       start_date, end_date, prescribed_for, status
                FROM medications
                WHERE user_id=:u AND deleted_at IS NULL
                  AND (start_date >= :s OR (status <> 'taking' AND end_date >= :s))
                ORDER BY start_date DESC, medication_name"""),
        {"u": uid, "s": since}).mappings().all()
    return {"started": [_medication(r) for r in rows if r["start_date"] >= since],
            "stopped": [_medication(r) for r in rows
                        if r["status"] != "taking" and r["end_date"] and r["end_date"] >= since]}


def _diagnosis(r) -> dict:
    return {"name": r["diagnosis_name"], "icd10": r["icd10_code"],
            "clinical_status": r["clinical_status"],
            "verification_status": r["verification_status"], "at": r["diagnosed_at"]}


def _trends(conn, uid, markers: list[dict], first: list[str], names: dict) -> list[dict]:
    """Up to TREND_CHARTS lab markers with ≥ TREND_MIN_POINTS comparable values: the ones still
    out of range first, then the most measured."""
    labs = {m["type_code"]: m for m in markers if m["category"] == "lab"}
    order = [c for c in first if c in labs]
    order += [c for c in sorted(labs, key=lambda c: (-labs[c]["n"], c)) if c not in order]
    out = []
    for code in order:
        if len(out) == TREND_CHARTS:
            break
        rows = [p for p in q.series(conn, uid, code, days=365 * TREND_YEARS)["points"]
                if _comparable(p) is not None]
        if len(rows) < TREND_MIN_POINTS:
            continue
        last = rows[-1]
        unit = last["canonical_unit"]
        # the band is the latest form's range, and only when it is in the plotted unit
        same_unit = (last["unit"] or "").strip().lower() == (unit or "").strip().lower()
        out.append({"code": code, "name": names.get(code, code), "unit": unit,
                    "ref_min": _number(last["ref_min"]) if same_unit else None,
                    "ref_max": _number(last["ref_max"]) if same_unit else None,
                    "points": [{"at": p["effective_at"], "value": _comparable(p),
                                "status": p["status"]} for p in rows],
                    "change": rcv.compare(code, _comparable(rows[-2]), _comparable(last))})
    return out


def report(conn, lang: str = "en", since: date | None = None) -> dict:
    lang = lang if lang in LANGUAGES else "en"
    uid = q.user_id(conn)
    now = conn.execute(text("SELECT now()")).scalar()
    today = now.date()
    counts = conn.execute(
        text("""SELECT (SELECT count(*) FROM v_observations WHERE user_id=:u) AS approved,
                       (SELECT count(*) FROM observations WHERE user_id=:u
                          AND review_status='pending' AND deleted_at IS NULL) AS pending"""),
        {"u": uid}).mappings().one() if uid else {"approved": 0, "pending": 0}
    base = {"lang": lang, "generated_at": now, "approved_values": counts["approved"],
            "pending_values": counts["pending"]}
    if uid is None:
        return {**base, "empty": True}

    names = q.marker_names(conn, lang)
    facts = read_facts(conn, uid)
    prof = facts["profile"]
    window = _since(conn, uid, today, since)
    markers = q.markers(conn, uid)
    still = q.open_results(conn, uid)
    medications = q.view_rows(conn, uid, "medications")["rows"]
    diagnoses = q.view_rows(conn, uid, "diagnoses")["rows"]
    s = window["date"]

    return {
        **base,
        "empty": False,
        "profile": {
            "age": facts["age"],
            "date_of_birth": prof["date_of_birth"] if prof else None,
            "sex": prof["sex"] if prof else None,
            "blood_type": prof["blood_type"] if prof else None,
            "rh_factor": prof["rh_factor"] if prof else None,
            "height_cm": _number(prof["height_cm"]) if prof else None,
        },
        "allergies": [{"allergen": a["allergen"], "reaction": a["reaction"],
                       "severity": a["severity"], "verified": bool(a["verified"])}
                      for a in facts["allergies"]],
        "medications": [_medication(m) for m in medications],
        "diagnoses": [_diagnosis(d) for d in diagnoses],
        "out_of_range": {
            "lab_markers_seen": still["lab_markers_seen"],
            "rows": [{"code": r["type_code"], "name": names.get(r["type_code"], r["type_code"]),
                      **_value({**r, "effective_at": r["at"]}),
                      "since": r["since"], "streak": r["streak"],
                      "newer_pending": bool(r["newer_pending"])} for r in still["open"]],
        },
        "trends": _trends(conn, uid, markers, [r["type_code"] for r in still["open"]], names),
        "changes": {
            "since": s,
            "since_source": window["source"],
            "last_visit": window["last_visit"],
            "results": _new_results(conn, uid, s, names),
            "medications": _medication_changes(conn, uid, s),
            "diagnoses": [_diagnosis(d) for d in diagnoses if d["diagnosed_at"] >= s],
        },
        "rcv": {"z": rcv.Z_95, "cva_share": rcv.CVA_SHARE,
                "markers": [{"code": c, "name": names.get(c, c), "cvi": cvi,
                             "rcv": round(rcv.rcv_percent(cvi), 1), "source": src}
                            for c, (cvi, src) in rcv.WITHIN_SUBJECT_CV.items()]},
    }
