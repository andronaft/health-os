"""Screening calendar (plan 5, level 1 — deterministic, zero LLM).

Profile-dependent recommendations with an age gate and "you don't need this YET" logic
(protection against overtesting: colonoscopy/PSA without family history — no). The status source
is the date of the last time it was done (from the DB). The calendar deliberately can say
"too early" and "long overdue".

Pure function build_calendar(sex, age, last_done, flags) — tested without a DB. for_user() gathers
its inputs from the database, for the MCP tool and the browser UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text

# recommendation statuses
DUE = "due"                 # time to do it (not done yet or no data, but the age fits)
OVERDUE = "overdue"         # overdue relative to the interval
UP_TO_DATE = "up_to_date"   # done recently, within the interval
NOT_YET = "not_yet"         # not needed yet by age/profile ("you don't need this YET")


@dataclass
class Recommendation:
    code: str
    label: str
    status: str
    detail: str
    last_done: date | None = None


# Each rule: applies(sex, age, flags) → bool; interval_years (None = one-off/special);
# not_yet(sex, age, flags) → bool (age not reached yet); rationale.
def _rules():
    return [
        {"code": "bp", "label": "Blood pressure",
         "applies": lambda s, a, f: a >= 18, "interval": 1,
         "not_yet": lambda s, a, f: False,
         "rationale": "yearly; more often with risk factors"},
        {"code": "lipids", "label": "Lipid panel",
         "applies": lambda s, a, f: a >= 20, "interval": 5,
         "not_yet": lambda s, a, f: False,
         "rationale": "about every 5 years if normal; more often with familial hyperlipidemia"},
        {"code": "glucose_hba1c", "label": "Glucose / HbA1c",
         "applies": lambda s, a, f: a >= 18, "interval": 3,
         "not_yet": lambda s, a, f: False,
         "rationale": "by risk factors (overweight, family history of diabetes)"},
        {"code": "hiv", "label": "HIV test",
         "applies": lambda s, a, f: a >= 18, "interval": None,
         "not_yet": lambda s, a, f: False,
         "rationale": "at least once in a lifetime, then by risk (Ukraine — high burden)"},
        {"code": "hcv", "label": "anti-HCV (hepatitis C)",
         "applies": lambda s, a, f: a >= 18, "interval": None,
         "not_yet": lambda s, a, f: False,
         "rationale": "at least once (the most underused screen in the young)"},
        {"code": "hbsag_hepb", "label": "HBsAg + hepatitis B vaccination",
         "applies": lambda s, a, f: a >= 18, "interval": None,
         "not_yet": lambda s, a, f: False,
         "rationale": "check the status and get vaccinated if not immunized"},
        {"code": "tdap", "label": "Tdap (tetanus-diphtheria)",
         "applies": lambda s, a, f: a >= 18, "interval": 10,
         "not_yet": lambda s, a, f: False,
         "rationale": "every 10 years; critical given low adult coverage and injuries"},
        {"code": "dental", "label": "Dental check-up",
         "applies": lambda s, a, f: True, "interval": 1,
         "not_yet": lambda s, a, f: False,
         "rationale": "every 6–12 months"},
        {"code": "checkup", "label": "Primary-care check-up",
         "applies": lambda s, a, f: a >= 18, "interval": 1,
         "not_yet": lambda s, a, f: False,
         "rationale": "the annual first-class event of the screening calendar"},
        {"code": "testicular", "label": "Testicular self-exam",
         "applies": lambda s, a, f: s == "male" and 15 <= a <= 40, "interval": 1,
         "not_yet": lambda s, a, f: False,
         "rationale": "peak of germ-cell tumors is exactly this age; regular self-exam"},
        {"code": "skin", "label": "Skin self-exam",
         "applies": lambda s, a, f: True, "interval": 1,
         "not_yet": lambda s, a, f: False,
         "rationale": "a reminder; watch for changes in moles"},
        {"code": "mental", "label": "PHQ-9 / GAD-7 (mood/anxiety screen)",
         "applies": lambda s, a, f: a >= 16, "interval": 1,
         "not_yet": lambda s, a, f: False,
         "rationale": "periodically"},
        {"code": "audiometry", "label": "Audiometry",
         "applies": lambda s, a, f: f.get("noise_or_blast_exposure", False),
         "interval": 2, "not_yet": lambda s, a, f: False,
         "rationale": "with a noise/blast history (concussions/acoustic barotrauma)"},
        # "You don't need this YET" — protection against overtesting
        {"code": "colonoscopy", "label": "Colonoscopy",
         "applies": lambda s, a, f: a >= 45 or f.get("family_colorectal_cancer", False),
         "interval": 10,
         "not_yet": lambda s, a, f: a < 45 and not f.get("family_colorectal_cancer", False),
         "rationale": "from age 45 (or earlier with a family history of colorectal cancer)"},
        {"code": "psa", "label": "PSA (prostate)",
         "applies": lambda s, a, f: s == "male" and (a >= 50 or f.get("family_prostate_cancer", False)),
         "interval": 2,
         "not_yet": lambda s, a, f: s == "male" and a < 50 and not f.get("family_prostate_cancer", False),
         "rationale": "discussion from age 50 (earlier — only with a family history)"},
    ]


def build_calendar(
    sex: str, age: int, last_done: dict[str, date] | None = None,
    flags: dict | None = None, today: date | None = None,
) -> list[Recommendation]:
    last_done = last_done or {}
    flags = flags or {}
    today = today or date.today()
    out: list[Recommendation] = []

    for r in _rules():
        # check "not needed yet" even if applies=False (to explicitly say "too early")
        if r["not_yet"](sex, age, flags):
            out.append(Recommendation(r["code"], r["label"], NOT_YET,
                                      f"Not needed yet. {r['rationale']}"))
            continue
        if not r["applies"](sex, age, flags):
            continue

        done = last_done.get(r["code"])
        if done is None:
            out.append(Recommendation(r["code"], r["label"], DUE,
                                      f"No record of it being done. {r['rationale']}", None))
            continue
        if r["interval"] is None:
            out.append(Recommendation(r["code"], r["label"], UP_TO_DATE,
                                      f"Done {done:%Y-%m-%d} (one-off screening). {r['rationale']}",
                                      done))
            continue
        years = (today - done).days / 365.25
        status = OVERDUE if years >= r["interval"] else UP_TO_DATE
        detail = (f"Last {done:%Y-%m-%d} (~{years:.1f} yr ago, interval {r['interval']} yr). "
                  f"{r['rationale']}")
        out.append(Recommendation(r["code"], r["label"], status, detail, done))

    return out


def for_user(conn, uid: str | None) -> dict:
    """The calendar for this user's profile, or {"error": ...} without one. Reads base tables
    (the profile, family history, exposures), which the read-only login can't."""
    prof = conn.execute(
        text("SELECT date_of_birth, sex FROM user_profile WHERE user_id=:u"), {"u": uid}
    ).mappings().first()
    if not prof or not prof["date_of_birth"] or not prof["sex"]:
        return {"error": "profile not filled in (date of birth and sex required)"}
    dob, sex = prof["date_of_birth"], prof["sex"]
    age = date.today().year - dob.year - ((date.today().month, date.today().day) < (dob.month, dob.day))

    def _last(codes: list[str]):
        return conn.execute(
            text("""SELECT max(o.effective_at) FROM observations o
                    JOIN observation_types ot ON ot.id=o.type_id
                    WHERE o.user_id=:u AND ot.code = ANY(:c)
                      AND o.review_status='approved' AND o.deleted_at IS NULL"""),
            {"u": uid, "c": codes},
        ).scalar()

    last_done = {}
    for key, codes in {"bp": ["systolic_bp"], "lipids": ["cholesterol_total"],
                       "glucose_hba1c": ["glucose", "hba1c"]}.items():
        d = _last(codes)
        if d is not None:
            last_done[key] = d.date() if hasattr(d, "date") else d
    tdap = conn.execute(
        text("""SELECT max(vaccination_date) FROM vaccinations WHERE user_id=:u
                AND deleted_at IS NULL AND (disease ILIKE '%правець%' OR disease ILIKE '%дифтер%'
                OR disease ILIKE '%tetanus%' OR disease ILIKE '%diphther%')"""),
        {"u": uid},
    ).scalar()
    if tdap:
        last_done["tdap"] = tdap

    def _fam(patterns: list[str]) -> bool:
        return bool(conn.execute(
            text("""SELECT 1 FROM family_history WHERE user_id=:u AND deleted_at IS NULL
                    AND (""" + " OR ".join(f"condition ILIKE :p{i}" for i in range(len(patterns))) + ") LIMIT 1"),
            {"u": uid, **{f"p{i}": p for i, p in enumerate(patterns)}},
        ).first())

    flags = {
        "family_colorectal_cancer": _fam(["%колорект%", "%товстої кишки%", "%colorectal%"]),
        "family_prostate_cancer": _fam(["%простат%", "%prostate%"]),
        "noise_or_blast_exposure": bool(conn.execute(
            text("""SELECT 1 FROM exposures WHERE user_id=:u AND deleted_at IS NULL
                    AND exposure_type IN ('military','blast_injury','occupational') LIMIT 1"""),
            {"u": uid},
        ).first()),
    }
    return {"age": age, "sex": sex,
            "recommendations": [vars(r) for r in build_calendar(sex, age, last_done, flags)]}
