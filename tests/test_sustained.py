"""Sustained deviations from the personal baseline (#75): pure rules on synthetic series, no DB."""
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from analytics.baselines import (
    DEFAULTS,
    SustainedParams,
    daily_runs,
    intraday_episodes,
    limits_text,
    pair_runs,
    resting_medians,
    sustained_days,
    usual_range,
)

TODAY = date(2026, 11, 20)
UTCZ = ZoneInfo("UTC")


def history(base: float, days: int = 70, end: date = TODAY, wobble: float = 1.0) -> dict:
    """`days` days up to `end` (inclusive) around `base`: -1, 0, +1, 0, … (a spread of ~1.5)."""
    pattern = (-wobble, 0.0, wobble, 0.0)
    return {end - timedelta(days=i): base + pattern[i % 4] for i in range(days)}


def with_days(series: dict, values: dict[int, float | None], end: date = TODAY) -> dict:
    """Set (or, with None, remove) the values `days ago` → value."""
    out = dict(series)
    for ago, v in values.items():
        d = end - timedelta(days=ago)
        if v is None:
            out.pop(d, None)
        else:
            out[d] = v
    return out


# ---- the days rule ------------------------------------------------------------------------------

def test_three_elevated_nights_fire():
    rhr = with_days(history(58), {2: 66, 1: 67, 0: 65})
    [run] = daily_runs("resting_hr", rhr)
    assert (run["first_day"], run["last_day"], run["days"]) == (TODAY - timedelta(days=2), TODAY, 3)
    assert run["usual"] == 58 and run["direction"] == "up"
    assert run["mean_delta"] == 8.0 and run["max_delta"] == 9.0


def test_a_single_bad_night_does_not_fire():
    assert daily_runs("resting_hr", with_days(history(58), {5: 70})) == []


def test_two_nights_are_not_enough():
    assert daily_runs("resting_hr", with_days(history(58), {1: 68, 0: 68})) == []


def test_a_workout_spike_does_not_fire():
    # a hard race day lifts the next morning's resting HR once; a day later it is back
    assert daily_runs("resting_hr", with_days(history(58), {10: 72, 9: 63})) == []


def test_a_missing_day_breaks_the_run():
    rhr = with_days(history(58), {4: 67, 3: 67, 2: None, 1: 67, 0: 67})
    assert daily_runs("resting_hr", rhr) == []


def test_a_day_back_in_range_breaks_the_run():
    rhr = with_days(history(58), {4: 67, 3: 67, 2: 58, 1: 67, 0: 67})
    assert daily_runs("resting_hr", rhr) == []


def test_the_run_is_not_part_of_its_own_baseline():
    # twenty elevated days in a row: with the run inside its baseline it would stop being "outside"
    rhr = with_days(history(58), {ago: 68 for ago in range(20)})
    [run] = daily_runs("resting_hr", rhr)
    assert run["days"] == 20 and run["usual"] == 58


def test_a_drop_in_resting_hr_is_not_a_finding_and_hrv_counts_downwards():
    assert daily_runs("resting_hr", with_days(history(58), {2: 48, 1: 48, 0: 48})) == []
    hrv = with_days(history(45, wobble=3), {2: 30, 1: 31, 0: 29})
    [run] = daily_runs("hrv", hrv)
    assert run["direction"] == "down" and run["mean_delta"] == -15.0
    assert daily_runs("hrv", with_days(history(45, wobble=3), {2: 60, 1: 61, 0: 62})) == []


def test_too_little_history_checks_nothing():
    short = with_days(history(58, days=25), {2: 70, 1: 70, 0: 70})
    assert daily_runs("resting_hr", short) == []


def test_a_steady_history_needs_the_minimum_difference():
    flat = {TODAY - timedelta(days=i): 58.0 for i in range(70)}  # spread 0
    assert daily_runs("resting_hr", with_days(flat, {2: 60, 1: 60, 0: 60})) == []  # +2 < 3 bpm
    assert len(daily_runs("resting_hr", with_days(flat, {2: 61, 1: 61, 0: 61}))) == 1


def test_the_spread_is_robust():
    rng = usual_range([58, 59, 57, 58, 90])  # one wild value barely moves median or spread
    assert rng.median == 58 and round(rng.spread, 2) == 1.48


def test_thresholds_are_parameters():
    rhr = with_days(history(58), {1: 67, 0: 67})
    assert daily_runs("resting_hr", rhr) == []
    assert len(daily_runs("resting_hr", rhr, SustainedParams(run_days=2))) == 1


# ---- reported together ----------------------------------------------------------------------------

def test_resting_hr_up_and_hrv_down_on_the_same_days_are_one_finding():
    rhr = with_days(history(58), {3: 66, 2: 67, 1: 66})
    hrv = with_days(history(45, wobble=3), {2: 30, 1: 29, 0: 31})
    [finding] = sustained_days({"resting_hr": rhr, "hrv": hrv}, since=TODAY - timedelta(days=30), tz=UTCZ)
    assert [m["code"] for m in finding["metrics"]] == ["resting_hr", "hrv"]
    assert finding["together_days"] == 2
    assert (finding["first_day"], finding["last_day"], finding["days"]) == (
        TODAY - timedelta(days=3), TODAY, 4)


def test_runs_on_different_days_stay_apart():
    rhr = with_days(history(58), {30: 66, 29: 67, 28: 66})
    hrv = with_days(history(45, wobble=3), {2: 30, 1: 29, 0: 31})
    findings = pair_runs(daily_runs("resting_hr", rhr) + daily_runs("hrv", hrv))
    assert [[m["code"] for m in f["metrics"]] for f in findings] == [["resting_hr"], ["hrv"]]
    assert all(f["together_days"] is None for f in findings)


def test_findings_that_ended_before_the_window_are_left_out():
    rhr = with_days(history(58), {30: 66, 29: 67, 28: 66})
    assert sustained_days({"resting_hr": rhr}, since=TODAY - timedelta(days=7), tz=UTCZ) == []
    assert len(sustained_days({"resting_hr": rhr}, since=TODAY - timedelta(days=28), tz=UTCZ)) == 1


# ---- context --------------------------------------------------------------------------------------

def _elevated():
    return {"resting_hr": with_days(history(58), {2: 66, 1: 67, 0: 66})}


def test_a_current_beta_blocker_is_listed_and_the_rule_is_unchanged():
    meds = [{"name": "Bisoprolol", "atc_code": "C07AB07", "start_date": TODAY - timedelta(days=100)},
            {"name": "Vitamin D3", "atc_code": "A11CC05", "start_date": None}]
    [finding] = sustained_days(_elevated(), since=TODAY - timedelta(days=7), medications=meds, tz=UTCZ)
    assert finding["context"] == [{"kind": "beta_blocker", "name": "Bisoprolol", "atc_code": "C07AB07"}]
    [plain] = sustained_days(_elevated(), since=TODAY - timedelta(days=7), tz=UTCZ)
    assert plain["metrics"] == finding["metrics"]


def test_a_beta_blocker_started_after_the_run_is_not_its_context():
    meds = [{"name": "Metoprolol", "atc_code": "c07ab02", "start_date": TODAY + timedelta(days=1)}]
    [finding] = sustained_days(_elevated(), since=TODAY - timedelta(days=7), medications=meds, tz=UTCZ)
    assert finding["context"] == []


def test_a_workout_on_those_days_is_listed_in_the_users_zone():
    kyiv = ZoneInfo("Europe/Kyiv")
    # 23:30 UTC the evening before the run is already the run's first day in Kyiv (UTC+2)
    late = datetime.combine(TODAY - timedelta(days=3), datetime.min.time(), UTC) + timedelta(hours=23, minutes=30)
    workouts = [{"start": late, "minutes": 45, "type": "running"}]
    [in_kyiv] = sustained_days(_elevated(), since=TODAY - timedelta(days=7), workouts=workouts, tz=kyiv)
    assert in_kyiv["context"] == [{"kind": "workout", "day": TODAY - timedelta(days=2),
                                   "type": "running", "minutes": 45}]
    [in_utc] = sustained_days(_elevated(), since=TODAY - timedelta(days=7), workouts=workouts, tz=UTCZ)
    assert in_utc["context"] == []


# ---- the minutes rule -----------------------------------------------------------------------------

DAY = date(2026, 11, 19)


def at(hour: int, minute: int = 0, tz=UTC) -> datetime:
    return datetime.combine(DAY, datetime.min.time(), tz) + timedelta(hours=hour, minutes=minute)


def samples(start: datetime, minutes: int, bpm: float, every: int = 5) -> list:
    return [(start + timedelta(minutes=m), bpm) for m in range(0, minutes + 1, every)]


RESTING = {DAY: 58.0}


def test_twenty_still_minutes_well_above_resting_fire():
    hr = samples(at(15), 25, 95)
    [ep] = intraday_episodes(hr, resting_by_day=RESTING, tz=UTCZ)
    assert ep["minutes"] == 25 and ep["usual"] == 58 and ep["threshold"] == 88
    assert ep["mean_hr"] == 95 and ep["day"] == DAY and ep["samples"] == 6


def test_a_short_rise_does_not_fire():
    assert intraday_episodes(samples(at(15), 15, 95), resting_by_day=RESTING, tz=UTCZ) == []


def test_steps_mean_moving_not_resting():
    hr = samples(at(15), 40, 110)
    steps = [(at(15, 21), 30.0)]  # a walk in the middle: neither half is 20 still minutes
    assert intraday_episodes(hr, resting_by_day=RESTING, steps=steps, tz=UTCZ) == []
    assert intraday_episodes(hr, resting_by_day=RESTING, steps=[(at(15, 21), 0.0)], tz=UTCZ) != []


def test_a_recorded_workout_is_not_an_episode_nor_its_recovery():
    hr = samples(at(18), 30, 140)
    workout = [{"start": at(17, 10), "minutes": 40}]  # ends 17:50; recovery to 18:20 overlaps
    assert intraday_episodes(hr, resting_by_day=RESTING, workouts=workout, tz=UTCZ) == []
    early = [{"start": at(12), "minutes": 40}]
    assert len(intraday_episodes(hr, resting_by_day=RESTING, workouts=early, tz=UTCZ)) == 1


def test_a_gap_in_the_samples_breaks_the_run():
    hr = samples(at(15), 12, 95) + samples(at(15, 30), 12, 95)  # 18 min apart: watch off
    assert intraday_episodes(hr, resting_by_day=RESTING, tz=UTCZ) == []


def test_one_sample_back_near_resting_breaks_the_run():
    hr = samples(at(15), 30, 95)
    hr[3] = (hr[3][0], 70)
    assert intraday_episodes(hr, resting_by_day=RESTING, tz=UTCZ) == []


def test_no_resting_baseline_checks_nothing():
    assert intraday_episodes(samples(at(15), 30, 120), resting_by_day={}, tz=UTCZ) == []


def test_the_episodes_day_and_baseline_are_the_users():
    tokyo = ZoneInfo("Asia/Tokyo")  # 20:00 UTC on DAY is 05:00 next day in Tokyo
    hr = samples(at(20), 25, 95)
    assert intraday_episodes(hr, resting_by_day=RESTING, tz=tokyo) == []
    [ep] = intraday_episodes(hr, resting_by_day={DAY + timedelta(days=1): 58.0}, tz=tokyo)
    assert ep["day"] == DAY + timedelta(days=1) and ep["start"].hour == 5


def test_resting_medians_come_from_the_days_before():
    resting = history(58, days=70, end=DAY - timedelta(days=1))
    resting[DAY] = 90.0  # the day itself is not its own baseline
    assert resting_medians(resting, [DAY]) == {DAY: 58.0}
    assert resting_medians(history(58, days=10, end=DAY), [DAY]) == {}


def test_the_limits_are_spelled_out():
    text = limits_text(DEFAULTS)
    assert "No ECG" in text and "wrist" in text and "watch was off" in text and "30 days" in text
