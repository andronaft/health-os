"""The Vitals page's data (#56): home blood pressure by protocol, the watch's daily values, a year
of calendar heatmaps.

Only approved values (v_observations) are drawn or averaged; blood pressure readings still under
review are only counted, so the page can say they are left out. Plain data, no model output.

Home blood pressure follows the ESH protocol for home monitoring, as the 2021 position paper of
the ESH Working Group on Blood Pressure Monitoring puts it (Parati G. et al., "Home blood pressure
monitoring: methodology, clinical relevance and practical application", J Hypertens
2021;39(9):1742–1767, https://pmc.ncbi.nlm.nih.gov/articles/PMC9904446/): 3 to 7 days of
readings, 2 in the morning and 2 in the evening, the first day discarded, and the mean of the rest
compared with the home threshold of 135/85 mmHg. The paper notes that discarding day one matters
on a 3-day schedule; this page reads "at least 3 days" as 3 complete days LEFT after day one, so it
never prints a mean from fewer days than the minimum. Which clock hours count as morning and
evening is this page's own choice, not the paper's (it gives no hours): MORNING and EVENING below.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text

from core import queries as q
from safety.critical_values import LANGUAGES

WINDOWS = (7, 30, 90, 365, 1825)
DEFAULT_WINDOW = 30

# ---- home blood pressure --------------------------------------------------------------------------

BP_CODES = ("systolic_bp", "diastolic_bp")
MORNING = (4, 12)    # [from, to) local hour
EVENING = (16, 24)
DIARY_DAYS = 7        # ESH: up to 7 days; a longer run of daily readings is summarised by its last 7
DIARY_MIN_DAYS = 3    # ESH: at least 3 days (here: complete days after the discarded first one)
READINGS_PER_SESSION = 2
DIARY_GAP = 2         # days between two reading days that still belong to one diary (1 day missed)
BP_SOURCE = {
    "label": "ESH 2021 home blood pressure position paper (Parati et al., J Hypertens 2021;39:1742–1767)",
    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9904446/",
}
BP_THRESHOLD = {"systolic": 135, "diastolic": 85}  # the same paper: home BP threshold, ≥135/85
RAW_POINTS_MAX_DAYS = 90  # longer windows get weekly means per session
UNTIMED = "untimed"       # the session of a value entered per day: its time of day is unknown

# ---- the watch ------------------------------------------------------------------------------------

WEARABLE_CODES = (
    "sleep_duration", "sleep_deep", "sleep_rem", "sleep_score",
    "hrv", "resting_hr", "stress_avg", "body_battery_high", "body_battery_low",
    "steps", "intensity_minutes", "vo2max",
)
# a day with two rows of one code (two devices, a re-import): steps take the larger count (two
# step counters summed would count one walk twice), everything else the mean
DAY_AGGREGATE = {"steps": "max"}
HEATMAP_CODES = ("steps", "sleep_score", "stress_avg")
HEATMAP_DAYS = 365
# acute vs chronic load: the mean daily intensity minutes over the last 7 and the last 28 days
# (Gabbett TJ, "The training-injury prevention paradox", Br J Sports Med 2016;50:273–280). Days
# without the watch are unknown, not zero: a mean needs at least half of its days.
LOAD_CODE = "intensity_minutes"
ACUTE_DAYS, CHRONIC_DAYS = 7, 28


def _number(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def window_days(days) -> int:
    try:
        days = int(days)
    except (TypeError, ValueError):
        return DEFAULT_WINDOW
    return days if days in WINDOWS else DEFAULT_WINDOW


def bucket_for(days: int) -> str:
    """How long a window's points are: a day up to 90 days, a week up to two years, else a month."""
    if days <= RAW_POINTS_MAX_DAYS:
        return "day"
    return "week" if days <= 730 else "month"


def bucket_start(day: date, bucket: str) -> date:
    if bucket == "week":
        return day - timedelta(days=day.weekday())  # ISO weeks start on Monday, like date_trunc
    if bucket == "month":
        return day.replace(day=1)
    return day


def session_of(hour: int) -> str:
    if MORNING[0] <= hour < MORNING[1]:
        return "morning"
    if EVENING[0] <= hour < EVENING[1]:
        return "evening"
    return "other"


def parse_tz(value: str | None) -> tzinfo | None:
    """The `tz` query parameter: an IANA zone name ("Europe/Madrid") or nothing (the database's
    zone). ValueError for anything else."""
    if not value:
        return None
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ValueError(f"unknown time zone {value!r}") from e


def _db_zone(conn) -> ZoneInfo:
    """The zone the database writes days in: a value entered per day sits at its midnight."""
    name = conn.execute(text("SELECT current_setting('TimeZone')")).scalar()
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _means(readings: list[dict]) -> dict:
    return {"systolic": _mean([r["systolic"] for r in readings if r["systolic"] is not None]),
            "diastolic": _mean([r["diastolic"] for r in readings if r["diastolic"] is not None]),
            "n": len(readings)}


def _summary_window(readings: list[dict]) -> tuple[list[dict], list[date], int]:
    """A run's last DIARY_DAYS days: its readings, its reading days, and how many reading days
    came before them. Day one is the first day WITH readings in that span, so discarding it always
    discards something."""
    last = max(r["day"] for r in readings)
    start = last - timedelta(days=DIARY_DAYS - 1)
    used = [r for r in readings if r["day"] >= start]
    return used, sorted({r["day"] for r in used}), len({r["day"] for r in readings if r["day"] < start})


def summarize_diary(readings: list[dict]) -> dict:
    """One diary's protocol check. `readings`: {at, day, session, systolic, diastolic, complete},
    all of one run of reading days. Only its last DIARY_DAYS days count; the first of them is
    discarded. Only complete readings (a systolic AND a diastolic) count or are averaged; the
    rest are reported. Readings without a time of day (entered per day) can't be checked against
    the protocol: if a diary has nothing else, it says so and gives a plain mean instead."""
    used, days, earlier = _summary_window(readings)
    first, last = days[0], days[-1]
    pairs = [r for r in used if r["complete"]]
    timed = [r for r in pairs if r["session"] != UNTIMED]
    untimed = [r for r in pairs if r["session"] == UNTIMED]
    out = {
        "first_day": first,
        "last_day": last,
        "days": len(days),
        "earlier_days": earlier,
        "incomplete_readings": len(used) - len(pairs),
        "untimed_readings": len(untimed),
        "timing": "recorded",
        "followed": False,
        "mean": None,
    }
    if untimed and not timed:
        kept = [r for r in untimed if r["day"] != first]
        per_day: dict[date, int] = defaultdict(int)
        for r in untimed:
            per_day[r["day"]] += 1
        out.update({
            "timing": "unrecorded",
            "followed": None,  # unknown, not "not followed": the values may well follow it
            "per_day": [{"day": d, "values": per_day.get(d, 0)} for d in days],
            "value_days": len(per_day),
        })
        if kept:
            out["mean"] = {**_means(kept), "from_day": first + timedelta(days=1),
                           "days": len({r["day"] for r in kept})}
        return out

    counts: dict[date, dict[str, int]] = {d: {"morning": 0, "evening": 0, "other": 0} for d in days}
    for r in timed:
        counts[r["day"]][r["session"]] += 1
    sessions = [n for d in days for n in (counts[d]["morning"], counts[d]["evening"]) if n]
    complete = [d for d in days if counts[d]["morning"] >= READINGS_PER_SESSION
                and counts[d]["evening"] >= READINGS_PER_SESSION]
    counted = [d for d in complete if d != first]   # ESH: day one is discarded
    followed = len(counted) >= DIARY_MIN_DAYS
    out.update({
        "per_day": [{"day": d, **counts[d]} for d in days],
        "complete_days": len(complete),
        "counted_days": len(counted),
        "sessions": len(sessions),
        "full_sessions": sum(n >= READINGS_PER_SESSION for n in sessions),
        "other_readings": sum(counts[d]["other"] for d in days),
        "followed": followed,
    })
    if followed:  # a mean of an incomplete diary would pass for the protocol's number
        kept = [r for r in timed if r["day"] != first and r["session"] != "other"]
        out["mean"] = {
            **_means(kept),
            "morning": _means([r for r in kept if r["session"] == "morning"]),
            "evening": _means([r for r in kept if r["session"] == "evening"]),
            "from_day": first + timedelta(days=1),
        }
    return out


def diaries(readings: list[dict]) -> list[dict]:
    """Runs of reading days (at most DIARY_GAP days apart: one missed day still joins) with at
    least two days, newest first. A lone day of readings is a check, not a diary."""
    by_day: dict[date, list[dict]] = defaultdict(list)
    for r in readings:
        by_day[r["day"]].append(r)
    runs: list[list[date]] = []
    for day in sorted(by_day):
        if runs and (day - runs[-1][-1]).days <= DIARY_GAP:
            runs[-1].append(day)
        else:
            runs.append([day])
    return [summarize_diary([r for d in run for r in by_day[d]])
            for run in reversed(runs) if len(run) >= 2]


def _reading(at: datetime, precision: str, systolic, diastolic, tz: tzinfo,
             day_zone: tzinfo) -> dict:
    timed = precision == "datetime"
    # a value entered per day sits at midnight of the zone it was written in: its day is there
    local = at.astimezone(tz if timed else day_zone)
    return {"at": local if timed else local.date(), "day": local.date(),
            "session": session_of(local.hour) if timed else UNTIMED,
            "systolic": systolic, "diastolic": diastolic,
            "complete": systolic is not None and diastolic is not None}


def pair_readings(rows, tz: tzinfo, day_zone: tzinfo | None = None) -> list[dict]:
    """(type_code, effective_at, value, group_id, time_precision) rows, oldest first → readings.
    A reading is a systolic and a diastolic of one group when the rows have a group_id; without
    one, the k-th systolic and the k-th diastolic recorded at the same moment, so two readings
    logged at "08:00" stay two. Which of those systolics went with which diastolic is then unknown,
    but neither the counts nor the means depend on it. A value left without its pair is an
    incomplete reading."""
    day_zone = day_zone or tz
    groups: dict[tuple, dict[str, list]] = defaultdict(lambda: {"systolic_bp": [], "diastolic_bp": []})
    for code, at, value, group, precision in rows:
        key = ("group", str(group)) if group else ("time", at, precision)
        groups[key][code].append((at, _number(value), precision))
    readings = []
    for by_code in groups.values():
        systolic, diastolic = by_code["systolic_bp"], by_code["diastolic_bp"]
        for k in range(max(len(systolic), len(diastolic))):
            s = systolic[k] if k < len(systolic) else None
            d = diastolic[k] if k < len(diastolic) else None
            at, _, precision = s or d
            readings.append(_reading(at, precision, s and s[1], d and d[1], tz, day_zone))
    return sorted(readings, key=lambda r: (r["day"], r["session"] == UNTIMED,
                                          r["at"] if isinstance(r["at"], datetime) else r["day"]))


def bp_points(readings: list[dict], since: date, bucket: str) -> list[dict]:
    """The chart's points in the window: every reading, or a mean per session and bucket."""
    shown = [r for r in readings if r["day"] >= since]
    if bucket == "day":
        return [{"at": r["at"], "session": r["session"], "systolic": r["systolic"],
                 "diastolic": r["diastolic"], "n": 1} for r in shown]
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in shown:
        groups[(bucket_start(r["day"], bucket), r["session"])].append(r)
    return [{"at": start, "session": session, **_means(group)}
            for (start, session), group in sorted(groups.items())]


def _blood_pressure(conn, uid, since: date, bucket: str, tz: tzinfo, day_zone: tzinfo) -> dict:
    rows = conn.execute(text(
        """SELECT type_code, effective_at, value_canonical, group_id, time_precision
           FROM v_observations
           WHERE user_id = :u AND type_code = ANY(:codes) AND value_canonical IS NOT NULL
           ORDER BY effective_at, id"""), {"u": uid, "codes": list(BP_CODES)}).all()
    pending = conn.execute(text(
        """SELECT count(*) FROM v_observations_pending
           WHERE user_id = :u AND type_code = ANY(:codes)"""),
        {"u": uid, "codes": list(BP_CODES)}).scalar()
    readings = pair_readings(rows, tz, day_zone)
    return {
        "unit": "mmHg",
        "points": bp_points(readings, since, bucket),
        "readings": len(readings),
        "pending_values": pending,  # systolic and diastolic rows: one reading may be two
        "diaries": diaries(readings),
        "protocol": {
            "morning": list(MORNING), "evening": list(EVENING),
            "max_days": DIARY_DAYS, "min_days": DIARY_MIN_DAYS,
            "readings_per_session": READINGS_PER_SESSION, "max_gap_days": DIARY_GAP - 1,
            "threshold": BP_THRESHOLD, "source": BP_SOURCE,
        },
    }


# ---- the watch ------------------------------------------------------------------------------------

def _daily(conn, uid, codes, since: date, until: date, tz: ZoneInfo,
           day_zone: ZoneInfo) -> dict[str, dict[date, float]]:
    """code → {day: the day's value}, aggregated in the database (DAY_AGGREGATE). A timed value's
    day is its date in the user's zone; a value entered per day keeps the day it was written for."""
    rows = conn.execute(text(
        """SELECT type_code, day,
                  CASE WHEN type_code = ANY(:max_codes) THEN max(value_canonical)
                       ELSE avg(value_canonical) END AS value
           FROM (SELECT type_code, value_canonical,
                        CASE WHEN time_precision = 'datetime'
                             THEN (effective_at AT TIME ZONE :tz)::date
                             ELSE (effective_at AT TIME ZONE :day_zone)::date END AS day
                 FROM v_observations
                 WHERE user_id = :u AND type_code = ANY(:codes) AND value_canonical IS NOT NULL
                   AND effective_at >= :lo AND effective_at < :hi) v
           WHERE day BETWEEN :since AND :until
           GROUP BY type_code, day"""),
        {"u": uid, "codes": list(codes), "since": since, "until": until,
         "tz": tz.key, "day_zone": day_zone.key,
         # a day of any zone lies within a day either side of the same date in the database's
         "lo": since - timedelta(days=2), "hi": until + timedelta(days=2),
         "max_codes": [c for c, how in DAY_AGGREGATE.items() if how == "max"]}).all()
    out: dict[str, dict[date, float]] = defaultdict(dict)
    for code, day, value in rows:
        if _number(value) is not None:
            out[code][day] = _number(value)
    return out


def rebucket(days: dict[date, float], bucket: str) -> list[dict]:
    """{day: value} → [{at, value, n}] oldest first; a week or a month is the mean of its days."""
    groups: dict[date, list[float]] = defaultdict(list)
    for day, value in days.items():
        groups[bucket_start(day, bucket)].append(value)
    return [{"at": start, "value": round(sum(v) / len(v), 2), "n": len(v)}
            for start, v in sorted(groups.items())]


def training_load(days: dict[date, float], since: date, until: date) -> dict[date, dict]:
    """Each day's acute (7-day) and chronic (28-day) mean of intensity minutes; None where fewer
    than half of the days in that span have a value."""
    def mean(day: date, span: int) -> float | None:
        values = [days[d] for d in (day - timedelta(days=i) for i in range(span)) if d in days]
        return round(sum(values) / len(values), 1) if len(values) * 2 >= span else None

    out = {}
    day = since
    while day <= until:
        acute, chronic = mean(day, ACUTE_DAYS), mean(day, CHRONIC_DAYS)
        if acute is not None or chronic is not None:
            out[day] = {"acute": acute, "chronic": chronic}
        day += timedelta(days=1)
    return out


def _load_points(load: dict[date, dict], bucket: str) -> list[dict]:
    out = []
    for key in ("acute", "chronic"):
        days = {d: v[key] for d, v in load.items() if v[key] is not None}
        out.append({"key": key, "points": rebucket(days, bucket)})
    return out


def _units(conn, codes) -> dict[str, str | None]:
    return dict(conn.execute(text(
        "SELECT code, canonical_unit FROM observation_types WHERE code = ANY(:c)"),
        {"c": list(codes)}).all())


def vitals(conn, lang: str = "en", days=DEFAULT_WINDOW, tz: tzinfo | None = None) -> dict:
    """`tz`: the user's zone (the browser's), from parse_tz; None is the database's. Days, "today"
    and morning/evening are read in it."""
    lang = lang if lang in LANGUAGES else "en"
    days = window_days(days)
    bucket = bucket_for(days)
    day_zone = _db_zone(conn)
    tz = tz if isinstance(tz, ZoneInfo) else day_zone
    today = conn.execute(text("SELECT now()")).scalar().astimezone(tz).date()
    since = today - timedelta(days=days - 1)
    year_from = today - timedelta(days=HEATMAP_DAYS - 1)
    window = {"days": days, "from": since, "to": today, "bucket": bucket, "options": list(WINDOWS),
              "tz": tz.key}
    uid = q.user_id(conn)
    if uid is None:
        return {"window": window, "blood_pressure": None, "wearables": [], "load": None,
                "heatmaps": []}
    names = q.marker_names(conn, lang)
    units = _units(conn, (*WEARABLE_CODES, *BP_CODES))

    load_since = since - timedelta(days=CHRONIC_DAYS - 1)
    daily = _daily(conn, uid, WEARABLE_CODES, min(load_since, year_from), today, tz, day_zone)
    wearables = []
    for code in WEARABLE_CODES:
        in_window = {d: v for d, v in daily.get(code, {}).items() if d >= since}
        if in_window:
            wearables.append({"code": code, "name": names.get(code, code), "unit": units.get(code),
                              "days": len(in_window), "points": rebucket(in_window, bucket)})
    load = None
    if daily.get(LOAD_CODE):
        lines = _load_points(training_load(daily[LOAD_CODE], since, today), bucket)
        if any(line["points"] for line in lines):
            load = {"code": LOAD_CODE, "name": names.get(LOAD_CODE, LOAD_CODE),
                    "unit": units.get(LOAD_CODE), "acute_days": ACUTE_DAYS,
                    "chronic_days": CHRONIC_DAYS, "lines": lines}
    heatmaps = []
    for code in HEATMAP_CODES:
        year = {d: v for d, v in daily.get(code, {}).items() if d >= year_from}
        if year:
            heatmaps.append({"code": code, "name": names.get(code, code), "unit": units.get(code),
                             "from": year_from, "to": today,
                             "days": [[d, v] for d, v in sorted(year.items())]})
    return {
        "window": window,
        "blood_pressure": _blood_pressure(conn, uid, since, bucket, tz, day_zone),
        "wearables": wearables,
        "load": load,
        "heatmaps": heatmaps,
    }
