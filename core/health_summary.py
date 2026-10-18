"""Health Summary — deterministic block + post-validation (plan 4.1).

Safety-critical sections must NOT be trusted to LLM generation (one regeneration that
rephrases "anaphylaxis to penicillin" as "sensitivity to antibiotics" — and the point of
the system is dead). So this block is built SQL→template, zero LLM. The LLM block
(trends/questions) is added separately later in Phase 1, AFTER the cache breakpoint, and
never touches these sections.

Post-validation: the count of allergies/diagnoses/medications/habits in the text == COUNT from the
database; on a mismatch the summary is not published (the old version stays + an alert).

"Absence of data is also a clinical fact" (protection against false reassurance): a list of
important markers that have not been checked in a long time or never measured.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import text

# markers whose absence is itself a clinical fact (the profile's screening minimum)
STALE_WATCH = [
    ("cholesterol_total", "Lipid panel (cholesterol)"),
    ("glucose", "Glucose"),
    ("hba1c", "HbA1c"),
    ("hemoglobin", "Complete blood count (Hb)"),
    ("tsh", "TSH"),
    ("creatinine", "Creatinine"),
]
STALE_MONTHS = 12


@dataclass
class SummaryResult:
    text: str
    counts: dict[str, int]
    valid: bool
    issues: list[str] = field(default_factory=list)


def _age(dob: date) -> int:
    t = date.today()
    return t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))


def build(conn, user_id: str) -> SummaryResult:
    lines: list[str] = []
    counts: dict[str, int] = {}

    # --- age/sex ---
    prof = conn.execute(
        text("SELECT date_of_birth, sex, blood_type FROM user_profile WHERE user_id=:u"),
        {"u": user_id},
    ).mappings().first()
    lines.append(f"# Health Summary (deterministic block) — {datetime.now():%Y-%m-%d %H:%M}")
    lines.append("")
    if prof:
        age = _age(prof["date_of_birth"])
        bt = f", blood type {prof['blood_type']}" if prof["blood_type"] else ""
        lines.append(f"**Profile:** {prof['sex']}, {age} yr{bt}")
    else:
        lines.append("**Profile:** not filled in (date of birth and sex required).")
    lines.append("")

    # --- pending review: critical values first (never let "no abnormalities" hide them) ---
    pending = conn.execute(
        text(
            """SELECT ot.code, o.raw_name, o.value_numeric, o.value_text, o.unit,
                      o.effective_at, o.status, (o.type_id IS NULL) AS unmapped,
                      (o.value_canonical IS NULL AND o.value_numeric IS NOT NULL
                       AND EXISTS (SELECT 1 FROM critical_thresholds ct
                                   WHERE ct.type_id = o.type_id)) AS unverifiable
               FROM observations o LEFT JOIN observation_types ot ON ot.id = o.type_id
               WHERE o.user_id=:u AND o.review_status='pending' AND o.deleted_at IS NULL
               ORDER BY o.effective_at DESC"""
        ),
        {"u": user_id},
    ).mappings().all()
    alarming = [p for p in pending if p["status"] == "critical" or p["unverifiable"]]
    unmapped = [p for p in pending if p["unmapped"]]
    if pending:
        lines.append(f"## ⚠️ Awaiting review ({len(pending)} values, not yet facts)")
        for p in alarming:
            what = ("**CRITICAL value** — contact a doctor today, even if it may be a "
                    "recognition error" if p["status"] == "critical" else
                    "**unit not recognized — critical check impossible**, compare with the form now")
            lines.append(f"- {p['code']} {p['value_numeric']:g} {p['unit'] or ''} "
                         f"({p['effective_at']:%Y-%m-%d}): {what}")
        if unmapped:
            # an unrecognized marker can't be checked against critical thresholds at all
            shown = ", ".join(
                f"“{p['raw_name']}” "
                + (f"{p['value_numeric']:g} {p['unit'] or ''}".strip()
                   if p["value_numeric"] is not None else (p["value_text"] or ""))
                for p in unmapped[:8])
            more = f" … and {len(unmapped) - 8} more" if len(unmapped) > 8 else ""
            lines.append(f"- **{len(unmapped)} unrecognized marker(s)** — not checked for critical "
                         f"values until mapped (map_pending_observation): {shown}{more}")
        rest = len(pending) - len(alarming) - len(unmapped)
        if rest > 0:
            lines.append(f"- {rest} other value(s) — see list_pending_reviews")
        lines.append("")

    # --- allergies (including unverified!) ---
    allergies = conn.execute(
        text(
            """SELECT allergen, reaction, severity, verified FROM allergies
               WHERE user_id=:u AND deleted_at IS NULL ORDER BY verified DESC, allergen"""
        ),
        {"u": user_id},
    ).mappings().all()
    counts["allergies"] = len(allergies)
    lines.append(f"## Allergies ({len(allergies)})")
    if allergies:
        for a in allergies:
            mark = "" if a["verified"] else " ⚠️(unverified — treated as an allergy)"
            r = f" — {a['reaction']}" if a["reaction"] else ""
            lines.append(f"- **{a['allergen']}**{r}{mark}")
    else:
        lines.append("- None known in the system (≠ guarantee of absence).")
    lines.append("")

    # --- active diagnoses with verification_status ---
    diags = conn.execute(
        text(
            """SELECT diagnosis_name, verification_status, icd10_code FROM diagnoses
               WHERE user_id=:u AND clinical_status='active' AND deleted_at IS NULL
               ORDER BY diagnosed_at DESC"""
        ),
        {"u": user_id},
    ).mappings().all()
    counts["active_diagnoses"] = len(diags)
    lines.append(f"## Active diagnoses ({len(diags)})")
    if diags:
        for d in diags:
            icd = f" [{d['icd10_code']}]" if d["icd10_code"] else ""
            vs = d["verification_status"] or "?"
            flag = "" if vs == "confirmed" else f" — ⚠️ {vs} (not certain)"
            lines.append(f"- {d['diagnosis_name']}{icd}{flag}")
    else:
        lines.append("- None active in the system.")
    lines.append("")

    # --- current medications with doses ---
    meds = conn.execute(
        text(
            """SELECT medication_name, dose_amount, dose_unit, times_per_day, product_type
               FROM medications WHERE user_id=:u AND status='taking' AND deleted_at IS NULL
               ORDER BY medication_name"""
        ),
        {"u": user_id},
    ).mappings().all()
    counts["current_medications"] = len(meds)
    lines.append(f"## Current medications ({len(meds)})")
    if meds:
        for m in meds:
            dose = ""
            if m["dose_amount"] is not None:
                dose = f" {m['dose_amount']:g}{m['dose_unit'] or ''}"
            freq = f" ×{m['times_per_day']:g}/day" if m["times_per_day"] else ""
            tag = "" if m["product_type"] == "prescription" else f" ({m['product_type']})"
            lines.append(f"- {m['medication_name']}{dose}{freq}{tag}")
    else:
        lines.append("- None in the system.")
    lines.append("")

    # --- habits: current + former (past smoking still counts for risk) ---
    habits = conn.execute(
        text(
            """SELECT habit_type, status, frequency, start_date, end_date FROM habits
               WHERE user_id=:u AND deleted_at IS NULL AND status IN ('current', 'former')
               ORDER BY status = 'current' DESC, start_date DESC NULLS LAST"""
        ),
        {"u": user_id},
    ).mappings().all()
    counts["habits"] = len(habits)
    lines.append(f"## Habits ({len(habits)})")
    if habits:
        for h in habits:
            freq = f", {h['frequency']}" if h["frequency"] else ""
            since = f" since {h['start_date']}" if h["start_date"] else ""
            until = f" until {h['end_date']}" if h["end_date"] else ""
            lines.append(f"- {h['habit_type']} — {h['status']}{freq}{since}{until}")
    else:
        lines.append("- None recorded (≠ none: may simply not have been asked).")
    lines.append("")

    # --- last panel + what hasn't been checked in a long time/ever ---
    last_panel = conn.execute(
        text("SELECT max(panel_date) FROM panels WHERE user_id=:u"), {"u": user_id}
    ).scalar()
    lines.append("## Recency check of examinations")
    lines.append(f"- Last lab panel: {last_panel or 'none in the system'}")
    stale: list[str] = []
    for code, label in STALE_WATCH:
        last = conn.execute(
            text(
                """SELECT max(o.effective_at) FROM observations o
                   JOIN observation_types ot ON ot.id=o.type_id
                   WHERE o.user_id=:u AND ot.code=:c
                     AND o.review_status='approved' AND o.deleted_at IS NULL"""
            ),
            {"u": user_id, "c": code},
        ).scalar()
        if last is None:
            stale.append(f"{label}: **never** measured in the system")
        else:
            months = (datetime.now(last.tzinfo) - last).days / 30.44
            if months >= STALE_MONTHS:
                stale.append(f"{label}: last ~{months:.0f} mo. ago ({last:%Y-%m-%d})")
    if stale:
        lines.append("- ⚠️ Not checked in a long time/ever (absence of data is also a fact):")
        lines.extend(f"  - {s}" for s in stale)
    lines.append("")
    lines.append("_This is a guide; specific values and dates — always via a query to the "
                 "database. Not medical care, does not replace a doctor._")

    text_out = "\n".join(lines)
    valid, issues = _validate(conn, user_id, text_out, counts)
    return SummaryResult(text=text_out, counts=counts, valid=valid, issues=issues)


def _validate(conn, user_id: str, rendered: str, counts: dict[str, int]) -> tuple[bool, list[str]]:
    """Mechanical post-validation: numbers in the text == COUNT from the database (plan 4.1)."""
    issues: list[str] = []
    checks = {
        "allergies": "SELECT count(*) FROM allergies WHERE user_id=:u AND deleted_at IS NULL",
        "active_diagnoses": "SELECT count(*) FROM diagnoses WHERE user_id=:u "
                            "AND clinical_status='active' AND deleted_at IS NULL",
        "current_medications": "SELECT count(*) FROM medications WHERE user_id=:u "
                              "AND status='taking' AND deleted_at IS NULL",
        "habits": "SELECT count(*) FROM habits WHERE user_id=:u AND deleted_at IS NULL "
                  "AND status IN ('current', 'former')",
    }
    for key, sql in checks.items():
        db_n = conn.execute(text(sql), {"u": user_id}).scalar()
        if db_n != counts.get(key):
            issues.append(f"{key}: in text {counts.get(key)}, in database {db_n}")
    return (len(issues) == 0), issues
