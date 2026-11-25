"""v_observations shows how precise a value's time is (#56, 2026-11-25).

A home blood pressure diary entered per day (time_precision 'date', effective_at at midnight)
can't say whether a value was taken in the morning or the evening; read without the precision,
midnight looks like a time of day. The view gains `time_precision` at its end (CREATE OR REPLACE
VIEW can only append), so the existing grants keep working; the GRANT is repeated anyway.
"""
from __future__ import annotations

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_COLUMNS = """o.id, o.user_id, ot.code AS type_code, uk.name AS name_uk, ot.category, ot.specimen,
               o.effective_at, o.value_type, o.value_numeric, o.comparator, o.value_text,
               o.unit, o.value_canonical, ot.canonical_unit, o.ref_min, o.ref_max, o.status,
               o.result_status, o.context, o.group_id, o.panel_id, o.notes,
               ot.loinc_code, f.name AS facility"""
_FROM = """
          FROM observations o
          JOIN observation_types ot ON ot.id = o.type_id
          LEFT JOIN observation_type_names uk ON uk.type_id = ot.id AND uk.lang = 'uk'
          LEFT JOIN panels p ON p.id = o.panel_id
          LEFT JOIN facilities f ON f.id = p.facility_id
         WHERE o.review_status = 'approved' AND o.deleted_at IS NULL;"""


def upgrade() -> None:
    op.execute(
        f"""
    CREATE OR REPLACE VIEW v_observations AS
        SELECT {_COLUMNS},
               o.time_precision{_FROM}
    GRANT SELECT ON v_observations TO health_readonly;
    """
    )


def downgrade() -> None:
    # a column to remove: the view can't be replaced in place (nothing else is built on it)
    op.execute(
        f"""
    DROP VIEW v_observations;
    CREATE VIEW v_observations AS
        SELECT {_COLUMNS}{_FROM}
    GRANT SELECT ON v_observations TO health_readonly;
    """
    )
