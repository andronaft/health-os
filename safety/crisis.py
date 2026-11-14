"""Crisis protocol (plan 4.6) — deterministic, independent of the LLM/API.

A Telegram bot at 3am is de facto the first line. This can't be left to the LLM's mood.
A local keyword/regex layer (zero dependencies; uk/ru/en/es/de/pl) is the first net; an LLM
classifier (Phase 4) sits on top. The fixed response with the hotlines (CRISIS_COUNTRY, default UA: 7333/103/112) must be
delivered even with a dead API.

Suicidality is NOT an observation: it doesn't go into trends/correlations/reports (handled
separately).
"""
from __future__ import annotations

import re
import unicodedata

# High-recall patterns (a false positive is better than a miss), grouped by language.
# Written in the form _norm() produces: lower case, "е" for "ё", a plain ' for any apostrophe,
# single spaces. Spanish, German and Polish accept the unaccented spelling too ("mas", "zyc") —
# people type without diacritics. Stems like "suicid" serve every language that shares them.
_PATTERNS_BY_LANG = {
    "uk": [
        r"не хоч(?:у|еться).{0,20}жити", r"немає сенсу жити", r"не бачу сенсу",
        r"хочу (?:померти|вмерти)", r"краще б я (?:помер|вмер)", r"краще не прокидатись",
        r"покінчити з (?:собою|життям)", r"накласти на себе руки", r"звести рахунки з життям",
        r"(?:вбити|убити|вб'ю|уб'ю) себе", r"себе (?:вбити|убити|вб'ю|уб'ю)",
        r"порізати себе", r"завдати собі шкоди", r"зробити собі боляче",
        r"суїцид", r"самогубств",
    ],
    "ru": [
        r"не хоч(?:у|ется).{0,20}жить", r"нет смысла жить", r"не вижу смысла (?:жить|в жизни)",
        r"хочу умереть", r"лучше бы я (?:умер|сдох)", r"лучше не просыпаться",
        r"покончить с (?:собой|жизнью)", r"наложить на себя руки", r"свести счеты",
        r"(?:убить|убью) себя", r"себя (?:убить|убью)",
        r"порезать себя", r"причинить себе (?:вред|боль)",
        r"суицид", r"самоубий",
    ],
    "en": [
        r"kill(?:ing)? myself", r"want to die", r"wanna die", r"end(?:ing)? my (?:own )?life",
        r"tak(?:e|ing) my (?:own )?life", r"(?:don'?t|do not) want to (?:live|be alive)",
        r"wish i (?:was|were) dead", r"no reason to live", r"better off dead",
        r"(?:to|wanna|gonna) (?:hurt|harm|cut) myself", r"(?:hurting|harming|cutting) myself",
        r"suicid", r"self[- ]?harm",
    ],
    "es": [
        r"(?:quiero|quisiera|deseo|ganas de) morir", r"me (?:quiero|quisiera) morir",
        r"no quiero (?:seguir |continuar )?viv(?:ir|iendo)", r"sin ganas de vivir",
        r"quitarme la vida", r"(?:acabar|terminar) con mi vida",
        r"matarme", r"me (?:quiero|quisiera|voy a) matar",
        r"no (?:tiene sentido|vale la pena) (?:seguir )?viv(?:ir|iendo)",
        r"mi vida no tiene sentido", r"mejor muert[oa]",
        r"autolesi", r"hacerme da[nñ]o", r"cortarme las (?:venas|mu[nñ]ecas)",
    ],
    "de": [
        r"(?:will|m[oö]chte|moechte) (?:nur noch |einfach )?sterben",
        r"nicht (?:mehr|l[aä]nger|laenger) leben", r"mich um(?:zu)?bringen", r"bringe? mich um",
        r"mir das leben (?:zu )?nehmen", r"meinem leben ein ende",
        r"keinen sinn mehr zu leben", r"lebensm[uü]de",
        r"selbstmord", r"suizid", r"selbstverletz", r"mich (?:selbst )?(?:zu )?verletzen",
    ],
    "pl": [
        r"chc[eę] umrze[cć]", r"nie chc[eę] (?:ju[zż] |d[lł]u[zż]ej |wi[eę]cej )*[zż]y[cć]",
        r"nie ma sensu [zż]y[cć]", r"zabi(?:[cć]|j[eę]) si[eę]", r"si[eę] zabi[cć]",
        r"odebra[cć] sobie [zż]ycie", r"sko[nń]czy[cć] ze sob[aą]",
        r"zrobi[cć] sobie krzywd[eę]", r"samob[oó]j", r"samookalecz",
    ],
}
_PATTERNS = [p for patterns in _PATTERNS_BY_LANG.values() for p in patterns]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]
_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "`": "'", "‘": "'"})


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower().replace("ё", "е")
    return " ".join(text.translate(_APOSTROPHES).split())


def is_crisis(text: str | None) -> bool:
    if not text:
        return False
    n = _norm(text)
    return any(rx.search(n) for rx in _COMPILED)


# Per-country crisis lines (no network, no model). Every label is checked against the official
# source next to it — this text is shown to someone in crisis. Unset → UA (the original
# behaviour); a country we have no line for gets the local emergency number and an international
# directory, never another country's short number (7333 can't be dialled from abroad).
_HOTLINES = {
    # lifeline.org.ua — national suicide-prevention line, free from any operator, 24/7
    "UA": {
        "label": "Lifeline Ukraine — 7333 (free, 24/7, confidential)",
        "emergency": "103 or 112",
    },
    # sanidad.gob.es/linea024 — Ministerio de Sanidad, free, confidential, 24/7
    "ES": {
        "label": "Línea 024 de atención a la conducta suicida — 024 (free, 24/7)",
        "emergency": "112",
    },
    # 988lifeline.org
    "US": {
        "label": "988 Suicide & Crisis Lifeline — call or text 988 (24/7)",
        "emergency": "911",
    },
    # samaritans.org
    "GB": {
        "label": "Samaritans — 116 123 (free, 24/7)",
        "emergency": "999 or 112",
    },
    # telefonseelsorge.de — free, 24/7, not shown on the phone bill
    "DE": {
        "label": "TelefonSeelsorge — 0800 111 0 111, 0800 111 0 222 or 116 123 (free, 24/7)",
        "emergency": "112",
    },
    # gov.pl/web/zdrowie/gdzie-uzyskac-pomoc-psychologiczna-i-psychiatryczna
    "PL": {
        "label": "Poradnia Telefoniczna dla Osób Przeżywających Kryzys Emocjonalny — 116 123, "
                 "or Centrum Wsparcia — 800 70 2222 (free, 24/7)",
        "emergency": "112",
    },
}
_ALIASES = {"UK": "GB"}
_UNKNOWN_COUNTRY = {
    # findahelpline.com — international directory of crisis lines (ThroughLine)
    "label": "Find a crisis line in your country — findahelpline.com",
    "emergency": "your local emergency number (112 across the EU)",
}


def _country_hotlines(country: str | None = None) -> dict:
    from core.config import settings  # read through Settings: .env does not reach os.environ

    code = (country or settings.crisis_country or "UA").strip().upper()
    return _HOTLINES.get(_ALIASES.get(code, code), _UNKNOWN_COUNTRY)


def crisis_response(emergency_contact: str | None = None, country: str | None = None) -> str:
    """Fixed crisis response. No analytics, no "let's look at your trends"."""
    hot = _country_hotlines(country)
    lines = [
        "It sounds like things are very hard for you right now. You're not alone — there are "
        "people ready to listen right now.",
        "",
        f"📞 **{hot['label']}**",
        f"🚨 **Emergency services — {hot['emergency']}**",
    ]
    if emergency_contact:
        lines.append(f"👤 Your trusted contact: {emergency_contact}")
    lines += [
        "",
        f"If there is an immediate threat to life — please call {hot['emergency']} right now.",
        "I'm not a medical professional and I don't replace crisis care, but I'm here and I "
        "won't leave you.",
    ]
    return "\n".join(lines)
