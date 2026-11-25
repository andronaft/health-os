// What the medications, diagnoses and habits pages say, from what their /api/v1 routes send.
// Nothing here touches the page, so it can be tested without a browser (tests/web_ui.test.mjs).
// Plain facts from the record; the only figures are date arithmetic and recorded dose × times.

import { formatDate } from "../components.js";
import { t } from "../strings.js";
import { tn } from "./labs-model.js";
import { toDay } from "./timeline-model.js";

/** A stored value's word, when there is one; a value added later shows as stored. */
export function word(group, stored) {
  if (stored === null || stored === undefined || stored === "") return "";
  const key = `record.${group}.${stored}`;
  const found = t(key);
  return found === key ? String(stored).replaceAll("_", " ") : found;
}

/** "9 days", "6 months", "9 years": how long, rounded down, never more than it was. */
export function durationText(days) {
  if (days === null || days === undefined || days < 0) return "";
  // a day's slack, so 2017-11-25 → 2026-11-25 is 9 years whatever the leap days
  if (days < 61) return tn("record.duration.days", { n: days });
  if (days < 730) return tn("record.duration.months", { n: Math.floor((days + 1) / 30.44) });
  return tn("record.duration.years", { n: Math.floor((days + 1) / 365.25) });
}

const plain = (n) => (n === null || n === undefined ? "" : String(Number(n)));

// ----------------------------------------------------------------------------- medications

/** "500 mg × 2/day" — only what was recorded. */
export function doseText({ dose_amount: dose, dose_unit: unit, times_per_day: times }) {
  const amount = [plain(dose), dose !== null && dose !== undefined ? unit : ""].filter(Boolean).join(" ");
  const per = times ? t("record.medication.per_day", { n: plain(times) }) : "";
  return [amount, per].filter(Boolean).join(" × ");
}

/** "since 2017-11-25 · 9 years" / "2022-11-25 → 2023-05-27 · 6 months" */
export function medicationPeriod(m) {
  let dates = t("record.since", { date: formatDate(m.start_date) });
  if (m.end_date) dates = `${formatDate(m.start_date)} → ${formatDate(m.end_date)}`;
  // stopped, but when was never recorded: never "since", which would read as still taken
  else if (m.status !== "taking") dates = `${formatDate(m.start_date)} → ${t("timeline.end_not_recorded")}`;
  return [dates, durationText(m.days)].filter(Boolean).join(" · ");
}

/** Why it stopped, as recorded; a stop without a reason says so instead of guessing. */
export function stopText(m) {
  if (m.status === "taking") return "";
  const why = m.stop_reason || t("record.medication.no_reason");
  return m.status === "stopped" ? why : `${word("med_status", m.status)}: ${why}`;
}

/** The small tags after a medication's name: product type (not prescription), route, pattern. */
export function medicationTags(m) {
  return [
    m.product_type && m.product_type !== "prescription" && word("product", m.product_type),
    m.route && word("route", m.route),
    m.dosing_pattern && word("pattern", m.dosing_pattern),
  ].filter(Boolean);
}

/**
 * The recorded paracetamol per day, as sentences. Arithmetic on recorded doses only: no verdict
 * under the limit (a sum is no reassurance), and a product without a dose in mg is named, not
 * counted as nothing.
 */
export function paracetamolLines(p) {
  if (!p) return [];
  const lines = [];
  if (p.mg_per_day) {
    lines.push(tn("record.paracetamol.total", { n: p.products.length - p.missing_dose.length, mg: plain(p.mg_per_day) }));
  }
  if (p.missing_dose.length) lines.push(t("record.paracetamol.missing", { names: p.missing_dose.join(", ") }));
  if (p.over_limit) lines.push(t("record.paracetamol.over", { limit: p.limit_mg }));
  lines.push(t("record.paracetamol.note"));
  return lines;
}

/** "penicillin — rash · moderate", with "unverified, treated as an allergy" when not verified. */
export function allergyLine(a) {
  return [
    a.allergen,
    [a.reaction, a.severity && word("severity", a.severity)].filter(Boolean).join(" · "),
  ].filter(Boolean).join(" — ");
}

// ------------------------------------------------------------------------------- diagnoses

export const verificationTitle = (verification) => word("verification", verification);

/** What each group means, so "suspected" can't be read as a diagnosis. */
export const verificationNote = (verification) => {
  const key = `record.verification_note.${verification}`;
  return t(key) === key ? "" : t(key);
};

const ACTIVE = new Set(["active", "recurrence", "relapse"]);
/** Active, and believed: a refuted diagnosis left with the default "active" status is not. */
export const isActive = (d) => ACTIVE.has(d.clinical_status) && d.verification_status !== "refuted";

/** The clinical-status tag; none for a refuted diagnosis, whatever status it was left with. */
export const clinicalTag = (d) => (d.verification_status === "refuted" ? "" : word("clinical", d.clinical_status));

/** Active ones first (newest first), then the rest (newest first). */
export function sortDiagnoses(rows) {
  return [...rows].sort((a, b) => isActive(b) - isActive(a) || toDay(b.diagnosed_at) - toDay(a.diagnosed_at));
}

/** "since 2017-11-25" / "2022-11-25 → 2023-03-01" / "recorded 2024-05-26" */
export function diagnosisDates(d) {
  if (d.resolved_at) return `${formatDate(d.diagnosed_at)} → ${formatDate(d.resolved_at)}`;
  return t(isActive(d) ? "record.since" : "record.recorded", { date: formatDate(d.diagnosed_at) });
}

/** The neutral hint: an observation about the record, never advice about the person. */
export function reviewHint(d, today) {
  if (!d.review_hint) return "";
  // what the check measures: the entry's own date, the only date a diagnosis has (none is ever
  // updated in place) — not whether anything else was recorded about the condition since
  return t("record.diagnosis.review_hint", { duration: durationText(toDay(today) - toDay(d.diagnosed_at)), date: formatDate(d.diagnosed_at) });
}

export const reviewCount = (groups) => groups.reduce((n, group) => n + group.rows.filter((d) => d.review_hint).length, 0);

// ---------------------------------------------------------------------------------- habits

/** "8 cigarettes a day · 10 years" / "2–3 drinks a week" — what was recorded about the amount. */
export function habitAmount(h) {
  return [
    h.frequency,
    h.cigarettes_per_day && tn("record.habit.cigarettes", { n: h.cigarettes_per_day }),
    h.drinks_per_week && !h.frequency && tn("record.habit.drinks", { n: Number(h.drinks_per_week) }),
    h.smoking_years && tn("record.habit.smoking_years", { n: h.smoking_years }),
  ].filter(Boolean).join(" · ");
}

/**
 * The streak, said plainly: a current habit "for 3 years (since …)", a former one "stopped 12
 * years ago, after 10 years". Date arithmetic on the recorded dates only; none, none said.
 */
export function habitStreak(h) {
  if (h.status === "current") {
    return h.start_date ? t("record.habit.for", { duration: durationText(h.days), date: formatDate(h.start_date) }) : t("record.habit.no_start");
  }
  if (h.status === "former") {
    if (h.end_date) {
      const after = h.start_date ? t("record.habit.after", { duration: durationText(h.days) }) : "";
      return [t("record.habit.stopped_ago", { duration: durationText(h.days_since_end), date: formatDate(h.end_date) }), after].filter(Boolean).join(", ");
    }
    return t("record.habit.stopped_undated");
  }
  return word("habit_status", h.status);
}

/**
 * Where a habit's bar sits on a strip from `from` to `today` (days): { left, width } as shares
 * of 0–1, and undated: a former habit with no end date, drawn as a stub. None without a start.
 */
export function habitBar(h, from, today) {
  if (!h.start_date) return null;
  const span = Math.max(1, today - from);
  const start = Math.max(toDay(h.start_date), from);
  // only a current habit runs to today; a former one with no end date is a stub at its start
  const undated = !h.end_date && h.status !== "current";
  const end = h.end_date ? toDay(h.end_date) : undated ? start : today;
  return { left: (start - from) / span, width: Math.max(0.005, (end - start) / span), undated };
}
