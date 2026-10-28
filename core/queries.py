"""Read queries shared by the MCP tools and the browser UI (#51).

Every function takes an open connection — normally on the read-only engine — and a user id,
reads only the approved views (v_*, health_timeline), and returns plain Python data. Values come
back as the driver returns them (datetime, Decimal); callers serialise (the MCP tools with
json.dumps(default=str), the web API with its own encoder). One implementation, so the chat and
the charts can never disagree.
"""
from __future__ import annotations

import difflib

from sqlalchemy import text

MAX_ROWS = 200            # MCP responses: keep tool results small
AGG_THRESHOLD_DAYS = 90   # longer windows → weekly buckets in observations()
MAX_DAYS = 36500          # 100 years is "all time"; far larger windows overflow make_interval
SERIES_MAX_ROWS = 5000    # a chart's points (a year of daily wearable data is ~365)

# name → view for the simple per-user lists
VIEWS = {
    "medications": "v_medications_current",
    "diagnoses": "v_diagnoses",
    "allergies": "v_allergies",
    "habits": "v_habits",
    "pending": "v_observations_pending",
}


def clamp_days(days) -> int:
    return max(0, min(int(days), MAX_DAYS))


def norm_code(type_code: str | None) -> str:
    return (type_code or "").strip().lower()


def user_id(conn) -> str | None:
    row = conn.execute(text("SELECT id FROM users LIMIT 1")).first()
    return str(row[0]) if row else None


def no_values_note(conn, uid: str, type_code: str) -> dict:
    """An empty result for a code the user has no values for at all ("LDL", "cholesterol") read
    exactly like "no data for this marker". Say which it is and offer the closest codes that do
    have approved values."""
    codes = [r[0] for r in conn.execute(
        text("SELECT DISTINCT type_code FROM v_observations WHERE user_id=:u"), {"u": uid})]
    if type_code in codes:
        return {"note": f"no approved values for “{type_code}” in this period"}
    close = difflib.get_close_matches(type_code, codes, n=5, cutoff=0.5)
    close += [c for c in codes if type_code and type_code in c and c not in close]
    out = {"note": f"“{type_code}” has no approved values at all — check the type_code"}
    if close:
        out["did_you_mean"] = close[:5]
    return out


def observations(conn, uid: str, type_code: str, days: int = 365) -> dict:
    """A marker's values for the MCP tool: newest first, ≤MAX_ROWS; windows over
    AGG_THRESHOLD_DAYS come back as weekly min/avg/max buckets."""
    code, days = norm_code(type_code), clamp_days(days)
    params = {"u": uid, "c": code, "d": days, "lim": MAX_ROWS}
    if days > AGG_THRESHOLD_DAYS:
        rows = conn.execute(
            text(
                """
                SELECT date_trunc('week', effective_at)::date AS week,
                       count(*) AS n,
                       round(min(value_canonical)::numeric, 3) AS min,
                       round(avg(value_canonical)::numeric, 3) AS avg,
                       round(max(value_canonical)::numeric, 3) AS max
                FROM v_observations
                WHERE user_id=:u AND type_code=:c
                  AND effective_at >= now() - make_interval(days => :d)
                GROUP BY 1 ORDER BY 1 DESC LIMIT :lim
                """
            ),
            params,
        ).mappings().all()
        out = {"type_code": code, "aggregation": "weekly", "buckets": [dict(r) for r in rows]}
    else:
        rows = conn.execute(
            text(
                """
                SELECT effective_at, value_numeric, unit, value_canonical, canonical_unit, status
                FROM v_observations
                WHERE user_id=:u AND type_code=:c
                  AND effective_at >= now() - make_interval(days => :d)
                ORDER BY effective_at DESC LIMIT :lim
                """
            ),
            params,
        ).mappings().all()
        out = {"type_code": code, "rows": [dict(r) for r in rows]}
    if not rows:
        out.update(no_values_note(conn, uid, code))
    return out


def series(conn, uid: str, type_code: str, days: int = MAX_DAYS,
           limit: int = SERIES_MAX_ROWS) -> dict:
    """A marker's points for a chart, oldest first. Each point carries its OWN reference range,
    because ranges differ between labs; one band for the whole chart would be wrong."""
    code, days = norm_code(type_code), clamp_days(days)
    rows = conn.execute(
        text(
            """SELECT effective_at, value_numeric, comparator, value_text, unit,
                      value_canonical, canonical_unit, ref_min, ref_max, status, panel_id
               FROM (SELECT * FROM v_observations
                     WHERE user_id=:u AND type_code=:c
                       AND effective_at >= now() - make_interval(days => :d)
                     ORDER BY effective_at DESC LIMIT :lim) recent
               ORDER BY effective_at ASC"""
        ),
        {"u": uid, "c": code, "d": days, "lim": max(1, int(limit))},
    ).mappings().all()
    out = {"type_code": code, "points": [dict(r) for r in rows]}
    if not rows:
        out.update(no_values_note(conn, uid, code))
    return out


def trend(conn, uid: str, type_code: str, days: int = 1825) -> dict:
    """Mann-Kendall trend over the most recent ≤500 approved values, with a per-year slope."""
    from analytics.trends import trend as _trend

    code, days = norm_code(type_code), clamp_days(days)
    rows = conn.execute(
        text(
            """SELECT value_canonical, effective_at FROM (
                 SELECT value_canonical, effective_at FROM v_observations
                 WHERE user_id=:u AND type_code=:c AND value_canonical IS NOT NULL
                   AND effective_at >= now() - make_interval(days => :d)
                 ORDER BY effective_at DESC LIMIT 500
               ) recent ORDER BY effective_at ASC"""
        ),
        {"u": uid, "c": code, "d": days},
    ).all()
    missing = no_values_note(conn, uid, code) if not rows else {}
    t = _trend([float(r[0]) for r in rows], times=[r[1] for r in rows])
    return {"type_code": code, "n": t.n, "direction": t.direction,
            "slope_per_year": (round(t.slope_per_year, 4)
                               if t.slope_per_year is not None else None),
            "detail": t.detail,
            "from": str(rows[0][1]) if rows else None,
            "to": str(rows[-1][1]) if rows else None,
            **missing}


def markers(conn, uid: str, category: str | None = None) -> list[dict]:
    """Every marker with approved values: its latest value (with that measurement's range and
    status), how many values there are and since when — the lab table's rows."""
    cat = "AND category = :cat" if category else ""
    rows = conn.execute(
        text(
            f"""WITH latest AS (
                    SELECT DISTINCT ON (type_code)
                           type_code, name_uk, category, effective_at, value_numeric, comparator,
                           value_text, unit, value_canonical, canonical_unit, ref_min, ref_max,
                           status
                    FROM v_observations WHERE user_id=:u {cat}
                    ORDER BY type_code, effective_at DESC),
                counts AS (
                    SELECT type_code, count(*) AS n, min(effective_at) AS first_at
                    FROM v_observations WHERE user_id=:u {cat} GROUP BY type_code)
                SELECT l.*, c.n, c.first_at
                FROM latest l JOIN counts c USING (type_code)
                ORDER BY l.category, l.type_code"""
        ),
        {"u": uid, "cat": category},
    ).mappings().all()
    return [dict(r) for r in rows]


def timeline(conn, uid: str, days: int = 3650, limit: int = MAX_ROWS) -> list[dict]:
    """Health events, newest first; a panel without a type is titled "lab panel"."""
    rows = conn.execute(
        text(
            """SELECT kind, at,
                      COALESCE(title, CASE kind WHEN 'panel' THEN 'lab panel' ELSE kind END)
                      AS title
               FROM health_timeline
               WHERE user_id=:u AND at >= now() - make_interval(days => :d)
               ORDER BY at DESC LIMIT :lim"""
        ),
        {"u": uid, "d": clamp_days(days), "lim": max(1, int(limit))},
    ).mappings().all()
    return [dict(r) for r in rows]


def view_rows(conn, uid: str, name: str, limit: int = MAX_ROWS) -> list[dict]:
    """The user's rows of one of VIEWS (medications, diagnoses, allergies, habits, pending)."""
    view = VIEWS[name]  # KeyError for anything else: never interpolate a caller's string
    rows = conn.execute(
        text(f"SELECT * FROM {view} WHERE user_id=:u LIMIT :lim"),
        {"u": uid, "lim": max(1, int(limit))},
    ).mappings().all()
    return [dict(r) for r in rows]
