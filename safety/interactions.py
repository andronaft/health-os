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


def biotin_interference_warning(taking_biotin: bool, planned_test_codes: list[str]) -> str | None:
    """Biotin before TSH/troponin/other immunoassays distorts the result."""
    if not taking_biotin:
        return None
    hits = [c for c in planned_test_codes if c in _BIOTIN_AFFECTED]
    if not hits:
        return None
    return (f"You're taking biotin — it distorts immunoassays ({', '.join(hits)}). "
            "It's usually advised to stop biotin 48–72 h before the test. Check with the lab/doctor.")
