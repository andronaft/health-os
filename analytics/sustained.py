"""Sustained deviations from the personal baseline (#75): reads the data, then runs the pure rules
of analytics.baselines on it. Shared by get_anomalies, the weekly report and the Vitals page.

Reads base tables (device_samples, physical_activities), which the read-only login can't: the
caller passes a connection on the main login, inside a read-only transaction.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text

from analytics.baselines import (
    DEFAULTS,
    SustainedParams,
    context_for,
    intraday_episodes,
    limits_text,
    resting_medians,
    sustained_days,
)

# the days before a window that a run starting before it, and that run's baseline, can need
LOOKBACK_DAYS = 2 * DEFAULTS.baseline_days


def db_zone(conn) -> ZoneInfo:
    """The zone the database writes days in: a value entered per day sits at its midnight."""
    name = conn.execute(text("SELECT current_setting('TimeZone')")).scalar()
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def daily_values(conn, uid, codes, since: date, until: date, tz: ZoneInfo,
                 day_zone: ZoneInfo) -> dict[str, dict[date, float]]:
    """code → {day: the day's mean}. A timed value's day is its date in the user's zone; a value
    entered per day keeps the day it was written for (as the Vitals page reads them)."""
    rows = conn.execute(text(
        """SELECT type_code, day, avg(value_canonical) AS value
           FROM (SELECT type_code, value_canonical,
                        CASE WHEN time_precision = 'datetime'
                             THEN (effective_at AT TIME ZONE :tz)::date
                             ELSE (effective_at AT TIME ZONE :day_zone)::date END AS day
                 FROM v_observations
                 WHERE user_id = :u AND type_code = ANY(:codes) AND value_canonical IS NOT NULL
                   AND effective_at >= :lo AND effective_at < :hi) v
           WHERE day BETWEEN :since AND :until
           GROUP BY type_code, day"""),
        {"u": uid, "codes": list(codes), "since": since, "until": until, "tz": tz.key,
         "day_zone": day_zone.key, "lo": since - timedelta(days=2),
         "hi": until + timedelta(days=2)}).all()
    out: dict[str, dict[date, float]] = {}
    for code, day, value in rows:
        if value is not None:
            out.setdefault(code, {})[day] = float(value)
    return out


def _bounds(since: date, until: date, tz: tzinfo) -> tuple[datetime, datetime]:
    return (datetime.combine(since, time.min, tz),
            datetime.combine(until + timedelta(days=1), time.min, tz))


def workouts(conn, uid, since: date, until: date, tz: tzinfo) -> list[dict]:
    lo, hi = _bounds(since, until, tz)
    rows = conn.execute(text(
        """SELECT activity_date, duration_minutes, activity_type FROM physical_activities
           WHERE user_id = :u AND deleted_at IS NULL
             AND activity_date >= :lo AND activity_date < :hi ORDER BY activity_date"""),
        {"u": uid, "lo": lo - timedelta(days=1), "hi": hi}).all()
    return [{"start": at, "minutes": minutes, "type": kind} for at, minutes, kind in rows]


def beta_blockers(conn, uid, params: SustainedParams = DEFAULTS) -> list[dict]:
    rows = conn.execute(text(
        """SELECT medication_name, atc_code, start_date FROM v_medications_current
           WHERE user_id = :u AND upper(atc_code) LIKE :atc"""),
        {"u": uid, "atc": params.beta_blocker_atc + "%"}).all()
    return [{"name": name, "atc_code": atc, "start_date": start} for name, atc, start in rows]


def _high_runs(conn, uid, lo: datetime, hi: datetime, tz: ZoneInfo, first: date,
               lines: list[float | None],
               params: SustainedParams) -> list[list[tuple[datetime, float]]]:
    """Runs of heart rate samples at or above their day's line (`lines[k]`: the line of day
    `first + k` in the user's zone; None: no baseline that day), split where a sample is below it
    or two samples are more than `max_sample_gap_minutes` apart, that last at least
    `min_minutes`. Found in the database (gaps and islands over the index-ordered samples, the
    line looked up by position, so nothing is sorted twice); only those runs' samples leave it.
    A year of samples (~250k at one per two minutes) is otherwise read and walked in Python on
    every page load. Steps and workouts are not looked at here: the pure rule re-checks each run
    with them."""
    params_sql = {"u": uid, "lo": lo, "hi": hi, "tz": tz.key, "first": first, "lines": lines,
                  "floor": min(v for v in lines if v is not None),
                  "gap": timedelta(minutes=params.max_sample_gap_minutes),
                  "min_span": timedelta(minutes=params.min_minutes),
                  "min_samples": params.min_samples}
    spans = conn.execute(text(
        """WITH s AS (
               -- most samples are below every day's line: no zone arithmetic for them
               SELECT ts, CASE WHEN value < :floor THEN false
                               ELSE value >= (CAST(:lines AS float8[]))
                                   [((ts AT TIME ZONE :tz)::date - CAST(:first AS date)) + 1]
                          END AS high
               FROM device_samples
               WHERE user_id = :u AND type_code = 'heart_rate' AND ts >= :lo AND ts < :hi
               ORDER BY ts),
           g AS (
               SELECT ts, high,
                      CASE WHEN high AND lag(high) OVER w AND ts - lag(ts) OVER w <= :gap
                           THEN 0 ELSE 1 END AS starts
               FROM s WINDOW w AS (ORDER BY ts)),
           r AS (SELECT ts, high, sum(starts) OVER (ORDER BY ts ROWS UNBOUNDED PRECEDING) AS run
                 FROM g)
           SELECT min(ts) AS lo, max(ts) AS hi FROM r WHERE high GROUP BY run
           HAVING max(ts) - min(ts) >= :min_span AND count(*) >= :min_samples
           ORDER BY lo"""), params_sql).all()
    if not spans:
        return []
    rows = conn.execute(text(
        """SELECT w.k, s.ts, s.value FROM device_samples s
           JOIN unnest(CAST(:los AS timestamptz[]), CAST(:his AS timestamptz[]))
                WITH ORDINALITY AS w(lo, hi, k) ON s.ts BETWEEN w.lo AND w.hi
           WHERE s.user_id = :u AND s.type_code = 'heart_rate'
           ORDER BY w.k, s.ts"""),
        {"u": uid, "los": [a for a, _ in spans], "his": [b for _, b in spans]}).all()
    runs: dict[int, list[tuple[datetime, float]]] = {}
    for k, ts, value in rows:
        runs.setdefault(k, []).append((ts, float(value)))
    return list(runs.values())


def _steps_near(conn, uid, spans: list[tuple[datetime, datetime]],
                margin: timedelta) -> list[tuple[datetime, float]]:
    if not spans:
        return []
    rows = conn.execute(text(
        """SELECT DISTINCT s.ts, s.value FROM device_samples s
           JOIN unnest(CAST(:los AS timestamptz[]), CAST(:his AS timestamptz[])) AS w(lo, hi)
             ON s.ts BETWEEN w.lo AND w.hi
           WHERE s.user_id = :u AND s.type_code = 'steps' AND s.value > 0"""),
        {"u": uid, "los": [lo - margin for lo, _ in spans],
         "his": [hi + margin for _, hi in spans]}).all()
    return [(ts, float(v)) for ts, v in rows]


def _has_heart_rate(conn, uid, lo: datetime, hi: datetime) -> bool:
    return bool(conn.execute(text(
        """SELECT EXISTS (SELECT 1 FROM device_samples WHERE user_id = :u
                            AND type_code = 'heart_rate' AND ts >= :lo AND ts < :hi)"""),
        {"u": uid, "lo": lo, "hi": hi}).scalar())


def workouts_recorded(conn, uid) -> bool:
    """Whether any workout is recorded at all. Without one, the minutes rule can't tell a
    step-free ride, row or gym session from sitting still, and must say so."""
    return bool(conn.execute(text(
        """SELECT EXISTS (SELECT 1 FROM physical_activities
                          WHERE user_id = :u AND deleted_at IS NULL)"""), {"u": uid}).scalar())


def intraday(conn, uid, since: date, until: date, tz: ZoneInfo, resting: dict[date, float],
             work: list[dict], meds: list[dict],
             params: SustainedParams = DEFAULTS) -> tuple[list[dict], str]:
    """The minutes rule on Apple Health raw samples between `since` and `until` (user's days):
    its episodes and whether it ran — "checked", "no_samples" (no raw heart rate in the
    window: Garmin imports daily values only) or "no_baseline" (no resting heart rate history)."""
    days = [since + timedelta(days=i) for i in range((until - since).days + 1)]
    lo, hi = _bounds(since, until, tz)
    if not _has_heart_rate(conn, uid, lo, hi):
        return [], "no_samples"
    medians = resting_medians(resting, days, params)
    if not medians:
        return [], "no_baseline"
    lines = [medians[d] + params.hr_above_resting if d in medians else None for d in days]
    runs = _high_runs(conn, uid, lo, hi, tz, since, lines, params)
    if not runs:
        return [], "checked"
    # the step records near those runs only; each run is then checked on its own by the pure
    # rule, so two runs the database split are never joined again
    spans = [(run[0][0], run[-1][0]) for run in runs]
    steps = _steps_near(conn, uid, spans, timedelta(minutes=params.step_margin_minutes))
    episodes = [e for run in runs
                for e in intraday_episodes(run, resting_by_day=medians, steps=steps, workouts=work,
                                           tz=tz, params=params)]
    for e in episodes:
        e["context"] = context_for(e["day"], e["day"], ["heart_rate"], [], meds, tz, params)
    return episodes, "checked"


def find(conn, uid, since: date, until: date, tz: ZoneInfo | None = None,
         daily: dict[str, dict[date, float]] | None = None,
         params: SustainedParams = DEFAULTS) -> dict:
    """Findings that end between `since` and `until` (days in `tz`, the database's zone if
    None), newest first: runs of days, then episodes of minutes. `daily`: the caller's own daily
    values per code, if it has them (they must reach LOOKBACK_DAYS before `since`)."""
    day_zone = db_zone(conn)
    tz = tz if isinstance(tz, ZoneInfo) else day_zone
    codes = tuple(params.daily)
    if daily is None:
        daily = daily_values(conn, uid, codes, since - timedelta(days=LOOKBACK_DAYS), until, tz,
                             day_zone)
    daily = {c: {d: v for d, v in daily.get(c, {}).items() if d <= until} for c in codes}
    work = workouts(conn, uid, since - timedelta(days=LOOKBACK_DAYS), until, tz)
    meds = beta_blockers(conn, uid, params)
    days = sustained_days(daily, since=since, workouts=work, medications=meds, tz=tz,
                          params=params)
    minutes, minutes_rule = intraday(conn, uid, since, until, tz, daily.get("resting_hr", {}),
                                     work, meds, params)
    recorded = workouts_recorded(conn, uid)
    notes = []
    if minutes_rule == "checked" and not recorded:
        notes.append("No workouts are recorded, so a step-free ride, row or gym session can't "
                     "be told apart from sitting still: it may show up as a minutes finding.")
    return {
        "from": since, "to": until, "tz": tz.key,
        "findings": sorted(days, key=lambda f: f["last_day"], reverse=True)
        + sorted(minutes, key=lambda e: e["start"], reverse=True),
        "days_with_values": {code: len(v) for code, v in daily.items()},
        "minutes_rule": minutes_rule,
        "workouts_recorded": recorded,
        "notes": notes,
        "params": params.as_dict(),
        "limits": limits_text(params),
        "wording": "Worth checking, not a diagnosis: a cold, short sleep, alcohol, travel, heat "
                   "or hard training can all do this.",
    }
