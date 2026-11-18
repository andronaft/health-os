"""A lab panel is on the timeline only while it has a value that isn't deleted (2026-11-18).

Panels have no deleted_at: deleting a wrongly staged panel soft-deletes its observations, and
the panel row stays. The timeline listed every panel row, so a deleted panel still showed up in
get_timeline, the overview's events and the summary's "last lab panel" — a lab visit that the
user had removed as a mistake. The view now keeps a panel only while one of its observations is
live. Its columns are unchanged (CREATE OR REPLACE VIEW can't change them), so its grants stay.
"""
from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_TIMELINE = """
    CREATE OR REPLACE VIEW health_timeline AS
        SELECT 'diagnosis' AS kind, user_id, id,
               (diagnosed_at::timestamp AT TIME ZONE 'UTC') AS at, diagnosis_name AS title
          FROM diagnoses WHERE deleted_at IS NULL
        UNION ALL SELECT 'visit', user_id, id,
               (visit_date::timestamp AT TIME ZONE 'UTC'), reason_for_visit
          FROM doctor_visits WHERE deleted_at IS NULL
        UNION ALL SELECT 'procedure', user_id, id,
               (procedure_date::timestamp AT TIME ZONE 'UTC'), procedure_name
          FROM procedures WHERE deleted_at IS NULL
        UNION ALL SELECT 'panel', user_id, id,
               (panel_date::timestamp AT TIME ZONE 'UTC'), panel_type
          FROM panels p {live}
        UNION ALL SELECT 'medication_start', user_id, id,
               (start_date::timestamp AT TIME ZONE 'UTC'), medication_name
          FROM medications WHERE deleted_at IS NULL
        UNION ALL SELECT 'medication_stop', user_id, id,
               (end_date::timestamp AT TIME ZONE 'UTC'), medication_name
          FROM medications WHERE deleted_at IS NULL AND end_date IS NOT NULL
        UNION ALL SELECT 'hospital', user_id, id,
               (admission_date::timestamp AT TIME ZONE 'UTC'), admission_diagnosis
          FROM hospital_stays WHERE deleted_at IS NULL
        UNION ALL SELECT 'vaccination', user_id, id,
               (vaccination_date::timestamp AT TIME ZONE 'UTC'), vaccine_name
          FROM vaccinations WHERE deleted_at IS NULL;
"""
_LIVE = """WHERE EXISTS (SELECT 1 FROM observations o
                             WHERE o.panel_id = p.id AND o.deleted_at IS NULL)"""


def upgrade() -> None:
    op.execute(_TIMELINE.format(live=_LIVE))


def downgrade() -> None:
    op.execute(_TIMELINE.format(live=""))
