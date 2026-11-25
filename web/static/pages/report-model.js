// What the doctor-visit report says, from what /api/v1/report sends, in the report's language. Nothing
// here touches the page, so it can be tested without a browser (tests/web_ui.test.mjs). Every function
// takes the translator `tr` from report-strings.js: the report's language is not the UI's.

import { chartRange } from "../components.js";

export const QUESTIONS_KEY = "health-os-report-questions";
export const LANG_KEY = "health-os-report-lang";

const has = (value) => value !== null && value !== undefined && value !== "";

/** The date part of what the API sends, as the report's language writes a date: "26 sept 2026". */
export function reportDate(iso, tr) {
  if (!iso) return "";
  const day = String(iso).slice(0, 10); // the offset the API sent decides the day, not this machine
  const at = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) return day;
  return new Intl.DateTimeFormat(tr.locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(at);
}

/** A number as the report's language writes it: 5,8 in uk and es. */
export const reportNumber = (n, tr, digits = 3) =>
  new Intl.NumberFormat(tr.locale, { maximumFractionDigits: digits }).format(n);

// unit parts in Ukrainian; µ for u everywhere; IU is UI in Spanish
const UNIT_PARTS = {
  uk: {
    mol: "моль", mmol: "ммоль", umol: "мкмоль", µmol: "мкмоль", nmol: "нмоль", pmol: "пмоль",
    g: "г", mg: "мг", ug: "мкг", µg: "мкг", mcg: "мкг", ng: "нг", pg: "пг", kg: "кг",
    l: "л", dl: "дл", ml: "мл", fl: "фл", iu: "МО", miu: "мМО", uiu: "мкМО", µiu: "мкМО", u: "Од",
    mmhg: "мм рт. ст.", cm: "см", mm: "мм", h: "год", min: "хв", s: "с", bpm: "уд/хв",
  },
  es: { iu: "UI", miu: "mUI", uiu: "µUI", µiu: "µUI", umol: "µmol", ug: "µg", mcg: "µg", bpm: "lpm" },
  en: { umol: "µmol", ug: "µg", mcg: "µg" },
};

/** "umol/L" → "мкмоль/л" (uk), "µmol/L" (en, es). A part it doesn't know stays as printed. */
export function reportUnit(unit, tr) {
  if (!unit) return "";
  const parts = UNIT_PARTS[tr.lang] ?? {};
  return unit.split(/(\/|\s+)/).map((part) => parts[part.toLowerCase()] ?? part).join("");
}

/** "<5 mmol/L", "3,8 ммоль/л"; a non-numeric result's text as printed. */
export function reportValue({ value, comparator, text, unit }, tr) {
  if (!has(value)) return text ?? "";
  return [`${comparator ?? ""}${reportNumber(value, tr)}`, reportUnit(unit, tr)].filter(Boolean).join(" ");
}

/** "0–5,2", "≤ 5,2", "≥ 1,2"; "" when the form printed none. */
export function reportRange({ ref_min: low, ref_max: high }, tr) {
  const n = (v) => reportNumber(v, tr);
  if (has(low) && has(high)) return `${n(low)}–${n(high)}`;
  if (has(high)) return `≤ ${n(high)}`;
  return has(low) ? `≥ ${n(low)}` : "";
}

const STATUSES = ["low", "high", "critical", "normal"];
export const statusText = (status, tr) => tr.t(`status.${STATUSES.includes(status) ? status : "unknown"}`);

/** "born 12 Apr 1985"; Spanish and Ukrainian say it in the patient's grammatical gender. */
function bornText(sex, born, tr) {
  const vars = { date: reportDate(born, tr) };
  const gendered = tr.t(`profile.born.${sex}`, vars);
  return gendered.startsWith("profile.born.") ? tr.t("profile.born", vars) : gendered;
}

/** "Female, 41 years (born 12 Apr 1985) · blood type A+ · height 168 cm" */
export function profileLine(profile, tr) {
  if (!profile || (!profile.sex && !has(profile.age) && !profile.blood_type && !has(profile.height_cm))) {
    return tr.t("profile.missing");
  }
  const { sex, age, date_of_birth: born, blood_type: blood, rh_factor: rh, height_cm: height } = profile;
  const who = [
    sex && (["female", "male"].includes(sex) ? tr.t(`sex.${sex}`) : tr.t("sex.other", { sex })),
    has(age) && tr.t("profile.age", { age }),
  ].filter(Boolean).join(", ");
  return [
    [who, born && `(${bornText(sex, born, tr)})`].filter(Boolean).join(" "),
    blood && tr.t("profile.blood", { type: `${blood}${rh ?? ""}` }),
    has(height) && tr.t("profile.height", { height: `${reportNumber(height, tr, 1)} ${reportUnit("cm", tr)}` }),
  ].filter(Boolean).join(" · ");
}

/** "rash · moderate · not verified": what is on record, as entered; the words we own translated. */
export function allergyDetail({ reaction, severity, verified }, tr) {
  const sev = severity && tr.t(`severity.${severity.toLowerCase()}`);
  return [
    reaction && tr.t("allergies.reaction", { text: reaction }),
    severity && (sev.startsWith("severity.") ? severity : sev),
    !verified && tr.t("allergies.unverified"),
  ].filter(Boolean).join(" · ");
}

/** "2000 IU, 1× a day · supplement · since 29 Jan 2026 · for: …" (the name is printed on its own). */
export function medicationDetail(med, tr, { stopped = false } = {}) {
  const dose = has(med.dose_amount) ? `${reportNumber(med.dose_amount, tr)} ${reportUnit(med.dose_unit ?? "", tr)}`.trim() : "";
  const perDay = has(med.times_per_day) ? tr.t("meds.per_day", { n: reportNumber(med.times_per_day, tr) }) : "";
  const product = med.product_type && tr.t(`product.${med.product_type}`);
  const when = stopped && med.end_date
    ? tr.t("meds.until", { from: reportDate(med.start_date, tr), to: reportDate(med.end_date, tr) })
    : med.start_date && tr.t("meds.since", { date: reportDate(med.start_date, tr) });
  return [
    [dose, perDay].filter(Boolean).join(", "),
    product && !product.startsWith("product.") && product,
    when,
    med.prescribed_for && tr.t("meds.for", { text: med.prescribed_for }),
  ].filter(Boolean).join(" · ");
}

const ACTIVE = ["active", "recurrence", "relapse"];
const IN_QUESTION = ["provisional", "suspected", "differential"];

/**
 * Diagnoses by status: confirmed (and active), in question, past. A refuted one is left out: it is
 * not a diagnosis. A diagnosis with no clinical status counts as current, never as past.
 */
export function groupDiagnoses(diagnoses) {
  const groups = { confirmed: [], in_question: [], past: [] };
  for (const d of diagnoses ?? []) {
    if (d.verification_status === "refuted") continue;
    if (d.clinical_status && !ACTIVE.includes(d.clinical_status)) groups.past.push(d);
    else if (IN_QUESTION.includes(d.verification_status)) groups.in_question.push(d);
    else groups.confirmed.push(d);
  }
  return groups;
}

/** "E78.0 · suspected · since 26 Oct 2026" */
export function diagnosisDetail(d, tr) {
  const word = (prefix, value) => {
    const text = value && tr.t(`${prefix}.${value}`);
    return text && !text.startsWith(`${prefix}.`) ? text : value;
  };
  return [
    d.icd10,
    d.clinical_status && !["active"].includes(d.clinical_status) && word("clinical", d.clinical_status),
    d.verification_status && d.verification_status !== "confirmed" && word("verification", d.verification_status),
    d.at && tr.t("diag.since", { date: reportDate(d.at, tr) }),
  ].filter(Boolean).join(" · ");
}

/** "+8,6 %" */
export function percentText(percent, tr) {
  const sign = percent > 0 ? "+" : percent < 0 ? "−" : "±";
  return `${sign}${reportNumber(Math.abs(percent), tr, 1)} %`;
}

/** The sentence on a change between two results; "" when no cited number exists for the marker. */
export function changeText(change, tr) {
  if (!change) return "";
  const vars = { pct: percentText(change.percent, tr), rcv: `${reportNumber(change.rcv, tr, 1)} %` };
  return tr.t(change.significant ? "change.significant" : "change.within", vars);
}

/** The trend chart's short form: "last change +8,6 %, RCV 22,9 %". */
export function changeShort(change, tr) {
  if (!change) return "";
  const vars = { pct: percentText(change.percent, tr), rcv: `${reportNumber(change.rcv, tr, 1)} %` };
  return tr.t(change.significant ? "change.short_significant" : "change.short", vars);
}

/** "since 5 Dec 2024 (4 values in a row)" */
export const streakText = (row, tr) =>
  (row.since ? tr.tn("out.streak", { n: row.streak ?? 1, date: reportDate(row.since, tr) }) : "");

/** The lead of the out-of-range section; it counts what it can see and never says "all is well". */
export function outLead(out, tr) {
  const n = out?.lab_markers_seen ?? 0;
  return tr.tn(out?.rows?.length ? "out.lead" : "out.none", { n });
}

/** "LDL 3,5 → 3,8 mmol/L"-style parts of a "what changed" row. */
export function resultChange(row, tr) {
  return {
    now: reportValue(row, tr),
    status: row.status && row.status !== "normal" ? statusText(row.status, tr) : "",
    before: row.before
      ? tr.t("changes.before", { value: reportValue(row.before, tr), date: reportDate(row.before.at, tr) })
      : tr.t("changes.first"),
    moved: row.moved ? tr.t(`changes.moved.${row.moved}`) : "",
    change: changeText(row.change, tr),
  };
}

/** "What changed since 27 May 2026 (the last six months; no visit on record)" */
export function changesTitle(changes, tr) {
  return tr.t("changes.title", { date: reportDate(changes.since, tr) });
}

export const changesSource = (changes, tr) => tr.t(`changes.source.${changes.since_source}`);

/** True when no medication or diagnosis changed: one sentence instead of three empty lists. */
export const noOtherChanges = ({ medications, diagnoses }) =>
  !medications.started.length && !medications.stopped.length && !diagnoses.length;

export const footerText = (data, tr) =>
  tr.tn("footer", { n: data.approved_values, date: reportDate(data.generated_at, tr) });

export const methodText = (rcv, tr) =>
  tr.t("method.rcv", { markers: rcv.markers.map((m) => m.name).join(", ") });

/** "5 values, 8 Jun 2024 – 26 Sept 2026" */
export function trendSpan(trend, tr) {
  const { points } = trend;
  return tr.tn("trends.span", {
    n: points.length, from: reportDate(points[0]?.at, tr), to: reportDate(points.at(-1)?.at, tr),
  });
}

/**
 * A trend's mini-chart in a width × height box: the points, the latest form's range as a band
 * (clipped to the box), and the value axis' two ends. The axis spans the values and the band, so
 * the band never hides how far out a value is. Coordinates are rounded to 0.1.
 */
export function miniChart(trend, width, height, pad = 4) {
  const values = trend.points.map((p) => p.value);
  const bounds = [trend.ref_min, trend.ref_max].filter(Number.isFinite);
  const [low, high] = chartRange([...values, ...bounds]);
  const times = trend.points.map((p) => Date.parse(p.at));
  const [t0, t1] = [Math.min(...times), Math.max(...times)];
  const round = (n) => Math.round(n * 10) / 10;
  const x = (time) => round(t1 === t0 ? width / 2 : pad + ((time - t0) / (t1 - t0)) * (width - 2 * pad));
  const y = (value) => round(high === low ? height / 2 : pad + ((high - value) / (high - low)) * (height - 2 * pad));
  const clamp = (v) => Math.min(height, Math.max(0, v));
  let band = null;
  if (bounds.length) {
    const top = clamp(Number.isFinite(trend.ref_max) ? y(trend.ref_max) : 0);
    const bottom = clamp(Number.isFinite(trend.ref_min) ? y(trend.ref_min) : height);
    if (bottom > top) band = { y: top, height: round(bottom - top) };
  }
  return {
    points: trend.points.map((p, i) => ({ x: x(times[i]), y: y(p.value), out: ["low", "high", "critical"].includes(p.status) })),
    band,
    low,
    high,
  };
}

/** What a screen reader hears for a mini-chart: every value with its date. */
export function trendLabel(trend, tr) {
  const values = trend.points.map((p) => `${reportNumber(p.value, tr)} (${reportDate(p.at, tr)})`).join(", ");
  return tr.t("trends.label", { name: trend.name, unit: reportUnit(trend.unit, tr), values });
}

/** The questions box's text from localStorage; storage may be blocked, then it is just empty. */
export function loadQuestions(storage) {
  try {
    return storage?.getItem(QUESTIONS_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveQuestions(storage, text) {
  try {
    if (text) storage?.setItem(QUESTIONS_KEY, text);
    else storage?.removeItem(QUESTIONS_KEY);
    return true;
  } catch {
    return false;
  }
}
