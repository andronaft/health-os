"""The emergency packet (#74): what a paramedic can read without unlocking the phone.

Two layouts of the same facts, for the user to copy by hand — health-os never writes to the phone
or to a tag:
- lock_screen: one block per Medical ID field (iOS Medical ID, Android "Emergency information"),
  each ready to paste;
- nfc: one text block for an NFC tag, with its size against the NTAG213/215/216 user memory.

Approved data only, and no model: allergies (v_allergies — unverified ones too, marked, the same
fail-safe as everywhere else), current medications (v_medications_current — a stopped one is not
there), active diagnoses (v_diagnoses, clinical status active / recurrence / relapse; a refuted one
is no diagnosis, a resolved, inactive or in-remission one is not current; a suspected, provisional
or differential one is listed and says so), blood type and emergency contact from the profile.
Observations never appear: nothing pending can.

Nothing is ever dropped to fit. Every list is read whole (no MAX_ROWS cut), and an NFC text over a
tag's budget is reported with its size: which medical item matters less is not for code to decide.

The user's own entries (allergen, reaction, diagnosis and medication names, the contact) are as
entered; the words we own are in the packet's language (en / uk / es). Dates are ISO (2026-11-26):
the same in every language, never 11/26 vs 26/11.
"""
from __future__ import annotations

import math
from datetime import tzinfo

from sqlalchemy import text

from core import queries as q

LANGUAGES = ("en", "uk", "es")
LAYOUTS = ("lock_screen", "nfc")
FIELDS = ("conditions", "medications", "allergies", "blood_type", "emergency_contact", "notes")
ACTIVE = ("active", "recurrence", "relapse")

# User memory of NXP's NFC Forum Type 2 tags, in bytes: NTAG213/215/216 data sheet (NXP, Rev. 3.2,
# 2 June 2015), §8.5 "Memory organization" — 144, 504 and 888 bytes. The NDEF message must fit in
# it together with its TLV wrapping (ndef_size below).
NFC_TAGS = {"NTAG213": 144, "NTAG215": 504, "NTAG216": 888}
DEFAULT_TAG = "NTAG215"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "field.conditions": "Medical conditions",
        "field.medications": "Medications",
        "field.allergies": "Allergies & reactions",
        "field.blood_type": "Blood type",
        "field.emergency_contact": "Emergency contact",
        "field.notes": "Medical notes",
        "nfc.title": "MEDICAL INFO",
        "none": "None recorded.",
        "allergies.none": "None recorded. That does not mean there are none.",
        "not_recorded": "Not recorded.",
        "unverified": "not verified",
        "severity.mild": "mild",
        "severity.moderate": "moderate",
        "severity.severe": "severe",
        "verification.provisional": "provisional",
        "verification.suspected": "suspected",
        "verification.differential": "differential",
        "clinical.recurrence": "recurrence",
        "clinical.relapse": "relapse",
        "per_day": "{n}×/day",
        "pattern.as_needed": "as needed",
        "pattern.seasonal": "seasonal",
        "as_of": "As of {date}.",
        "notice": "From a personal health record kept by the patient, not a clinical system.",
        "privacy": ("Anyone holding the phone or the tag can read this without unlocking anything. "
                    "Put there only what you choose: no address, no ID numbers. A passive NFC tag "
                    "keeps no record of who read it. health-os never writes to the phone or the "
                    "tag: you copy it there yourself."),
        "nfc.fits": "{size} bytes on the tag: fits {tag} ({capacity} bytes).",
        "nfc.over": ("{size} bytes on the tag: does not fit {tag} ({capacity} bytes) by {over} "
                     "bytes. Nothing was cut: shorten it yourself or use a larger tag."),
        "empty": "No profile on record yet: there is nothing to put on the lock screen.",
    },
    "uk": {
        "field.conditions": "Захворювання",
        "field.medications": "Ліки",
        "field.allergies": "Алергії та реакції",
        "field.blood_type": "Група крові",
        "field.emergency_contact": "Контакт на екстрений випадок",
        "field.notes": "Медичні нотатки",
        "nfc.title": "МЕДИЧНА ІНФОРМАЦІЯ",
        "none": "Нічого не записано.",
        "allergies.none": "Нічого не записано. Це не означає, що алергій немає.",
        "not_recorded": "Не записано.",
        "unverified": "не підтверджено",
        "severity.mild": "легка",
        "severity.moderate": "помірна",
        "severity.severe": "тяжка",
        "verification.provisional": "попередній",
        "verification.suspected": "підозра",
        "verification.differential": "диференційний",
        "clinical.recurrence": "рецидив",
        "clinical.relapse": "загострення",
        "per_day": "{n}×/день",
        "pattern.as_needed": "за потреби",
        "pattern.seasonal": "сезонно",
        "as_of": "Станом на {date}.",
        "notice": "З особистого запису про здоров'я, який веде сам пацієнт, а не з медичної системи.",
        "privacy": ("Це може прочитати будь-хто, у кого в руках телефон або мітка, нічого не "
                    "розблоковуючи. Пишіть туди лише те, що вирішите самі: без адреси, без номерів "
                    "документів. Пасивна NFC-мітка не веде журналу, хто її читав. health-os ніколи "
                    "не пише в телефон чи мітку: ви копіюєте текст туди самі."),
        # "Б" (байт): no plural form to pick for the number
        "nfc.fits": "На мітці {size} Б: вміщується в {tag} ({capacity} Б).",
        "nfc.over": ("На мітці {size} Б: не вміщується в {tag} ({capacity} Б), зайві {over} Б. "
                     "Нічого не обрізано: скоротіть текст самі або візьміть більшу мітку."),
        "empty": "Профілю ще немає: на екран блокування нічого покласти.",
    },
    "es": {
        "field.conditions": "Afecciones médicas",
        "field.medications": "Medicamentos",
        "field.allergies": "Alergias y reacciones",
        "field.blood_type": "Grupo sanguíneo",
        "field.emergency_contact": "Contacto de emergencia",
        "field.notes": "Notas médicas",
        "nfc.title": "INFORMACIÓN MÉDICA",
        "none": "Nada registrado.",
        "allergies.none": "Nada registrado. Eso no significa que no haya ninguna.",
        "not_recorded": "No registrado.",
        "unverified": "no verificada",
        "severity.mild": "leve",
        "severity.moderate": "moderada",
        "severity.severe": "grave",
        "verification.provisional": "provisional",
        "verification.suspected": "sospecha",
        "verification.differential": "diferencial",
        "clinical.recurrence": "recurrencia",
        "clinical.relapse": "recaída",
        "per_day": "{n}×/día",
        "pattern.as_needed": "si es necesario",
        "pattern.seasonal": "estacional",
        "as_of": "A fecha de {date}.",
        "notice": ("De un registro personal de salud que lleva el propio paciente, no de un "
                   "sistema clínico."),
        "privacy": ("Cualquiera que tenga el teléfono o la etiqueta puede leer esto sin desbloquear "
                    "nada. Ponga ahí solo lo que usted elija: sin dirección ni números de "
                    "documentos. Una etiqueta NFC pasiva no registra quién la leyó. health-os nunca "
                    "escribe en el teléfono ni en la etiqueta: lo copia usted."),
        "nfc.fits": "{size} bytes en la etiqueta: cabe en {tag} ({capacity} bytes).",
        "nfc.over": ("{size} bytes en la etiqueta: no cabe en {tag} ({capacity} bytes), sobran "
                     "{over} bytes. No se ha recortado nada: acórtelo usted o use una etiqueta "
                     "más grande."),
        "empty": "Aún no hay perfil: no hay nada que poner en la pantalla de bloqueo.",
    },
}
SEVERITY_ORDER = {"severe": 0, "moderate": 1, "mild": 2}


def _t(lang: str, key: str, **values) -> str:
    return STRINGS[lang].get(key, STRINGS["en"][key]).format(**values)


def utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def ndef_size(value: str, lang: str = "en") -> int:
    """Bytes an NDEF Text record holding `value` takes in a Type 2 tag's user memory: the record
    (header, type length, payload length — 1 byte up to 255, else 4 —, type "T", the status byte
    and the language code, then the UTF-8 text) inside an NDEF Message TLV (tag, length — 1 byte
    up to 254, else 3) and the Terminator TLV. NFC Forum Text RTD 1.0 and Type 2 Tag 1.0."""
    payload = 1 + utf8_size(lang) + utf8_size(value)
    record = 3 + (1 if payload <= 255 else 4) + payload
    return 1 + (1 if record <= 254 else 3) + record + 1


def nfc_budget(value: str, lang: str = "en") -> dict:
    size = ndef_size(value, lang)
    return {"text_bytes": utf8_size(value), "size": size, "default_tag": DEFAULT_TAG,
            "tags": [{"tag": tag, "capacity": cap, "fits": size <= cap, "over": max(0, size - cap)}
                     for tag, cap in NFC_TAGS.items()]}


def _number(value, lang: str) -> str:
    value = float(value)
    if not math.isfinite(value):
        return ""
    out = f"{value:.3f}".rstrip("0").rstrip(".")
    return out.replace(".", ",") if lang in ("uk", "es") else out


def _word(lang: str, prefix: str, value: str | None) -> str | None:
    if not value:
        return None
    key = f"{prefix}.{value.lower()}"
    return _t(lang, key) if key in STRINGS["en"] else value


def blood_type(blood: str | None, rh: str | None) -> str | None:
    """"A" + "+" → "A+"; "A+" alone stays; Rh as entered when it is not a sign."""
    blood, rh = (blood or "").strip(), (rh or "").strip()
    if not blood:
        return None
    if not rh or blood[-1] in "+-−":
        return blood
    # ASCII signs: a tag reader or a lock screen may not have "−"
    sign = {"+": "+", "pos": "+", "positive": "+", "-": "-", "−": "-", "neg": "-",
            "negative": "-"}.get(rh.lower())
    return f"{blood}{sign}" if sign else f"{blood} Rh {rh}"


def allergy_text(a: dict, lang: str) -> str:
    detail = [a["reaction"], _word(lang, "severity", a["severity"]),
              None if a["verified"] else _t(lang, "unverified")]
    detail = [d for d in detail if d]
    return f"{a['allergen']} ({', '.join(detail)})" if detail else a["allergen"]


def medication_text(m: dict, lang: str) -> str:
    dose = ""
    if m["dose_amount"] is not None:
        dose = f"{_number(m['dose_amount'], lang)} {m['dose_unit'] or ''}".strip()
    per_day = (_t(lang, "per_day", n=_number(m["times_per_day"], lang))
               if m["times_per_day"] is not None else "")
    pattern = _word(lang, "pattern", m["dosing_pattern"])
    return " ".join(p for p in (m["name"], dose, per_day, pattern and f"({pattern})") if p)


def condition_text(d: dict, lang: str) -> str:
    marks = [_word(lang, "clinical", d["clinical_status"]) if d["clinical_status"] != "active"
             else None,
             _word(lang, "verification", d["verification_status"])
             if d["verification_status"] != "confirmed" else None]
    marks = [m for m in marks if m]
    name = f"{d['name']} {d['icd10']}" if d["icd10"] else d["name"]
    return f"{name} ({', '.join(marks)})" if marks else name


def _read(conn, uid: str) -> dict:
    prof = conn.execute(
        text("SELECT blood_type, rh_factor, emergency_contact FROM user_profile WHERE user_id=:u"),
        {"u": uid}).mappings().first()
    allergies = conn.execute(
        text("""SELECT allergen, reaction, severity, verified FROM v_allergies
                WHERE user_id=:u ORDER BY allergen, id"""), {"u": uid}).mappings().all()
    meds = conn.execute(
        text("""SELECT medication_name, dose_amount, dose_unit, times_per_day, dosing_pattern,
                       product_type
                FROM v_medications_current WHERE user_id=:u
                ORDER BY medication_name, id"""), {"u": uid}).mappings().all()
    diags = conn.execute(
        text("""SELECT diagnosis_name, icd10_code, clinical_status, verification_status
                FROM v_diagnoses
                WHERE user_id=:u AND clinical_status = ANY(:active)
                  AND verification_status IS DISTINCT FROM 'refuted'
                ORDER BY (verification_status IS DISTINCT FROM 'confirmed'), diagnosed_at DESC,
                         diagnosis_name, id"""),
        {"u": uid, "active": list(ACTIVE)}).mappings().all()
    return {
        "profile": prof,
        # the most severe first; nothing is left out
        "allergies": sorted(
            ({"allergen": a["allergen"], "reaction": a["reaction"], "severity": a["severity"],
              "verified": bool(a["verified"])} for a in allergies),
            key=lambda a: (SEVERITY_ORDER.get((a["severity"] or "").lower(), 3),
                           a["allergen"].lower())),
        "medications": [{"name": m["medication_name"],
                         "dose_amount": None if m["dose_amount"] is None else float(m["dose_amount"]),
                         "dose_unit": m["dose_unit"],
                         "times_per_day": (None if m["times_per_day"] is None
                                           else float(m["times_per_day"])),
                         "dosing_pattern": m["dosing_pattern"],
                         "product_type": m["product_type"]} for m in meds],
        "conditions": [{"name": d["diagnosis_name"], "icd10": d["icd10_code"],
                        "clinical_status": d["clinical_status"],
                        "verification_status": d["verification_status"]} for d in diags],
    }


def _lines(items: list[str], none: str) -> str:
    return "\n".join(items) if items else none


def build(conn, lang: str = "en", tz: tzinfo | None = None) -> dict:
    """The packet as data, both layouts rendered. `tz`: the user's zone for "as of" (default:
    this machine's — the server runs on the user's own computer)."""
    lang = lang if lang in LANGUAGES else "en"
    now = conn.execute(text("SELECT now()")).scalar().astimezone(tz)
    as_of = now.date()
    base = {"lang": lang, "as_of": as_of, "generated_at": now, "title": _t(lang, "nfc.title"),
            "as_of_text": _t(lang, "as_of", date=as_of.isoformat()),
            "notice": _t(lang, "notice"), "privacy": _t(lang, "privacy")}
    uid = q.user_id(conn)
    data = _read(conn, uid) if uid else None
    if data is None or data["profile"] is None and not (
            data["allergies"] or data["medications"] or data["conditions"]):
        return {**base, "empty": True, "message": _t(lang, "empty")}

    prof = data["profile"] or {}
    blood = blood_type(prof.get("blood_type"), prof.get("rh_factor"))
    contact = (prof.get("emergency_contact") or "").strip() or None
    allergies = [allergy_text(a, lang) for a in data["allergies"]]
    meds = [medication_text(m, lang) for m in data["medications"]]
    conditions = [condition_text(d, lang) for d in data["conditions"]]
    as_of_line = _t(lang, "as_of", date=as_of.isoformat())

    values = {
        "conditions": _lines(conditions, _t(lang, "none")),
        "medications": _lines(meds, _t(lang, "none")),
        "allergies": _lines(allergies, _t(lang, "allergies.none")),
        "blood_type": blood or _t(lang, "not_recorded"),
        "emergency_contact": contact or _t(lang, "not_recorded"),
        "notes": f"{as_of_line} {_t(lang, 'notice')}",
    }
    fields = [{"key": k, "label": _t(lang, f"field.{k}"), "text": values[k],
               "recorded": k == "notes" or bool({"conditions": conditions, "medications": meds,
                                                 "allergies": allergies, "blood_type": blood,
                                                 "emergency_contact": contact}[k])}
              for k in FIELDS]

    def joined(items, none):
        return "; ".join(items) if items else none

    nfc_text = "\n".join([
        f"{_t(lang, 'nfc.title')} · {as_of_line}",
        f"{_t(lang, 'field.allergies')}: {joined(allergies, _t(lang, 'allergies.none'))}",
        f"{_t(lang, 'field.conditions')}: {joined(conditions, _t(lang, 'none'))}",
        f"{_t(lang, 'field.medications')}: {joined(meds, _t(lang, 'none'))}",
        f"{_t(lang, 'field.blood_type')}: {values['blood_type']}",
        f"{_t(lang, 'field.emergency_contact')}: {values['emergency_contact']}",
        _t(lang, "notice"),
    ])
    budget = nfc_budget(nfc_text, lang)
    default = next(b for b in budget["tags"] if b["tag"] == DEFAULT_TAG)
    budget["message"] = (_t(lang, "nfc.fits", size=budget["size"], tag=DEFAULT_TAG,
                            capacity=default["capacity"]) if default["fits"] else
                         _t(lang, "nfc.over", size=budget["size"], tag=DEFAULT_TAG,
                            capacity=default["capacity"], over=default["over"]))
    return {**base, "empty": False,
            "allergies": data["allergies"], "medications": data["medications"],
            "conditions": data["conditions"], "blood_type": blood, "emergency_contact": contact,
            "lock_screen": {"fields": fields},
            "nfc": {"text": nfc_text, **budget}}


def render_text(packet: dict, layout: str = "lock_screen") -> str:
    """The packet as plain text, to read or paste: the chosen layout, then the privacy note."""
    if packet["empty"]:
        return f"{packet['message']}\n\n{packet['privacy']}"
    if layout == "nfc":
        nfc = packet["nfc"]
        return f"{nfc['text']}\n\n{nfc['message']}\n\n{packet['privacy']}"
    blocks = [f"{f['label']}:\n{f['text']}" for f in packet["lock_screen"]["fields"]]
    return "\n\n".join([*blocks, packet["privacy"]])
