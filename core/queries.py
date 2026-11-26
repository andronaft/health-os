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

# name → (view, ORDER BY) for the simple per-user lists. A fixed order makes the row cap drop
# the oldest rows: without one, LIMIT returned whichever rows Postgres met first, and in the
# review queue that was the newest values. id breaks ties so the order is stable.
VIEWS = {
    "medications": ("v_medications_current", "start_date DESC NULLS LAST, medication_name, id"),
    "diagnoses": ("v_diagnoses", "diagnosed_at DESC NULLS LAST, diagnosis_name, id"),
    "allergies": ("v_allergies", "allergen, id"),
    "habits": ("v_habits", "start_date DESC NULLS LAST, habit_type, id"),
    "pending": ("v_observations_pending", "effective_at DESC, raw_name, id"),
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
    """A marker's values for the MCP tool, newest first. Every value as recorded (status, unit,
    range, text) while they fit in MAX_ROWS; only more than that come back as weekly
    min/avg/max buckets. Bucketing by window length alone turned the default year of a lab
    marker — a few values — into buckets without status, unit or text results."""
    code, days = norm_code(type_code), clamp_days(days)
    params = {"u": uid, "c": code, "d": days, "lim": MAX_ROWS}
    n = conn.execute(
        text("""SELECT count(*) FROM v_observations WHERE user_id=:u AND type_code=:c
                AND effective_at >= now() - make_interval(days => :d)"""),
        params,
    ).scalar()
    if n > MAX_ROWS and days > AGG_THRESHOLD_DAYS:
        rows = conn.execute(
            text(
                """
                SELECT date_trunc('week', effective_at)::date AS week,
                       count(*) AS n,
                       round(min(value_canonical)::numeric, 3) AS min,
                       round(avg(value_canonical)::numeric, 3) AS avg,
                       round(max(value_canonical)::numeric, 3) AS max,
                       max(canonical_unit) AS unit,
                       -- a bucket must not hide that a value in it was out of range
                       count(*) FILTER (WHERE status IN ('low', 'high')) AS out_of_range,
                       count(*) FILTER (WHERE status = 'critical') AS critical,
                       count(*) FILTER (WHERE value_canonical IS NULL) AS not_numeric
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
                SELECT effective_at, value_numeric, comparator, value_text, unit,
                       value_canonical, canonical_unit, ref_min, ref_max, status
                FROM v_observations
                WHERE user_id=:u AND type_code=:c
                  AND effective_at >= now() - make_interval(days => :d)
                ORDER BY effective_at DESC LIMIT :lim
                """
            ),
            params,
        ).mappings().all()
        out = {"type_code": code, "rows": [dict(r) for r in rows]}
        if n > MAX_ROWS:
            out["truncated"] = f"the latest {MAX_ROWS} of {n} values"
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
            """SELECT id::text AS id, effective_at, value_numeric, comparator, value_text, unit,
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
                   AND comparator IS NULL  -- ">600" is a limit, not a value to trend
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
            "p": round(t.p_approx, 4) if t.p_approx is not None else None,
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
                           id::text AS id, type_code, name_uk, category, effective_at,
                           value_numeric, comparator,
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


OUT_OF_RANGE = ("low", "high", "critical")


def open_results(conn, uid: str, days: int = MAX_DAYS) -> dict:
    """Lab markers whose latest approved value is out of range — nothing approved has measured
    them since. Each says since when it has been out of range in a row (`streak`: how many
    consecutive values), and whether a newer value of it is waiting for review: that one is not
    a fact yet, so its number is not shown. Lab markers only: a single high blood-pressure
    reading or a short night is no result to follow up. Oldest first — the longest unanswered."""
    rows = conn.execute(
        text(
            """WITH ranked AS (
                    SELECT type_code, effective_at, value_numeric, comparator, value_text, unit,
                           ref_min, ref_max, status,
                           row_number() OVER (PARTITION BY type_code
                                              ORDER BY effective_at DESC) AS rn
                    FROM v_observations
                    WHERE user_id=:u AND category = 'lab'
                      AND effective_at >= now() - make_interval(days => :d)),
                runs AS (  -- the first value, newest first, that breaks the out-of-range run
                    SELECT type_code, min(rn) FILTER (
                               WHERE status IS NULL OR status NOT IN ('low','high','critical')
                           ) AS break_rn, count(*) AS n
                    FROM ranked GROUP BY type_code)
               SELECT l.type_code, l.effective_at AS at, l.value_numeric, l.comparator,
                      l.value_text, l.unit, l.ref_min, l.ref_max, l.status,
                      COALESCE(r.break_rn - 1, r.n) AS streak,
                      s.effective_at AS since,
                      EXISTS (SELECT 1 FROM v_observations_pending p
                              WHERE p.user_id=:u AND p.type_code = l.type_code
                                AND p.effective_at > l.effective_at) AS newer_pending
               FROM ranked l
               JOIN runs r USING (type_code)
               JOIN ranked s ON s.type_code = l.type_code
                            AND s.rn = COALESCE(r.break_rn - 1, r.n)
               WHERE l.rn = 1 AND l.status IN ('low','high','critical')
               ORDER BY (l.status = 'critical') DESC, l.effective_at"""
        ),
        {"u": uid, "d": clamp_days(days)},
    ).mappings().all()
    seen = conn.execute(
        text("""SELECT count(DISTINCT type_code) FROM v_observations
                WHERE user_id=:u AND category = 'lab'
                  AND effective_at >= now() - make_interval(days => :d)"""),
        {"u": uid, "d": clamp_days(days)},
    ).scalar()
    return {"open": [dict(r) for r in rows], "lab_markers_seen": seen}


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


def recent_events(conn, uid: str, limit: int) -> list[dict]:
    """The latest events up to now, for the overview. A lab panel with values still under review
    is flagged: it must not read as a finished result. A panel also says how many values it has
    and how many approved ones are out of range. It takes a base table to tell, so this one
    doesn't run on the read-only login."""
    rows = conn.execute(
        text(
            """SELECT t.kind, (t.at AT TIME ZONE 'UTC')::date AS date, t.title,
                      (t.kind = 'panel' AND EXISTS (
                          SELECT 1 FROM observations o
                          WHERE o.panel_id = t.id AND o.review_status = 'pending'
                            AND o.deleted_at IS NULL)) AS pending,
                      -- a panel's size and how many of its approved values are out of range
                      CASE WHEN t.kind = 'panel' THEN (
                          SELECT count(*) FROM observations o
                          WHERE o.panel_id = t.id AND o.deleted_at IS NULL) END AS values,
                      CASE WHEN t.kind = 'panel' THEN (
                          SELECT count(*) FROM observations o
                          WHERE o.panel_id = t.id AND o.deleted_at IS NULL
                            AND o.review_status = 'approved'
                            AND o.status IN ('low', 'high', 'critical')) END AS out_of_range
               FROM health_timeline t
               WHERE t.user_id=:u AND t.at <= now()
               ORDER BY t.at DESC LIMIT :lim"""
        ),
        {"u": uid, "lim": max(1, int(limit))},
    ).mappings().all()
    return [dict(r) for r in rows]


def marker_names(conn, lang: str) -> dict[str, str]:
    """code → name in `lang`; a marker without one falls back to English, then Ukrainian."""
    rows = conn.execute(
        text("SELECT type_code, lang, name FROM v_observation_type_names "
             "WHERE lang IN ('uk', 'en', :lang)"),
        {"lang": lang},
    ).all()
    rank = {"uk": 0, "en": 1, lang: 2}
    return {code: name for code, _, name in sorted(rows, key=lambda r: rank[r[1]])}


def view_rows(conn, uid: str, name: str, limit: int = MAX_ROWS) -> dict:
    """The user's rows of one of VIEWS (medications, diagnoses, allergies, habits, pending), in
    the view's fixed order: {"rows": [...], "truncated": bool}. One extra row is fetched, so a
    capped list says it is capped instead of passing for the whole list."""
    view, order = VIEWS[name]  # KeyError for anything else: never interpolate a caller's string
    limit = max(1, int(limit))
    rows = conn.execute(
        text(f"SELECT * FROM {view} WHERE user_id=:u ORDER BY {order} LIMIT :lim"),
        {"u": uid, "lim": limit + 1},
    ).mappings().all()
    return {"rows": [dict(r) for r in rows[:limit]], "truncated": len(rows) > limit}
