"""get_anomalies: the latest value vs the personal baseline from earlier values (#33)."""
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from core.db import engine
from core.services import get_or_create_user, ingest_observation
from mcp_server import tools

pytestmark = pytest.mark.integration


@pytest.fixture()
def glucose_series():
    """8 stable fasting glucose values over a year, then one far off 5 days ago."""
    now = datetime.now(UTC)
    values = [(400 - 40 * i, v) for i, v in enumerate([5.0, 5.1, 4.9, 5.0, 5.2, 4.8, 5.0, 5.1])]
    values.append((5, 7.5))
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        oids = [ingest_observation(conn, uid, "глюкоза", v, "mmol/L",
                                   effective_at=now - timedelta(days=d)).observation_id
                for d, v in values]
    yield
    with engine.begin() as conn:
        sids = [r[0] for r in conn.execute(
            text("SELECT source_id FROM observations WHERE id = ANY(CAST(:i AS uuid[]))"),
            {"i": oids})]
        conn.execute(text("DELETE FROM observations WHERE id = ANY(CAST(:i AS uuid[]))"),
                     {"i": oids})
        conn.execute(text("DELETE FROM ingestion_sources WHERE id = ANY(CAST(:s AS uuid[]))"),
                     {"s": sids})


def test_latest_value_far_from_personal_baseline_is_listed(glucose_series):
    out = json.loads(tools.get_anomalies())
    (a,) = [x for x in out["anomalies"] if x["type_code"] == "glucose"]
    assert a["value"] == 7.5 and a["z"] > 2 and "baseline" in a["detail"]
    assert out["markers_checked"] >= 1 and "not a diagnosis" in out["caveat"]


def test_window_and_threshold_are_respected(glucose_series):
    assert json.loads(tools.get_anomalies(days=2))["anomalies"] == []       # latest is 5 days old
    big = json.loads(tools.get_anomalies("GLUCOSE", z_threshold=100))
    assert big["anomalies"] == [] and big["markers_checked"] == 1


def test_short_history_is_skipped_not_flagged():
    now = datetime.now(UTC)
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        oids = [ingest_observation(conn, uid, "глюкоза", v, "mmol/L",
                                   effective_at=now - timedelta(days=d)).observation_id
                for d, v in ((30, 5.0), (20, 5.1), (2, 9.0))]
    try:
        out = json.loads(tools.get_anomalies("glucose"))
        assert out["anomalies"] == [] and out["skipped_short_history"] == 1
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM observations WHERE id = ANY(CAST(:i AS uuid[]))"),
                         {"i": oids})


def test_unknown_code_is_explained():
    out = json.loads(tools.get_anomalies("glucos"))
    assert "no approved values at all" in out["note"] and out["anomalies"] == []


def test_personal_records_are_not_anomalies():
    # a new personal best is far from the earlier values by definition
    now = datetime.now(UTC)
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        # Garmin personal records come from private importers, so the seed has none: add one
        tid = conn.execute(text("""INSERT INTO observation_types (code, name_uk, category,
                                     value_kind, canonical_unit)
                                   VALUES ('pr_test_longest_ride', 'Тест: рекорд', 'fitness',
                                           'numeric', 'm') RETURNING id""")).scalar()
        sid = conn.execute(text("""INSERT INTO ingestion_sources (user_id, channel, extracted_by,
                                     review_status) VALUES (:u, 'manual', 'human', 'approved')
                                   RETURNING id"""), {"u": uid}).scalar()
        for i, v in enumerate([10, 10, 11, 11, 12, 12, 40]):
            conn.execute(text("""INSERT INTO observations (user_id, type_id, effective_at,
                                   value_numeric, value_canonical, review_status, source_id)
                                 VALUES (:u, :t, :at, :v, :v, 'approved', :s)"""),
                         {"u": uid, "t": tid, "at": now - timedelta(days=60 - 9 * i), "v": v,
                          "s": sid})
    try:
        out = json.loads(tools.get_anomalies())
        assert not any(a["type_code"].startswith("pr_") for a in out["anomalies"])
        # records are left out entirely, not just below the threshold
        assert json.loads(tools.get_anomalies("pr_test_longest_ride"))["markers_checked"] == 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM observations WHERE source_id=:s"), {"s": sid})
            conn.execute(text("DELETE FROM ingestion_sources WHERE id=:s"), {"s": sid})
            conn.execute(text("DELETE FROM observation_types WHERE id=:t"), {"t": tid})
