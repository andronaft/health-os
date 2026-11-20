"""Tracker importers (plan 3.9, Phase 3) — writing parsed data to the DB.

Apple Health: raw samples → device_samples (upsert, dedup of the cumulative export);
daily aggregates of mapped types → observations (auto-approve); event flags → device_alerts
(+ a red-flag alert for irregular rhythm).
"""
from __future__ import annotations

from sqlalchemy import text

from core.services import get_or_create_channel_source
from ingestion.apple_health import daily_aggregates, parse

# write daily aggregates only for types that have observation_types
_AGG_TO_OBS = {"heart_rate", "spo2", "body_weight", "body_temp"}


def import_apple_health(conn, user_id: str, xml: str, alerter=None) -> dict:
    """Imports an export.xml. Values are stored in canonical units; records whose unit the
    parser doesn't know are left out and listed in `skipped_unknown_unit` (see
    ingestion.apple_health)."""
    parsed = parse(xml)
    samples, alerts = parsed.samples, parsed.alerts
    source_id = get_or_create_channel_source(conn, user_id, "apple_health")

    # 1) raw samples → device_samples (ON CONFLICT DO NOTHING = dedup of the cumulative export)
    inserted = 0
    for s in samples:
        r = conn.execute(
            text(
                """INSERT INTO device_samples (user_id, type_code, ts, value, source_id)
                   VALUES (:u, :tc, :ts, :v, :sid)
                   ON CONFLICT (user_id, type_code, ts, source_id) DO NOTHING"""
            ),
            {"u": user_id, "tc": s.type_code, "ts": s.ts, "v": s.value, "sid": source_id},
        )
        inserted += r.rowcount

    # 2) daily aggregates of mapped types → observations (auto-approve)
    type_ids = dict(
        conn.execute(
            text("SELECT code, id FROM observation_types WHERE code = ANY(:codes)"),
            {"codes": list(_AGG_TO_OBS)},
        ).all()
    )
    n_obs = 0
    for a in daily_aggregates(samples):
        tid = type_ids.get(a["type_code"])
        if tid is None:
            continue
        # idempotent: a daily aggregate per (type, day, source) is inserted only once;
        # a repeated cumulative import updates the value, doesn't create duplicates
        res = conn.execute(
            text(
                """INSERT INTO observations (user_id, type_id, effective_at, time_precision,
                       value_numeric, value_canonical, unit, status, review_status, source_id, context)
                   SELECT :u, :tid, :eff, 'date', :v, :v, :unit, NULL, 'approved', :sid, 'daily_aggregate'
                   WHERE NOT EXISTS (
                       SELECT 1 FROM observations WHERE user_id=:u AND type_id=:tid
                         AND effective_at=:eff AND source_id=:sid AND context='daily_aggregate'
                         AND deleted_at IS NULL)"""
            ),
            {"u": user_id, "tid": tid, "eff": a["day"], "v": a["value"],
             "unit": _canonical_unit(a["type_code"]), "sid": source_id},
        )
        n_obs += res.rowcount

    # 3) event flags → device_alerts (+ an alert for irregular rhythm)
    n_alerts = 0
    for al in alerts:
        conn.execute(
            text(
                """INSERT INTO device_alerts (user_id, alert_type, detected_at, source, reliability)
                   VALUES (:u, :t, :dt, 'apple_health', :rel)"""
            ),
            {"u": user_id, "t": al.alert_type, "dt": al.detected_at, "rel": al.reliability},
        )
        n_alerts += 1
        if al.alert_type in ("irregular_rhythm", "afib") and alerter is not None:
            alerter("Health OS — device alert",
                    f"Apple Watch: {al.alert_type} at {al.detected_at:%Y-%m-%d %H:%M} "
                    "(consumer device, not a diagnosis) — discuss with your doctor.")

    out = {"samples_inserted": inserted, "daily_observations": n_obs,
           "device_alerts": n_alerts, "source_id": source_id,
           "skipped_unknown_unit": [
               {"type_code": tc, "unit": unit, "records": n}
               for (tc, unit), n in sorted(parsed.skipped_units.items(), key=lambda kv: str(kv[0]))]}
    if parsed.skipped_units:
        out["note"] = (f"{sum(parsed.skipped_units.values())} record(s) skipped: unit not "
                       "recognised for the type — not stored rather than stored in the wrong unit")
    return out


def _canonical_unit(type_code: str) -> str:
    return {"heart_rate": "bpm", "spo2": "%", "body_weight": "kg", "body_temp": "Cel"}.get(
        type_code, "")
