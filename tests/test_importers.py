"""Integration test of the Apple Health importer (committed data, cleanup in finally)."""
import pytest
from sqlalchemy import text

from core.db import engine
from core.services import get_or_create_user
from ingestion.importers import import_apple_health

pytestmark = pytest.mark.integration  # hits the DB via `engine` / MCP tools directly

_XML = """<?xml version="1.0"?>
<HealthData>
  <Record type="HKQuantityTypeIdentifierStepCount" unit="count" startDate="2024-01-15 08:00:00 +0200" value="1200"/>
  <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" startDate="2024-01-15 08:00:00 +0200" value="60"/>
  <Record type="HKQuantityTypeIdentifierHeartRate" unit="count/min" startDate="2024-01-15 08:05:00 +0200" value="80"/>
  <Record type="HKCategoryTypeIdentifierIrregularHeartRhythmEvent" startDate="2024-01-15 09:00:00 +0200" value="x"/>
</HealthData>"""


class _Fake:
    def __init__(self): self.calls = []
    def __call__(self, t, m): self.calls.append((t, m))


def _cleanup(uid, source_id):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM device_samples WHERE source_id=:s"), {"s": source_id})
        conn.execute(text("DELETE FROM device_alerts WHERE user_id=:u"), {"u": uid})
        conn.execute(text("DELETE FROM observations WHERE source_id=:s"), {"s": source_id})
        conn.execute(text("DELETE FROM ingestion_sources WHERE id=:s"), {"s": source_id})


def test_apple_health_import_end_to_end():
    fake = _Fake()
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out = import_apple_health(conn, uid, _XML, alerter=fake)
    sid = out["source_id"]
    try:
        assert out["samples_inserted"] == 3          # 1 step + 2 hr
        assert out["daily_observations"] == 1        # heart_rate daily aggregate (steps has no obs_type)
        assert out["device_alerts"] == 1
        assert len(fake.calls) == 1                   # irregular_rhythm → alert
        with engine.connect() as conn:
            hr = conn.execute(
                text("""SELECT value_canonical FROM observations o
                        JOIN observation_types ot ON ot.id=o.type_id
                        WHERE ot.code='heart_rate' AND o.source_id=:s"""), {"s": sid}
            ).scalar()
            assert float(hr) == 70.0                  # (60+80)/2
    finally:
        _cleanup(uid, sid)


def test_reimport_is_idempotent():
    """Cumulative re-import doesn't double samples (UNIQUE + reused source)."""
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        out1 = import_apple_health(conn, uid, _XML)
    with engine.begin() as conn:
        out2 = import_apple_health(conn, uid, _XML)
    sid = out1["source_id"]
    try:
        assert out1["source_id"] == out2["source_id"]   # the same channel source
        assert out2["samples_inserted"] == 0            # ON CONFLICT DO NOTHING
    finally:
        _cleanup(uid, sid)


_XML_US = """<?xml version="1.0"?><HealthData>
  <Record type="HKQuantityTypeIdentifierBodyMass" unit="lb" startDate="2026-11-10 08:00:00 +0100" value="180"/>
  <Record type="HKQuantityTypeIdentifierBodyTemperature" unit="degF" startDate="2026-11-10 08:00:00 +0100" value="103.1"/>
  <Record type="HKQuantityTypeIdentifierBodyMass" unit="oz" startDate="2026-11-11 08:00:00 +0100" value="2880"/>
</HealthData>"""


def test_record_units_are_converted_and_unknown_ones_reported(conn, user_id):
    """A US iPhone exports lb and degF: 180 lb was stored as 180 kg, 103.1 °F as 103.1 °C."""
    out = import_apple_health(conn, user_id, _XML_US)
    rows = dict(conn.execute(text(
        "SELECT type_code, value_canonical::float FROM v_observations WHERE user_id=:u"),
        {"u": user_id}).all())
    assert rows["body_weight"] == pytest.approx(81.647, abs=1e-3)
    assert rows["body_temp"] == pytest.approx(39.5, abs=1e-3)
    samples = dict(conn.execute(text(
        "SELECT type_code, value::float FROM device_samples WHERE source_id=:s"),
        {"s": out["source_id"]}).all())
    assert samples == {"body_weight": pytest.approx(81.647, abs=1e-3),
                       "body_temp": pytest.approx(39.5, abs=1e-3)}
    # the ounce record is neither stored nor silently lost
    assert out["skipped_unknown_unit"] == [{"type_code": "body_weight", "unit": "oz", "records": 1}]
    assert "1 record(s) skipped" in out["note"]
    assert out["daily_observations"] == 2
