"""The Labs page's data (#55): the marker table, one marker's history, the panel matrix.

Only approved values are facts here: the table, the matrix, the chart's line, the trend and the
baseline read v_observations. A value still under review is sent apart, flagged as pending, so the
page can draw it hollow and keep it out of every number. Plain data, no model output.

Reference ranges are the ones printed on each form, in the form's unit, and differ between labs.
The chart is drawn in the marker's canonical unit, so each point's range is converted with the
same factor as its value; a range in a unit with no conversion is sent as unknown, never guessed.
"""
from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import text

from analytics.baselines import baseline
from core import queries as q
from core.normalize import canonicalize_unit
from safety.critical_values import LANGUAGES

LAB = "lab"
SPARK_POINTS = 12    # the table's sparkline: the latest values of each marker
MATRIX_DATES = 12    # the matrix's columns: the latest days with a lab value
BASELINE_MIN = 5     # like analytics.baselines.check_anomaly: no "personal norm" from 2 points
BASELINE_SIGMAS = 2
TREND_DAYS = 1825    # get_trend's default window: the chat and the page give the same trend
TREND_MIN_N = 5      # analytics.trends.trend's default: fewer values give no direction


def _number(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _day(at) -> str:
    """The date part of what the API sends for `at`: the day formatDate() shows for it."""
    return at.isoformat()[:10]


def _value(row) -> dict:
    """A value as printed on its form."""
    return {"value": _number(row["value_numeric"]), "comparator": row.get("comparator"),
            "text": row["value_text"], "unit": row["unit"]}


def _specimens(conn) -> dict[str, str | None]:
    rows = conn.execute(text("SELECT code, specimen FROM observation_types WHERE category = :c"),
                        {"c": LAB})
    return dict(rows.all())


def _sparklines(conn, uid) -> dict[str, list[dict]]:
    rows = conn.execute(text(
        """SELECT type_code, effective_at, value_canonical FROM (
               SELECT type_code, effective_at, value_canonical,
                      row_number() OVER (PARTITION BY type_code ORDER BY effective_at DESC) AS rn
               FROM v_observations
               WHERE user_id = :u AND category = :c AND value_canonical IS NOT NULL) recent
           WHERE rn <= :n ORDER BY type_code, effective_at"""),
        {"u": uid, "c": LAB, "n": SPARK_POINTS}).all()
    out = defaultdict(list)
    for code, at, value in rows:
        if _number(value) is not None:
            out[code].append({"at": at, "value": _number(value)})
    return out


def _pending_counts(conn, uid) -> dict[str, int]:
    rows = conn.execute(text(
        """SELECT p.type_code, count(*) FROM v_observations_pending p
           JOIN observation_types ot ON ot.code = p.type_code
           WHERE p.user_id = :u AND ot.category = :c GROUP BY p.type_code"""),
        {"u": uid, "c": LAB}).all()
    return dict(rows)


def _matrix(conn, uid, names: dict) -> dict:
    """Markers × the latest MATRIX_DATES days with a lab value, newest day first. A day with two
    values of one marker shows the later one."""
    rows = conn.execute(text(
        """SELECT id::text AS id, type_code, effective_at, value_numeric, comparator, value_text,
                  unit, status
           FROM v_observations WHERE user_id = :u AND category = :c
           ORDER BY effective_at"""),
        {"u": uid, "c": LAB}).mappings().all()
    days = sorted({_day(r["effective_at"]) for r in rows}, reverse=True)[:MATRIX_DATES]
    shown = set(days)
    cells: dict[str, dict] = defaultdict(dict)
    for r in rows:
        day = _day(r["effective_at"])
        if day in shown:
            cells[r["type_code"]][day] = {**_value(r), "status": r["status"], "id": r["id"]}
    return {
        "dates": days,
        "older_dates": len({_day(r["effective_at"]) for r in rows}) - len(days),
        "rows": [{"code": code, "name": names.get(code, code), "cells": cells[code]}
                 for code in sorted(cells, key=lambda c: names.get(c, c).lower())],
    }


def lab_index(conn, lang: str = "en") -> dict:
    lang = lang if lang in LANGUAGES else "en"
    uid = q.user_id(conn)
    if uid is None:
        return {"markers": [], "pending": 0, "matrix": {"dates": [], "older_dates": 0, "rows": []}}
    names = q.marker_names(conn, lang)
    specimens = _specimens(conn)
    sparks = _sparklines(conn, uid)
    pending = _pending_counts(conn, uid)
    markers = [{
        "id": m["id"],  # the latest value's: what the drawer opens
        "code": m["type_code"],
        "name": names.get(m["type_code"], m["type_code"]),
        "specimen": specimens.get(m["type_code"]),
        **_value(m),
        "ref_min": _number(m["ref_min"]),
        "ref_max": _number(m["ref_max"]),
        "status": m["status"],
        "at": m["effective_at"],
        "n": m["n"],
        "first_at": m["first_at"],
        "pending": pending.get(m["type_code"], 0),
        "spark": sparks.get(m["type_code"], []),
    } for m in q.markers(conn, uid, category=LAB)]
    return {
        "markers": markers,
        # pending lab values of markers with nothing approved yet have no row: count them all
        "pending": sum(pending.values()),
        "matrix": _matrix(conn, uid, names),
    }


def _conversions(conn, type_id: int, canonical_unit: str | None) -> dict[str, tuple]:
    """from_unit → (factor, offset) into the canonical unit; a marker's own beats a universal
    one, as in core.normalize.convert_to_canonical."""
    if canonical_unit is None:
        return {}
    rows = conn.execute(text(
        """SELECT from_unit, factor, add_offset FROM unit_conversions
           WHERE to_unit = :cu AND (type_id = :tid OR type_id IS NULL)
           ORDER BY (type_id IS NOT NULL)"""),
        {"cu": canonical_unit, "tid": type_id}).all()
    return {unit: (float(factor), float(offset or 0)) for unit, factor, offset in rows}


def band(row, canonical_unit: str | None, conversions: dict) -> dict | None:
    """The point's range on its form, in the canonical unit; None if it had none, or if its unit
    can't be converted (a band drawn in the wrong unit would misplace the value)."""
    low, high = _number(row["ref_min"]), _number(row["ref_max"])
    if low is None and high is None:
        return None
    unit = canonicalize_unit(row["unit"], canonical_unit)
    if canonical_unit is None or unit == canonical_unit:
        factor, offset = 1.0, 0.0
    elif unit in conversions:
        factor, offset = conversions[unit]
    else:
        return {"min": None, "max": None, "unconverted": True}
    def convert(v):
        return None if v is None else round(v * factor + offset, 6)

    return {"min": convert(low), "max": convert(high), "unconverted": False}


def lab_marker(conn, code: str, lang: str = "en") -> dict | None:
    """One marker's whole history for the detail chart; None if there is no such lab marker."""
    lang = lang if lang in LANGUAGES else "en"
    code = q.norm_code(code)
    kind = conn.execute(text(
        """SELECT id, canonical_unit, specimen, loinc_code FROM observation_types
           WHERE code = :c AND category = :lab"""), {"c": code, "lab": LAB}).mappings().first()
    if kind is None:
        return None
    names = q.marker_names(conn, lang)
    uid = q.user_id(conn)
    unit = kind["canonical_unit"]
    conversions = _conversions(conn, kind["id"], unit)

    def point(row, pending: bool) -> dict:
        original = {**_value(row), "ref_min": _number(row["ref_min"]),
                    "ref_max": _number(row["ref_max"])}
        return {"id": row["id"], "at": row["effective_at"],
                "value": _number(row["value_canonical"]),
                "original": original, "range": band(row, unit, conversions),
                "status": row["status"], "pending": pending}

    approved = q.series(conn, uid, code)["points"] if uid else []
    pending = conn.execute(text(
        """SELECT id::text AS id, effective_at, value_numeric, comparator, value_text, unit,
                  value_canonical, ref_min, ref_max, status
           FROM v_observations_pending WHERE user_id = :u AND type_code = :c
           ORDER BY effective_at"""), {"u": uid, "c": code}).mappings().all() if uid else []

    values = [_number(p["value_canonical"]) for p in approved if p["comparator"] is None]
    values = [v for v in values if v is not None]
    base = baseline(values) if len(values) >= BASELINE_MIN else None
    trend = q.trend(conn, uid, code, TREND_DAYS) if uid else None
    if trend:
        trend.pop("note", None)
        trend.pop("did_you_mean", None)  # the page knows the code exists: it came from the table
        trend["min_n"] = TREND_MIN_N
        trend["days"] = TREND_DAYS
    return {
        "code": code,
        "name": names.get(code, code),
        "unit": unit,
        "specimen": kind["specimen"],
        "loinc": kind["loinc_code"],
        "points": [point(p, False) for p in approved],
        # with its comparator: a pending "<10" is a limit, not 10 (the view has it since 0016)
        "pending": [point(p, True) for p in pending],
        "trend": trend,
        "baseline": {
            "n": len(values), "min_n": BASELINE_MIN, "sigmas": BASELINE_SIGMAS,
            "mean": base and round(base.mean, 6),
            "low": base and round(base.mean - BASELINE_SIGMAS * base.std, 6),
            "high": base and round(base.mean + BASELINE_SIGMAS * base.std, 6),
        },
    }
