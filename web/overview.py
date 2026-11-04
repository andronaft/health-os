"""The Overview page's data (#54): what needs attention and the latest picture.

Everything get_health_summary says comes from core.health_summary.read_facts, the rows it renders,
so the page and the summary can't disagree. Only approved values reach the numbers and the tiles
(q.markers and q.series read v_observations); a pending value appears only in the pending list,
or in the critical list when it can't wait for its review. Plain data, no model output.
"""
from __future__ import annotations

import math
from datetime import timedelta

from sqlalchemy import text

from analytics.screening import DUE, OVERDUE
from analytics.screening import for_user as screening_for_user
from core import queries as q
from core.health_summary import STALE_MONTHS, STALE_WATCH, is_alarming, read_facts
from safety.critical_values import LANGUAGES, load_thresholds, message_for
from safety.policy import DISCLAIMER

WINDOW_DAYS = 30
AVERAGE_DAYS = 7
PENDING_ROWS = 20   # the review queue page has them all; alarming ones always show in full
EVENT_ROWS = 10

# (tile, its markers, averaged over AVERAGE_DAYS?)
TILES = [
    ("blood_pressure", ("systolic_bp", "diastolic_bp"), True),
    ("resting_hr", ("resting_hr",), False),
    ("hrv", ("hrv",), False),
    ("sleep_score", ("sleep_score",), False),
    ("weight", ("body_weight",), False),
]


def _number(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def rolling_average(points: list[tuple], days: int = AVERAGE_DAYS) -> list[tuple]:
    """[(at, value)], oldest first → one (at, mean, readings) per day with a reading: the mean of
    all readings in the `days` days ending that day. `at` is that day's last reading."""
    last_of_day = {at.date(): at for at, _ in points}
    out = []
    for day, at in last_of_day.items():
        start = day - timedelta(days=days - 1)
        window = [value for t, value in points if start <= t.date() <= day]
        out.append((at, sum(window) / len(window), len(window)))
    return out


def _tile(conn, uid, tile: str, codes: tuple, averaged: bool, latest: dict, names: dict,
          today) -> dict:
    series, values, ats, unit, readings = [], [], [], None, None
    for code in codes:
        days = WINDOW_DAYS + (AVERAGE_DAYS - 1 if averaged else 0)
        rows = [p for p in q.series(conn, uid, code, days=days)["points"]
                if _number(p["value_canonical"]) is not None]
        raw = [(p["effective_at"], _number(p["value_canonical"])) for p in rows]
        if averaged:
            since = today - timedelta(days=WINDOW_DAYS)
            shown = [(at, round(mean, 1), n) for at, mean, n in rolling_average(raw)
                     if at.date() >= since]
        else:
            shown = [(at, value, None) for at, value in raw]
        if not shown:
            continue
        at, value, n = shown[-1]
        unit = rows[-1]["canonical_unit"]
        readings = readings if n is None else max(readings or 0, n)
        ats.append(at)
        series.append({"code": code, "name": names.get(code, code),
                       "points": [{"at": a, "value": v} for a, v, _ in shown]})
        # an average has no status of its own, and a lone reading's would misdescribe it
        values.append({"code": code, "value": value,
                       "status": None if averaged else rows[-1]["status"]})
    last_recorded = None
    if not series:  # nothing in the window: say when there last was, not just "no values"
        old = [latest[c] for c in codes if c in latest and _number(latest[c]["value_canonical"])
               is not None]
        if old:
            last_recorded = {"at": max(m["effective_at"] for m in old),
                             "unit": old[0]["canonical_unit"],
                             "values": [_number(m["value_canonical"]) for m in old]}
    return {"id": tile, "average_days": AVERAGE_DAYS if averaged and series else None,
            "readings": readings, "unit": unit, "at": max(ats) if ats else None,
            "values": values, "series": series, "last_recorded": last_recorded}


def _marker_row(m: dict, names: dict) -> dict:
    return {"code": m["type_code"], "name": names.get(m["type_code"], m["type_code"]),
            "value": _number(m["value_numeric"]), "comparator": m["comparator"],
            "text": m["value_text"], "unit": m["unit"], "ref_min": _number(m["ref_min"]),
            "ref_max": _number(m["ref_max"]), "status": m["status"], "at": m["effective_at"]}


def _pending_row(p, names: dict) -> dict:
    return {"code": p["code"], "name": names.get(p["code"]) or p["raw_name"] or p["code"],
            "raw_name": p["raw_name"], "value": _number(p["value_numeric"]),
            "comparator": p["comparator"], "text": p["value_text"], "unit": p["unit"],
            "at": p["effective_at"], "critical": p["status"] == "critical",
            "unverifiable": bool(p["unverifiable"]), "unmapped": bool(p["unmapped"])}


def _critical(markers: list[dict], pending, names: dict, lang: str, conn) -> list[dict]:
    """Critical values first (approved or not), with the escalation text from safety/."""
    wanted = [m for m in markers if m["status"] == "critical"]
    alarming = [p for p in pending if is_alarming(p)]
    if not wanted and not alarming:
        return []
    message_uk = {t.type_code: t.message_uk for t in load_thresholds(conn)}
    rows = [{**_marker_row(m, names), "pending": False, "unverifiable": False,
             "message": message_for(m["type_code"], message_uk.get(m["type_code"]), lang)}
            for m in wanted]
    for p in alarming:
        critical = p["status"] == "critical"
        rows.append({**_pending_row(p, names), "pending": True,
                     "message": (message_for(p["code"], message_uk.get(p["code"]), lang)
                                 if critical else None)})
    return rows


def _screening(conn, uid) -> dict:
    calendar = screening_for_user(conn, uid)
    if "error" in calendar:
        return {"available": False, "overdue": [], "no_record": []}
    rows = [{"code": r["code"], "label": r["label"], "status": r["status"],
             "last_done": r["last_done"]} for r in calendar["recommendations"]]
    return {"available": True,
            "overdue": [r for r in rows if r["status"] == OVERDUE],
            "no_record": [r for r in rows if r["status"] == DUE]}


def overview(conn, lang: str = "en") -> dict:
    lang = lang if lang in LANGUAGES else "en"
    uid = q.user_id(conn)
    now = conn.execute(text("SELECT now()")).scalar()
    names = q.marker_names(conn, lang)
    facts = read_facts(conn, uid)
    markers = q.markers(conn, uid)
    latest = {m["type_code"]: m for m in markers}

    prof = facts["profile"]
    in_range = sum(m["status"] == "normal" for m in markers)
    out_of_range = [m for m in markers if m["status"] in ("low", "high")]
    n_critical = sum(m["status"] == "critical" for m in markers)
    pending = facts["pending"]
    ordered = sorted(pending, key=lambda p: (not is_alarming(p), not p["unmapped"]))
    last_panel_pending = bool(facts["last_panel"] and conn.execute(
        text("""SELECT EXISTS (SELECT 1 FROM observations o JOIN panels p ON p.id = o.panel_id
                               WHERE p.user_id=:u AND p.panel_date=:d
                                 AND o.review_status='pending' AND o.deleted_at IS NULL)"""),
        {"u": uid, "d": facts["last_panel"]},
    ).scalar())

    return {
        "window": {"days": WINDOW_DAYS, "from": now - timedelta(days=WINDOW_DAYS), "to": now},
        "profile": {
            "age": facts["age"],
            "sex": prof["sex"] if prof else None,
            "blood_type": prof["blood_type"] if prof else None,
            "rh_factor": prof["rh_factor"] if prof else None,
            "height_cm": _number(prof["height_cm"]) if prof else None,
            "missing": [f for f in ("date_of_birth", "sex") if not (prof and prof[f])],
        },
        "allergies": [dict(a) for a in facts["allergies"]],
        "diagnoses": [dict(d) for d in facts["diagnoses"]],
        "medications": [{**m, "dose_amount": _number(m["dose_amount"]),
                         "times_per_day": _number(m["times_per_day"])}
                        for m in facts["medications"]],
        "habits": [dict(h) for h in facts["habits"]],
        "coverage": {
            "recorded": len(markers),
            "in_range": in_range,
            "out_of_range": len(out_of_range) + n_critical,
            "no_range": len(markers) - in_range - len(out_of_range) - n_critical,
            "last_panel": facts["last_panel"],
            "last_panel_pending": last_panel_pending,
        },
        "attention": {
            "critical": _critical(markers, pending, names, lang, conn),
            "disclaimer": DISCLAIMER,
            "pending": {"total": len(pending),
                        "unmapped": sum(bool(p["unmapped"]) for p in pending),
                        "rows": [_pending_row(p, names) for p in ordered[:PENDING_ROWS]]},
            "out_of_range": [_marker_row(m, names) for m in out_of_range],
            "screening": _screening(conn, uid),
            "not_checked": {
                "months": STALE_MONTHS,
                "watched": len(STALE_WATCH),
                "rows": [{"code": s["code"], "name": names.get(s["code"], s["label"]),
                          "last": s["last"], "months": s["months"] and round(s["months"])}
                         for s in facts["stale"]],
            },
        },
        "tiles": [_tile(conn, uid, tile, codes, averaged, latest, names, now.date())
                  for tile, codes, averaged in TILES],
        "events": q.recent_events(conn, uid, EVENT_ROWS),
    }
