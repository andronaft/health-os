// Where a value sits against its reference range (#64): below, inside, above — or that it can't be
// told. Pure: tests/web_ui.test.mjs runs it without a browser; range-bar.js draws it.
//
// The value and the range are the form's own, in the form's unit: a bar never mixes units.
// The track spans the range plus half of it on each side; a value past the margin is drawn at the
// edge with an arrow ("clamped"), so a value 10× the limit doesn't squash the range to a line.
// A limit (">600") is drawn at the limit with an arrow the way it points; it is "above" only when
// the limit itself is past the range, and "unknown" when the true value could be either side.

import { formatRange, formatValue } from "../components.js";
import { t } from "../strings.js";

const has = (n) => typeof n === "number" && Number.isFinite(n);
const ABOVE = new Set([">", ">="]);
const BELOW = new Set(["<", "<="]);

// where the range's limits sit on the track, in % of its width
export const BAND_FROM = 25;
export const BAND_TO = 75;

/**
 * Where a value (or a limit) sits: "below" | "inside" | "above" | "unknown". Mirrors
 * core.normalize.compute_limit_status: a limit decides only when it is past the range on its side.
 */
export function rangePosition(value, comparator, low, high) {
  if (!has(value) || (!has(low) && !has(high))) return "unknown";
  if (ABOVE.has(comparator)) {
    // ">600" with a range up to 500 is above; with a range up to 1000 it may be either
    if (has(high) && (comparator === ">" ? value >= high : value > high)) return "above";
    if (!has(high) && has(low) && value >= low) return "inside";
    return "unknown";
  }
  if (BELOW.has(comparator)) {
    // "0–5": a concentration can't be below 0, so "<0.5" is in range
    const floor = has(low) && low > 0 ? low : null;
    if (floor !== null && (comparator === "<" ? value <= floor : value < floor)) return "below";
    if (floor === null && (!has(high) || value <= high)) return "inside";
    return "unknown";
  }
  if (has(low) && value < low) return "below";
  if (has(high) && value > high) return "above";
  return "inside";
}

/**
 * The track's [start, end] for a range. Both limits: the range in the middle half. One limit:
 * the open side runs to the track's edge — "≤ 5.2" fills from 0 when the limit is positive.
 */
export function trackDomain(low, high) {
  if (has(low) && has(high) && high > low) {
    const margin = (high - low) / 2; // the range is the middle half: BAND_FROM–BAND_TO
    return [low - margin, high + margin];
  }
  if (has(low) && has(high)) {
    // a range of one point: give it a width of its own size
    const span = Math.abs(low) || 1;
    return [low - span, low + span];
  }
  if (has(high)) {
    if (high > 0) return [0, high / (BAND_TO / 100)];
    const span = Math.abs(high) || 1;
    return [high - 3 * span, high + span];
  }
  const span = Math.abs(low) || 1;
  return [low - span, low + 3 * span];
}

const percent = (n, [start, end]) => ((n - start) / (end - start)) * 100;
const round = (n) => Math.round(n * 10) / 10;

/**
 * What the bar draws and says, from { value, comparator, text, unit, ref_min, ref_max }:
 *   { kind: "none" }  — no range on the form, or no number (a result in words): no bar
 *   { kind: "bar", position, at, clamped, band: {from, to, openLow, openHigh}, limit, label }
 * `at` is the marker's place in % (0–100); `clamped` is "low"/"high" when the value is off the
 * track; `limit` is the comparator of a limit value. `label` is the text equivalent.
 */
export function rangeBar({ value, comparator = null, text = null, unit = null, ref_min: low, ref_max: high }) {
  if (!has(value) || (!has(low) && !has(high))) {
    return { kind: "none", label: has(value) ? t("range.none") : "" };
  }
  const domain = trackDomain(low, high);
  const raw = percent(value, domain);
  const clamped = raw < 0 ? "low" : raw > 100 ? "high" : null;
  const position = rangePosition(value, comparator, low, high);
  const band = {
    from: has(low) ? round(Math.max(0, percent(low, domain))) : 0,
    to: has(high) ? round(Math.min(100, percent(high, domain))) : 100,
    openLow: !has(low),
    openHigh: !has(high),
  };
  const shown = formatValue({ value, comparator, text, unit });
  const range = formatRange({ ref_min: low, ref_max: high });
  const key = comparator ? `range.limit.${position}` : `range.${position}`;
  return {
    kind: "bar",
    position,
    at: round(Math.min(100, Math.max(0, raw))),
    clamped,
    band,
    limit: comparator || null,
    label: t(key, { value: shown, range: unit ? `${range} ${unit}` : range })
      + (clamped ? ` ${t(`range.far_${clamped}`)}` : ""),
  };
}
