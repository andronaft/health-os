// The range bar (#64): a small inline bar with the reference range as a band and the value as a
// mark. Plain DOM and CSS (styles.css, "the range bar"); what it says is range-model.js's.
// Positions are set through the CSSOM (node.style.left): the CSP blocks a style attribute, not
// that.

import { el } from "../components.js";
import { t } from "../strings.js";
import { rangeBar } from "./range-model.js";

/**
 * The bar for a value with its form's range; "" when there is nothing to draw. A pending value's
 * mark is hollow and dashed, like every pending value: it is not a fact yet.
 */
export function rangeBarElement(row, { wide = false, pending = false } = {}) {
  const bar = rangeBar(row);
  if (bar.kind !== "bar") return "";
  const band = el("span", {
    class: "range-bar-band",
    "data-open-low": bar.band.openLow,
    "data-open-high": bar.band.openHigh,
  });
  band.style.left = `${bar.band.from}%`;
  band.style.width = `${Math.max(0, bar.band.to - bar.band.from)}%`;
  const mark = el("span", {
    class: "range-bar-mark",
    "data-clamped": bar.clamped,
    "data-limit": bar.limit && (bar.limit.startsWith(">") ? "above" : "below"),
  });
  mark.style.left = `${bar.at}%`;
  return el("span", {
    class: wide ? "range-bar range-bar-wide" : "range-bar",
    "data-position": bar.position,
    "data-pending": pending,
    role: "img",
    "aria-label": pending ? `${bar.label} (${t("status.pending")})` : bar.label,
    title: pending ? `${bar.label} (${t("status.pending")})` : bar.label,
  }, el("span", { class: "range-bar-track", "aria-hidden": "true" }, band, mark));
}
