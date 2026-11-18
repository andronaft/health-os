"""Classifier of critical NARRATIVE findings (plan 4.5, v3).

The critical-values rule-engine is numeric, but ultrasound/MRI/CT conclusions and histology
are text. A phrase like "mass, suspicion of malignancy / Bi-RADS 4–5 / 5 cm aneurysm /
urgent follow-up recommended" has no numeric trigger and may settle into pending or be
rephrased by the LLM in the summary. This is the same class of false reassurance as
potassium 6.8.

A deterministic keyword/pattern classifier (zero dependencies on the LLM). High-recall:
a false positive a human dismisses is better than a missed malignancy.

Negation is deliberately NOT handled for findings: "sin signos de trombosis" / "без ознак
малігнізації" still flag. Phrases like "no se puede descartar malignidad" (can't be ruled out)
look negated and are exactly the ones that must fire, so a negation filter would cost recall
where it matters most. Exceptions:
  - a few fixed collocations that only look alarming ("índice de masa corporal");
  - the bare word "suspicious" / "sospechoso" / "підозрілий". Routine reports say "no suspicious
    findings" in nearly every normal mammogram, so without negation the classifier would fire on
    every one of them and real alerts would drown. Only the plainest forms are recognised (see
    `_suspicion_negated`): a negation word ("no", "without", "sin", "без", "не", ...) followed by
    at most four whitelisted filler words ("evidence of", "hallazgos", "ознак", "masses or")
    before the word, or — in Ukrainian/Russian — "підозрілих утворень не виявлено". Anything
    else (a comma, "but", "cannot exclude", "no change in", an unknown word) keeps the flag.
    The negation never suppresses another category: "no findings suspicious for malignancy"
    still fires on "malign".

Radiology scales (BI-RADS, TI-RADS, PI-RADS, Lung-RADS, Bosniak) are matched with the words
reports put between the scale and the number ("category", "score", "v2.1", "categoría",
"категорія"), Roman numerals and sub-letters (4A/4B/4C/4X), and ranges ending in a suspicious
grade ("BI-RADS 3–4"). Benign grades (BI-RADS 1–3, TR1–TR3, PI-RADS 1–3, Lung-RADS 1–3,
Bosniak I/II/IIF) do not fire.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# What reports put between a scale's name and its grade: "BI-RADS: 4", "BI-RADS® category 4",
# "PI-RADS v2.1 score 5", "Lung-RADS v2022 category 4B", "BI-RADS categoría IV", "Bosniak type III".
_SEP = (r"(?:[\s:=\-–—®()\[\]]|category|categoria|categ\.|cat\.|категорія|категорії|категория"
        r"|assessment|score|class|clase|grade|type|tipo|тип|v\d+(?:\.\d+)?)*")
# A range ending in a suspicious grade ("BI-RADS 3-4", "BI-RADS 3 o 4") — the higher grade counts.
# No "a"/"to"/"до": "BI-RADS 3 a 6 meses" is a follow-up interval, not a grade range.
_RANGE = r"(?:[0-3][a-c]?\s*(?:-|–|/|or|o|або|чи|или)\s*)?"
# ...and a number followed by a time unit is never a grade ("BI-RADS 3 - 6 months").
_NOT_INTERVAL = r"(?!\s*(?:months?|meses?|weeks?|semanas?|міс|мес|тижн|недел))"
_ROMAN_4_6 = r"(?:vi|iv|v)(?![a-z\d])"
_ROMAN_4_5 = r"(?:iv|v)(?![a-z\d])"

# (category, regex). Patterns run over normalized text: lowercase, Latin accents folded
# (á→a, ñ→n — Cyrillic untouched), uk+ru+en+es+lat.
_PATTERNS: list[tuple[str, str]] = [
    ("malignancy", r"малігн|злоякісн|озлоякіснен|малигн|злокачествен|malign|carcinom|карцином|сарком|sarcom|метастаз|metastas|неоплаз|neoplas"
                   r"|лімфом|лимфом|lymphom|linfom|лейкоз|лейкемі|лейкеми|leuka?emi|leucemi|меланом|melanom"),
    ("suspicion", r"підозра на|подозрение на|підозріл|подозрительн|susp(?:ected|icion|icious)|susp\."
                  r"|sospech"),
    ("birads", r"\bbi[-\s]?rads" + _SEP + _RANGE + r"(?:[4-6][a-c]?(?!\d)|" + _ROMAN_4_6 + ")"
               + _NOT_INTERVAL),
    ("tirads", r"(?:\bti[-\s]?rads" + _SEP + _RANGE + r"(?:tr)?[45][a-c]?(?!\d)|\btr\s?[45](?!\d))"
               + _NOT_INTERVAL),
    ("pirads", r"\bpi[-\s]?rads" + _SEP + _RANGE + r"(?:[45](?!\d)|" + _ROMAN_4_5 + ")"
               + _NOT_INTERVAL),
    ("lungrads", r"\blung[-\s]?rads" + _SEP + _RANGE + r"4[abx]?(?!\d)" + _NOT_INTERVAL),
    ("bosniak", r"\bbosniak" + _SEP + r"(?:[34](?!\d)|(?:iii|iv)(?![a-z\d]))"),
    ("aneurysm", r"аневризм|aneurysm|aneurism"),
    ("urgent", r"рекомендовано терміново|терміново дообстеж|срочно|ургентн|urgent|urgenci|cito\b|cito!|негайн(?:о|е)\s+звернен"),
    ("acute_vascular", r"тромбоембол|тромбоз|thrombos|trombos|\btrombos?\b|embol|інсульт|stroke|\bictus\b"
                       r"|accidente cerebrovascular|інфаркт|infarct|infart"
                       r"|розшаруванн\w* аорт|расслоени\w* аорт|aortic dissection|dissection of the aorta"
                       r"|diseccion (?:de (?:la )?)?aort"),
    ("mass", r"новоутворен|об'?ємне утворення|объемное образование|пухлин|tumor|tumou?r|вогнищев[еі] утворенн"
             r"|neoformaci|ocupante de espacio"
             r"|(?<!indice de )\bmasas?\b(?!\s+(?:corporal|oseas?|muscular|magra|grasa|ventricular))"),
]

# Latin letters with diacritics → base letter. Not unicodedata NFD stripping: that would also turn
# Ukrainian й/ї into и/і and break the Cyrillic patterns.
_FOLD = str.maketrans("áàâäãéèêëíìîïóòôöõúùûüñç", "aaaaaeeeeiiiiooooouuuunc")

_COMPILED = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in _PATTERNS]

# --- negation of the bare "suspicious" word (and only that; see the module docstring) ---------
# A negation word, then up to four filler words from a closed list, then the suspicion word.
# The list is closed on purpose: an unknown word in between ("no change in", "no se puede
# descartar", "cannot exclude") means we don't understand the sentence, so it keeps the flag.
_NEG_CUE = (r"no|not|without|nor|negative\s+for|free\s+of|absence\s+of|absent"
            r"|sin|ningun|ninguna|ningunos|ningunas|ausencia\s+de|libre\s+de|negativo\s+para"
            r"|без|немає|відсутні|відсутність|нема|нет|отсутствуют|отсутствие|не")
_NEG_FILLER = (
    # en
    r"any|other|new|further|additional|definite|discrete|focal|evidence|of|sign|signs|finding"
    r"|findings|area|areas|lesion|lesions|mass|masses|nodule|nodules|lymph|node|nodes"
    r"|calcification|calcifications|microcalcifications|features|feature|the|or|seen|identified"
    r"|axillary|sonographically|mammographically|clinically|is|are|appear|appears"
    # es (accents folded)
    r"|otros|otras|otro|otra|nuevos|nuevas|hallazgo|hallazgos|lesion|lesiones|imagen|imagenes"
    r"|nodulo|nodulos|adenopatias|ganglios|calcificaciones|microcalcificaciones|signos|datos"
    r"|areas|zonas|focos|de|ni|evidencia|masas|se|observan|observa|aprecian|aprecia|identifican"
    r"|identifica|visualizan|visualiza|objetivan|objetiva|evidencian|hay|es|son|parece|parecen"
    # uk
    r"|ознак|ознаки|даних|за|вогнищ|утворень|змін|ділянок|нових|інших|лімфовузлів|виявлено"
    r"|визначається|визначаються|кальцинатів|мікрокальцинатів|або|чи"
    # ru
    r"|признаков|данных|очагов|образований|изменений|участков|новых|других|лимфоузлов|выявлено"
    r"|определяется|определяются|кальцинатов|микрокальцинатов|или"
)
_PRE_NEG = re.compile(rf"(?:^|[^\w])(?:(?:{_NEG_CUE})(?:\s+(?:{_NEG_FILLER})){{0,4}}\s+|non-?)$")
# Ukrainian/Russian put the negation after the noun: "підозрілих утворень не виявлено".
_POST_NEG = re.compile(rf"^\w*(?:\s+(?:{_NEG_FILLER})){{0,3}}\s+"
                       r"(?:не\s+(?:виявлено|визначається|визначаються|выявлено|определяется"
                       r"|определяются)|немає|відсутні|нет|отсутствуют)(?!\w)")
# The clause the negation may reach across: a sentence, not past a comma or a "but".
_CLAUSE_BREAK = re.compile(r"[.;:!?,\n]|\b(?:but|however|pero|aunque|sin embargo|але|однак|проте|но|однако)\b")


def _suspicion_negated(norm: str, start: int, end: int) -> bool:
    """True when the "suspicious" word at norm[start:end] is plainly negated in its own clause."""
    before = norm[max(0, start - 120):start]
    breaks = list(_CLAUSE_BREAK.finditer(before))
    if breaks:
        before = before[breaks[-1].end():]
    if _PRE_NEG.search(before):
        return True
    after = norm[start:end + 120]
    m = _CLAUSE_BREAK.search(after)
    if m:
        after = after[:m.start()]
    return bool(_POST_NEG.search(after))


@dataclass(frozen=True)
class NarrativeFlag:
    category: str
    matched_text: str


def _normalize(text: str) -> str:
    # ё→е, keep ї/і; collapse extra spaces; lowercase
    text = text.replace("ё", "е").replace("Ё", "Е")
    text = unicodedata.normalize("NFC", text)
    return text.lower().translate(_FOLD)


def scan(text: str | None) -> list[NarrativeFlag]:
    """Returns a list of found critical narrative markers (may be empty)."""
    if not text:
        return []
    norm = _normalize(text)
    hits: list[NarrativeFlag] = []
    for name, rx in _COMPILED:
        for m in rx.finditer(norm):
            if name == "suspicion" and _suspicion_negated(norm, m.start(), m.end()):
                continue  # "no suspicious findings" — look for a later, un-negated mention
            hits.append(NarrativeFlag(category=name, matched_text=m.group(0)))
            break
    return hits


def is_critical(text: str | None) -> bool:
    return bool(scan(text))


def send_alert(categories, *, source_label: str, alerter) -> None:
    """One alert naming every category found in `source_label` (no-op without categories)."""
    cats = ", ".join(sorted(set(categories)))
    if cats:
        alerter("Health OS — critical narrative finding",
                f'In "{source_label}" markers [{cats}] were detected — needs a doctor\'s attention today.')


def check_and_alert(text: str | None, *, source_label: str = "document", alerter=None) -> list[NarrativeFlag]:
    """Scans the narrative and, if there are critical markers, sends an alert (the same forced
    display as critical numbers). `alerter(title, message)` — in production
    safety.alerts.send_critical_alert."""
    hits = scan(text)
    if hits and alerter is not None:
        send_alert((h.category for h in hits), source_label=source_label, alerter=alerter)
    return hits
