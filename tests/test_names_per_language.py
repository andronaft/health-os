"""Names per language (#52): uk/en/es for the whole catalog, readable by the read-only role; a
value never depends on its name row; migration 0014 moves the names there and back."""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from core.config import settings
from seed.data import NUTRIENT_TYPES, OBSERVATION_TYPES
from seed.load import load
from seed.names_es import NUTRIENT_NAMES_ES, OBSERVATION_NAMES_ES

ROOT = Path(__file__).resolve().parent.parent
MARKER_CODES = [t[0] for t in OBSERVATION_TYPES]
NUTRIENT_CODES = [t[0] for t in NUTRIENT_TYPES]
ALL_LANGS = ["en", "es", "uk"]


def test_every_catalog_code_has_a_spanish_name():
    assert set(OBSERVATION_NAMES_ES) == set(MARKER_CODES)
    assert set(NUTRIENT_NAMES_ES) == set(NUTRIENT_CODES)
    assert all(0 < len(n) <= 200 for n in OBSERVATION_NAMES_ES.values())
    assert all(0 < len(n) <= 80 for n in NUTRIENT_NAMES_ES.values())


def _langs_per_code(conn, view: str, column: str, codes: list[str]) -> dict[str, list[str]]:
    rows = conn.execute(
        text(f"""SELECT {column}, array_agg(lang ORDER BY lang) FROM {view}
                 WHERE {column} = ANY(:c) GROUP BY {column}"""),
        {"c": codes},
    ).all()
    return dict(rows)


def test_readonly_login_reads_every_name_in_every_language(conn):
    conn.execute(text("SET LOCAL SESSION AUTHORIZATION health_readonly"))
    markers = _langs_per_code(conn, "v_observation_type_names", "type_code", MARKER_CODES)
    nutrients = _langs_per_code(conn, "v_nutrient_type_names", "nutrient_code", NUTRIENT_CODES)
    assert markers == dict.fromkeys(MARKER_CODES, ALL_LANGS)
    assert nutrients == dict.fromkeys(NUTRIENT_CODES, ALL_LANGS)


def test_readonly_role_gets_the_views_not_the_tables(conn):
    def can_read(relation: str) -> bool:
        return conn.execute(text("SELECT has_table_privilege('health_readonly', :r, 'SELECT')"),
                            {"r": relation}).scalar()

    assert can_read("v_observation_type_names") and can_read("v_nutrient_type_names")
    assert can_read("v_observations") and can_read("v_observations_pending")
    assert can_read("v_food_nutrients")
    for table in ("observation_type_names", "nutrient_type_names", "observation_types",
                  "facilities", "panels"):
        assert not can_read(table), table


def _source(conn, uid) -> str:
    return conn.execute(
        text("""INSERT INTO ingestion_sources (user_id, channel, extracted_by, review_status)
                VALUES (:u, 'manual', 'human', 'approved') RETURNING id"""),
        {"u": uid},
    ).scalar()


def _value(conn, uid, type_id, *, panel=None, review="approved") -> str:
    return conn.execute(
        text("""INSERT INTO observations (user_id, type_id, effective_at, value_numeric,
                                          value_canonical, review_status, source_id, panel_id)
                VALUES (:u, :t, now(), 1, 1, :r, :s, :p) RETURNING id"""),
        {"u": uid, "t": type_id, "r": review, "s": _source(conn, uid), "p": panel},
    ).scalar()


def _type_id(conn, code: str) -> int:
    return conn.execute(text("SELECT id FROM observation_types WHERE code=:c"), {"c": code}).scalar()


def test_v_observations_has_loinc_and_facility(conn, user_id):
    fac = conn.execute(text("INSERT INTO facilities (user_id, name) VALUES (:u, 'Demo Lab') "
                            "RETURNING id"), {"u": user_id}).scalar()
    panel = conn.execute(text("INSERT INTO panels (user_id, panel_date, facility_id) "
                              "VALUES (:u, current_date, :f) RETURNING id"),
                         {"u": user_id, "f": fac}).scalar()
    hb = _type_id(conn, "hemoglobin")
    row = conn.execute(text("SELECT name_uk, loinc_code, facility FROM v_observations WHERE id=:i"),
                       {"i": _value(conn, user_id, hb, panel=panel)}).one()
    assert tuple(row) == ("Гемоглобін", "718-7", "Demo Lab")

    # a value outside any panel (wearables, manual entries) stays, just without a facility
    row = conn.execute(text("SELECT loinc_code, facility FROM v_observations WHERE id=:i"),
                       {"i": _value(conn, user_id, hb)}).one()
    assert tuple(row) == ("718-7", None)


def test_a_marker_without_names_keeps_its_values_visible(conn, user_id):
    tid = conn.execute(text("""INSERT INTO observation_types (code, category, value_kind)
                               VALUES ('test_no_names', 'lab', 'numeric') RETURNING id""")).scalar()
    approved = _value(conn, user_id, tid)
    pending = _value(conn, user_id, tid, review="pending")
    assert conn.execute(text("SELECT type_code, name_uk FROM v_observations WHERE id=:i"),
                        {"i": approved}).one() == ("test_no_names", None)
    assert conn.execute(text("SELECT type_code, name_uk FROM v_observations_pending WHERE id=:i"),
                        {"i": pending}).one() == ("test_no_names", None)


def test_v_food_nutrients_still_has_the_ukrainian_name(conn, user_id):
    meal = conn.execute(text("""INSERT INTO food_log (user_id, eaten_at, description)
                                VALUES (:u, now(), 'test meal') RETURNING id"""),
                        {"u": user_id}).scalar()
    conn.execute(text("""INSERT INTO food_nutrients (food_log_id, nutrient_id, amount)
                         SELECT :m, id, 10 FROM nutrient_types WHERE code='protein'"""), {"m": meal})
    name = conn.execute(text("SELECT name_uk FROM v_food_nutrients WHERE food_log_id=:m"),
                        {"m": meal}).scalar()
    assert name == "Білки"


@pytest.mark.integration
def test_seed_can_run_again(conn):
    def counts():
        return conn.execute(text("""SELECT (SELECT count(*) FROM observation_type_names),
                                           (SELECT count(*) FROM nutrient_type_names)""")).one()

    before = counts()
    load()
    assert counts() == before


# ---- migration 0014 on a database of its own: the shared test DB stays at head ----------------

@pytest.fixture()
def scratch_db(monkeypatch):
    url = make_url(settings.database_url)
    name = f"{url.database}_migrations"
    assert "_test" in name  # settings point at the test DB here (conftest)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    scratch = url.set(database=name)
    monkeypatch.setattr(settings, "database_url", scratch.render_as_string(hide_password=False))
    engine = create_engine(scratch)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _alembic() -> Config:
    # no ini file: env.py would re-run fileConfig and switch off every logger that exists by now
    cfg = Config()
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("path_separator", "os")
    return cfg


def _columns(c, relation: str) -> list[str]:
    return list(c.execute(text("""SELECT column_name FROM information_schema.columns
                                  WHERE table_name=:r ORDER BY ordinal_position"""),
                          {"r": relation}).scalars())


def _names(c, table: str, key: str, code: str) -> dict[str, str]:
    parent = "observation_types" if table == "observation_type_names" else "nutrient_types"
    return dict(c.execute(text(f"""SELECT n.lang, n.name FROM {table} n
                                   JOIN {parent} t ON t.id = n.{key} WHERE t.code=:c"""),
                          {"c": code}).all())


@pytest.mark.integration
def test_migration_0014_moves_the_names_and_back(scratch_db):
    cfg = _alembic()
    command.upgrade(cfg, "0013")
    with scratch_db.begin() as c:
        uid = c.execute(text("INSERT INTO users DEFAULT VALUES RETURNING id")).scalar()
        both = c.execute(text("""INSERT INTO observation_types
                                   (code, loinc_code, name_uk, name_en, category, value_kind)
                                 VALUES ('m_both', '1-8', 'Показник', 'Marker', 'lab', 'numeric')
                                 RETURNING id""")).scalar()
        # types added outside the seed can have no English name
        c.execute(text("""INSERT INTO observation_types (code, name_uk, category, value_kind)
                          VALUES ('m_uk', 'Лише українською', 'lab', 'numeric')"""))
        c.execute(text("""INSERT INTO nutrient_types (code, name_uk, name_en, unit, category)
                          VALUES ('n_both', 'Поживна', 'Nutrient', 'g', 'macro')"""))
        fac = c.execute(text("INSERT INTO facilities (user_id, name) VALUES (:u, 'Demo Lab') "
                             "RETURNING id"), {"u": uid}).scalar()
        panel = c.execute(text("INSERT INTO panels (user_id, panel_date, facility_id) "
                               "VALUES (:u, current_date, :f) RETURNING id"),
                          {"u": uid, "f": fac}).scalar()
        oid = _value(c, uid, both, panel=panel)
        pending = _value(c, uid, both, review="pending")
        meal = c.execute(text("INSERT INTO food_log (user_id, eaten_at, description) "
                              "VALUES (:u, now(), 'test meal') RETURNING id"), {"u": uid}).scalar()
        c.execute(text("""INSERT INTO food_nutrients (food_log_id, nutrient_id, amount)
                          SELECT :m, id, 1 FROM nutrient_types WHERE code='n_both'"""), {"m": meal})
        old_columns = _columns(c, "v_observations")
        old_type_columns = set(_columns(c, "observation_types"))

    command.upgrade(cfg, "head")
    with scratch_db.begin() as c:
        key = "observation_type_names", "type_id"
        assert _names(c, *key, "m_both") == {"uk": "Показник", "en": "Marker"}
        assert _names(c, *key, "m_uk") == {"uk": "Лише українською"}
        assert _names(c, "nutrient_type_names", "nutrient_id", "n_both") == {
            "uk": "Поживна", "en": "Nutrient"}
        assert "name_uk" not in _columns(c, "observation_types")
        assert "name_uk" not in _columns(c, "nutrient_types")
        assert _columns(c, "v_observations") == [*old_columns, "loinc_code", "facility"]
        assert tuple(c.execute(text("""SELECT name_uk, loinc_code, facility FROM v_observations
                                       WHERE id=:i"""), {"i": oid}).one()) == (
            "Показник", "1-8", "Demo Lab")
        assert c.execute(text("SELECT name_uk FROM v_observations_pending WHERE id=:i"),
                         {"i": pending}).scalar() == "Показник"
        assert c.execute(text("SELECT name_uk FROM v_food_nutrients WHERE food_log_id=:m"),
                         {"m": meal}).scalar() == "Поживна"

        # what the old schema has no place for
        c.execute(text("""INSERT INTO observation_type_names (type_id, lang, name)
                          VALUES (:t, 'es', 'Marcador')"""), {"t": both})
        en_only = c.execute(text("""INSERT INTO observation_types (code, category, value_kind)
                                    VALUES ('m_en', 'lab', 'numeric') RETURNING id""")).scalar()
        c.execute(text("""INSERT INTO observation_type_names (type_id, lang, name)
                          VALUES (:t, 'en', 'English only')"""), {"t": en_only})
        c.execute(text("""INSERT INTO observation_types (code, category, value_kind)
                          VALUES ('m_none', 'lab', 'numeric')"""))

    command.downgrade(cfg, "0013")
    with scratch_db.begin() as c:
        rows = {r.code: (r.name_uk, r.name_en) for r in c.execute(
            text("SELECT code, name_uk, name_en FROM observation_types"))}
        assert rows == {"m_both": ("Показник", "Marker"), "m_uk": ("Лише українською", None),
                        "m_en": ("English only", "English only"), "m_none": ("m_none", None)}
        assert c.execute(text("SELECT name_uk, name_en FROM nutrient_types")).one() == (
            "Поживна", "Nutrient")
        assert set(_columns(c, "observation_types")) == old_type_columns
        assert _columns(c, "v_observations") == old_columns
        for gone in ("observation_type_names", "nutrient_type_names",
                     "v_observation_type_names", "v_nutrient_type_names"):
            assert not _columns(c, gone), gone
        assert c.execute(text("SELECT name_uk FROM v_observations WHERE id=:i"),
                         {"i": oid}).scalar() == "Показник"
        for view in ("v_observations", "v_observations_pending", "v_food_nutrients"):
            assert c.execute(text("SELECT has_table_privilege('health_readonly', :v, 'SELECT')"),
                             {"v": view}).scalar(), view

    command.upgrade(cfg, "head")
    with scratch_db.begin() as c:
        assert _names(c, "observation_type_names", "type_id", "m_both") == {
            "uk": "Показник", "en": "Marker"}
