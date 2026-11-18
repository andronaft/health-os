"""Drug interactions — a hard interim guardrail (plan 3.6, v3).

The LLM is NOT an interaction engine (it hallucinates both ways). Until a deterministic DDI
layer EXISTS, the system REFUSES to assess interactions and does not let the LLM answer "can I
take X with my medications". The exception — a few deterministic rules that can actually be
computed:
  1) the total daily paracetamol dose across all products (the main real risk — paracetamol
     in 3 combination OTCs at once);
  2) biotin before TSH/troponin distorts immunoassays.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

REFUSAL = (
    "I don't assess drug interactions and don't say whether a specific medication is \"safe to "
    "take\" — that must be checked by a doctor/pharmacist or an interaction checker (e.g. "
    "Drugs.com interaction checker). Likewise I don't assess contraindications by condition "
    "(asthma/CKD/ulcer), cross-allergy, pregnancy/lactation."
)

PARACETAMOL_MAX_DAILY_MG = 4000       # upper adult limit
PARACETAMOL_CAUTION_MG = 3000         # caution (long-term use / liver factors)


@dataclass
class ParacetamolLoad:
    total_mg_per_day: float
    products: list[str]
    level: str            # ok / caution / exceeded / incomplete
    message: str
    missing_dose: list[str] = field(default_factory=list)  # products the total couldn't include


def refuse_interaction_query() -> str:
    return REFUSAL


# Names a recorded medication may carry when it is paracetamol: the INN in several languages and
# brands that are paracetamol products (all of them contain it). A brand list is never complete,
# so the check also looks at the ATC code, and the model is told to ask about cold/flu remedies.
# Combination products (Frenadol, Efferalgan codeine…) contain other drugs too: their paracetamol
# content must come from the dose given (mg of paracetamol per dose), never assumed from the name.
PARACETAMOL_ALIASES = (
    "paracetamol", "paracetamolo", "paracetamolum", "acetaminophen",
    "acetaminofen",  # also "acetaminofén": names are matched without accents
    "парацетамол", "ацетамінофен", "ацетаминофен",
    "gelocatil", "panadol", "efferalgan", "dafalgan", "termalgin", "tylenol", "apiretal",
    "frenadol", "calpol", "xumadol", "perfalgan",
)
# ATC: paracetamol; paracetamol combinations excl. / with psycholeptics
PARACETAMOL_ATC = ("N02BE01", "N02BE51", "N02BE71")


def fold(s: str | None) -> str:
    """Lower-case with accents stripped (NFKD): "Acetaminofén" → "acetaminofen". Cyrillic й/ї
    lose their marks too, which is harmless for matching because the aliases are folded alike."""
    decomposed = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


# Anywhere in the name, as before: a whole-word match missed inflected and joined-up names
# ("Парацетамолу таблетки", "Paracetamolratiopharm") and so skipped the daily total. Counting a
# product that isn't paracetamol only adds to the total; missing one is false reassurance.
_PARACETAMOL_RE = re.compile("|".join(re.escape(fold(a)) for a in PARACETAMOL_ALIASES))


def is_paracetamol(name: str | None, atc_code: str | None = None) -> bool:
    """A medication is counted as paracetamol by its ATC code or by a known name/brand.

    A substring match on a few INN spellings missed every brand (Gelocatil 1 g × 4 = 4 g/day
    gave no paracetamol check at all) and accented spellings (Acetaminofén)."""
    if atc_code and atc_code.strip().upper() in PARACETAMOL_ATC:
        return True
    return bool(_PARACETAMOL_RE.search(fold(name)))


def same_product(a: str | None, b: str | None) -> bool:
    """Two names of one product: equal after folding and dropping spaces and punctuation
    ("Gelocatil 1 g" == "gelocatil 1g")."""
    def key(s):
        return "".join(c for c in fold(s) if c.isalnum())
    return bool(key(a)) and key(a) == key(b)


def check_paracetamol_load(products: list[dict]) -> ParacetamolLoad:
    """products: [{name, mg_per_dose, doses_per_day}] — only those containing paracetamol.

    Computes the total daily dose across all products (combination OTCs + mono). This is
    deterministic arithmetic, not "interaction assessment": paracetamol in several
    over-the-counter products at once — the main real overdose risk.
    """
    total = 0.0
    names: list[str] = []
    missing: list[str] = []
    for p in products:
        name = p.get("name", "?")
        names.append(name)
        mg, n = _positive(p.get("mg_per_dose")), _positive(p.get("doses_per_day"))
        if mg is None or n is None:
            # counting it as 0 mg used to report "within limits" — false reassurance
            missing.append(name)
            continue
        total += mg * n

    if total > PARACETAMOL_MAX_DAILY_MG:
        level = "exceeded"
        msg = (f"⚠️ Total paracetamol ~{total:.0f} mg/day exceeds the limit of "
               f"{PARACETAMOL_MAX_DAILY_MG} mg. Risk of liver damage — review with a doctor/pharmacist.")
        if missing:
            msg += f" Not counted (dose unknown): {', '.join(missing)}."
    elif missing:
        level = "incomplete"
        msg = (f"Can't confirm the daily paracetamol total: the dose or doses per day is unknown "
               f"for {', '.join(missing)}. Ask the user for mg per dose and doses per day — "
               f"4 doses of 1000 mg already reach the {PARACETAMOL_MAX_DAILY_MG} mg limit."
               + (f" The products with a known dose add up to ~{total:.0f} mg/day." if total
                  else ""))
    elif total >= PARACETAMOL_CAUTION_MG:
        level = "caution"
        msg = (f"Total paracetamol ~{total:.0f} mg/day is close to the limit of "
               f"{PARACETAMOL_MAX_DAILY_MG} mg. Caution with long-term use/liver factors.")
    else:
        level = "ok"
        msg = f"Total paracetamol ~{total:.0f} mg/day — within limits."
    if len(names) > 1:
        msg += f" Sources ({len(names)}): {', '.join(names)}."
    return ParacetamolLoad(total, names, level, msg, missing)


def _positive(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


# analytes that biotin distorts (immunoassays)
_BIOTIN_AFFECTED = {"tsh", "ft4", "ft3", "troponin", "vitamin_d", "vitamin_b12", "ferritin"}


def _test_code(name: str) -> str:
    """"TSH", " Vitamin D", "vitamin-b12" → the catalog codes the set above uses."""
    return re.sub(r"[\s\-]+", "_", fold(str(name)).strip())


def biotin_interference_warning(taking_biotin: bool, planned_test_codes: list[str]) -> str | None:
    """Biotin before TSH/troponin/other immunoassays distorts the result.

    Test names are matched case-insensitively: ["TSH"] used to give no warning at all."""
    if not taking_biotin:
        return None
    hits = [c for c in dict.fromkeys(_test_code(t) for t in planned_test_codes)
            if c in _BIOTIN_AFFECTED]
    if not hits:
        return None
    return (f"You're taking biotin — it distorts immunoassays ({', '.join(hits)}). "
            "It's usually advised to stop biotin 48–72 h before the test. Check with the lab/doctor.")
