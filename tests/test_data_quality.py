"""check_data_quality: what to verify against the original documents."""
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from core.db import engine
from core.services import get_or_create_user, ingest_observation
from mcp_server import tools

pytestmark = pytest.mark.integration


@pytest.fixture()
def records():
    now = datetime.now(UTC)
    rows = [  # (raw name, value, unit, ref_min, ref_max, days ago)
        ("LDL", 3.1, "mmol/L", 0.0, 3.4, 400),        # normal range
        ("LDL", 3.2, "mmol/L", 3.15, 3.25, 300),      # far narrower than the other → flag
        ("LDL", 3.0, "mmol/L", 3.4, 0.0, 200),        # swapped → flag
        ("ferritin", 120, "ng/mL", None, None, 100),
        ("ferritin", 12, "ng/mL", None, None, 50),    # 10× drop → flag
        ("sodium", 140, "mmol/L", 135, 145, 90),      # narrow but normal for sodium
        ("sodium", 141, "mmol/L", 136, 146, 30),
    ]
    with engine.begin() as conn:
        uid = get_or_create_user(conn)
        oids = [ingest_observation(conn, uid, n, v, u, ref_min=lo, ref_max=hi,
                                   effective_at=now - timedelta(days=d)).observation_id
                for n, v, u, lo, hi, d in rows]
    yield
    with engine.begin() as conn:
        sids = [r[0] for r in conn.execute(
            text("SELECT DISTINCT source_id FROM observations WHERE id = ANY(CAST(:i AS uuid[]))"),
            {"i": oids})]
        conn.execute(text("DELETE FROM observation_history WHERE observation_id = "
                          "ANY(CAST(:i AS uuid[]))"), {"i": oids})
        conn.execute(text("DELETE FROM observations WHERE id = ANY(CAST(:i AS uuid[]))"),
                     {"i": oids})
        conn.execute(text("DELETE FROM ingestion_sources WHERE id = ANY(CAST(:s AS uuid[]))"),
                     {"s": sids})


def _kinds(out):
    return {(i["kind"], i["type_code"]) for i in out["issues"]}


def test_flags_ranges_and_jumps_to_verify(records):
    out = json.loads(tools.check_data_quality())
    kinds = _kinds(out)
    assert ("range_unusually_narrow", "ldl") in kinds
    assert ("range_swapped_or_empty", "ldl") in kinds
    assert ("large_jump", "ferritin") in kinds
    assert "verify each item against the original" in out["note"]


def test_normal_narrow_ranges_are_not_flagged(records):
    # sodium's range is narrow by nature; two labs with similar ranges are fine
    assert not any(t == "sodium" for _, t in _kinds(json.loads(tools.check_data_quality())))


def test_counts_are_reported():
    out = json.loads(tools.check_data_quality())
    assert {"observations", "issues", "approved_without_canonical", "pending_review",
            "pending_unmapped", "active_diagnoses_older_than_2y"} <= set(out["counts"])
