// What the "where does this value come from" drawer says, from /api/v1/observations/<id>. Pure, so
// tests/web_ui.test.mjs runs it without a browser; observation.js builds the drawer from it.

import { formatDate, formatRange, formatValue } from "../components.js";
import { t } from "../strings.js";

const has = (n) => n !== null && n !== undefined;
const number = (n) => String(Number(n.toPrecision(6)));

/** The printed value as on the form: "<5 mg/L", "negative". */
export const printedText = (data) => formatValue(data.printed);

/**
 * What became of the printed number, said as it is. Never "converted" without a stored canonical
 * value, never a factor that isn't in the conversion table.
 */
export function conversionText({ canonical, printed }) {
  const unit = canonical.unit ?? "";
  switch (canonical.state) {
    case "text":
      return t("obs.conv.text");
    case "no_canonical_unit":
      return t("obs.conv.no_unit");
    case "not_converted":
      return t("obs.conv.not_converted", { unit: printed.unit || t("obs.no_unit"), to: unit || "—" });
    case "same_unit":
      return t("obs.conv.same", { value: `${printed.comparator ?? ""}${number(canonical.value)}`, unit });
    case "converted": {
      const value = `${printed.comparator ?? ""}${number(canonical.value)}`;
      if (!has(canonical.factor)) return t("obs.conv.converted", { value, unit, from: printed.unit ?? "" });
      const how = has(canonical.offset)
        ? t("obs.conv.factor_offset", { factor: number(canonical.factor), offset: number(canonical.offset) })
        : t("obs.conv.factor", { factor: number(canonical.factor) });
      return `${t("obs.conv.converted", { value, unit, from: printed.unit ?? "" })} ${how}`;
    }
    default:
      return t("obs.conv.not_converted", { unit: printed.unit || t("obs.no_unit"), to: unit || "—" });
  }
}

/** The range and where it came from: the form, or none on it. */
export function rangeText({ range }) {
  if (range.source !== "form") return t("obs.range.none");
  const shown = formatRange({ ref_min: range.min, ref_max: range.max });
  return t("obs.range.form", { range: range.unit ? `${shown} ${range.unit}` : shown });
}

/** The same range in the canonical unit, when it differs from the form's; "" when there is none. */
export function canonicalRangeText({ range, canonical, printed }) {
  const band = range.canonical;
  if (!band || canonical.state !== "converted") return "";
  if (band.unconverted) return t("obs.range.canonical_unconverted", { unit: canonical.unit ?? "" });
  const shown = formatRange({ ref_min: band.min, ref_max: band.max });
  return printed.unit === canonical.unit ? "" : t("obs.range.canonical", { range: `${shown} ${canonical.unit}` });
}

/** A catalog default: "3.9–5.5 mmol/L · fasting · ADA 2023". Its source is shown verbatim. */
export function defaultRangeText(range) {
  const shown = formatRange({ ref_min: range.min, ref_max: range.max });
  const kind = range.kind && range.kind !== "population" ? t(`obs.range.kind.${range.kind}`) : null;
  return [`${shown} ${range.unit}`, kind, range.sex && t(`obs.range.sex.${range.sex}`),
    range.condition, range.source].filter(Boolean).join(" · ");
}

/** The review lines: status, how it came in, when it was staged and reviewed. */
export function reviewLines({ review, pending }) {
  const lines = [];
  const statusKey = `obs.review.status.${review.status}`;
  const word = t(statusKey);
  lines.push(t("obs.review.status", { status: word === statusKey ? review.status : word }));
  if (review.channel) {
    const channelKey = `obs.review.channel.${review.channel}`;
    const channel = t(channelKey);
    lines.push(t("obs.review.channel", { channel: channel === channelKey ? review.channel : channel }));
  }
  if (review.staged_at) lines.push(t("obs.review.staged", { date: formatDate(review.staged_at) }));
  if (pending) {
    lines.push(t("obs.review.not_yet"));
  } else if (review.reviewed_at) {
    const by = review.reviewed_by === "human" ? t("obs.review.by_you") : review.reviewed_by;
    lines.push(t("obs.review.reviewed", { date: formatDate(review.reviewed_at), by: by ?? "—" }));
  } else {
    lines.push(t("obs.review.no_review"));
  }
  return lines;
}

/** The source document's line, or that none is stored. */
export function documentText(doc) {
  if (!doc) return t("obs.doc.none");
  return [doc.title || t("obs.doc.untitled"), doc.date && formatDate(doc.date), doc.type]
    .filter(Boolean).join(" · ");
}

/** The panel's line: date, kind, lab, and how many rows the form had. */
export function panelText(panel) {
  const rows = has(panel.rows_in_document)
    ? t("obs.panel.rows", { n: panel.rows_in_document })
    : null;
  return [formatDate(panel.date), panel.type, panel.facility, rows].filter(Boolean).join(" · ");
}

/** The heading's date: a form's date has no time of day, so none is invented. */
export const atText = (data) => formatDate(data.at);
