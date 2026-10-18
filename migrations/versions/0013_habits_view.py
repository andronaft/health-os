"""Habits readable over MCP: v_habits + a free-text frequency (2026-10-18).

The habits table (smoking, alcohol, cannabis, …) existed since 0001 but no view or tool read it,
so a habit the user reported never reached get_health_summary or prepare_doctor_visit. Only the
numeric cigarettes_per_day / drinks_per_week columns could hold "how often", which does not fit
"about once a week" — `frequency` holds it as said.
"""
from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    ALTER TABLE habits ADD COLUMN frequency VARCHAR(100);

    CREATE VIEW v_habits AS
        SELECT id, user_id, habit_type, status, frequency, cigarettes_per_day, smoking_years,
               drinks_per_week, start_date, end_date, notes
          FROM habits
         WHERE deleted_at IS NULL;

    GRANT SELECT ON v_habits TO health_readonly;
    """
    )


def downgrade() -> None:
    op.execute(
        """
    REVOKE ALL ON v_habits FROM health_readonly;
    DROP VIEW IF EXISTS v_habits;
    ALTER TABLE habits DROP COLUMN IF EXISTS frequency;
    """
    )
