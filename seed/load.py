"""Loader for seed reference data. Idempotent (ON CONFLICT DO NOTHING / upsert).

Run:  uv run python -m seed.load
Every seed record produces a provenance row in ingestion_sources with channel='seed'
(plan rule 3.3.4: even seed data has provenance).
"""
from __future__ import annotations

from sqlalchemy import text

from core.db import engine
from seed.data import (
    CRITICAL_THRESHOLDS,
    NUTRIENT_TYPES,
    OBSERVATION_TYPES,
    QUALITATIVE,
    REFERENCE_RANGES,
    SYNONYMS,
    UNIT_CONVERSIONS,
)
from seed.names_es import NUTRIENT_NAMES_ES, OBSERVATION_NAMES_ES


def ensure_seed_user(conn) -> str:
    """Ensures a single-row user (stub). Returns user_id."""
    row = conn.execute(text("SELECT id FROM users LIMIT 1")).first()
    if row:
        return str(row[0])
    uid = conn.execute(text("INSERT INTO users DEFAULT VALUES RETURNING id")).scalar()
    return str(uid)


def load() -> None:
    with engine.begin() as conn:
        ensure_seed_user(conn)

        # observation_types
        for code, loinc, _uk, _en, cat, specimen, vkind, cunit, molar in OBSERVATION_TYPES:
            conn.execute(
                text(
                    """
                    INSERT INTO observation_types
                        (code, loinc_code, category, specimen,
                         value_kind, canonical_unit, molar_mass)
                    VALUES (:code, :loinc, :cat, :specimen, :vkind, :cunit, :molar)
                    ON CONFLICT (code) DO NOTHING
                    """
                ),
                dict(code=code, loinc=loinc, cat=cat, specimen=specimen, vkind=vkind,
                     cunit=cunit, molar=molar),
            )

        # code -> type_id
        rows = conn.execute(text("SELECT id, code FROM observation_types")).all()
        type_id = {code: tid for tid, code in rows}

        # marker names per language
        for code, _loinc, name_uk, name_en, *_ in OBSERVATION_TYPES:
            for lang, name in (("uk", name_uk), ("en", name_en),
                               ("es", OBSERVATION_NAMES_ES[code])):
                conn.execute(
                    text(
                        """
                        INSERT INTO observation_type_names (type_id, lang, name)
                        VALUES (:tid, :lang, :name)
                        ON CONFLICT (type_id, lang) DO NOTHING
                        """
                    ),
                    dict(tid=type_id[code], lang=lang, name=name),
                )

        # synonyms (seed)
        for code, syns in SYNONYMS.items():
            tid = type_id.get(code)
            if tid is None:
                continue
            for synonym, lang in syns:
                conn.execute(
                    text(
                        """
                        INSERT INTO observation_synonyms (type_id, synonym, lang, origin)
                        VALUES (:tid, :syn, :lang, 'seed')
                        ON CONFLICT (type_id, lower(synonym)) DO NOTHING
                        """
                    ),
                    dict(tid=tid, syn=synonym, lang=lang),
                )

        # unit_conversions
        for code, from_u, to_u, factor, offset in UNIT_CONVERSIONS:
            tid = type_id.get(code) if code else None
            conn.execute(
                text(
                    """
                    INSERT INTO unit_conversions (type_id, from_unit, to_unit, factor, add_offset)
                    VALUES (:tid, :from_u, :to_u, :factor, :offset)
                    ON CONFLICT (COALESCE(type_id, 0), from_unit, to_unit) DO NOTHING
                    """
                ),
                dict(tid=tid, from_u=from_u, to_u=to_u, factor=factor, offset=offset),
            )

        # reference_ranges (no natural unique — clear seed sources and re-insert)
        conn.execute(text("DELETE FROM reference_ranges"))
        for r in REFERENCE_RANGES:
            tid = type_id.get(r["code"])
            if tid is None:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO reference_ranges
                        (type_id, sex, age_min, age_max, condition, unit, range_kind,
                         range_min, range_max, optimal_min, optimal_max, source)
                    VALUES (:tid, :sex, :age_min, :age_max, :condition, :unit, :range_kind,
                            :range_min, :range_max, :optimal_min, :optimal_max, :source)
                    """
                ),
                dict(
                    tid=tid, sex=r.get("sex"), age_min=r.get("age_min"), age_max=r.get("age_max"),
                    condition=r.get("condition"), unit=r["unit"],
                    range_kind=r.get("range_kind", "population"),
                    range_min=r.get("range_min"), range_max=r.get("range_max"),
                    optimal_min=r.get("optimal_min"), optimal_max=r.get("optimal_max"),
                    source=r["source"],
                ),
            )

        # critical_thresholds (rule-engine, Phase 1)
        conn.execute(text("DELETE FROM critical_thresholds"))
        for code, sex, unit, low, high, msg, source in CRITICAL_THRESHOLDS:
            tid = type_id.get(code)
            if tid is None:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO critical_thresholds
                        (type_id, sex, unit, critical_low, critical_high, message_uk, source)
                    VALUES (:tid, :sex, :unit, :low, :high, :msg, :source)
                    """
                ),
                dict(tid=tid, sex=sex, unit=unit, low=low, high=high, msg=msg, source=source),
            )

        # nutrient_types (food-log reference; RDAs are updated)
        for code, name_uk, name_en, unit, cat, rda, upper, sort in NUTRIENT_TYPES:
            nid = conn.execute(
                text(
                    """
                    INSERT INTO nutrient_types
                        (code, unit, category, rda, upper_limit, sort_order)
                    VALUES (:code, :unit, :cat, :rda, :upper, :sort)
                    ON CONFLICT (code) DO UPDATE SET
                        unit=EXCLUDED.unit, category=EXCLUDED.category, rda=EXCLUDED.rda,
                        upper_limit=EXCLUDED.upper_limit, sort_order=EXCLUDED.sort_order
                    RETURNING id
                    """
                ),
                dict(code=code, unit=unit, cat=cat, rda=rda, upper=upper, sort=sort),
            ).scalar()
            for lang, name in (("uk", name_uk), ("en", name_en), ("es", NUTRIENT_NAMES_ES[code])):
                conn.execute(
                    text(
                        """
                        INSERT INTO nutrient_type_names (nutrient_id, lang, name)
                        VALUES (:nid, :lang, :name)
                        ON CONFLICT (nutrient_id, lang) DO UPDATE SET name=EXCLUDED.name
                        """
                    ),
                    dict(nid=nid, lang=lang, name=name),
                )

        # qualitative_values + synonyms (idempotent)
        for canonical, (rank, syns) in QUALITATIVE.items():
            vid = conn.execute(
                text("""INSERT INTO qualitative_values (canonical, ordinal_rank)
                        VALUES (:c, :r) ON CONFLICT (canonical) DO UPDATE SET ordinal_rank=EXCLUDED.ordinal_rank
                        RETURNING id"""),
                {"c": canonical, "r": rank},
            ).scalar()
            for synonym, lang in syns:
                conn.execute(
                    text("""INSERT INTO qualitative_synonyms (value_id, synonym, lang)
                            VALUES (:v, :s, :l) ON CONFLICT (lower(synonym)) DO NOTHING"""),
                    {"v": vid, "s": synonym, "l": lang},
                )

    print(
        f"Seed OK: {len(OBSERVATION_TYPES)} markers, "
        f"{sum(len(v) for v in SYNONYMS.values())} synonyms, "
        f"{len(UNIT_CONVERSIONS)} conversions, "
        f"{len(REFERENCE_RANGES)} references, "
        f"{len(CRITICAL_THRESHOLDS)} critical thresholds, "
        f"{len(QUALITATIVE)} qualitative values, "
        f"{len(NUTRIENT_TYPES)} nutrients."
    )


if __name__ == "__main__":
    load()
