from datetime import date

import pytest
from sqlalchemy import text

from core.health_summary import build
from seed.demo import load_demo


def test_demo_loads_into_empty_db(conn):
    uid = load_demo(conn, today=date(2026, 1, 15))
    res = build(conn, uid)
    assert res.valid, res.issues
    assert res.counts == {"allergies": 1, "active_diagnoses": 1, "current_medications": 1,
                          "habits": 0}
    # every demo marker is known to the seed catalog; only the fresh, unapproved panel is pending
    q = lambda sql: conn.execute(text(sql)).scalar()  # noqa: E731
    assert q("SELECT count(*) FROM observations WHERE review_status = 'pending'") == 2
    assert q("""SELECT count(*) FROM observations o JOIN observation_types t ON t.id = o.type_id
                WHERE t.code = 'ldl' AND o.review_status = 'approved'""") == 5  # enough for a trend
    assert q("SELECT count(*) FROM food_log") == 10


def test_demo_refuses_non_empty_db(conn):
    load_demo(conn, today=date(2026, 1, 15))
    with pytest.raises(RuntimeError, match="fresh database"):
        load_demo(conn)
