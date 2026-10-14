"""Medication lifecycle: change history + stop events on the timeline (2026-10-13).

Medications could only be added: a wrong dose or a stopped drug could be fixed only with raw SQL,
and get_medications kept listing what the user no longer takes. update_medication and
stop_medication now edit rows in place, so — like observation_history — a trigger keeps every
previous version of the row. The timeline gets a medication_stop event next to
medication_start (title stays medication_name: the view's column types must not change).
"""
from __future__ import annotations

from alembic import op

revision = "0012"
down_revision = "0011"
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
          FROM panels
        UNION ALL SELECT 'medication_start', user_id, id,
               (start_date::timestamp AT TIME ZONE 'UTC'), medication_name
          FROM medications WHERE deleted_at IS NULL
        {stop}UNION ALL SELECT 'hospital', user_id, id,
               (admission_date::timestamp AT TIME ZONE 'UTC'), admission_diagnosis
          FROM hospital_stays WHERE deleted_at IS NULL
        UNION ALL SELECT 'vaccination', user_id, id,
               (vaccination_date::timestamp AT TIME ZONE 'UTC'), vaccine_name
          FROM vaccinations WHERE deleted_at IS NULL;
"""
_STOP = """UNION ALL SELECT 'medication_stop', user_id, id,
               (end_date::timestamp AT TIME ZONE 'UTC'), medication_name
          FROM medications WHERE deleted_at IS NULL AND end_date IS NOT NULL
        """


def upgrade() -> None:
    op.execute(
        """
    CREATE TABLE medication_history (
        id            BIGSERIAL PRIMARY KEY,
        medication_id UUID NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
        changed_at    TIMESTAMPTZ DEFAULT NOW(),
        changed_by    VARCHAR(60),
        reason        VARCHAR(40),
        old_row       JSONB NOT NULL
    );
    CREATE INDEX idx_med_history ON medication_history (medication_id, changed_at DESC);

    CREATE OR REPLACE FUNCTION log_medication_change() RETURNS TRIGGER AS $$
    BEGIN
        INSERT INTO medication_history (medication_id, changed_by, reason, old_row)
        VALUES (OLD.id, current_setting('app.actor', true), current_setting('app.reason', true),
                to_jsonb(OLD));
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER trg_medication_history
        AFTER UPDATE ON medications
        FOR EACH ROW EXECUTE FUNCTION log_medication_change();
    """
        + _TIMELINE.format(stop=_STOP)
    )


def downgrade() -> None:
    op.execute(
        """
    DROP TRIGGER IF EXISTS trg_medication_history ON medications;
    DROP FUNCTION IF EXISTS log_medication_change();
    DROP TABLE IF EXISTS medication_history;
    """
        + _TIMELINE.format(stop="")
    )
