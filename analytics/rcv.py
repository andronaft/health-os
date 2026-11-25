"""Is a change between two results larger than lab noise? The reference change value (RCV).

    RCV = √2 · z · √(CVa² + CVi²)

CVi is the within-subject biological variation: how much one healthy person's value moves from
week to week by itself. CVa is the lab's analytical imprecision. Two results that differ by less
than the RCV can't be told apart from that noise (two-sided, 95 %: z = 1.96).

Only markers with a published, cited CVi are here; every other marker gets no verdict at all
(None), never "not significant". CVa is the lab's own and is not on record, so it is taken as the
"desirable" analytical performance specification derived from biological variation, CVa = 0.5 ·
CVi (Fraser & Petersen; kept as the desirable level in the EFLM 2015 Milan consensus). A lab worse
than that makes the true RCV larger, so this can call a change significant that the lab's own
noise would explain: the report says which numbers it used.
"""
from __future__ import annotations

import math

Z_95 = 1.96
CVA_SHARE = 0.5  # desirable analytical imprecision: half the within-subject CV

EFLM = ("EFLM Biological Variation Database, meta-analysis, serum/plasma "
        "(biologicalvariation.eu, read 2026-11-25)")
EFLM_VIA_BIORAD = ("EFLM Biological Variation Database 2021, as tabulated in Bio-Rad Q-1680-U "
                   "\"Biological Variation Updated Values\" (2025)")

# type_code → (CVi %, source). Add a marker only with a number you can cite.
WITHIN_SUBJECT_CV = {
    "ldl": (7.4, EFLM),
    "cholesterol_total": (5.3, EFLM),
    "glucose": (4.6, EFLM_VIA_BIORAD),
}


def rcv_percent(cvi: float, cva: float | None = None, z: float = Z_95) -> float:
    """The RCV in percent of the first value, for CVs given in percent."""
    cva = cvi * CVA_SHARE if cva is None else cva
    return math.sqrt(2) * z * math.sqrt(cva ** 2 + cvi ** 2)


def compare(code: str, before: float | None, after: float | None) -> dict | None:
    """{"percent", "rcv", "significant", "cvi", "cva", "source"} for a marker with a cited CVi
    and two positive numeric values; None otherwise (no verdict either way)."""
    known = WITHIN_SUBJECT_CV.get(code)
    if known is None or before is None or after is None:
        return None
    before, after = float(before), float(after)
    if not (math.isfinite(before) and math.isfinite(after)) or before <= 0:
        return None
    cvi, source = known
    rcv = rcv_percent(cvi)
    percent = (after - before) / before * 100
    return {"percent": round(percent, 1), "rcv": round(rcv, 1),
            "significant": abs(percent) > rcv, "cvi": cvi, "cva": round(cvi * CVA_SHARE, 2),
            "source": source}
