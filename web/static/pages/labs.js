// The Labs page: #/labs is the marker table and the panel matrix; #/labs/<code> is one marker's
// history. Approved values are the facts; pending ones are drawn hollow and counted nowhere.

import { ApiError, api } from "../api.js";
import {
  dataTable, el, emptyState, errorState, formatDate, formatRange, formatValue, statusIcon, statusKey,
  statusPill, statusWord,
} from "../components.js";
import { LANG, t } from "../strings.js";
import {
  baselineText, cellText, chartLabel, detailOption, filterMarkers, historyText, isOutOfRange,
  qualitative, qualitativeOption, sparkLabel, sparkPoints, specimenOptions, specimenWord, tableRows,
  tn, trendLines, unconverted,
} from "./labs-model.js";

const SVG = "http://www.w3.org/2000/svg";
const SPARK = { width: 96, height: 24 };

const quiet = (text) => el("p", { class: "quiet" }, text);
const section = (title, ...children) =>
  el("section", { class: "labs-section" }, el("h2", {}, title), ...children);
const markerLink = (row) => el("a", { href: `#/labs/${encodeURIComponent(row.code)}` }, row.name);

function svg(tag, attributes = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  node.append(...children);
  return node;
}

/** Drawn as SVG, not with the chart library: a table of them would be dozens of canvases. */
function sparkline(marker) {
  const points = sparkPoints(marker.spark, SPARK.width, SPARK.height);
  if (!points.length) return "";
  const [lastX, lastY] = points.at(-1);
  return svg("svg", {
    class: "spark",
    viewBox: `0 0 ${SPARK.width} ${SPARK.height}`,
    width: SPARK.width,
    height: SPARK.height,
    role: "img",
    "aria-label": sparkLabel(marker),
  },
  points.length > 1 ? svg("polyline", { points: points.map((p) => p.join(",")).join(" ") }) : "",
  svg("circle", { cx: lastX, cy: lastY, r: 2.5 }));
}

function pendingNotice(total) {
  if (!total) return null;
  return el("p", { class: "labs-pending" },
    statusPill("pending"), " ",
    tn("labs.pending_note", { n: total }), " ",
    el("a", { href: "#/review" }, t("overview.pending.queue")));
}

function markerTable(markers) {
  const table = dataTable({
    caption: t("labs.caption.markers"),
    rows: markers,
    sort: { key: "specimen" },
    empty: emptyState({ message: t("labs.none_filtered") }),
    columns: [
      { key: "name", label: t("labs.col.marker"), render: markerLink },
      { key: "specimen", label: t("labs.col.specimen"), value: (row) => specimenWord(row.specimen) },
      { key: "value", label: t("labs.col.latest"), numeric: true, render: formatValue, text: formatValue },
      { key: "status", label: t("labs.col.status"), value: (row) => statusWord(row.status), render: (row) => statusPill(row.status) },
      { key: "range", label: t("overview.col.range"), value: formatRange, sortable: false },
      { key: "spark", label: t("labs.col.history"), sortable: false, value: () => "", render: sparkline },
      { key: "n", label: t("labs.col.values"), numeric: true, text: historyText, render: historyText },
      { key: "at", label: t("labs.col.date"), render: (row) => formatDate(row.at) },
      {
        key: "pending",
        label: t("labs.col.pending"),
        numeric: true,
        value: (row) => row.pending || null,
        render: (row) => (row.pending ? t("labs.pending_badge", { n: row.pending }) : ""),
      },
    ],
  });

  const outOnly = el("input", { type: "checkbox", onchange: update });
  const specimen = el("select", { onchange: update },
    el("option", { value: "" }, t("labs.filter.all")),
    ...specimenOptions(markers).map(({ code, label }) => el("option", { value: code }, label)));
  function update() {
    table.setRows(filterMarkers(markers, { outOfRangeOnly: outOnly.checked, specimen: specimen.value }));
  }
  const outCount = markers.filter(isOutOfRange).length;
  return el("div", {},
    el("div", { class: "labs-filters" },
      el("label", {}, outOnly, " ", t("labs.filter.out_only", { n: outCount })),
      el("label", {}, t("labs.filter.specimen"), " ", specimen)),
    table.element);
}

function matrixCell(cell) {
  if (!cell) return el("td", { class: "matrix-empty" }, el("span", { class: "visually-hidden" }, t("labs.matrix.no_value")));
  const key = statusKey(cell.status);
  return el("td", { class: "matrix-cell", "data-status": key },
    cellText(cell), " ",
    el("span", { "aria-hidden": "true" }, statusIcon(key)),
    el("span", { class: "visually-hidden" }, ` ${statusWord(key)}`));
}

function matrixSection({ dates, older_dates: older, rows }) {
  if (!rows.length) return null;
  return section(t("labs.matrix.title"),
    quiet(t("labs.matrix.note", { n: dates.length })),
    older > 0 && quiet(tn("labs.matrix.older", { n: older })),
    el("div", { class: "table-scroll", role: "region", "aria-label": t("labs.matrix.title"), tabindex: "0" },
      el("table", { class: "matrix" },
        el("caption", { class: "visually-hidden" }, t("labs.matrix.caption")),
        el("thead", {}, el("tr", {},
          el("th", { scope: "col" }, t("labs.col.marker")),
          ...dates.map((date) => el("th", { scope: "col", class: "num" }, formatDate(date))))),
        el("tbody", {}, ...rows.map((row) => el("tr", {},
          el("th", { scope: "row" }, markerLink(row)),
          ...dates.map((date) => matrixCell(row.cells[date]))))))));
}

const byName = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

async function renderIndex(view) {
  const data = await api(`labs?lang=${LANG}`);
  // the table sorts by specimen and keeps this order inside each group: alphabetical
  data.markers.sort((a, b) => byName.compare(a.name, b.name));
  if (!data.markers.length) {
    view.replaceChildren(pendingNotice(data.pending) ?? "", emptyState({ message: t("labs.none") }));
    return;
  }
  view.replaceChildren(el("div", { class: "labs" },
    pendingNotice(data.pending),
    quiet(t("labs.note")),
    markerTable(data.markers),
    matrixSection(data.matrix)));
}

function valuesTable(data) {
  return dataTable({
    caption: t("labs.caption.values", { name: data.name }),
    rows: tableRows(data),
    pending: (row) => row.pending,
    filterable: false,
    sort: { key: "at", direction: "desc" },
    columns: [
      { key: "at", label: t("labs.col.date"), render: (row) => formatDate(row.at) },
      {
        key: "value",
        label: data.unit ? t("labs.col.value_in", { unit: data.unit }) : t("labs.col.value"),
        numeric: true,
        value: (row) => row.value,
        render: (row) => el("span", { class: row.pending ? "value-pending" : null }, row.value ?? row.original.text ?? ""),
      },
      { key: "form", label: t("labs.col.on_form"), value: (row) => formatValue(row.original) },
      { key: "range", label: t("overview.col.range"), sortable: false, value: (row) => formatRange(row.original) },
      {
        key: "status",
        label: t("labs.col.status"),
        value: (row) => (row.pending ? t("status.pending") : statusWord(row.status)),
        render: (row) => statusPill(row.pending ? "pending" : row.status),
      },
    ],
  });
}

async function drawDetail(chartBox, toggle, data) {
  const { drawChart, tokenColor } = await import("../chart.js"); // 1 MB: only when there is a chart
  const colors = () => ({
    band: tokenColor("--in-range"), baseline: tokenColor("--chart-2"), pending: tokenColor("--pending"),
  });
  const instance = await drawChart(chartBox, detailOption(data, { colors: colors() }), { label: chartLabel(data) });
  if (instance && toggle) {
    toggle.disabled = false;
    toggle.addEventListener("change", () =>
      instance.setOption(detailOption(data, { baseline: toggle.checked, colors: colors() }), true));
  }
  return instance;
}

async function renderMarker(view, code) {
  let data;
  try {
    data = await api(`labs/${encodeURIComponent(code)}?lang=${LANG}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      view.replaceChildren(errorState({ title: t("labs.detail.not_found", { code }) }),
        el("p", {}, el("a", { href: "#/labs" }, t("labs.detail.back"))));
      return;
    }
    throw err;
  }
  if (!view.isConnected) return; // the user moved on while it loaded: that page has its own heading
  const heading = view.parentElement.querySelector("h1");
  if (heading) heading.textContent = data.name;
  document.title = `${data.name} · health-os`;

  const numeric = data.points.filter((p) => p.value !== null);
  const numericPending = data.pending.filter((p) => p.value !== null);
  const texts = qualitative(data.points).length + qualitative(data.pending).length;
  const notConverted = unconverted(data.points).length;
  const meta = [specimenWord(data.specimen), data.unit && t("labs.detail.unit", { unit: data.unit }),
    data.loinc && `LOINC ${data.loinc}`].filter(Boolean).join(" · ");

  const chartBox = numeric.length || numericPending.length ? el("div", { class: "labs-chart" }) : null;
  const textBox = texts ? el("div", { class: "labs-chart labs-chart-text" }) : null;
  const toggle = el("input", { type: "checkbox", disabled: true });
  const hasBaseline = data.baseline.mean !== null && data.baseline.mean !== undefined;

  view.replaceChildren(el("div", { class: "labs-detail" },
    el("p", {}, el("a", { href: "#/labs" }, t("labs.detail.back"))),
    quiet(meta),
    data.pending.length > 0 && el("p", { class: "labs-pending" }, statusPill("pending"), " ",
      tn("labs.detail.pending", { n: data.pending.length })),
    !data.points.length && !data.pending.length && emptyState({ message: t("labs.detail.empty") }),
    chartBox,
    chartBox && quiet(t("labs.detail.range_note")),
    notConverted > 0 && quiet(tn("labs.detail.unconverted", { n: notConverted, unit: data.unit ?? "" })),
    textBox && el("h2", {}, t("labs.detail.qualitative")),
    textBox,
    section(t("labs.trend.title"), ...trendLines(data.trend, data.unit).map((line) => el("p", {}, line)),
      quiet(t("labs.trend.note"))),
    section(t("labs.baseline.title"),
      el("p", {}, baselineText(data.baseline, data.unit)),
      hasBaseline && chartBox && el("label", {}, toggle, " ", t("labs.baseline.toggle", { sigmas: data.baseline.sigmas })),
      quiet(t("labs.baseline.note"))),
    section(t("labs.detail.values"), valuesTable(data).element)));

  if (chartBox) await drawDetail(chartBox, hasBaseline ? toggle : null, data);
  if (textBox) {
    const { drawChart, tokenColor } = await import("../chart.js");
    await drawChart(textBox, qualitativeOption(data, { colors: { pending: tokenColor("--pending") } }),
      { label: t("labs.chart.label_text", { name: data.name, n: texts }) });
  }
}

export function render(view, [code] = []) {
  return code ? renderMarker(view, code) : renderIndex(view);
}
