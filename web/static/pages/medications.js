// The medications page (#57): allergies first (critical information, never something to scroll
// to), then what is taken now and what was taken before, with dose, route, dates and why it
// stopped. The only figure is the recorded paracetamol per day: arithmetic, not advice.

import { api } from "../api.js";
import { el } from "../components.js";
import { LANG, t } from "../strings.js";
import { tn } from "./labs-model.js";
import {
  allergyLine, doseText, medicationPeriod, medicationTags, paracetamolLines, stopText,
} from "./record-model.js";

const quiet = (text) => el("p", { class: "quiet" }, text);

function allergyBanner(allergies) {
  if (!allergies.length) {
    return el("section", { class: "rec-allergies rec-allergies-none" },
      el("h2", {}, t("record.allergies.title")),
      el("p", {}, t("record.allergies.none")));
  }
  return el("section", { class: "rec-allergies", "aria-labelledby": "rec-allergies-title" },
    el("h2", { id: "rec-allergies-title" },
      el("span", { class: "state-icon", "aria-hidden": "true" }, "!"),
      t("record.allergies.count", { n: allergies.length })),
    el("ul", {}, ...allergies.map((a) => el("li", {},
      el("strong", {}, allergyLine(a)),
      !a.verified && el("span", { class: "rec-tag rec-tag-warn" }, t("record.allergies.unverified")),
      a.notes && el("span", { class: "quiet" }, ` · ${a.notes}`)))),
    quiet(t("record.allergies.note")));
}

function medicationCard(m) {
  const dose = doseText(m);
  return el("li", { class: `card rec-med${m.status === "taking" ? "" : " rec-med-past"}` },
    el("h3", {}, m.name, ...medicationTags(m).map((tag) => el("span", { class: "rec-tag" }, tag))),
    el("dl", { class: "rec-fields" },
      dose && el("dt", {}, t("record.medication.dose")), dose && el("dd", {}, dose),
      el("dt", {}, t("record.medication.taken")), el("dd", {}, medicationPeriod(m)),
      m.prescribed_for && el("dt", {}, t("record.medication.for")), m.prescribed_for && el("dd", {}, m.prescribed_for),
      m.status !== "taking" && el("dt", {}, t("record.medication.stopped")), m.status !== "taking" && el("dd", {}, stopText(m)),
      m.side_effects && el("dt", {}, t("record.medication.side_effects")), m.side_effects && el("dd", {}, m.side_effects)));
}

function paracetamolNote(p) {
  const lines = paracetamolLines(p);
  if (!lines.length) return null;
  return el("aside", { class: `rec-note${p.over_limit ? " rec-note-warn" : ""}` },
    el("h3", {}, t("record.paracetamol.title")),
    ...lines.map((line) => el("p", {}, line)));
}

export async function render(view) {
  const data = await api(`medications?lang=${LANG}`);
  view.replaceChildren(el("div", { class: "record" },
    allergyBanner(data.allergies),
    el("section", {},
      el("h2", {}, t("record.medications.current", { n: data.current.length })),
      data.current.length
        ? el("ul", { class: "rec-cards" }, ...data.current.map(medicationCard))
        : quiet(t("record.medications.current_none")),
      paracetamolNote(data.paracetamol)),
    el("section", {},
      el("h2", {}, t("record.medications.past", { n: data.past.length })),
      data.past.length
        ? el("ul", { class: "rec-cards" }, ...data.past.map(medicationCard))
        : quiet(t("record.medications.past_none"))),
    quiet(t("record.medications.note")),
    el("p", {}, el("a", { href: "#/timeline" }, t("record.open_timeline")))));
}
