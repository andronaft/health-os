"""Critical-values rule-engine (plan 4.5).

The system's most dangerous scenario is built-in false reassurance: potassium 6.8 stuck
in pending at 23:00, in the morning "how are you?" → "no abnormalities". So critical values
are assessed by deterministic code at the ingestion stage, BEFORE review, and force-shown.

The core is the pure function `evaluate()` over a list of thresholds (easy to test without a DB).
`load_thresholds()` pulls thresholds from the critical_thresholds table.

High-recall by design: the bound is inclusive (>= / <=), a false escalation is better than a
miss. Unit gate: a threshold fires only when the value's unit = the threshold's canonical unit
(otherwise "glucose 95 mg/dL" would be falsely compared to a threshold in mmol/L).
"""
from __future__ import annotations

from dataclasses import dataclass

LANGUAGES = ("en", "uk", "es")

# The Ukrainian text lives in critical_thresholds.message_uk (seed/data.py); the other languages
# are here. A type without its own text gets the generic message in that language.
MESSAGES: dict[str, dict[str, str]] = {
    "potassium": {
        "en": "Critical potassium — see a doctor today, even if the value may be a recognition "
              "error.",
        "es": "Potasio crítico — consulte hoy a un médico, aunque el valor pueda ser un error de "
              "reconocimiento.",
    },
    "glucose": {
        "en": "Critical glucose — get medical help now.",
        "es": "Glucosa crítica — busque ayuda médica ahora.",
    },
    "hemoglobin": {
        "en": "Critically low haemoglobin — see a doctor today.",
        "es": "Hemoglobina críticamente baja — consulte hoy a un médico.",
    },
    "platelets": {
        "en": "Critically low platelets — bleeding risk, see a doctor.",
        "es": "Plaquetas críticamente bajas — riesgo de sangrado, consulte a un médico.",
    },
    "sodium": {
        "en": "Critical sodium — needs a medical assessment.",
        "es": "Sodio crítico — requiere valoración médica.",
    },
    "calcium_total": {
        "en": "Critical calcium — needs a medical assessment.",
        "es": "Calcio crítico — requiere valoración médica.",
    },
}
GENERIC = {
    "en": "Critical value — see a doctor today.",
    "uk": "Критичне значення — зверніться до лікаря сьогодні.",
    "es": "Valor crítico — consulte hoy a un médico.",
}


def message_for(type_code: str, message_uk: str | None, lang: str | None = None) -> str:
    """The critical-value message in `lang` (default: HEALTH_OS_LANG, English if unset)."""
    if lang is None:
        from core.config import settings
        lang = settings.health_os_lang
    lang = lang if lang in LANGUAGES else "en"
    if lang == "uk":
        return message_uk or GENERIC["uk"]
    return MESSAGES.get(type_code, {}).get(lang) or GENERIC[lang]


@dataclass(frozen=True)
class Threshold:
    type_code: str
    unit: str                       # canonical unit the threshold is defined in
    critical_low: float | None
    critical_high: float | None
    message_uk: str
    sex: str | None = None          # None = any sex


@dataclass(frozen=True)
class CriticalHit:
    type_code: str
    value: float
    unit: str
    bound: str                      # 'low' | 'high'
    threshold: float
    message_uk: str
    message: str = ""               # in the configured language (HEALTH_OS_LANG)


def evaluate(
    type_code: str,
    value: float | None,
    unit: str | None,
    thresholds: list[Threshold],
    sex: str | None = None,
    lang: str | None = None,
) -> CriticalHit | None:
    """Returns a CriticalHit if the value is critical, otherwise None.

    value must be in the canonical unit (value_canonical). unit — the same canonical one.
    """
    if value is None or unit is None:
        return None
    for t in thresholds:
        if t.type_code != type_code:
            continue
        if t.unit != unit:            # unit gate
            continue
        if t.sex is not None and sex is not None and t.sex != sex:
            continue
        if t.critical_low is not None and value <= t.critical_low:
            return CriticalHit(type_code, value, unit, "low", t.critical_low, t.message_uk,
                               message_for(type_code, t.message_uk, lang))
        if t.critical_high is not None and value >= t.critical_high:
            return CriticalHit(type_code, value, unit, "high", t.critical_high, t.message_uk,
                               message_for(type_code, t.message_uk, lang))
    return None


def load_thresholds(conn) -> list[Threshold]:
    """Loads thresholds from critical_thresholds (SQLAlchemy connection)."""
    from sqlalchemy import text

    rows = conn.execute(
        text(
            """
            SELECT ot.code, ct.unit, ct.critical_low, ct.critical_high, ct.message_uk, ct.sex
            FROM critical_thresholds ct
            JOIN observation_types ot ON ot.id = ct.type_id
            """
        )
    ).all()
    return [
        Threshold(
            type_code=code,
            unit=unit,
            critical_low=float(low) if low is not None else None,
            critical_high=float(high) if high is not None else None,
            message_uk=msg,
            sex=sex,
        )
        for code, unit, low, high, msg, sex in rows
    ]
