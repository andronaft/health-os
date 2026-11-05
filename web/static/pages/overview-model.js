// What the Overview page says, from what /api/v1/overview sends. Nothing here touches the page, so
// the wording can be tested without a browser (tests/web_ui.test.mjs).

import { formatDate } from "../components.js";
import { t } from "../strings.js";

/** A stored word's translation, or the word itself if it is not one the table knows. */
function word(group, stored) {
  const key = `overview.${group}.${stored}`;
  const found = t(key);
  return found === key ? stored : found;
}

export function profileLine({ age, sex, blood_type: blood, rh_factor: rh, height_cm: height }) {
  const type = blood && `${blood}${rh ? (rh.length === 1 ? rh : ` ${rh}`) : ""}`;
  return [
    age !== null && age !== undefined && t("overview.profile.age", { age }),
    sex && word("sex", sex),
    type && t("overview.profile.blood", { type }),
    height && t("overview.profile.height", { height }),
  ].filter(Boolean).join(" · ");
}

/** Which of date of birth and sex is missing, and what that breaks. Empty if neither. */
export function profileProblems({ missing }) {
  if (!missing.length) return [];
  return [
    ...missing.map((field) => t(`overview.profile.missing.${field}`)),
    t("overview.profile.breaks_screening"),
    t("overview.profile.breaks_ranges"),
  ];
}

export function allergyText({ allergen, reaction, verified }) {
  return [allergen, reaction, !verified && t("overview.allergy.unverified")].filter(Boolean).join(" — ");
}

export function diagnosisText({ diagnosis_name: name, icd10_code: icd, verification_status: status }) {
  const label = icd ? `${name} [${icd}]` : name;
  if (status === "confirmed") return label;
  const uncertain = word("verification", status ?? "unknown");
  return `${label} — ${t("overview.diagnosis.not_certain", { status: uncertain })}`;
}

export function medicationText({ medication_name: name, dose_amount: dose, dose_unit: unit, times_per_day: times, product_type: type }) {
  return [
    name,
    dose !== null && dose !== undefined && [dose, unit].filter(Boolean).join(" "),
    times && t("overview.medication.per_day", { n: times }),
    type !== "prescription" && `(${word("product", type)})`,
  ].filter(Boolean).join(" ");
}

export function habitText({ habit_type: type, status, frequency, start_date: start, end_date: end }) {
  const parts = [
    word("habit", status),
    frequency,
    start && t("overview.habit.since", { date: formatDate(start) }),
    end && t("overview.habit.until", { date: formatDate(end) }),
  ];
  return `${type} — ${parts.filter(Boolean).join(", ")}`;
}

/** "N of M recorded markers in range", and what the rest are, so M - N doesn't read as all bad. */
export function coverageLines(coverage) {
  if (!coverage.recorded) return { sentence: t("overview.coverage.none"), rest: [] };
  return {
    sentence: t("overview.coverage.sentence", coverage),
    rest: [
      t("overview.coverage.out", { n: coverage.out_of_range }),
      t("overview.coverage.no_range", { n: coverage.no_range }),
    ],
  };
}

export function lastPanelText({ last_panel: date, last_panel_pending: pending }) {
  if (!date) return t("overview.coverage.no_panel");
  return t(pending ? "overview.coverage.last_panel_pending" : "overview.coverage.last_panel", { date: formatDate(date) });
}

export function pendingNote({ critical, unverifiable, unmapped }) {
  if (critical) return t("overview.pending.flag_critical");
  if (unverifiable) return t("overview.pending.flag_unverifiable");
  return unmapped ? t("overview.pending.flag_unmapped") : "";
}

/** A row's name; a marker the system doesn't recognize keeps its wording from the form, in quotes. */
export const pendingName = (row) => (row.unmapped ? `“${row.raw_name}”` : row.name);

export function staleText({ name, last, months }) {
  return last
    ? t("overview.stale.last", { name, date: formatDate(last), months })
    : t("overview.stale.never", { name });
}

export const kindWord = (kind) => word("kind", kind);

// an average's decimals would be false precision: blood pressure is read in whole mmHg
const tileNumber = (tile, value) => String(tile.average_days ? Math.round(value) : value);

/** "133/85" */
export const tileHeadline = (tile) => tile.values.map(({ value }) => tileNumber(tile, value)).join("/");

export function tileNote(tile) {
  if (tile.average_days) return t("overview.tile.average", { days: tile.average_days, n: tile.readings });
  return tile.series.length ? t("overview.tile.latest") : "";
}

export const tileAsOf = (tile) => t("overview.tile.as_of", { date: formatDate(tile.at) });

/** For a tile with nothing in the window: when there last was a value, if ever. */
export function tileEmptyLines(tile, days) {
  const lines = [t("overview.tile.empty", { days })];
  const old = tile.last_recorded;
  if (old) {
    const value = [old.values.join("/"), old.unit].filter(Boolean).join(" ");
    lines.push(t("overview.tile.last_recorded", { value, date: formatDate(old.at) }));
  }
  return lines;
}

export function chartLabel(tile, name, days) {
  const [{ points }] = tile.series;
  return t("overview.tile.chart", {
    name,
    days,
    n: points.length,
    first: formatDate(points[0].at),
    last: formatDate(points.at(-1).at),
  });
}

/** What the readout says with the pointer at this time: each series' nearest point. */
export function readoutAt(tile, time) {
  const nearest = tile.series.map(({ points }) => points.reduce((best, point) =>
    (Math.abs(Date.parse(point.at) - time) < Math.abs(Date.parse(best.at) - time) ? point : best)));
  const value = nearest.map((point) => tileNumber(tile, point.value)).join("/");
  return t("overview.tile.point", {
    date: formatDate(nearest[0].at),
    value: [value, tile.unit].filter(Boolean).join(" "),
  });
}

const FEW_POINTS = 8; // with fewer, every point gets a dot: a line alone would suggest a steady record

/**
 * The tile's chart: no axes, one 2px line per series and a dot on the last point, over the whole
 * window, so that two weeks of readings fill half of it. The tooltip paints on the chart's own
 * canvas, far too small for it here, so hovering only moves the pointer; the tile's readout says
 * the values.
 */
export function sparklineOption(tile, { from, to }) {
  return {
    animation: false,
    grid: { left: 6, right: 6, top: 6, bottom: 6 },
    xAxis: { type: "time", min: Date.parse(from), max: Date.parse(to), show: false },
    yAxis: { type: "value", min: "dataMin", max: "dataMax", show: false },
    tooltip: { trigger: "axis", showContent: false },
    series: tile.series.map(({ name, points }) => ({
      type: "line",
      name,
      symbolSize: 8,
      lineStyle: { width: 2 },
      data: points.map(({ at, value }, i) => ({
        value: [Date.parse(at), value],
        symbol: points.length < FEW_POINTS || i === points.length - 1 ? "circle" : "none",
      })),
    })),
  };
}
