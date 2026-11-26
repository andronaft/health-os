// The emergency page's logic that needs no browser (tests/web_ui.test.mjs): the NFC byte counter,
// copying, and which Medical ID field goes on which side of the wallet card. The packet's words come
// from /api/v1/emergency in the packet's own language; nothing here translates or shortens them.

export const LANG_KEY = "health-os-emergency-lang";
export const PACKET_LANGS = ["en", "uk", "es"];
export const packetLang = (lang) => (PACKET_LANGS.includes(lang) ? lang : "en");

// User memory of NXP's NFC Forum Type 2 tags: NTAG213/215/216 data sheet (NXP, Rev. 3.2, 2 June
// 2015), §8.5 "Memory organization". The same figures as core/emergency.py NFC_TAGS.
export const NFC_TAGS = [
  { tag: "NTAG213", capacity: 144 },
  { tag: "NTAG215", capacity: 504 },
  { tag: "NTAG216", capacity: 888 },
];

export const utf8Size = (text) => new TextEncoder().encode(text).length;

/**
 * Bytes an NDEF Text record holding `text` takes on the tag, as core/emergency.py ndef_size counts
 * them: the record (header, type length, payload length — 1 byte up to 255, else 4 —, type "T",
 * status byte, language code, UTF-8 text) in an NDEF Message TLV (1-byte length up to 254, else 3)
 * plus the Terminator TLV.
 */
export function ndefSize(text, lang = "en") {
  const payload = 1 + utf8Size(lang) + utf8Size(text);
  const record = 3 + (payload <= 255 ? 1 : 4) + payload;
  return 1 + (record <= 254 ? 1 : 3) + record + 1;
}

/** The size and, per tag, whether it fits and by how much it does not. Never shortens the text. */
export function nfcBudget(text, lang = "en") {
  const size = ndefSize(text, lang);
  return {
    size,
    textBytes: utf8Size(text),
    chars: [...text].length,
    tags: NFC_TAGS.map(({ tag, capacity }) => ({ tag, capacity, fits: size <= capacity, over: Math.max(0, size - capacity) })),
  };
}

/**
 * Copy `text`: the Clipboard API, else `fallback()` (a selected textarea and execCommand), which
 * returns true when it worked. "copied" or "failed" — on "failed" the page selects the text for the
 * user to copy by hand.
 */
export async function copyText(text, clipboard, fallback) {
  try {
    if (!clipboard?.writeText) throw new Error("no Clipboard API");
    await clipboard.writeText(text);
    return "copied";
  } catch {
    try {
      return fallback(text) ? "copied" : "failed";
    } catch {
      return "failed";
    }
  }
}

// a paramedic opening the card sees what can kill first: allergies, blood type, whom to call
const FRONT = ["allergies", "blood_type", "emergency_contact"];
const BACK = ["conditions", "medications", "notes"];

/** The lock-screen fields split over the card's two sides; every field is on one of them. */
export function cardSides(fields) {
  const byKey = new Map(fields.map((f) => [f.key, f]));
  const side = (keys) => keys.filter((k) => byKey.has(k)).map((k) => byKey.get(k));
  const placed = new Set([...FRONT, ...BACK]);
  return { front: side(FRONT), back: [...side(BACK), ...fields.filter((f) => !placed.has(f.key))] };
}

/** Is any side taller than a card? Heights in px, the card's from a 54 mm probe in the same layout. */
export const tallerThanCard = (sideHeights, cardHeight) => sideHeights.some((height) => height > cardHeight + 0.5);
