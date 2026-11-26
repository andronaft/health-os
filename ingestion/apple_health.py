"""Apple Health export.xml import (plan 3.9, Phase 3) — a deterministic parser.

export.zip is a CUMULATIVE full snapshot; every import contains all previous samples
→ into device_samples with UNIQUE + ON CONFLICT DO NOTHING (upsert), otherwise baselines double.

device_alert ≠ sample: "possible atrial fibrillation"/irregular rhythm/SpO₂ alert/fall —
event flags for the red-flag logic (reliability marker: consumer_grade, the AI does not over-interpret).

Units: every quantity Record carries its own `unit` attribute, and it follows the phone's
locale — a US iPhone exports body mass in "lb" and temperature in "degF". The value is
converted to the type's canonical unit (kg, °C, bpm, %); a record whose unit isn't in
`HK_UNITS` for its type is skipped and counted, never stored as if it were canonical
(180 lb stored as 180 kg, a 103.1 °F fever stored as 103.1 °C). A record without a unit is
skipped the same way: Apple always writes one, so its absence means we can't trust the number.

Pure functions over the XML string; DB writes are separate (importers, in Phase 3 in full).
"""
from __future__ import annotations

import io
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from xml.etree import ElementTree as ET

# HK identifier → (type_code, daily aggregation method)
HK_QUANTITY = {
    "HKQuantityTypeIdentifierHeartRate": ("heart_rate", "avg"),
    "HKQuantityTypeIdentifierRestingHeartRate": ("resting_hr", "avg"),
    # Apple's HRV is SDNN; Garmin's overnight HRV is RMSSD-based: two measures, two codes, never
    # one baseline (#75)
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("hrv_sdnn", "avg"),
    "HKQuantityTypeIdentifierStepCount": ("steps", "sum"),
    "HKQuantityTypeIdentifierOxygenSaturation": ("spo2", "avg"),
    "HKQuantityTypeIdentifierBodyMass": ("body_weight", "last"),
    "HKQuantityTypeIdentifierBodyTemperature": ("body_temp", "avg"),
}

# type_code → {Apple unit string: conversion to the canonical unit}. Only units Apple writes
# for these types; anything else is reported, not guessed.
HK_UNITS = {
    "heart_rate": {"count/min": lambda v: v},
    "resting_hr": {"count/min": lambda v: v},
    "hrv_sdnn": {"ms": lambda v: v},
    "steps": {"count": lambda v: v},
    # Apple stores SpO2 as a fraction 0..1 with unit "%"; older exports may hold 0..100
    "spo2": {"%": lambda v: v * 100.0 if v <= 1.0 else v},
    "body_weight": {"kg": lambda v: v, "g": lambda v: v / 1000.0,
                    "lb": lambda v: v * 0.45359237, "st": lambda v: v * 6.35029318},
    "body_temp": {"degC": lambda v: v, "degF": lambda v: (v - 32.0) * 5.0 / 9.0,
                  "K": lambda v: v - 273.15},
}

# category events → alert type
HK_ALERTS = {
    "HKCategoryTypeIdentifierIrregularHeartRhythmEvent": "irregular_rhythm",
    "HKCategoryTypeIdentifierHighHeartRateEvent": "high_hr",
    "HKCategoryTypeIdentifierLowHeartRateEvent": "low_hr",
}


@dataclass
class Sample:
    type_code: str
    ts: datetime
    value: float


@dataclass
class DeviceAlert:
    alert_type: str
    detected_at: datetime
    reliability: str = "consumer_grade"


def _parse_ts(s: str) -> datetime:
    # Apple format: '2024-01-15 08:30:00 +0200'
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


@dataclass
class Workout:
    """A recorded workout (Apple's <Workout>): what heart rate is expected to be high in."""
    activity_type: str          # "cycling", from HKWorkoutActivityTypeCycling
    start: datetime
    end: datetime | None
    minutes: int | None         # end − start, else the record's own duration in minutes
    source: str | None          # the app or device that recorded it


# Apple writes a workout's duration in its durationUnit; minutes are what is stored
_DURATION_TO_MINUTES = {"min": 1.0, "s": 1 / 60, "hr": 60.0, "h": 60.0}


def _activity_type(raw: str | None) -> str:
    name = (raw or "").removeprefix("HKWorkoutActivityType") or "other"
    # "TraditionalStrengthTraining" → "traditional_strength_training"
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in name).lstrip("_")


def _workout(el) -> Workout | None:
    start = el.get("startDate")
    if not start:
        return None
    begin = _parse_ts(start)
    end = _parse_ts(el.get("endDate")) if el.get("endDate") else None
    minutes = None
    if end is not None and end > begin:
        minutes = round((end - begin).total_seconds() / 60)
    else:
        try:
            factor = _DURATION_TO_MINUTES.get(el.get("durationUnit") or "min")
            minutes = round(float(el.get("duration")) * factor) if factor else None
        except (TypeError, ValueError):
            minutes = None
    return Workout(_activity_type(el.get("workoutActivityType")), begin, end, minutes,
                   el.get("sourceName"))


@dataclass
class ParsedExport:
    samples: list[Sample] = field(default_factory=list)
    alerts: list[DeviceAlert] = field(default_factory=list)
    workouts: list[Workout] = field(default_factory=list)
    # (type_code, unit as written or None) → number of records skipped for an unknown unit
    skipped_units: Counter = field(default_factory=Counter)


def parse(xml: str) -> ParsedExport:
    """Parses export.xml; quantity values come out in canonical units (see `HK_UNITS`)."""
    out = ParsedExport()
    for _event, el in ET.iterparse(io.StringIO(xml), events=("end",)):
        if el.tag == "Workout":
            workout = _workout(el)
            if workout is not None:
                out.workouts.append(workout)
            el.clear()
            continue
        if el.tag != "Record":
            continue
        rtype = el.get("type")
        start = el.get("startDate")
        if rtype in HK_QUANTITY and start:
            try:
                val = float(el.get("value"))
            except (TypeError, ValueError):
                el.clear()
                continue
            type_code = HK_QUANTITY[rtype][0]
            unit = el.get("unit")
            convert = HK_UNITS[type_code].get(unit)
            if convert is None:
                out.skipped_units[(type_code, unit)] += 1
            else:
                val = convert(val)
                if math.isfinite(val):
                    out.samples.append(Sample(type_code, _parse_ts(start), val))
        elif rtype in HK_ALERTS and start:
            out.alerts.append(DeviceAlert(HK_ALERTS[rtype], _parse_ts(start)))
        el.clear()
    return out


def parse_export(xml: str) -> tuple[list[Sample], list[DeviceAlert]]:
    """(samples, alerts) — `parse` without the skipped-unit report."""
    p = parse(xml)
    return p.samples, p.alerts


def daily_aggregates(samples: list[Sample]) -> list[dict]:
    """Daily aggregates (auto-approved into observations). Method is per type_code."""
    agg_method = {tc: m for tc, m in HK_QUANTITY.values()}
    buckets: dict[tuple[str, str], list[float]] = {}
    for s in samples:
        key = (s.type_code, s.ts.date().isoformat())
        buckets.setdefault(key, []).append(s.value)

    out = []
    for (type_code, day), vals in sorted(buckets.items()):
        method = agg_method.get(type_code, "avg")
        if method == "sum":
            value = sum(vals)
        elif method == "last":
            value = vals[-1]
        else:
            value = sum(vals) / len(vals)
        out.append({"type_code": type_code, "day": day,
                    "value": round(value, 3), "n": len(vals), "method": method})
    return out
