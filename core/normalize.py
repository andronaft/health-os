"""Observation normalization — the system's hardest problem (plan 4.4).

Raw name from a lab form → canonical observation type, with strict rules:
- ONLY an exact match of the normalized string against synonyms (lowercase, trim, ё→е, dashes).
  Embedding similarity is NOT used here (auto-accept is forbidden; "total protein" and
  "urine protein" are cosine twins but clinically different universes).
- Unit gate: no conversion to canonical_unit → mapping is forbidden even with an exact
  name match ("glucose 95" without a unit / with an unknown unit is not mapped).
- Unknown name → unknown_type=True (the pipeline asks the user, it does not guess).

Unit conversion is analyte-specific (canonical = value*factor + add_offset).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import text

_DASHES = dict.fromkeys(map(ord, "–—−‒―"), "-")
_WS = re.compile(r"\s+")


def _strip_latin_accents(s: str) -> str:
    """"Fósforo" → "Fosforo", but keep Cyrillic intact ("й", "ї" also decompose in NFD)."""
    out = []
    for ch in unicodedata.normalize("NFD", s):
        if unicodedata.combining(ch) and out and out[-1].isascii():
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def canonicalize(name: str) -> str:
    """lowercase + ё→е + Latin accents stripped + dash unification + whitespace collapse + trim."""
    s = name.replace("ё", "е").replace("Ё", "е")
    s = _strip_latin_accents(s)
    s = s.translate(_DASHES)
    s = _WS.sub(" ", s).strip().lower()
    return s


# ---- unit spelling → canonical spelling -------------------------------------------------
# Lab forms write the same unit many ways: "mmol/l", "ммоль/л", "10^9/L", "×10⁹/л", "мкМО/мл".
# Without this the unit gate fails and — worse — the critical-value check is silently skipped.
_CYR_UNITS = [  # longest first; applied to a lower-cased, space-free string
    ("ммрт.ст.", "mmhg"), ("ммрт.ст", "mmhg"), ("мм/год", "mm/h"), ("мм/ч", "mm/h"),
    ("уд/хв", "bpm"), ("уд/мин", "bpm"),
    ("мкмоль", "umol"), ("ммоль", "mmol"), ("нмоль", "nmol"), ("пмоль", "pmol"), ("моль", "mol"),
    ("мкмо", "uiu"), ("ммо", "miu"), ("мо", "iu"),
    ("мкг", "ug"), ("мг", "mg"), ("нг", "ng"), ("пг", "pg"), ("фл", "fl"),
    ("год", "h"), ("од", "u"), ("ед", "u"), ("дл", "dl"), ("мл", "ml"), ("л", "l"), ("г", "g"),
]
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_POW10 = re.compile(r"^[x×*]?10[\^*e]?(3|6|9|12)/")
# canonical spellings: every canonical unit of the catalog + source units of conversions
_KNOWN_UNITS = [
    "%", "10*9/L", "10*12/L", "mmol/L", "umol/L", "nmol/L", "pmol/L", "g/L", "g/dL", "mg/L",
    "mg/dL", "U/L", "IU/L", "IU/mL", "mIU/L", "mIU/mL", "uIU/mL", "ng/mL", "pg/mL", "ug/L",
    "mEq/L", "mmHg", "bpm", "fL", "pg", "mm/h", "h", "min", "ms", "kg", "g", "cm", "Cel",
    "degF", "kcal", "/uL", "10*3/uL", "10*6/uL", "ug/dL", "U/mL", "mU/L", "ug/g", "s",
    "mL/min/1.73m2",
]
# spellings whose key differs from the canonical unit's key (Spanish UI = IU, seg = s)
_UNIT_ALIASES = {"uui/ml": "uIU/mL", "mui/ml": "mIU/mL", "ui/ml": "IU/mL", "ui/l": "IU/L",
                 "mui/l": "mIU/L", "seg": "s", "sec": "s", "ml/min/1,73m2": "mL/min/1.73m2",
                 "ml/min/1.73": "mL/min/1.73m2", "ml/min/1,73": "mL/min/1.73m2"}


def _unit_key(unit: str) -> str:
    k = _WS.sub("", unit).lower().translate(_SUPERSCRIPTS).replace("µ", "u").replace("μ", "u")
    for cyr, lat in _CYR_UNITS:
        k = k.replace(cyr, lat)
    return _POW10.sub(lambda m: f"10*{m.group(1)}/", k)


_UNIT_BY_KEY = {_unit_key(u): u for u in _KNOWN_UNITS} | _UNIT_ALIASES

# Coarse dimension of a canonical unit spelling. Units in different groups can never be converted
# into each other, so a missing conversion between them means the name matched the wrong type
# (e.g. a bare leukocyte name mapped to the % type, printed in 10^9/L) — not a missing factor.
# Molar, mass and activity concentrations share one group: some analytes convert between them.
_DIMENSIONS = {
    "fraction": ["%"],
    "count": ["10*9/L", "10*12/L", "/uL", "10*3/uL", "10*6/uL"],
    "concentration": ["mmol/L", "umol/L", "nmol/L", "pmol/L", "mEq/L", "g/L", "g/dL", "mg/L",
                      "mg/dL", "ng/mL", "pg/mL", "ug/L", "ug/dL", "U/L", "IU/L", "IU/mL",
                      "mIU/L", "mIU/mL", "uIU/mL", "U/mL", "mU/L"],
    "pressure": ["mmHg"], "rate": ["bpm"], "volume": ["fL"], "mass": ["pg", "g", "kg"],
    "length": ["cm"], "temperature": ["Cel", "degF"], "time": ["h", "min", "ms", "s"],
    "energy": ["kcal"], "sedimentation": ["mm/h"], "filtration": ["mL/min/1.73m2"],
}
_DIMENSION_OF = {u: d for d, units in _DIMENSIONS.items() for u in units}


def units_incompatible(unit: str | None, canonical_unit: str | None) -> bool:
    """True only when both units are recognized and belong to different dimensions."""
    a = _DIMENSION_OF.get(canonicalize_unit(unit, canonical_unit) or "")
    b = _DIMENSION_OF.get(canonical_unit or "")
    return a is not None and b is not None and a != b


# "G/L" (giga per litre = 10^9/L) and "T/L" (tera = 10^12/L) — blood counts on FR/CH/DE/ES forms.
# Only the capital letter says so: lower-cased, "G/L" became g/L (grams), so platelets 25 G/L
# failed the dimension gate and were stored unmapped, never checked against the critical threshold.
_SI_COUNT_UNITS = {"G/L": "10*9/L", "G/l": "10*9/L", "T/L": "10*12/L", "T/l": "10*12/L"}


def canonicalize_unit(unit: str | None, target: str | None = None) -> str | None:
    """Map a unit as printed on a form to its canonical spelling; unknown → stripped original.

    `target` — the matched type's canonical unit, when known. "G/L" is a count (10^9/L) by
    default, but an all-caps form may print haemoglobin 145 "G/L" meaning grams: for a type that
    isn't a count, the grams reading is the only one that fits, so it is kept.
    """
    if unit is None or not unit.strip():
        return None
    by_key = _UNIT_BY_KEY.get(_unit_key(unit), unit.strip())
    si = _SI_COUNT_UNITS.get(_WS.sub("", unit))  # case-sensitive, unlike the key
    if si is None or (target is not None and _DIMENSION_OF.get(target, "count") != "count"):
        return by_key
    return si


@dataclass
class NormResult:
    raw_name: str
    type_id: int | None
    type_code: str | None
    canonical_unit: str | None
    value_canonical: float | None
    matched_synonym: str | None
    synonym_origin: str | None          # 'seed' | 'learned'
    unknown_type: bool
    conversion_missing: bool            # unit gate triggered (mapping forbidden)
    dimension_mismatch: bool = False    # the unit can't belong to this type → likely wrong type

    @property
    def ok(self) -> bool:
        return not self.unknown_type and not self.conversion_missing


def find_type(raw_name: str, conn) -> dict | None:
    """Exact match of the canonicalized string against observation_synonyms."""
    canon = canonicalize(raw_name)
    row = conn.execute(
        text(
            """
            SELECT ot.id AS type_id, ot.code, ot.canonical_unit, s.synonym, s.origin
            FROM observation_synonyms s
            JOIN observation_types ot ON ot.id = s.type_id
            WHERE translate(lower(s.synonym), 'ё', 'е') = :canon
            ORDER BY (s.origin = 'seed') DESC   -- seed takes priority over learned
            LIMIT 1
            """
        ),
        {"canon": canon},
    ).mappings().first()
    return dict(row) if row else None


def convert_to_canonical(
    type_id: int, value: float, from_unit: str, canonical_unit: str, conn
) -> float | None:
    """value in from_unit → canonical unit. None = no conversion (unit gate)."""
    if from_unit == canonical_unit:
        return value
    row = conn.execute(
        text(
            """
            SELECT factor, add_offset FROM unit_conversions
            WHERE from_unit = :from_u AND to_unit = :to_u
              AND (type_id = :tid OR type_id IS NULL)
            ORDER BY (type_id IS NOT NULL) DESC   -- analyte-specific takes priority over universal
            LIMIT 1
            """
        ),
        {"from_u": from_unit, "to_u": canonical_unit, "tid": type_id},
    ).first()
    if row is None:
        return None
    factor, offset = float(row[0]), float(row[1] or 0.0)
    return value * factor + offset


def normalize(raw_name: str, value: float | None, unit: str | None, conn) -> NormResult:
    """Full pass: name → type; value+unit → canonical (with the unit gate)."""
    t = find_type(raw_name, conn)
    if t is None:
        return NormResult(raw_name, None, None, None, None, None, None,
                          unknown_type=True, conversion_missing=False)

    canonical_unit = t["canonical_unit"]
    unit = canonicalize_unit(unit, canonical_unit)
    value_canonical: float | None = None
    conversion_missing = False

    if value is not None and canonical_unit is None:
        # dimensionless type (INR, ratios, indices, titres): nothing to convert — without this
        # the row never gets a canonical value and silently drops out of trends (#11)
        value_canonical = value
    elif value is not None and canonical_unit is not None:
        if unit is None:
            conversion_missing = True            # no unit → the value cannot be mapped
        else:
            value_canonical = convert_to_canonical(t["type_id"], value, unit, canonical_unit, conn)
            if value_canonical is None:
                conversion_missing = True

    return NormResult(
        raw_name=raw_name,
        type_id=t["type_id"],
        type_code=t["code"],
        canonical_unit=canonical_unit,
        value_canonical=value_canonical,
        matched_synonym=t["synonym"],
        synonym_origin=t["origin"],
        unknown_type=False,
        conversion_missing=conversion_missing,
        dimension_mismatch=conversion_missing and units_incompatible(unit, canonical_unit),
    )


def compute_status(
    value: float | None, ref_min: float | None, ref_max: float | None
) -> str | None:
    """status from the range ON THE FORM (plan 3.1): value and ref are in the same unit by construction.

    normal/high/low. None if there is no value or no bound at all.
    """
    if value is None or (ref_min is None and ref_max is None):
        return None
    if ref_max is not None and value > ref_max:
        return "high"
    if ref_min is not None and value < ref_min:
        return "low"
    return "normal"


def compute_limit_status(comparator: str | None, value: float | None, ref_min: float | None,
                         ref_max: float | None) -> str | None:
    """Status of a value printed as a limit (">600", "<0.5"), only when the limit decides it:
    ">600" with range 70–100 is high, "<0.5" with range 0–5 is in range. ">2" with range 0–5
    may be in range or high: None, never a guess."""
    if comparator is None:
        return compute_status(value, ref_min, ref_max)
    if value is None or (ref_min is None and ref_max is None):
        return None
    if comparator in (">", ">="):
        if ref_max is not None and value >= ref_max:
            return "high"
        if ref_max is None and (ref_min is None or value >= ref_min):
            return "normal"
        return None
    if ref_min is not None and ref_min <= 0:
        ref_min = None  # "0–5": a concentration can't be below 0, so "<0.5" is in range
    if ref_min is not None and value <= ref_min:
        return "low"
    if ref_min is None and (ref_max is None or value <= ref_max):
        return "normal"
    return None
