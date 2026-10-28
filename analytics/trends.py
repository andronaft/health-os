"""Trends (plan 5, level 1). Mann-Kendall (non-parametric) + a Theil–Sen slope per year.

Mann-Kendall is robust to outliers and assumes no normality — more appropriate than a naive
regression on medical time series. Caution: on STRONGLY autocorrelated series p is understated
(plan 5 level 2 — a separate topic with prewhitening); here it's a basic trend over sparse lab points.

Pure functions, no numpy/scipy.
"""
from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date

_YEAR_S = 365.25 * 86400

INCREASING = "increasing"
DECREASING = "decreasing"
NO_TREND = "no_trend"


@dataclass
class TrendResult:
    direction: str
    z: float | None
    p_approx: float | None
    slope: float | None            # units per point (simple OLS), kept for compatibility
    n: int
    detail: str
    slope_per_year: float | None = None   # Theil–Sen over the timestamps, when they're given


def _mann_kendall_stat(values: list[float]) -> tuple[int, float]:
    n = len(values)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += (values[j] > values[i]) - (values[j] < values[i])
    # tie correction: lab values are rounded and wearable values are integers, so equal values
    # are common; without it the variance is too large and real trends are missed
    ties = sum(t * (t - 1) * (2 * t + 5) for t in Counter(values).values() if t > 1)
    var = (n * (n - 1) * (2 * n + 5) - ties) / 18
    return s, var


def _ols_slope(values: list[float]) -> float:
    n = len(values)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((xs[i] - mx) * (values[i] - my) for i in range(n)) / denom


def theil_sen_per_year(points: list[tuple[date, float]]) -> float | None:
    """Median of the pairwise slopes, in units per year (robust to outliers and to irregular
    spacing — two tests a month apart, then a year's gap). None without two distinct times."""
    slopes = []
    for i in range(len(points) - 1):
        for j in range(i + 1, len(points)):
            (ti, vi), (tj, vj) = points[i], points[j]
            dt = (tj - ti).total_seconds() / _YEAR_S
            if dt:
                slopes.append((vj - vi) / dt)
    return statistics.median(slopes) if slopes else None


def _norm_p(z: float) -> float:
    # two-sided p via erfc
    return math.erfc(abs(z) / math.sqrt(2))


def trend(values: list[float], alpha: float = 0.05, min_n: int = 5,
          times: list[date] | None = None) -> TrendResult:
    """Trend direction by Mann-Kendall. Needs ≥min_n points. With `times` (same order as
    values) the slope is also reported per year (Theil–Sen)."""
    n = len(values)
    if n < min_n:
        return TrendResult(NO_TREND, None, None, None, n,
                           f"Not enough points ({n}, need ≥{min_n}).")
    s, var = _mann_kendall_stat(values)
    if var == 0:
        return TrendResult(NO_TREND, 0.0, 1.0, 0.0, n, "No variation.")
    # continuity correction
    if s > 0:
        z = (s - 1) / math.sqrt(var)
    elif s < 0:
        z = (s + 1) / math.sqrt(var)
    else:
        z = 0.0
    p = _norm_p(z)
    slope = _ols_slope(values)
    per_year = (theil_sen_per_year(list(zip(times, values, strict=True)))
                if times is not None else None)
    if p < alpha and z > 0:
        direction = INCREASING
    elif p < alpha and z < 0:
        direction = DECREASING
    else:
        direction = NO_TREND
    rate = (f"Theil–Sen slope≈{per_year:+.3g}/year" if per_year is not None
            else f"slope≈{slope:+.3f}/point")
    detail = (f"Mann-Kendall z={z:+.2f}, p≈{p:.3f}, {rate}, n={n}. "
              + {INCREASING: "steady increase.", DECREASING: "steady decrease.",
                 NO_TREND: "no significant trend."}[direction])
    return TrendResult(direction, z, p, slope, n, detail, per_year)
