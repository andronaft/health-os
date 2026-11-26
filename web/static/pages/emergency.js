// The emergency packet (#74): what a paramedic can read without unlocking the phone. Three ways to
// carry it, all copied by the user — health-os never writes to the phone or a tag: the lock screen's
// Medical ID fields, an NFC tag's text (with its size against the tag), a printed wallet card. The
// packet has its own language, chosen apart from the UI's; approved data only, nothing cut to fit.

import { api, explain } from "../api.js";
import { el, errorState } from "../components.js";
import { LANG, t } from "../strings.js";
import { LANG_NAMES } from "./report-strings.js";
import { LANG_KEY, PACKET_LANGS, cardSides, copyText, nfcBudget, packetLang, tallerThanCard } from "./emergency-model.js";
import { browserZone } from "./report-model.js";

function storage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function savedLang() {
  try {
    return packetLang(storage()?.getItem(LANG_KEY) ?? LANG);
  } catch {
    return packetLang(LANG);
  }
}

/** The old way, for a browser without the Clipboard API: a selected off-screen textarea. */
function execCopy(text) {
  const area = el("textarea", { class: "visually-hidden", readonly: true, "aria-hidden": "true" });
  area.value = text;
  document.body.append(area);
  area.select();
  try {
    return document.execCommand("copy");
  } finally {
    area.remove();
  }
}

function selectText(node) {
  if (node instanceof HTMLTextAreaElement) {
    node.focus();
    node.select();
    return;
  }
  const range = document.createRange();
  range.selectNodeContents(node);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

function copyButton(getText, target, label) {
  const status = el("span", { class: "emergency-copy-status", role: "status" });
  const button = el("button", {
    type: "button", class: "emergency-copy", "aria-label": `${t("emergency.copy")}: ${label}`,
    onclick: async () => {
      const result = await copyText(getText(), navigator.clipboard, execCopy);
      status.textContent = t(result === "copied" ? "emergency.copied" : "emergency.copy_failed");
      if (result !== "copied") selectText(target);
      clearTimeout(button.timer);
      button.timer = setTimeout(() => { status.textContent = ""; }, 4000);
    },
  }, t("emergency.copy"));
  return el("span", { class: "emergency-copy-wrap" }, button, status);
}

function lockScreen(packet) {
  const cards = packet.lock_screen.fields.map((field) => {
    const body = el("pre", { class: "emergency-field-text", lang: packet.lang }, field.text);
    return el("li", { class: "card emergency-field", "data-recorded": String(field.recorded) },
      el("div", { class: "emergency-field-head" },
        el("h3", { lang: packet.lang }, field.label),
        !field.recorded && el("span", { class: "quiet" }, t("emergency.not_recorded")),
        copyButton(() => field.text, body, field.label)),
      body);
  });
  return el("section", { class: "emergency-section" },
    el("h2", {}, t("emergency.lock.title")),
    el("p", { class: "quiet public" }, t("emergency.lock.lead")),
    el("ul", { class: "emergency-fields" }, ...cards));
}

function nfc(packet) {
  const full = packet.nfc.text;
  const area = el("textarea", {
    class: "emergency-nfc-text", rows: "9", lang: packet.lang, spellcheck: "false",
    "aria-label": t("emergency.nfc.title"), "aria-describedby": "emergency-nfc-size",
  });
  area.value = full;
  const size = el("p", { id: "emergency-nfc-size", class: "emergency-nfc-size", "aria-live": "polite" });
  const tags = el("ul", { class: "emergency-tags" });
  const edited = el("p", { class: "emergency-edited", hidden: true }, t("emergency.nfc.edited"));
  const reset = el("button", {
    type: "button", hidden: true,
    onclick: () => { area.value = full; update(); },
  }, t("emergency.nfc.reset"));
  function update() {
    const budget = nfcBudget(area.value, packet.lang);
    size.textContent = t("emergency.nfc.size", { size: budget.size, text: budget.textBytes, chars: budget.chars });
    tags.replaceChildren(...budget.tags.map((tag) => el("li", { "data-fits": String(tag.fits) },
      el("span", { class: "emergency-tag-name" }, t("emergency.nfc.tag", { tag: tag.tag, capacity: tag.capacity })),
      // green, amber when nearly full, red only when over: a full tag that fits stays under `high`
      el("meter", {
        min: "0", max: String(tag.capacity), optimum: "0", low: String(tag.capacity * 0.9), high: String(tag.capacity - 0.5),
        value: String(tag.fits ? Math.min(budget.size, tag.capacity - 0.5) : tag.capacity), "aria-hidden": "true",
      }),
      el("span", { class: "emergency-tag-verdict" },
        el("span", { "aria-hidden": "true" }, tag.fits ? "✓ " : "✕ "),
        tag.fits ? t("emergency.nfc.fits") : t("emergency.nfc.over", { over: tag.over })))));
    const changed = area.value !== full;
    edited.hidden = !changed;
    reset.hidden = !changed;
  }
  area.addEventListener("input", update);
  update();
  return el("section", { class: "emergency-section" },
    el("h2", {}, t("emergency.nfc.title")),
    el("p", { class: "quiet public" }, t("emergency.nfc.lead")),
    area,
    el("div", { class: "emergency-nfc-actions" }, copyButton(() => area.value, area, t("emergency.nfc.title")), reset),
    edited, size, tags,
    el("p", { class: "footnote" }, t("emergency.nfc.source")));
}

function cardSide(packet, fields, heading) {
  return el("div", { class: "wallet-side" },
    heading,
    ...fields.map((f) => el("div", { class: "wallet-field", "data-recorded": String(f.recorded) },
      el("p", { class: "wallet-label" }, f.label),
      el("p", { class: "wallet-text" }, f.text))));
}

function walletCard(packet) {
  const sides = cardSides(packet.lock_screen.fields);
  const front = cardSide(packet, sides.front, el("p", { class: "wallet-title" }, el("span", { "aria-hidden": "true" }, "✚ "), packet.title));
  const back = cardSide(packet, sides.back, null);
  const card = el("div", { class: "wallet-card", lang: packet.lang }, front, back);
  // a side that is too full grows (styles.css: never clipped); the warning is on screen and on paper
  const overflow = el("p", { class: "emergency-warning", hidden: true }, t("emergency.card.overflow"));
  const printed = el("p", { class: "wallet-overflow-print", hidden: true }, t("emergency.card.overflow_print"));
  const probe = el("div", { class: "wallet-probe", "aria-hidden": "true" });
  const sheet = el("div", { class: "wallet-sheet" }, probe, card, printed);
  const print = matchMedia("print");
  const check = () => {
    if (!sheet.isConnected) {
      // the page was left: stop listening
      window.removeEventListener("beforeprint", check);
      window.removeEventListener("resize", check);
      print.removeEventListener("change", check);
      return;
    }
    const tall = tallerThanCard([front, back].map((side) => side.getBoundingClientRect().height),
      probe.getBoundingClientRect().height);
    card.dataset.overflow = String(tall);
    overflow.hidden = !tall;
    printed.hidden = !tall;
  };
  // measured again whenever the layout may change: fonts, window size, and the print layout itself
  requestAnimationFrame(check);
  document.fonts?.ready.then(check);
  window.addEventListener("beforeprint", check);
  window.addEventListener("resize", check);
  print.addEventListener("change", check);
  return el("section", { class: "emergency-section emergency-wallet" },
    el("h2", {}, t("emergency.card.title")),
    el("p", { class: "quiet public" }, t("emergency.card.lead")),
    el("button", { type: "button", class: "emergency-print", onclick: () => window.print() }, t("emergency.card.print")),
    overflow,
    sheet);
}

function controls(state, redraw) {
  const select = el("select", {
    onchange: (e) => {
      state.lang = e.target.value;
      try {
        storage()?.setItem(LANG_KEY, state.lang);
      } catch {
        // storage blocked: the choice lasts until the page is left
      }
      redraw();
    },
  }, ...PACKET_LANGS.map((code) => el("option", { value: code, lang: code, selected: code === state.lang }, LANG_NAMES[code])));
  return el("div", { class: "emergency-controls" },
    el("label", {}, t("emergency.language"), " ", select),
    el("p", { class: "quiet public" }, t("emergency.note")));
}

function page(packet, state, redraw) {
  const privacy = el("div", { class: "emergency-privacy", role: "note" },
    el("p", {}, el("strong", {}, t("emergency.privacy.title")), " ",
      el("span", { lang: packet.lang }, packet.privacy)));
  const head = el("div", { class: "emergency-head", lang: packet.lang },
    el("p", { class: "emergency-asof" }, packet.as_of_text),
    el("p", { class: "emergency-notice" }, packet.notice));
  if (packet.empty) {
    return el("div", { class: "emergency" }, controls(state, redraw), privacy, head,
      el("p", { class: "emergency-empty", lang: packet.lang }, packet.message));
  }
  return el("div", { class: "emergency" }, controls(state, redraw), privacy, head,
    lockScreen(packet), nfc(packet), walletCard(packet));
}

export async function render(view) {
  const state = { lang: savedLang() };
  let latest = 0;
  const draw = async () => {
    const request = ++latest; // a slow answer for the previous language is stale
    const query = new URLSearchParams({ lang: state.lang });
    const zone = browserZone();
    if (zone) query.set("tz", zone);
    let packet;
    try {
      packet = await api(`emergency?${query}`);
    } catch (err) {
      if (request !== latest) return;
      throw err;
    }
    if (request !== latest) return;
    view.replaceChildren(page(packet, state, redraw));
  };
  const redraw = () => draw().catch((err) => {
    console.error(err);
    if (!view.isConnected) return;
    view.replaceChildren(errorState({ message: explain(err), onRetry: redraw }));
  });
  await draw();
}
