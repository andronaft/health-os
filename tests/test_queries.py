"""core/queries.py: the read layer shared by the MCP tools and the browser UI (#51)."""
from datetime import UTC, datetime, timedelta

import pytest

from core import queries as q
from core.services import ingest_observation


@pytest.fixture()
def labs(conn, user_id):
    now = datetime.now(UTC)
    # two labs with different reference ranges for the same marker
    ingest_observation(conn, user_id, "гемоглобін", 165, "g/L", ref_min=130, ref_max=160,
                       effective_at=now - timedelta(days=400))
    ingest_observation(conn, user_id, "hemoglobin", 16.8, "g/dL", ref_min=13, ref_max=17.5,
                       effective_at=now - timedelta(days=40))
    ingest_observation(conn, user_id, "глюкоза", 5.2, "mmol/L", ref_min=3.9, ref_max=5.5,
                       effective_at=now - timedelta(days=10))
    return user_id


def test_markers_latest_value_with_its_own_range_and_counts(conn, labs):
    rows = {r["type_code"]: r for r in q.markers(conn, labs)}
    hb = rows["hemoglobin"]
    assert float(hb["value_canonical"]) == 168 and hb["n"] == 2      # latest, in g/L
    assert (float(hb["ref_min"]), float(hb["ref_max"])) == (13, 17.5)  # that report's range
    assert hb["status"] == "normal" and hb["first_at"] < hb["effective_at"]
    assert "glucose" in rows


def test_markers_category_filter(conn, labs):
    assert {r["category"] for r in q.markers(conn, labs, category="lab")} <= {"lab"}
    assert q.markers(conn, labs, category="no_such_category") == []


def test_series_oldest_first_with_per_point_ranges(conn, labs):
    pts = q.series(conn, labs, " Hemoglobin ")["points"]
    assert [float(p["value_canonical"]) for p in pts] == [165, 168]
    assert [(float(p["ref_min"]), float(p["ref_max"])) for p in pts] == [(130, 160), (13, 17.5)]
    assert [p["status"] for p in pts] == ["high", "normal"]


def test_series_limit_keeps_the_most_recent(conn, labs):
    (only,) = q.series(conn, labs, "hemoglobin", limit=1)["points"]
    assert float(only["value_canonical"]) == 168


def test_series_unknown_code_is_explained(conn, labs):
    out = q.series(conn, labs, "hemoglobn")
    assert out["points"] == [] and "hemoglobin" in out["did_you_mean"]


def test_view_rows_only_known_views(conn, user_id):
    assert isinstance(q.view_rows(conn, user_id, "diagnoses"), list)
    with pytest.raises(KeyError):
        q.view_rows(conn, user_id, "observations; DROP TABLE users")
