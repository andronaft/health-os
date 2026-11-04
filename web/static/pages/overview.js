// The home page: what needs attention and the latest picture. Critical values come first, above
// everything: they must never be something the user scrolls to.

import { api } from "../api.js";
import { dataTable, el, formatDate, formatRange, formatValue, statusPill } from "../components.js";
import { LANG, t } from "../strings.js";
import {
  allergyText, chartLabel, coverageLines, diagnosisText, habitText, kindWord, lastPanelText,
  medicationText, pendingName, pendingNote, profileLine, profileProblems, readoutAt, sparklineOption,
  staleText, tileAsOf, tileEmptyLines, tileHeadline, tileNote,
} from "./overview-model.js";

const FILTER_ABOVE = 8; // rows; a filter box over a shorter list is only in the way

const section = (title, ...children) =>
  el("section", { class: "overview-section" }, el("h2", {}, title), ...children);

const quiet = (text) => el("p", { class: "quiet" }, text);

function criticalRow(row) {
  return el("li", { class: "critical-row" },
    el("p", { class: "critical-value" },
      el("strong", { class: row.pending ? "value-pending" : null }, `${row.name} ${formatValue(row)}`),
      " · ",
      el("span", { class: "nowrap" }, formatDate(row.at)),
      " ",
      !row.unverifiable && statusPill("critical"),
      row.pending && statusPill("pending")),
    row.message && el("p", {}, row.message),
    row.unverifiable && el("p", {}, t("overview.critical.unverifiable")),
    row.pending && !row.unverifiable && el("p", {}, t("overview.critical.pending")));
}

function criticalSection({ critical, disclaimer }) {
  if (!critical.length) return null;
  return el("section", { class: "critical", role: "alert" },
    el("h2", {}, el("span", { class: "state-icon", "aria-hidden": "true" }, "!"), t("overview.critical.title")),
    el("ul", {}, ...critical.map(criticalRow)),
    el("p", { class: "critical-disclaimer" }, disclaimer));
}

function factList(label, items, none, toText) {
  return [
    el("dt", {}, t(label, { n: items.length })),
    ...(items.length ? items.map((item) => el("dd", {}, toText(item))) : [el("dd", { class: "quiet" }, t(none))]),
  ];
}

function profileCard(data) {
  const problems = profileProblems(data.profile);
  const line = profileLine(data.profile);
  return el("section", { class: "card" },
    el("h2", {}, t("overview.profile.title")),
    line && el("p", { class: "profile-line" }, line),
    problems.length > 0 && el("div", { class: "profile-problem" },
      el("p", { class: "state-title" }, t("overview.profile.not_filled")),
      el("ul", {}, ...problems.map((text) => el("li", {}, text))),
      el("p", {}, t("overview.profile.fix"))),
    el("dl", { class: "facts" },
      ...factList("overview.list.allergies", data.allergies, "overview.list.allergies_none", allergyText),
      ...factList("overview.list.diagnoses", data.diagnoses, "overview.list.diagnoses_none", diagnosisText),
      ...factList("overview.list.medications", data.medications, "overview.list.medications_none", medicationText),
      ...factList("overview.list.habits", data.habits, "overview.list.habits_none", habitText)));
}

function coverageCard({ coverage }) {
  const { sentence, rest } = coverageLines(coverage);
  return el("section", { class: "card" },
    el("h2", {}, t("overview.coverage.title")),
    el("p", { class: "figure" }, sentence),
    rest.length > 0 && el("ul", { class: "plain" }, ...rest.map((text) => el("li", {}, text))),
    el("p", { class: "quiet" }, t("overview.coverage.note")),
    el("p", {}, lastPanelText(coverage)));
}

function pendingPart({ total, rows }) {
  const heading = el("h3", {}, t("overview.pending.title", { n: total }));
  if (!total) return [heading, quiet(t("overview.pending.none"))];
  const table = dataTable({
    caption: t("overview.caption.pending"),
    rows,
    pending: () => true,
    filterable: rows.length > FILTER_ABOVE,
    columns: [
      { key: "name", label: t("overview.col.marker"), value: pendingName },
      {
        key: "value",
        label: t("overview.col.value"),
        numeric: true,
        render: (row) => el("span", { class: "value-pending" }, formatValue(row)),
        text: formatValue,
      },
      { key: "status", label: t("overview.col.status"), sortable: false, value: () => t("status.pending"), render: () => statusPill("pending") },
      { key: "at", label: t("overview.col.date"), render: (row) => formatDate(row.at) },
      { key: "note", label: t("overview.col.note"), wrap: true, value: pendingNote },
    ],
  });
  return [
    heading,
    quiet(t("overview.pending.note")),
    table.element,
    el("p", {},
      rows.length < total && `${t("overview.pending.more", { shown: rows.length, total })} `,
      el("a", { href: "#/review" }, t("overview.pending.queue"))),
  ];
}

function outOfRangePart(rows, { in_range: inRange }) {
  const heading = el("h3", {}, t("overview.out.title", { n: rows.length }));
  if (!rows.length) {
    return [heading, quiet(inRange ? t("overview.out.none", { n: inRange }) : t("overview.out.no_ranges"))];
  }
  const table = dataTable({
    caption: t("overview.caption.out"),
    rows,
    sort: { key: "at", direction: "desc" },
    filterable: rows.length > FILTER_ABOVE,
    columns: [
      { key: "name", label: t("overview.col.marker") },
      { key: "value", label: t("overview.col.value"), numeric: true, render: formatValue, text: formatValue },
      { key: "status", label: t("overview.col.status"), render: (row) => statusPill(row.status) },
      { key: "range", label: t("overview.col.range"), value: formatRange, sortable: false },
      { key: "at", label: t("overview.col.date"), render: (row) => formatDate(row.at) },
    ],
  });
  return [heading, table.element];
}

const screeningName = ({ code, label }) => {
  const key = `overview.screening.code.${code}`;
  const name = t(key);
  return name === key ? label : name; // a rule added later still shows, if only in English
};

function screeningPart({ available, overdue, no_record: noRecord }) {
  // without a calendar there is no count: a 0 here would read as "none overdue"
  if (!available) return [el("h3", {}, t("overview.screening.title_unknown")), quiet(t("overview.screening.unavailable"))];
  return [
    el("h3", {}, t("overview.screening.title", { n: overdue.length })),
    overdue.length
      ? el("ul", { class: "plain" }, ...overdue.map((row) =>
        el("li", {}, `${screeningName(row)}: ${t("overview.screening.last_done", { date: formatDate(row.last_done) })}`)))
      : quiet(t("overview.screening.none")),
    noRecord.length > 0 && el("details", {},
      el("summary", {}, t("overview.screening.no_record", { n: noRecord.length })),
      el("ul", { class: "plain" }, ...noRecord.map((row) => el("li", {}, screeningName(row))))),
  ];
}

function notCheckedPart({ months, watched, rows }) {
  return [
    el("h3", {}, t("overview.stale.title", { months, n: rows.length })),
    rows.length
      ? el("ul", { class: "plain" }, ...rows.map((row) => el("li", {}, staleText(row))))
      : quiet(t("overview.stale.none", { watched, months })),
  ];
}

function attentionSection({ attention, coverage }) {
  return section(t("overview.attention.title"),
    ...pendingPart(attention.pending),
    ...outOfRangePart(attention.out_of_range, coverage),
    ...screeningPart(attention.screening),
    ...notCheckedPart(attention.not_checked));
}

function tile(data, days, chartsToDraw) {
  const name = t(`overview.tile.${data.id}`);
  const title = el("h3", {}, name);
  if (!data.series.length) {
    return el("article", { class: "tile" }, title,
      ...tileEmptyLines(data, days).map((line) => quiet(line)));
  }
  const asOf = tileAsOf(data);
  const readout = el("p", { class: "quiet tile-readout" }, asOf);
  const chart = el("div", { class: "sparkline" });
  chartsToDraw.push({ tile: data, chart, readout, asOf, label: chartLabel(data, name, days) });
  const [{ status }] = data.values;
  return el("article", { class: "tile" }, title,
    el("p", { class: "tile-value" },
      el("strong", {}, tileHeadline(data)),
      data.unit && ` ${data.unit}`,
      status && " ",
      status && statusPill(status)),
    el("p", { class: "quiet" }, tileNote(data)),
    chart,
    data.series.length > 1 && el("p", { class: "tile-key" }, ...data.series.map((series, i) =>
      el("span", { class: `key-${i + 1}` }, series.name))),
    readout);
}

async function drawSparklines(charts, window) {
  if (!charts.length) return;
  const { drawChart } = await import("../chart.js"); // 1 MB: only when there is something to draw
  await Promise.all(charts.map(async ({ tile: data, chart, readout, asOf, label }) => {
    const instance = await drawChart(chart, sparklineOption(data, window), { label });
    instance?.on("updateAxisPointer", ({ axesInfo: [axis] }) => {
      if (axis) readout.textContent = readoutAt(data, axis.value);
    });
    instance?.on("globalout", () => {
      readout.textContent = asOf;
    });
  }));
}

function tilesSection({ tiles, window: { days } }, charts) {
  return section(t("overview.tiles.title", { days }),
    el("div", { class: "tiles" }, ...tiles.map((item) => tile(item, days, charts))),
    quiet(t("overview.tiles.note")));
}

function eventsSection({ events }) {
  const table = dataTable({
    caption: t("overview.caption.events"),
    rows: events,
    pending: (row) => row.pending,
    filterable: false,
    columns: [
      { key: "date", label: t("overview.col.date") },
      { key: "kind", label: t("overview.col.event"), value: (row) => kindWord(row.kind) },
      {
        key: "title",
        label: t("overview.col.details"),
        wrap: true,
        render: (row) => (row.pending ? el("span", {}, row.title ?? "", row.title ? " " : "", statusPill("pending")) : row.title),
      },
    ],
  });
  return section(t("overview.events.title"), table.element);
}

export async function render(view) {
  const data = await api(`overview?lang=${LANG}`);
  const charts = [];
  view.replaceChildren(el("div", { class: "overview" },
    criticalSection(data.attention),
    el("div", { class: "overview-top" }, profileCard(data), coverageCard(data)),
    attentionSection(data),
    tilesSection(data, charts),
    eventsSection(data)));
  await drawSparklines(charts, data.window);
}
