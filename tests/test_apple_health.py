import pytest

from ingestion.apple_health import daily_aggregates, parse, parse_export

_XML = """<?xml version="1.0"?>
<HealthData>
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count" startDate="2024-01-15 08:00:00 +0200" value="1200"/>
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count" startDate="2024-01-15 18:00:00 +0200" value="3000"/>
  <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" startDate="2024-01-15 08:00:00 +0200" value="60"/>
  <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" startDate="2024-01-15 08:05:00 +0200" value="80"/>
  <Record type="HKQuantityTypeIdentifierOxygenSaturation" unit="%" startDate="2024-01-15 08:00:00 +0200" value="0.98"/>
  <Record type="HKCategoryTypeIdentifierIrregularHeartRhythmEvent" startDate="2024-01-15 09:00:00 +0200" value="HKCategoryValueSeverityNotApplicable"/>
</HealthData>"""


def test_parse_samples_and_alerts():
    samples, alerts = parse_export(_XML)
    codes = [s.type_code for s in samples]
    assert codes.count("steps") == 2
    assert codes.count("heart_rate") == 2
    # SpO2 fraction 0.98 → 98%
    spo2 = next(s for s in samples if s.type_code == "spo2")
    assert spo2.value == 98.0
    # irregular rhythm alert
    assert len(alerts) == 1 and alerts[0].alert_type == "irregular_rhythm"
    assert alerts[0].reliability == "consumer_grade"


def test_daily_aggregates():
    samples, _ = parse_export(_XML)
    agg = {a["type_code"]: a for a in daily_aggregates(samples)}
    assert agg["steps"]["value"] == 4200 and agg["steps"]["method"] == "sum"    # sum
    assert agg["heart_rate"]["value"] == 70.0 and agg["heart_rate"]["method"] == "avg"  # average


# --- units: each Record carries its own unit, which follows the phone's locale ---------------
def _record(hk_type, unit, value):
    unit_attr = "" if unit is None else f' unit="{unit}"'
    return (f'<HealthData><Record type="HKQuantityTypeIdentifier{hk_type}"{unit_attr} '
            f'startDate="2026-11-10 08:00:00 +0100" value="{value}"/></HealthData>')


@pytest.mark.parametrize(("hk_type", "unit", "value", "code", "expected"), [
    ("BodyMass", "kg", 80, "body_weight", 80.0),
    ("BodyMass", "lb", 180, "body_weight", 81.6466),       # US locale
    ("BodyMass", "g", 80500, "body_weight", 80.5),
    ("BodyMass", "st", 12, "body_weight", 76.2035),         # UK locale (stone)
    ("BodyTemperature", "degC", 37.2, "body_temp", 37.2),
    ("BodyTemperature", "degF", 103.1, "body_temp", 39.5),  # a fever, not 103.1 °C
    ("BodyTemperature", "K", 310.15, "body_temp", 37.0),
    ("HeartRate", "count/min", 72, "heart_rate", 72.0),
    ("RestingHeartRate", "count/min", 55, "resting_hr", 55.0),
    ("StepCount", "count", 1200, "steps", 1200.0),
    ("OxygenSaturation", "%", 0.97, "spo2", 97.0),
])
def test_record_unit_is_converted_to_canonical(hk_type, unit, value, code, expected):
    p = parse(_record(hk_type, unit, value))
    [s] = p.samples
    assert s.type_code == code
    assert s.value == pytest.approx(expected, abs=1e-3)
    assert not p.skipped_units


@pytest.mark.parametrize(("hk_type", "unit", "code"), [
    ("BodyMass", "oz", "body_weight"),
    ("BodyMass", None, "body_weight"),          # no unit: the number can't be trusted
    ("BodyTemperature", "Cel", "body_temp"),    # not Apple's spelling — don't guess
    ("HeartRate", "count/s", "heart_rate"),
])
def test_unknown_unit_is_skipped_and_counted(hk_type, unit, code):
    p = parse(_record(hk_type, unit, 100))
    assert p.samples == []
    assert p.skipped_units == {(code, unit): 1}
