"""Marker and nutrient names per language; LOINC and facility in v_observations (#52, 2026-11-03).

The browser UI shows names in several languages, so name_uk / name_en move from the type tables
into observation_type_names and nutrient_type_names. The tools keep working: the views still
expose name_uk, now from the new tables, through a LEFT JOIN — a marker without a name row must
never drop a value out of v_observations. Spanish names arrive with seed.load, like the catalog
itself. health_readonly reads only views (0003), and those give the type's code, so the names
are readable through two new views keyed by code.
"""
from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    -- same lengths as the old columns: CREATE OR REPLACE VIEW can't change a column's type
    CREATE TABLE observation_type_names (
        type_id INT NOT NULL REFERENCES observation_types(id) ON DELETE CASCADE,
        lang    VARCHAR(5) NOT NULL,
        name    VARCHAR(200) NOT NULL,
        PRIMARY KEY (type_id, lang)
    );
    CREATE TABLE nutrient_type_names (
        nutrient_id INT NOT NULL REFERENCES nutrient_types(id) ON DELETE CASCADE,
        lang        VARCHAR(5) NOT NULL,
        name        VARCHAR(80) NOT NULL,
        PRIMARY KEY (nutrient_id, lang)
    );

    INSERT INTO observation_type_names (type_id, lang, name)
        SELECT id, 'uk', name_uk FROM observation_types
        UNION ALL
        SELECT id, 'en', name_en FROM observation_types WHERE name_en IS NOT NULL;
    INSERT INTO nutrient_type_names (nutrient_id, lang, name)
        SELECT id, 'uk', name_uk FROM nutrient_types
        UNION ALL
        SELECT id, 'en', name_en FROM nutrient_types WHERE name_en IS NOT NULL;

    -- columns only appended, so the existing grants keep working
    CREATE OR REPLACE VIEW v_observations AS
        SELECT o.id, o.user_id, ot.code AS type_code, uk.name AS name_uk, ot.category, ot.specimen,
               o.effective_at, o.value_type, o.value_numeric, o.comparator, o.value_text,
               o.unit, o.value_canonical, ot.canonical_unit, o.ref_min, o.ref_max, o.status,
               o.result_status, o.context, o.group_id, o.panel_id, o.notes,
               ot.loinc_code, f.name AS facility
          FROM observations o
          JOIN observation_types ot ON ot.id = o.type_id
          LEFT JOIN observation_type_names uk ON uk.type_id = ot.id AND uk.lang = 'uk'
          LEFT JOIN panels p ON p.id = o.panel_id
          LEFT JOIN facilities f ON f.id = p.facility_id
         WHERE o.review_status = 'approved' AND o.deleted_at IS NULL;

    CREATE OR REPLACE VIEW v_observations_pending AS
        SELECT o.id, o.user_id, ot.code AS type_code, uk.name AS name_uk,
               o.effective_at, o.value_numeric, o.unit, o.value_canonical, o.status,
               o.review_status, 'PENDING — unverified, do not cite as fact' AS review_note,
               o.raw_name, o.value_text, o.ref_min, o.ref_max, o.source_id,
               (o.type_id IS NULL) AS unmapped
          FROM observations o
          LEFT JOIN observation_types ot ON ot.id = o.type_id
          LEFT JOIN observation_type_names uk ON uk.type_id = ot.id AND uk.lang = 'uk'
         WHERE o.review_status <> 'approved' AND o.deleted_at IS NULL;

    CREATE OR REPLACE VIEW v_food_nutrients AS
        SELECT fn.food_log_id, f.user_id, f.eaten_at, f.meal_type,
               nt.code AS nutrient_code, uk.name AS name_uk, nt.category, nt.unit,
               fn.amount, nt.rda, nt.upper_limit
          FROM food_nutrients fn
          JOIN food_log f       ON f.id = fn.food_log_id AND f.deleted_at IS NULL
          JOIN nutrient_types nt ON nt.id = fn.nutrient_id
          LEFT JOIN nutrient_type_names uk ON uk.nutrient_id = nt.id AND uk.lang = 'uk';

    ALTER TABLE observation_types DROP COLUMN name_uk, DROP COLUMN name_en;
    ALTER TABLE nutrient_types DROP COLUMN name_uk, DROP COLUMN name_en;

    CREATE VIEW v_observation_type_names AS
        SELECT ot.code AS type_code, n.lang, n.name
          FROM observation_type_names n
          JOIN observation_types ot ON ot.id = n.type_id;

    CREATE VIEW v_nutrient_type_names AS
        SELECT nt.code AS nutrient_code, n.lang, n.name
          FROM nutrient_type_names n
          JOIN nutrient_types nt ON nt.id = n.nutrient_id;

    GRANT SELECT ON v_observation_type_names TO health_readonly;
    GRANT SELECT ON v_nutrient_type_names TO health_readonly;
    """
    )


def downgrade() -> None:
    op.execute(
        """
    REVOKE ALL ON v_observation_type_names, v_nutrient_type_names FROM health_readonly;
    DROP VIEW v_observation_type_names;
    DROP VIEW v_nutrient_type_names;

    ALTER TABLE observation_types ADD COLUMN name_uk VARCHAR(200), ADD COLUMN name_en VARCHAR(200);
    ALTER TABLE nutrient_types ADD COLUMN name_uk VARCHAR(80), ADD COLUMN name_en VARCHAR(80);

    -- other languages have no column to go back to; name_uk is NOT NULL in the old schema
    UPDATE observation_types t SET
        name_en = (SELECT name FROM observation_type_names WHERE type_id = t.id AND lang = 'en'),
        name_uk = COALESCE(
            (SELECT name FROM observation_type_names WHERE type_id = t.id AND lang = 'uk'),
            (SELECT name FROM observation_type_names WHERE type_id = t.id AND lang = 'en'),
            t.code);
    UPDATE nutrient_types t SET
        name_en = (SELECT name FROM nutrient_type_names WHERE nutrient_id = t.id AND lang = 'en'),
        name_uk = COALESCE(
            (SELECT name FROM nutrient_type_names WHERE nutrient_id = t.id AND lang = 'uk'),
            (SELECT name FROM nutrient_type_names WHERE nutrient_id = t.id AND lang = 'en'),
            t.code);
    ALTER TABLE observation_types ALTER COLUMN name_uk SET NOT NULL;
    ALTER TABLE nutrient_types ALTER COLUMN name_uk SET NOT NULL;

    -- has columns to remove, so it can't be replaced in place
    DROP VIEW v_observations;
    CREATE VIEW v_observations AS
        SELECT o.id, o.user_id, ot.code AS type_code, ot.name_uk, ot.category, ot.specimen,
               o.effective_at, o.value_type, o.value_numeric, o.comparator, o.value_text,
               o.unit, o.value_canonical, ot.canonical_unit, o.ref_min, o.ref_max, o.status,
               o.result_status, o.context, o.group_id, o.panel_id, o.notes
          FROM observations o
          JOIN observation_types ot ON ot.id = o.type_id
         WHERE o.review_status = 'approved' AND o.deleted_at IS NULL;
    GRANT SELECT ON v_observations TO health_readonly;

    CREATE OR REPLACE VIEW v_observations_pending AS
        SELECT o.id, o.user_id, ot.code AS type_code, ot.name_uk,
               o.effective_at, o.value_numeric, o.unit, o.value_canonical, o.status,
               o.review_status, 'PENDING — unverified, do not cite as fact' AS review_note,
               o.raw_name, o.value_text, o.ref_min, o.ref_max, o.source_id,
               (o.type_id IS NULL) AS unmapped
          FROM observations o
          LEFT JOIN observation_types ot ON ot.id = o.type_id
         WHERE o.review_status <> 'approved' AND o.deleted_at IS NULL;

    CREATE OR REPLACE VIEW v_food_nutrients AS
        SELECT fn.food_log_id, f.user_id, f.eaten_at, f.meal_type,
               nt.code AS nutrient_code, nt.name_uk, nt.category, nt.unit,
               fn.amount, nt.rda, nt.upper_limit
          FROM food_nutrients fn
          JOIN food_log f       ON f.id = fn.food_log_id AND f.deleted_at IS NULL
          JOIN nutrient_types nt ON nt.id = fn.nutrient_id;

    DROP TABLE observation_type_names;
    DROP TABLE nutrient_type_names;
    """
    )
