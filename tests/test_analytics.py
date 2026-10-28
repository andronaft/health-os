from analytics.baselines import baseline, check_anomaly
from analytics.calculators import bmi, calculator_applicable
from analytics.trends import DECREASING, INCREASING, NO_TREND, trend


# --- baselines ---
def test_baseline_basic():
    b = baseline([10, 12, 14])
    assert b.n == 3 and b.mean == 12


def test_anomaly_detected():
    hist = [70, 72, 71, 69, 73, 70]  # resting HR ~70
    res = check_anomaly(110, hist)
    assert res.is_anomaly and res.z > 2


def test_no_anomaly_within_norm():
    res = check_anomaly(71, [70, 72, 71, 69, 73, 70])
    assert not res.is_anomaly


def test_insufficient_baseline():
    res = check_anomaly(100, [70, 72])  # <5 points
    assert not res.is_anomaly and "Not enough" in res.detail


# --- trends ---
def test_increasing_trend():
    assert trend([3.0, 3.4, 3.9, 4.5, 5.1, 5.8]).direction == INCREASING


def test_decreasing_trend():
    assert trend([5.8, 5.1, 4.5, 3.9, 3.4, 3.0]).direction == DECREASING


def test_no_trend_flat_noise():
    assert trend([5.0, 5.1, 4.9, 5.0, 5.05, 4.95]).direction == NO_TREND


def test_trend_needs_min_points():
    assert trend([5.0, 6.0]).direction == NO_TREND


# --- calculators (age-gate) ---
def test_score2_refused_for_young():
    g = calculator_applicable("SCORE2", 27)
    assert not g.applicable and "false reassurance" in g.message


def test_score2_ok_in_range():
    assert calculator_applicable("SCORE2", 55).applicable


def test_frax_range():
    assert calculator_applicable("FRAX", 30).applicable is False
    assert calculator_applicable("FRAX", 60).applicable is True


def test_bmi_calc():
    r = bmi(80, 180)
    assert r["bmi"] == 24.7 and r["category"] == "normal"


# --- #34: tie correction and a per-year Theil–Sen slope ---
def test_mann_kendall_variance_has_tie_correction():
    from analytics.trends import _mann_kendall_stat
    s, var = _mann_kendall_stat([1, 2, 2, 3, 3, 3])
    # groups of 2 and 3 equal values: (6·5·17 − 2·1·9 − 3·2·11) / 18
    assert s == 11 and abs(var - (510 - 18 - 66) / 18) < 1e-9


def test_ties_no_longer_hide_a_real_trend():
    # integer-like readings with repeats: without the correction p stayed above 0.05
    values = [60, 60, 61, 61, 61, 62, 62, 63, 63, 63]
    assert trend(values).direction == INCREASING


def test_theil_sen_per_year_uses_the_dates():
    from datetime import date, timedelta

    from analytics.trends import theil_sen_per_year
    start = date(2020, 1, 1)
    # +1 unit per year on irregular gaps: 1 month, then almost 2 years, then 3 months
    days = [0, 30, 700, 790]
    pts = [(start + timedelta(days=d), 5 + d / 365.25) for d in days]
    assert abs(theil_sen_per_year(pts) - 1.0) < 1e-9


def test_theil_sen_ignores_an_outlier():
    from datetime import date

    from analytics.trends import theil_sen_per_year
    pts = [(date(2020, 1, 1), 1.0), (date(2021, 1, 1), 2.0),
           (date(2022, 1, 1), 30.0), (date(2023, 1, 1), 4.0)]
    assert abs(theil_sen_per_year(pts) - 1.0) < 0.01


def test_trend_reports_per_year_slope_when_times_are_given():
    from datetime import date
    times = [date(2020 + i, 1, 1) for i in range(6)]
    t = trend([3.0, 3.4, 3.9, 4.5, 5.1, 5.8], times=times)
    assert t.slope_per_year is not None and 0.5 < t.slope_per_year < 0.6
    assert "/year" in t.detail
    assert trend([3.0, 3.4, 3.9, 4.5, 5.1, 5.8]).slope_per_year is None   # no dates → per point
