// The review queue page (#58): every value awaiting review, by the staging it came in. None of it is
// a fact yet, so every row is drawn as pending. Read-only: approving and mapping stay with the MCP
// client, on the user's explicit instruction.

import { api } from "../api.js";
import { dataTable, el, emptyState, formatDate, formatRange, formatValue, statusPill } from "../components.js";
import { LANG, t } from "../strings.js";
import { tn } from "./labs-model.js";
import { pendingName, pendingNote } from "./overview-model.js";
import { printedAs, sourceMeta, sourceTitle } from "./review-model.js";

const FILTER_ABOVE = 8;
const quiet = (text) => el("p", { class: "quiet" }, text);

function markerCell(row) {
  const printed = printedAs(row);
  return printed ? el("span", {}, pendingName(row), el("br"), el("span", { class: "quiet" }, printed)) : pendingName(row);
}

function sourceSection(source) {
  const table = dataTable({
    caption: sourceTitle(source),
    rows: source.rows,
    pending: () => true,
    filterable: source.rows.length > FILTER_ABOVE,
    columns: [
      { key: "name", label: t("overview.col.marker"), value: pendingName, render: markerCell },
      {
        key: "value",
        label: t("overview.col.value"),
        numeric: true,
        render: (row) => el("span", { class: "value-pending" }, formatValue(row)),
        text: formatValue,
      },
      { key: "range", label: t("overview.col.range"), value: formatRange, sortable: false },
      { key: "status", label: t("overview.col.status"), sortable: false, value: () => t("status.pending"), render: () => statusPill("pending") },
      { key: "at", label: t("overview.col.date"), render: (row) => formatDate(row.at) },
      { key: "flag", label: t("overview.col.note"), wrap: true, value: pendingNote },
      // why a row came back to review, when it says: most rows have no notes
      source.rows.some((row) => row.notes) && { key: "notes", label: t("review.col.notes"), wrap: true, sortable: false },
    ].filter(Boolean),
  });
  return el("section", { class: "review-source" },
    el("h2", {}, sourceTitle(source)),
    quiet(sourceMeta(source)),
    el("p", { class: "quiet" }, t("review.source.id"), " ", el("code", {}, source.source_id)),
    table.element);
}

export async function render(view) {
  const data = await api(`review?lang=${LANG}`);
  if (!data.total) {
    view.replaceChildren(emptyState({ message: t("review.none") }));
    return;
  }
  view.replaceChildren(el("div", { class: "review" },
    el("p", { class: "labs-pending" }, statusPill("pending"), " ", tn("review.summary", { n: data.total })),
    quiet(t("review.note")),
    quiet(t("review.read_only")),
    data.alarming > 0 && el("p", { class: "review-alarming", role: "alert" },
      tn("review.alarming", { n: data.alarming }), " ",
      el("a", { href: "#/overview" }, t("review.alarming_link"))),
    ...data.sources.map(sourceSection)));
}
