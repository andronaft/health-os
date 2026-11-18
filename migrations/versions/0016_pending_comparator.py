"""The pending view shows a limit as a limit, and the row's notes (2026-11-18).

v_observations_pending had no comparator, so list_pending_reviews showed a potassium printed
as ">5" as a plain 5.0 — a value inside the range instead of one a critical value may lie past.
It gains `comparator`, and `notes`, where recompute explains why an approved row came back to
review. Columns are only appended (CREATE OR REPLACE VIEW can't insert or drop them), so the
existing grants keep working; the GRANT is repeated anyway, as 0011 does.
"""
from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_COLUMNS = """o.id, o.user_id, ot.code AS type_code, uk.name AS name_uk,
               o.effective_at, o.value_numeric, o.unit, o.value_canonical, o.status,
               o.review_status, 'PENDING — unverified, do not cite as fact' AS review_note,
               o.raw_name, o.value_text, o.ref_min, o.ref_max, o.source_id,
               (o.type_id IS NULL) AS unmapped"""
_FROM = """
          FROM observations o
          LEFT JOIN observation_types ot ON ot.id = o.type_id
          LEFT JOIN observation_type_names uk ON uk.type_id = ot.id AND uk.lang = 'uk'
         WHERE o.review_status <> 'approved' AND o.deleted_at IS NULL;"""


def upgrade() -> None:
    op.execute(
        f"""
    CREATE OR REPLACE VIEW v_observations_pending AS
        SELECT {_COLUMNS},
               o.comparator, o.notes{_FROM}
    GRANT SELECT ON v_observations_pending TO health_readonly;
    """
    )


def downgrade() -> None:
    # columns to remove: the view can't be replaced in place
    op.execute(
        f"""
    DROP VIEW v_observations_pending;
    CREATE VIEW v_observations_pending AS
        SELECT {_COLUMNS}{_FROM}
    GRANT SELECT ON v_observations_pending TO health_readonly;
    """
    )
