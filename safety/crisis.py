"""Crisis protocol (plan 4.6) — deterministic, independent of the LLM/API.

A Telegram bot at 3am is de facto the first line. This can't be left to the LLM's mood.
A local keyword/regex layer (zero dependencies) is the first net; an LLM classifier (Phase 4)
sits on top. The fixed response with 7333/103/112 must be delivered even with a dead API.

Suicidality is NOT an observation: it doesn't go into trends/correlations/reports (handled
separately).
"""
from __future__ import annotations

import re
import unicodedata

# High-recall patterns (a false positive is better than a miss). uk/ru/en.
_PATTERNS = [
    r"не хоч(?:у|еться).{0,20}жити", r"немає сенсу жити", r"не бачу сенсу",
    r"хочу померти", r"краще б я помер", r"краще не прокидатись",
    r"покінчити з (собою|життям)", r"накласти на себе руки", r"звести рахунки з життям",
    r"порізати себе", r"завдати собі шкоди", r"зробити собі боляче",
    r"суїцид", r"суицид", r"самогубств",
    r"не хочу больше жить", r"хочу умереть", r"покончить с собой", r"свести счёты",
    r"kill myself", r"want to die", r"end my life", r"suicid", r"self[- ]?harm",
    r"no reason to live", r"better off dead",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("ё", "е")).lower()


def is_crisis(text: str | None) -> bool:
    if not text:
        return False
    n = _norm(text)
    return any(rx.search(n) for rx in _COMPILED)


# Per-country crisis lines (no network, no model). 112 is the European emergency
# number and is kept as a fallback for every EU/EEA country listed here.
# Sources: Lifeline UA 7333 (lifeline.org.ua); emergency 103 (UA) / 112 (EU);
# 988 Suicide & Crisis Lifeline (988lifeline.org); 116 123 Samaritans (UK/IE);
# 0800 111 0 111 Telefonseelsorge (DE); 116 123 (PL — NFZ whisper line).
_HOTLINES = {
    "UA": {
        "label": "Lifeline Ukraine — 7333 (free, 24/7, confidential)",
        "emergency": "103 or 112",
    },
    "ES": {
        "label": "Línea 024 de atención a la conducta suicida — 024 (24/7)",
        "emergency": "112",
    },
    "US": {
        "label": "988 Suicide & Crisis Lifeline — call or text 988 (24/7)",
        "emergency": "911",
    },
    "GB": {
        "label": "Samaritans — 116 123 (free, 24/7)",
        "emergency": "999",
    },
    "UK": {
        "label": "Samaritans — 116 123 (free, 24/7)",
        "emergency": "999",
    },
    "DE": {
        "label": "Telefonseelsorge — 0800 111 0 111 or 0800 111 0 222 (24/7)",
        "emergency": "112",
    },
    "PL": {
        "label": "NFZ whisper line — 116 123 (24/7)",
        "emergency": "112",
    },
}


def _country_hotlines(country: str | None = None) -> dict:
    import os
    code = (country or os.getenv("CRISIS_COUNTRY", "UA") or "UA").strip().upper()
    return _HOTLINES.get(code, _HOTLINES["UA"])


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
