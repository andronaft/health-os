// What the review queue page says, from what /api/v1/review sends. Nothing here touches the page,
// so it can be tested without a browser (tests/web_ui.test.mjs).

import { formatDate } from "../components.js";
import { t } from "../strings.js";
import { tn } from "./labs-model.js";

/** "Lab panel, 2026-08-20 · Demo Lab"; a staging without a panel says when it was staged. */
export function sourceTitle({ panel_date: date, panel_type: type, facility, document, staged_at: staged }) {
  const head = date
    ? t("review.source.panel", { type: type || t("review.source.lab_panel"), date: formatDate(date) })
    : t("review.source.staged", { date: formatDate(staged) });
  return [head, facility, document].filter(Boolean).join(" · ");
}

/** "3 values · 1 not recognized · 1 can't wait · staged 2026-11-18 via mcp" */
export function sourceMeta({ total, unmapped, alarming, staged_at: staged, channel }) {
  const parts = [tn("review.source.values", { n: total })];
  if (unmapped) parts.push(tn("review.source.unmapped", { n: unmapped }));
  if (alarming) parts.push(tn("review.source.alarming", { n: alarming }));
  if (staged) parts.push(t(channel ? "review.source.staged_via" : "review.source.staged_on", { date: formatDate(staged), channel }));
  return parts.join(" · ");
}

/** The name as printed on the form, when the marker it was matched to has another name. */
export const printedAs = ({ raw_name: raw, name, unmapped }) =>
  (raw && !unmapped && raw.trim().toLowerCase() !== name.trim().toLowerCase()
    ? t("review.printed_as", { name: raw })
    : "");
