// What the timeline page draws, from what /api/v1/timeline sends: lanes, rows, the range shown,
// axis ticks, the "life in years" strip and every label. Nothing here touches the page, so it can
// be tested without a browser (tests/web_ui.test.mjs). Dates are whole days, counted in UTC.

import { formatDate } from "../components.js";
import { t } from "../strings.js";
import { tn } from "./labs-model.js";

const DAY_MS = 86400000;
const YEAR = 365.25;
export const MIN_SPAN_DAYS = 31; // zoomed all the way in: about a month
const MONTHS_BELOW_DAYS = 3 * YEAR; // a narrower range is ticked by month

// top to bottom; a lane with nothing in it is not drawn
export const LANES = ["diagnoses", "care", "labs", "vaccinations", "documents", "medications", "habits"];

/** "2026-08-20" (or a full ISO time) → days since 1970-01-01. */
export const toDay = (iso) => Math.floor(Date.parse(`${formatDate(iso)}T00:00:00Z`) / DAY_MS);

/** days since 1970-01-01 → "2026-08-20" */
export const fromDay = (day) => new Date(day * DAY_MS).toISOString().slice(0, 10);

const yearOf = (day) => new Date(day * DAY_MS).getUTCFullYear();
const yearStart = (year) => Date.UTC(year, 0, 1) / DAY_MS;

export const laneWord = (lane) => t(`timeline.lane.${lane}`);

/**
 * Where a period ends, in days: its end date; today while it is ongoing; null when it is over but
 * its end was never recorded (it must not be drawn as running to today).
 */
export function periodEnd(period, today) {
  if (period.end) return toDay(period.end);
  return period.ongoing ? today : null;
}

/** A period that is over, with no end date: drawn as a short faded stub, said in words. */
export const isUndatedEnd = (period) => !period.end && !period.ongoing;

/**
 * Rows for one lane's periods: a bar goes into the first row where it doesn't overlap the one
 * before it, so overlapping courses (two medications at once) sit one above the other.
 * → [[period, …], …]; an ongoing period runs to `today`, one with no recorded end only covers
 * its start day.
 */
export function packRows(periods, today) {
  const rows = [];
  const ends = [];
  const sorted = [...periods].sort((a, b) => toDay(a.start) - toDay(b.start) || a.title.localeCompare(b.title));
  for (const period of sorted) {
    const start = toDay(period.start);
    const end = periodEnd(period, today) ?? start;
    let row = ends.findIndex((last) => last < start);
    if (row === -1) {
      row = rows.length;
      rows.push([]);
    }
    rows[row].push(period);
    ends[row] = end;
  }
  return rows;
}

/** The lanes that have something, in LANES order: { id, events, rows } (rows: packed periods). */
export function lanesOf(data, hidden = new Set()) {
  const today = toDay(data.today);
  return LANES.filter((id) => !hidden.has(id)).map((id) => ({
    id,
    events: data.events.filter((event) => event.lane === id),
    rows: packRows(data.periods.filter((period) => period.lane === id), today),
  })).filter((lane) => lane.events.length || lane.rows.length);
}

/** Every lane with something in it, hidden or not: the legend's toggles. */
export const presentLanes = (data) => lanesOf(data).map((lane) => lane.id);

/**
 * The whole record: from the first event or period to today (or to the latest record, if one is
 * dated later: a planned visit, a discharge), with a little room at both ends so a mark on the
 * edge isn't cut in half. { from, to } in days.
 */
export function fullRange(data) {
  const today = toDay(data.today);
  const starts = [...data.events.map((event) => toDay(event.date)), ...data.periods.map((period) => toDay(period.start))];
  const ends = [...data.events.filter((event) => event.end).map((event) => toDay(event.end)),
    ...data.periods.filter((period) => period.end).map((period) => toDay(period.end))];
  const first = starts.length ? Math.min(...starts) : today - YEAR;
  const last = Math.max(today, ...starts, ...ends);
  const span = Math.max(last - first, MIN_SPAN_DAYS);
  // a little room at the start; at the end only enough for the last mark and an arrow
  return { from: first - Math.round(span * 0.02) - 7, to: last + Math.round(span * 0.01) + 7 };
}

const clampRange = ({ from, to }, bounds) => {
  const span = Math.min(to - from, bounds.to - bounds.from);
  const start = Math.min(Math.max(from, bounds.from), bounds.to - span);
  return { from: Math.round(start), to: Math.round(start + span) };
};

/** Zoom by `factor` (< 1 zooms in) around `center` (default: the middle), kept inside bounds. */
export function zoomRange(range, factor, bounds, center = (range.from + range.to) / 2) {
  const span = Math.min(Math.max((range.to - range.from) * factor, MIN_SPAN_DAYS), bounds.to - bounds.from);
  const share = (center - range.from) / (range.to - range.from || 1);
  return clampRange({ from: center - span * share, to: center - span * share + span }, bounds);
}

/** Move by `share` of the visible span (negative: earlier), kept inside bounds. */
export function panRange(range, share, bounds) {
  const shift = (range.to - range.from) * share;
  return clampRange({ from: range.from + shift, to: range.to + shift }, bounds);
}

/** One calendar year, with a fortnight either side so its first and last events show whole. */
export const yearRange = (year) => ({ from: yearStart(year) - 14, to: yearStart(year + 1) + 14 });

export const canZoomIn = (range) => range.to - range.from > MIN_SPAN_DAYS;
export const isWhole = (range, bounds) => range.from <= bounds.from && range.to >= bounds.to;

/** x of a day inside [0, width]. */
export const scaleX = (range, width) => (day) => ((day - range.from) / (range.to - range.from)) * width;

const MONTH_STEPS = [1, 2, 3, 6];
const YEAR_STEPS = [1, 2, 5, 10, 20, 25, 50];

/**
 * Axis ticks for the range, about one per `minGap` pixels: years for a wide range, months for a
 * narrow one (a month tick on January says the year). → [{ day, label, major }]
 */
export function ticks(range, width, minGap = 70) {
  const span = range.to - range.from;
  const fit = Math.max(1, Math.floor(width / minGap));
  const out = [];
  if (span >= MONTHS_BELOW_DAYS) {
    const step = YEAR_STEPS.find((s) => span / YEAR / s <= fit) ?? 100;
    for (let year = Math.ceil(yearOf(range.from) / step) * step; yearStart(year) <= range.to; year += step) {
      const day = yearStart(year);
      if (day >= range.from) out.push({ day, label: String(year), major: true });
    }
    return out;
  }
  const step = MONTH_STEPS.find((s) => span / 30.44 / s <= fit) ?? 12;
  const first = new Date(range.from * DAY_MS);
  let year = first.getUTCFullYear();
  let month = Math.ceil(first.getUTCMonth() / step) * step;
  for (;;) {
    if (month >= 12) {
      year += Math.floor(month / 12);
      month %= 12;
    }
    const day = Date.UTC(year, month, 1) / DAY_MS;
    if (day > range.to) break;
    if (day >= range.from) {
      out.push({ day, label: month === 0 ? String(year) : t(`timeline.month.${month + 1}`), major: month === 0 });
    }
    month += step;
  }
  return out;
}

/**
 * The "life in years" strip: one cell per year from the year of birth (or the first record, if
 * there is no birth date or the record is older) to this year, with how much happened in it.
 * level 0–4 is the shade; the count says it in words too.
 */
export function yearCells(data) {
  const today = toDay(data.today);
  const days = [
    ...data.events.map((event) => toDay(event.date)),
    ...data.periods.map((period) => toDay(period.start)),
    ...data.periods.filter((period) => period.end).map((period) => toDay(period.end)),
  ];
  const lastYear = yearOf(today);
  const firstRecord = days.length ? yearOf(Math.min(...days)) : lastYear;
  const firstYear = data.born ? Math.min(yearOf(toDay(data.born)), firstRecord) : firstRecord;
  const counts = new Map();
  for (const day of days) counts.set(yearOf(day), (counts.get(yearOf(day)) ?? 0) + 1);
  const max = Math.max(1, ...counts.values());
  const cells = [];
  for (let year = firstYear; year <= lastYear; year += 1) {
    const n = counts.get(year) ?? 0;
    // ongoing periods are "in" every year they span: the strip shows them as a quiet underline
    const ongoing = data.periods.some((period) => {
      const start = yearOf(toDay(period.start));
      const end = yearOf(periodEnd(period, today) ?? toDay(period.start));
      return start <= year && year <= end;
    });
    cells.push({ year, n, level: n ? Math.min(4, Math.ceil((n / max) * 4)) : 0, ongoing,
      age: data.born ? year - yearOf(toDay(data.born)) : null });
  }
  return cells;
}

export function yearCellLabel({ year, n, age }) {
  const what = tn("timeline.year.events", { n });
  return age === null ? `${year}: ${what}` : `${year} (${t("timeline.year.age", { age })}): ${what}`;
}

export const kindWord = (kind) => t(`timeline.kind.${kind}`);

/** A lab panel with a value still under review must not read as a finished result. */
export const isPendingEvent = (event) => event.kind === "panel" && event.pending > 0;

/** Not believed any more: drawn hollow and struck through, said in words. */
export const isRefuted = (event) => event.kind === "diagnosis" && event.verification === "refuted";

/** Not confirmed (provisional, differential, suspected, or not recorded): drawn dashed, never
 * like a confirmed diagnosis. */
export const isUncertain = (event) => event.kind === "diagnosis" && event.verification !== "confirmed" && !isRefuted(event);

/** A stored value's word, or the value itself (underscores as spaces): never a raw key. */
function word(group, stored) {
  const key = `timeline.${group}.${stored}`;
  const found = t(key);
  return found === key ? String(stored).replaceAll("_", " ") : found;
}

/** The details under an event's title: plain facts from its own record. */
export function eventDetails(event) {
  switch (event.kind) {
    case "diagnosis":
      return [
        event.icd10,
        word("verification", event.verification ?? "unknown"),
        // a refuted diagnosis is no longer anything clinically, whatever status it was left with
        !isRefuted(event) && event.clinical && word("clinical", event.clinical),
      ].filter(Boolean);
    case "panel":
      return [
        event.facility,
        tn("timeline.panel.values", { n: event.values }),
        event.out_of_range > 0 && tn("timeline.panel.out", { n: event.out_of_range }),
        event.pending > 0 && tn("timeline.panel.pending", { n: event.pending }),
      ].filter(Boolean);
    case "vaccination":
      return [event.disease, event.dose_number && t("timeline.vaccination.dose", { n: event.dose_number }), event.facility].filter(Boolean);
    case "hospital":
      return [event.end && t("timeline.until", { date: formatDate(event.end) }), event.facility].filter(Boolean);
    case "procedure":
      return [event.procedure_type, event.facility].filter(Boolean);
    default:
      return [event.facility].filter(Boolean);
  }
}

/** The title an event shows; a panel or visit without one is named by its kind. */
export const eventTitle = (event) => event.title || kindWord(event.kind);

/** What a screen reader hears for a mark: "Lab panel, 2026-08-20: Demo Lab · 6 values · 2 awaiting review" */
export function eventLabel(event) {
  const kind = kindWord(event.kind);
  const title = eventTitle(event);
  return `${kind}, ${formatDate(event.date)}: ${[title !== kind && title, ...eventDetails(event)].filter(Boolean).join(" · ")}`;
}

/** "2017-11-25 → today", "2022-11-25 → 2023-05-27" or "2004-11-24 → end not recorded" */
export function periodDates(period) {
  return `${formatDate(period.start)} → ${periodEndText(period)}`;
}

const periodEndText = (period) => {
  if (period.end) return formatDate(period.end);
  return t(period.ongoing ? "timeline.today" : "timeline.end_not_recorded");
};

export function periodDetails(period) {
  const stopped = period.kind === "medication" && !period.ongoing && period.status !== "taking";
  return [
    period.detail,
    period.kind === "habit" && t(`timeline.habit.${period.status}`),
    stopped && (period.stop_reason ? t("timeline.stopped_because", { reason: period.stop_reason }) : t("timeline.stopped")),
  ].filter(Boolean);
}

export function periodLabel(period) {
  return `${kindWord(period.kind)}: ${period.title}, ${periodDates(period)}${periodDetails(period).length ? ` · ${periodDetails(period).join(" · ")}` : ""}`;
}

/** The markers a panel links to: only those with an approved value in it. */
export const panelLinks = (event) => (event.markers ?? []).map(({ code, name }) => ({ code, name, href: `#/labs/${encodeURIComponent(code)}` }));

/** The table under the chart: every event and period, oldest first — the chart's text twin. */
export function tableRows(data) {
  return [
    ...data.events.map((event) => ({
      date: formatDate(event.date), end: event.end ? formatDate(event.end) : "", lane: laneWord(event.lane),
      kind: kindWord(event.kind), title: eventTitle(event), details: eventDetails(event).join(" · "),
      pending: isPendingEvent(event),
    })),
    ...data.periods.map((period) => ({
      date: formatDate(period.start), end: periodEndText(period),
      lane: laneWord(period.lane), kind: kindWord(period.kind), title: period.title,
      details: periodDetails(period).join(" · "), pending: false,
    })),
  ].sort((a, b) => a.date.localeCompare(b.date) || a.title.localeCompare(b.title));
}

/** "Showing 2012-11-10 to 2026-12-15": what the chart shows now, for its caption. */
export const rangeText = (range) => t("timeline.showing", { from: fromDay(range.from), to: fromDay(range.to) });
