// The diagnoses page (#57): grouped by how certain they are (confirmed / provisional / suspected /
// refuted), each with its ICD-10 code and clinical status. A refuted one is struck through, a
// suspected one is never drawn like a confirmed one. An active diagnosis with nothing recorded for
// two years carries a neutral hint: an observation about the record, not advice.

import { api } from "../api.js";
import { el } from "../components.js";
import { LANG, t } from "../strings.js";
import { tn } from "./labs-model.js";
import {
  diagnosisDates, isActive, reviewCount, reviewHint, sortDiagnoses, verificationNote, verificationTitle, word,
} from "./record-model.js";

function diagnosisItem(d, today) {
  const hint = reviewHint(d, today);
  return el("li", { class: "rec-dx", "data-verification": d.verification_status || "unknown", "data-active": isActive(d) },
    el("p", { class: "rec-dx-name" },
      el("span", { class: "rec-dx-title" }, d.name),
      d.icd10_code && el("code", { class: "rec-icd", title: t("record.diagnosis.icd") }, d.icd10_code),
      d.clinical_status && el("span", { class: "rec-tag" }, word("clinical", d.clinical_status)),
      d.severity && el("span", { class: "rec-tag" }, d.severity)),
    el("p", { class: "quiet" }, diagnosisDates(d)),
    d.notes && el("p", { class: "quiet" }, d.notes),
    hint && el("p", { class: "rec-hint" }, el("span", { class: "rec-hint-icon", "aria-hidden": "true" }, "◷"), hint));
}

export async function render(view) {
  const data = await api(`diagnoses?lang=${LANG}`);
  if (!data.groups.length) {
    view.replaceChildren(el("div", { class: "record" },
      el("p", {}, t("record.diagnoses.none")),
      el("p", { class: "quiet" }, t("empty.note"))));
    return;
  }
  const toReview = reviewCount(data.groups);
  view.replaceChildren(el("div", { class: "record" },
    el("p", { class: "quiet" }, t("record.diagnoses.note")),
    toReview > 0 && el("p", { class: "rec-hint" },
      el("span", { class: "rec-hint-icon", "aria-hidden": "true" }, "◷"),
      tn("record.diagnoses.review_summary", { n: toReview, years: Math.floor(data.review_after_days / 365) })),
    ...data.groups.map((group) => el("section", { class: "rec-dx-group", "data-verification": group.verification },
      el("h2", {}, verificationTitle(group.verification), " ", el("span", { class: "quiet" }, `(${group.rows.length})`)),
      verificationNote(group.verification) && el("p", { class: "quiet" }, verificationNote(group.verification)),
      el("ul", { class: "rec-dx-list" }, ...sortDiagnoses(group.rows).map((d) => diagnosisItem(d, data.today))))),
    el("p", {}, el("a", { href: "#/timeline" }, t("record.open_timeline")))));
}
