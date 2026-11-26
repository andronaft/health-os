"""Personal baselines, anomalies and sustained deviations (plan 5, level 1 — deterministic; #75).

An anomaly is a deviation from a PERSONAL baseline (rolling mean/σ), not "ML magic on n=1".
Pure functions, tested without a DB.
"""
from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, tzinfo
from statistics import median


@dataclass
class Baseline:
    n: int
    mean: float
    std: float


@dataclass
class AnomalyCheck:
    value: float
    z: float | None
    is_anomaly: bool
    detail: str


def baseline(values: list[float]) -> Baseline | None:
    """Mean and population σ over history. None if too few points."""
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    return Baseline(n=n, mean=mean, std=math.sqrt(var))


def check_anomaly(latest: float, history: list[float], z_threshold: float = 2.0,
                  min_n: int = 5) -> AnomalyCheck:
    """Whether latest is an anomaly relative to history (|z| > threshold).

    Needs ≥min_n historical points — otherwise "not enough baseline" (we don't shout on 2 points).
    """
    b = baseline(history)
    if b is None or len(history) < min_n:
        return AnomalyCheck(latest, None, False,
                            f"Not enough baseline ({len(history)} points, need ≥{min_n}).")
    if b.std == 0:
        anom = latest != b.mean
        return AnomalyCheck(latest, None, anom,
                            "History has no spread; any deviation is noticeable." if anom
                            else "Matches an unchanged history.")
    z = (latest - b.mean) / b.std
    is_anom = abs(z) > z_threshold
    return AnomalyCheck(
        latest, z, is_anom,
        f"z={z:+.1f} (baseline {b.mean:.2f}±{b.std:.2f}, n={b.n}). "
        + ("Deviation from the personal norm — worth watching/repeating."
           if is_anom else "Within the personal norm."),
    )


# ---- sustained deviations from the personal baseline (#75) ---------------------------------------
#
# A wearable value worth a look is rarely one odd day: it is a change that LASTS. Two rules:
#
# 1. Days: a daily value (resting heart rate, HRV) outside the user's own usual range on N days in
#    a row. The usual range is the median and the spread of the BASELINE_DAYS before the run, so
#    the run never pulls its own baseline toward itself. A day without a value ends a run: an
#    unknown day is not an elevated one. Resting heart rate up and HRV down on the same days are
#    reported together, as one finding.
# 2. Minutes (Apple Health raw samples only, Garmin imports daily values): heart rate at least
#    X bpm above the user's resting median for at least 20 minutes with no steps, outside a
#    recorded workout.
#
# Context is listed, never used to change the rule: a workout on those days, a current beta
# blocker (ATC C07*, which lowers heart rate and so hides a rise).
#
# What the rules can't see: there is no ECG here, only wrist sensors (optical heart rate, which
# drifts with fit and movement); days and minutes when the watch was off are gaps, not "normal";
# one person's history is the only baseline, so the first BASELINE_DAYS give no answer at all.
#
# THE NUMBERS BELOW ARE INITIAL DEFAULTS, TO BE REVIEWED: they were not taken from a study. The
# idea of a personal resting-heart-rate baseline and a rise that lasts days follows Mishra T. et
# al., "Pre-symptomatic detection of COVID-19 from smartwatch data", Nat Biomed Eng
# 2020;4:1208–1220 (https://doi.org/10.1038/s41551-020-00640-6) and Radin J.M. et al., "Harnessing
# wearable device data to improve state-level real-time surveillance of influenza-like illness in
# the USA", Lancet Digit Health 2020;2:e85–e93 (https://doi.org/10.1016/S2589-7500(19)30222-5).
# For scale on the minutes rule: Apple Watch's own high heart rate notification (Apple's support
# page on heart rate notifications) fires above a user-chosen 100–150 bpm after about 10 minutes
# of apparent inactivity; the rule here is personal (resting median + X) and twice as long,
# because false alarms are the main cost.

MAD_TO_SIGMA = 1.4826  # the median absolute deviation × this ≈ σ for normally spread values


@dataclass(frozen=True)
class SustainedParams:
    """Every threshold of the sustained rules, in one place. INITIAL DEFAULTS, TO BE REVIEWED."""
    baseline_days: int = 60       # the usual range: the days before the run
    min_baseline_days: int = 30   # fewer days with a value in those 60 → no baseline, no finding
    run_days: int = 3             # N days in a row outside the usual range
    spread_k: float = 2.0         # outside = beyond k × spread (robust σ: MAD × 1.4826)
    # each daily code: which way counts, and the smallest difference that counts at all (a very
    # steady history has a tiny spread; 1 bpm is not a change)
    daily: Mapping[str, Mapping] = field(default_factory=lambda: {
        "resting_hr": {"direction": "up", "min_delta": 3.0},   # bpm
        "hrv": {"direction": "down", "min_delta": 5.0},        # ms
    })
    paired: tuple[str, str] = ("resting_hr", "hrv")  # reported together when their days overlap
    hr_above_resting: float = 30.0   # bpm above the resting median, intraday
    min_minutes: int = 20            # that long, intraday
    max_sample_gap_minutes: int = 10  # two heart rate samples further apart break a run
    min_samples: int = 3
    step_margin_minutes: int = 5     # a step record (only its start is stored) covers ± this
    workout_recovery_minutes: int = 30  # heart rate stays up after a workout
    workout_default_minutes: int = 60   # a workout recorded without a duration
    beta_blocker_atc: str = "C07"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["daily"] = {k: dict(v) for k, v in self.daily.items()}
        d["paired"] = list(self.paired)
        return d


DEFAULTS = SustainedParams()
HR_CODES = ("resting_hr", "hrv", "heart_rate")  # the codes a beta blocker changes
LIMITS = ("No ECG: wrist sensors only (optical heart rate, which drifts with fit and movement). "
          "Days and minutes when the watch was off are gaps, not normal days. The baseline is "
          "your own history only: with fewer than {min} days of values in the {days} before, "
          "nothing is checked.")


def limits_text(params: SustainedParams = DEFAULTS) -> str:
    return LIMITS.format(min=params.min_baseline_days, days=params.baseline_days)


@dataclass
class UsualRange:
    median: float
    spread: float  # robust σ
    n: int


def usual_range(values: list[float]) -> UsualRange:
    m = median(values)
    mad = median(abs(v - m) for v in values)
    return UsualRange(median=m, spread=mad * MAD_TO_SIGMA, n=len(values))


def _baseline_before(series: Mapping[date, float], day: date,
                     params: SustainedParams) -> UsualRange | None:
    values = [series[d] for d in (day - timedelta(days=i) for i in range(1, params.baseline_days + 1))
              if d in series]
    return usual_range(values) if len(values) >= params.min_baseline_days else None


def _margin(rng: UsualRange, rule: Mapping, params: SustainedParams) -> float:
    return max(params.spread_k * rng.spread, float(rule.get("min_delta", 0.0)))


def _outside(value: float, rng: UsualRange, rule: Mapping, params: SustainedParams) -> bool:
    delta = value - rng.median
    margin = _margin(rng, rule, params)
    return delta >= margin if rule["direction"] == "up" else -delta >= margin


def daily_runs(code: str, series: Mapping[date, float],
               params: SustainedParams = DEFAULTS) -> list[dict]:
    """Runs of at least `run_days` consecutive days on which `code` stayed outside its usual
    range in its direction. `series`: {day: the day's value}. The usual range is fixed when a run
    starts (the days before it), so the run is never part of its own baseline."""
    rule = params.daily[code]
    runs: list[dict] = []
    days = sorted(series)
    i = 0
    while i < len(days):
        start = days[i]
        rng = _baseline_before(series, start, params)
        if rng is None or not _outside(series[start], rng, rule, params):
            i += 1
            continue
        run = [start]
        j = i + 1
        while (j < len(days) and days[j] - run[-1] == timedelta(days=1)
               and _outside(series[days[j]], rng, rule, params)):
            run.append(days[j])
            j += 1
        if len(run) >= params.run_days:
            deltas = [series[d] - rng.median for d in run]
            far = max if rule["direction"] == "up" else min
            runs.append({
                "code": code, "direction": rule["direction"],
                "first_day": run[0], "last_day": run[-1], "days": len(run),
                "usual": round(rng.median, 1), "spread": round(rng.spread, 1),
                "baseline_days": rng.n, "threshold": round(_margin(rng, rule, params), 1),
                "mean_delta": round(sum(deltas) / len(deltas), 1),
                "max_delta": round(far(deltas), 1),
                "values": [[d, series[d]] for d in run],
            })
        i = j  # a run, long or short, is not re-entered from its second day
    return runs


def _span(metrics: list[dict]) -> tuple[date, date]:
    return min(m["first_day"] for m in metrics), max(m["last_day"] for m in metrics)


def pair_runs(runs: list[dict], params: SustainedParams = DEFAULTS) -> list[dict]:
    """Findings, oldest first: a resting heart rate run and an HRV run that share a day are one
    finding (`together_days`: how many days both were outside); every other run is its own."""
    a, b = params.paired
    firsts = [r for r in runs if r["code"] == a]
    seconds = [r for r in runs if r["code"] == b]
    used: set[int] = set()
    findings = []
    for r in firsts:
        partners = [s for s in seconds if s["first_day"] <= r["last_day"]
                    and r["first_day"] <= s["last_day"]]
        used.update(id(s) for s in partners)
        metrics = [r, *partners]
        days_a = {d for d, _ in r["values"]}
        together = len(days_a & {d for s in partners for d, _ in s["values"]}) if partners else None
        findings.append({"metrics": metrics, "together_days": together})
    for r in runs:
        if r["code"] != a and id(r) not in used:
            findings.append({"metrics": [r], "together_days": None})
    out = []
    for f in findings:
        first, last = _span(f["metrics"])
        out.append({"kind": "days", "first_day": first, "last_day": last,
                    "days": (last - first).days + 1, **f, "context": []})
    return sorted(out, key=lambda f: (f["first_day"], f["metrics"][0]["code"]))


def _workout_span(w: Mapping, params: SustainedParams) -> tuple[datetime, datetime]:
    minutes = w.get("minutes") or params.workout_default_minutes
    return w["start"], w["start"] + timedelta(minutes=minutes + params.workout_recovery_minutes)


def context_for(first: date, last: date, codes: Iterable[str], workouts: Iterable[Mapping],
                medications: Iterable[Mapping], tz: tzinfo,
                params: SustainedParams = DEFAULTS) -> list[dict]:
    """What else was going on, to be listed beside a finding — it never changes the rule:
    workouts that started on those days (in the user's zone), and a current beta blocker taken
    since before the last day (it lowers heart rate and raises HRV, so it can hide a change)."""
    out = []
    for w in workouts:
        day = w["start"].astimezone(tz).date()
        if first <= day <= last:
            out.append({"kind": "workout", "day": day, "type": w.get("type"),
                        "minutes": w.get("minutes")})
    if any(c in HR_CODES for c in codes):
        for m in medications:
            atc = (m.get("atc_code") or "").upper()
            started = m.get("start_date")
            if atc.startswith(params.beta_blocker_atc) and (started is None or started <= last):
                out.append({"kind": "beta_blocker", "name": m.get("name"), "atc_code": atc})
    return out


def sustained_days(series_by_code: Mapping[str, Mapping[date, float]], *, since: date,
                   workouts: Iterable[Mapping] = (), medications: Iterable[Mapping] = (),
                   tz: tzinfo, params: SustainedParams = DEFAULTS) -> list[dict]:
    """The days rule over every code in params.daily; findings that end on or after `since`."""
    runs = [r for code in params.daily for r in daily_runs(code, series_by_code.get(code, {}), params)]
    workouts, medications = list(workouts), list(medications)
    out = []
    for f in pair_runs(runs, params):
        if f["last_day"] < since:
            continue
        f["context"] = context_for(f["first_day"], f["last_day"], [m["code"] for m in f["metrics"]],
                                   workouts, medications, tz, params)
        out.append(f)
    return out


def resting_medians(resting: Mapping[date, float], days: Iterable[date],
                    params: SustainedParams = DEFAULTS) -> dict[date, float]:
    """Each day's resting heart rate median over the baseline days before it (None-free: a day
    without enough history is left out, and the minutes rule then checks nothing on it)."""
    out = {}
    for d in days:
        rng = _baseline_before(resting, d, params)
        if rng is not None:
            out[d] = rng.median
    return out


def intraday_episodes(hr: Iterable[tuple[datetime, float]], *,
                      resting_by_day: Mapping[date, float],
                      steps: Iterable[tuple[datetime, float]] = (),
                      workouts: Iterable[Mapping] = (), tz: tzinfo,
                      params: SustainedParams = DEFAULTS) -> list[dict]:
    """Heart rate at least `hr_above_resting` above that day's resting median (in the user's
    zone) for at least `min_minutes`, with no step record near any of its samples, and not
    overlapping a recorded workout (plus its recovery). A sample below the line, a step, or a
    gap longer than `max_sample_gap_minutes` ends a run."""
    gap = timedelta(minutes=params.max_sample_gap_minutes)
    margin = timedelta(minutes=params.step_margin_minutes)
    moving = sorted(ts for ts, v in steps if v and v > 0)
    spans = [_workout_span(w, params) for w in workouts]

    def still(ts: datetime) -> bool:
        k = bisect_left(moving, ts - margin)
        return not (k < len(moving) and moving[k] <= ts + margin)

    runs: list[list[tuple[datetime, float, float]]] = []
    current: list[tuple[datetime, float, float]] = []

    def close():
        if current:
            runs.append(list(current))
            current.clear()

    for ts, value in sorted(hr, key=lambda s: s[0]):
        usual = resting_by_day.get(ts.astimezone(tz).date())
        if usual is None or value < usual + params.hr_above_resting or not still(ts):
            close()
            continue
        if current and ts - current[-1][0] > gap:
            close()
        current.append((ts, float(value), usual))
    close()

    out = []
    for run in runs:
        start, end = run[0][0], run[-1][0]
        minutes = (end - start).total_seconds() / 60
        if minutes < params.min_minutes or len(run) < params.min_samples:
            continue
        if any(lo <= end and start <= hi for lo, hi in spans):
            continue
        values = [v for _, v, _ in run]
        usual = run[0][2]
        out.append({
            "kind": "minutes", "start": start.astimezone(tz), "end": end.astimezone(tz),
            "day": start.astimezone(tz).date(), "minutes": round(minutes),
            "usual": round(usual, 1), "threshold": round(usual + params.hr_above_resting, 1),
            "mean_hr": round(sum(values) / len(values), 1), "max_hr": round(max(values), 1),
            "samples": len(run), "context": [],
        })
    return out
