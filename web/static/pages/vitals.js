// Vitals (#56): home blood pressure checked against the ESH home protocol, the watch's daily
// values on one shared time axis, and a year of days as calendar heatmaps.

import { api } from "../api.js";
import { dataTable, el, emptyState, formatDate, statusPill } from "../components.js";
import { LANG, t } from "../strings.js";
import {
  bpKey, bpOption, diaryState, diaryView, heatmapOption, heatmapSummary, panelTitle, pressure, readoutAt,
  wearableHeight, wearableOption, wearablePanels, windowLinks,
} from "./vitals-model.js";
import { findingView, sustainedEmpty, sustainedFootnote, sustainedState, withShading } from "./sustained-model.js";
import { sustainedTranslator } from "./sustained-strings.js";

const section = (title, ...children) =>
  el("section", { class: "vitals-section" }, el("h2", {}, title), ...children);

const quiet = (text) => el("p", { class: "quiet" }, text);

function windowSwitch(window) {
  return el("nav", { class: "window-switch", "aria-label": t("vitals.window.label") },
    ...windowLinks(window).map((link) => el("a", {
      href: link.href, "aria-current": link.current ? "true" : null,
    }, link.label)));
}

function diaryCard(diary, protocol) {
  const view = diaryView(diary, protocol);
  return el("article", { class: "card diary", "data-state": view.state },
    el("h3", {}, t("vitals.bp.diary.latest")),
    el("p", { class: "diary-period" }, view.period),
    el("p", { class: "diary-verdict" },
      el("span", { class: "diary-icon", "aria-hidden": "true" }, view.icon), " ", view.verdict),
    view.mean
      ? el("div", { class: "diary-mean" },
        el("p", { class: "figure" }, `${view.mean} mmHg`),
        el("p", { class: "quiet" }, view.meanNote),
        view.sessions && el("p", {}, view.sessions))
      : el("p", { class: "diary-no-mean" }, view.noMean),
    el("ul", { class: "plain diary-lines" }, ...view.lines.map((line) => el("li", {}, line))));
}

function earlierDiaries(diaries, protocol) {
  if (!diaries.length) return null;
  const table = dataTable({
    caption: t("vitals.bp.earlier.caption"),
    rows: diaries,
    filterable: false,
    columns: [
      { key: "first_day", label: t("vitals.bp.col.period"), value: (d) => diaryView(d, protocol).period },
      { key: "complete_days", label: t("vitals.bp.col.complete"), numeric: true },
      { key: "followed", label: t("vitals.bp.col.protocol"), value: (d) => diaryView(d, protocol).verdict },
      {
        key: "mean",
        label: t("vitals.bp.col.mean"),
        numeric: true,
        value: (d) => d.mean?.systolic ?? null,
        render: (d) => {
          if (!d.mean) return t("vitals.bp.col.no_mean");
          const mean = `${pressure(d.mean)} mmHg`;
          return diaryState(d) === "unrecorded" ? t("vitals.bp.col.plain_mean", { mean }) : mean;
        },
      },
    ],
  });
  return el("details", { class: "diary-history" },
    el("summary", {}, t("vitals.bp.earlier.title", { n: diaries.length })), table.element);
}

function protocolNote(protocol) {
  const { source, threshold, morning, evening } = protocol;
  return el("p", { class: "quiet footnote" },
    t("vitals.bp.footnote", {
      min: protocol.min_days, max: protocol.max_days, per: protocol.readings_per_session,
      systolic: threshold.systolic, diastolic: threshold.diastolic,
      m0: morning[0], m1: morning[1], e0: evening[0], e1: evening[1],
    }), " ",
    el("a", { href: source.url, rel: "noreferrer noopener", target: "_blank" }, source.label), ".");
}

function keyLine({ sessions, shapes }) {
  return el("p", { class: "vitals-key" },
    ...sessions.map(({ session, label }) => el("span", { class: `key-${session}` }, label)),
    ...shapes.map((shape) => el("span", { class: "quiet" }, shape)));
}

function bpSection(bp, window, charts) {
  const title = t("vitals.bp.title");
  if (!bp || !bp.readings) {
    return section(title, emptyState({ message: t("vitals.bp.empty") }),
      bp?.pending_values > 0 && el("p", {}, statusPill("pending"), " ", t("vitals.bp.pending", { n: bp.pending_values })));
  }
  const [latest, ...earlier] = bp.diaries;
  const chart = bp.points.length ? el("div", { class: "vitals-bp-chart" }) : null;
  if (chart) charts.push({ kind: "bp", element: chart, bp });
  return section(title,
    bp.pending_values > 0 && el("p", { class: "vitals-pending" }, statusPill("pending"), " ", t("vitals.bp.pending", { n: bp.pending_values })),
    el("div", { class: "vitals-bp" },
      latest ? diaryCard(latest, bp.protocol) : el("div", { class: "card" }, quiet(t("vitals.bp.no_diary", { gap: bp.protocol.max_gap_days }))),
      el("div", { class: "vitals-bp-plot" },
        chart && keyLine(bpKey(bp.points)),
        chart ?? quiet(t("vitals.bp.none_in_window", { days: window.days })),
        chart && window.bucket !== "day" && quiet(t(`vitals.bucket.${window.bucket}`)))),
    earlierDiaries(earlier, bp.protocol),
    protocolNote(bp.protocol));
}

// sustained deviations (#75): a short list above the charts; their days are shaded on them
function sustainedList(sustained) {
  const state = sustainedState(sustained);
  if (state === "none") return null;
  const { t } = sustainedTranslator(LANG);
  const items = sustained.findings.map((finding) => {
    const view = findingView(finding, LANG);
    return el("li", { class: "sustained-item", "data-kind": view.kind },
      el("p", { class: "sustained-head" }, el("strong", {}, view.title), " ", el("span", { class: "quiet" }, view.period)),
      ...view.lines.map((line) => el("p", {}, line)),
      view.chips.length ? el("p", { class: "sustained-chips" }, ...view.chips.map((chip) => el("span", { class: "sustained-chip" }, chip))) : null);
  });
  return el("section", { class: "card sustained", "aria-labelledby": "sustained-title" },
    el("h3", { id: "sustained-title" }, t("title")),
    el("p", { class: "quiet" }, t("note")),
    items.length ? el("ul", { class: "plain sustained-list" }, ...items) : el("p", {}, sustainedEmpty(sustained, LANG)),
    el("p", { class: "quiet footnote" }, sustainedFootnote(sustained, LANG)));
}

function wearableSection(data, charts) {
  const title = t("vitals.watch.title");
  const panels = wearablePanels(data.wearables, data.load);
  if (!panels.length) return section(title, emptyState({ message: t("vitals.watch.empty", { days: data.window.days }) }));
  const chart = el("div", { class: "vitals-watch-chart" });
  chart.dataset.panels = String(panels.length);
  const readout = el("div", { class: "vitals-readout", "aria-live": "polite" });
  charts.push({ kind: "watch", element: chart, panels, readout, sustained: data.sustained });
  const missing = data.wearables.length ? null : t("vitals.watch.only_load");
  return section(title,
    quiet(t("vitals.watch.note")),
    sustainedList(data.sustained),
    missing && quiet(missing),
    readout,
    chart,
    data.window.bucket !== "day" && quiet(t(`vitals.bucket.${data.window.bucket}`)),
    data.load && quiet(t("vitals.load.note", { acute: data.load.acute_days, chronic: data.load.chronic_days })));
}

function heatmapSection({ heatmaps }, charts) {
  const title = t("vitals.heatmap.title");
  if (!heatmaps.length) return section(title, emptyState({ message: t("vitals.heatmap.empty") }));
  return section(title,
    quiet(t("vitals.heatmap.note")),
    ...heatmaps.map((heatmap) => {
      const chart = el("div", { class: "vitals-heatmap" });
      charts.push({ kind: "heatmap", element: chart, heatmap });
      return el("figure", { class: "vitals-heatmap-figure" },
        el("figcaption", {}, el("strong", {}, heatmap.name), " · ", heatmapSummary(heatmap)),
        el("div", { class: "vitals-heatmap-scroll" }, chart));
    }));
}

// the options carry colours read from the tokens: on a theme change (or for print) they are read
// again and the charts redrawn with them
function chartColors(tokenColor) {
  return {
    morning: tokenColor("--chart-1"), evening: tokenColor("--chart-2"), muted: tokenColor("--muted"),
    c1: tokenColor("--chart-1"), c2: tokenColor("--chart-2"), c3: tokenColor("--chart-3"), c4: tokenColor("--chart-4"),
    area: withAlpha(tokenColor("--accent"), 0.08),
    low: tokenColor("--border"), high: tokenColor("--chart-1"), empty: tokenColor("--surface"), bg: tokenColor("--bg"),
    sustained: withAlpha(tokenColor("--chart-4"), 0.18), sustainedEdge: withAlpha(tokenColor("--chart-4"), 0.5),
  };
}

function optionFor(chart, window, colors) {
  if (chart.kind === "bp") return bpOption(chart.bp, window, { colors });
  if (chart.kind === "watch") {
    return withShading(wearableOption(chart.panels, window, { colors }), chart.sustained, chart.panels, { colors, lang: LANG, bucket: window.bucket });
  }
  return heatmapOption(chart.heatmap, { colors });
}

function labelFor(chart, window) {
  if (chart.kind === "bp") return t("vitals.bp.chart_label", { n: chart.bp.points.length, days: window.days });
  if (chart.kind === "watch") {
    return t("vitals.watch.chart_label", { panels: chart.panels.map(panelTitle).join(", "), days: window.days });
  }
  return `${chart.heatmap.name}: ${heatmapSummary(chart.heatmap)}`;
}

async function drawCharts(charts, window) {
  if (!charts.length) return;
  const { drawChart, tokenColor } = await import("../chart.js"); // 1 MB: only when there is a chart
  const colors = chartColors(tokenColor);
  const drawn = await Promise.all(charts.map(async (chart) => {
    if (chart.kind === "watch") chart.element.style.height = `${wearableHeight(chart.panels)}px`;
    const instance = await drawChart(chart.element, optionFor(chart, window, colors), { label: labelFor(chart, window) });
    if (instance && chart.kind === "watch") {
      const show = (time) => {
        const { title, lines } = readoutAt(chart.panels, time, window.bucket);
        chart.readout.replaceChildren(el("strong", {}, title), ...lines.map((line) => el("span", {}, line)));
      };
      show(Date.parse(window.to));
      instance.on("updateAxisPointer", ({ axesInfo: [axis] }) => {
        if (axis) show(axis.value);
      });
    }
    if (chart.kind === "heatmap") {
      // on a phone the year scrolls sideways: start at its newest end
      const scroller = chart.element.parentElement;
      scroller.scrollLeft = scroller.scrollWidth;
    }
    return instance && { chart, instance };
  }));
  const live = drawn.filter(Boolean);
  const recolor = () => {
    if (!live.some(({ chart }) => chart.element.isConnected)) {
      document.removeEventListener("themechange", recolor);
      return;
    }
    const fresh = chartColors(tokenColor);
    for (const { chart, instance } of live) instance.setOption(optionFor(chart, window, fresh), { replaceMerge: ["series"] });
  };
  if (live.length) document.addEventListener("themechange", recolor);
}

/** "rgb(42, 120, 214)" → "rgba(42, 120, 214, 0.08)" */
function withAlpha(color, alpha) {
  const match = color.match(/rgba?\(([^)]+)\)/);
  if (!match) return color;
  const [r, g, b] = match[1].split(",").map((part) => part.trim());
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export async function render(view, [days] = []) {
  const query = new URLSearchParams({ lang: LANG });
  if (days) query.set("days", days);
  // days, "today" and morning/evening are the user's: read in the browser's zone
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (zone) query.set("tz", zone);
  const data = await api(`vitals?${query}`);
  if (!view.isConnected) return;
  const charts = [];
  view.replaceChildren(el("div", { class: "vitals" },
    el("div", { class: "vitals-head" },
      windowSwitch(data.window),
      quiet(t("vitals.window.range", { from: formatDate(data.window.from), to: formatDate(data.window.to) }))),
    bpSection(data.blood_pressure, data.window, charts),
    wearableSection(data, charts),
    heatmapSection(data, charts)));
  await drawCharts(charts, data.window);
}
