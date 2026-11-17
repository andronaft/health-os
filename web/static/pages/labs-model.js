// What the Labs page says and draws, from what /api/v1/labs and /api/v1/labs/<code> send. Nothing
// here touches the page, so it can be tested without a browser (tests/web_ui.test.mjs).

import { formatDate, formatRange, formatValue, statusWord } from "../components.js";
import { t } from "../strings.js";

const OUT = new Set(["low", "high", "critical"]);

/** t() with "<key>_one" for n = 1 ("1 value is", "2 values are"). */
export const tn = (key, vars) => t(vars.n === 1 ? `${key}_one` : key, vars);

/** A latest value outside the range on its form. */
export const isOutOfRange = (marker) => OUT.has(marker.status);

/** A specimen's word; a marker without one is "other", a specimen added later keeps its code. */
export function specimenWord(specimen) {
  if (!specimen) return t("labs.specimen.other");
  const key = `labs.specimen.${specimen}`;
  const word = t(key);
  return word === key ? specimen : word;
}

/** The specimens the table can be narrowed to, in their words' order. */
export function specimenOptions(markers) {
  const codes = [...new Set(markers.map((marker) => marker.specimen ?? ""))];
  return codes
    .map((code) => ({ code, label: specimenWord(code || null) }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/** The table's rows under the page's own filters; the text filter is the table's. */
export function filterMarkers(markers, { outOfRangeOnly = false, specimen = "" } = {}) {
  return markers.filter((marker) =>
    (!outOfRangeOnly || isOutOfRange(marker)) && (!specimen || (marker.specimen ?? "") === specimen));
}

/** "5 since 2024-05-31", or the one date when there is a single value. */
export const historyText = ({ n, first_at: first, at }) =>
  (n > 1 ? t("labs.history", { n, date: formatDate(first) }) : t("labs.history_one", { date: formatDate(at) }));

/**
 * The sparkline's points in a width × height box: x by date, y by value (up is higher). A
 * single value, or values that never change, sit on the middle line.
 */
export function sparkPoints(points, width, height, pad = 3) {
  if (!points.length) return [];
  const times = points.map(({ at }) => Date.parse(at));
  const values = points.map(({ value }) => value);
  const [t0, t1] = [Math.min(...times), Math.max(...times)];
  const [v0, v1] = [Math.min(...values), Math.max(...values)];
  const x = (time) => (t1 === t0 ? width / 2 : pad + ((time - t0) / (t1 - t0)) * (width - 2 * pad));
  const y = (value) => (v1 === v0 ? height / 2 : pad + ((v1 - value) / (v1 - v0)) * (height - 2 * pad));
  return points.map((point, i) => [round(x(times[i])), round(y(values[i]))]);
}

const round = (n) => Math.round(n * 10) / 10;

export const sparkLabel = (marker) => t("labs.spark", { name: marker.name, n: marker.spark.length });

/** A matrix cell: the value without its unit (the marker's page has it), or "" for no value. */
export const cellText = (cell) => (cell ? formatValue({ ...cell, unit: null }) : "");

const formatP = (p) => (p < 0.001 ? "< 0.001" : `≈ ${p.toFixed(3)}`);

/** The trend in words, with what it was computed on. Pending values never count. */
export function trendLines(trend, unit) {
  if (!trend || trend.n < trend.min_n) {
    return [t("labs.trend.too_few", { n: trend?.n ?? 0, min: trend?.min_n ?? 5 })];
  }
  const vars = { n: trend.n, from: formatDate(trend.from), to: formatDate(trend.to) };
  const words = { increasing: "labs.trend.increasing", decreasing: "labs.trend.decreasing" };
  const lines = [t(words[trend.direction] ?? "labs.trend.none", vars)];
  if (trend.p !== null && trend.p !== undefined) lines.push(t("labs.trend.p", { p: formatP(trend.p) }));
  if (trend.slope_per_year !== null && trend.slope_per_year !== undefined) {
    const slope = Number(trend.slope_per_year.toPrecision(3));
    lines.push(t("labs.trend.slope", { slope: slope > 0 ? `+${slope}` : String(slope), unit: unit ?? "" }).trim());
  }
  return lines;
}

const short = (n) => String(Number(n.toPrecision(4)));

/** What the baseline is, or why there is none. */
export function baselineText({ n, min_n: min, mean, low, high, sigmas }, unit) {
  if (mean === null || mean === undefined) return t("labs.baseline.too_few", { n, min });
  return t("labs.baseline.range", {
    low: short(low), high: short(high), mean: short(mean), n, sigmas, unit: unit ?? "",
  });
}

/** Approved values that have a text and no number (qualitative), or none that fits the chart. */
export const qualitative = (points) => points.filter((p) => p.value === null && p.original.text);
/** Approved numbers that couldn't be converted to the chart's unit. */
export const unconverted = (points) => points.filter((p) => p.value === null && p.original.value !== null && p.original.value !== undefined);

/** The point's lines for the chart's tooltip: canonical value, the form's value and range. */
export function pointText(point, unit) {
  const lines = [
    `${formatDate(point.at)}: ${[point.value ?? point.original.text, unit].filter((part) => part !== null && part !== undefined && part !== "").join(" ")}`,
  ];
  const onForm = formatValue(point.original);
  if (point.value !== null && onForm && (point.original.unit ?? "") !== (unit ?? "")) {
    lines.push(t("labs.point.form", { value: onForm }));
  }
  const range = formatRange(point.original);
  if (!range) lines.push(t("labs.point.no_range"));
  else if (point.range?.unconverted) lines.push(t("labs.point.range_unconverted", { range, unit: point.original.unit ?? "" }));
  else lines.push(t("labs.point.range", { range: [range, point.original.unit].filter(Boolean).join(" ") }));
  lines.push(point.pending ? t("labs.point.pending") : statusWord(point.status));
  return lines.join("\n");
}

export function chartLabel(data) {
  const shown = data.points.filter((p) => p.value !== null);
  const pending = data.pending.filter((p) => p.value !== null).length;
  if (!shown.length) return t("labs.chart.label_pending", { name: data.name, pending });
  return t("labs.chart.label", {
    name: data.name,
    n: shown.length,
    first: formatDate(shown[0].at),
    last: formatDate(shown.at(-1).at),
    pending,
  });
}

const HOLLOW = (color) => ({ color: "transparent", borderColor: color, borderWidth: 2 });
const BAND_WIDTH = 14; // px: a range belongs to its own point, not to the time between points

/**
 * The marker's chart: approved values as a line, each over the range printed on its own form (a
 * short band, not one band for all: ranges differ between labs); pending values as hollow dots
 * labelled "unverified", not joined to the line; optionally the personal baseline. Values are in
 * the marker's canonical unit; the tooltip gives the form's value and unit.
 *
 * colors: { band, baseline, pending } — canvas colours from the theme's tokens.
 */
export function detailOption(data, { baseline = false, colors = {} } = {}) {
  const approved = data.points.filter((p) => p.value !== null);
  const pending = data.pending.filter((p) => p.value !== null);
  const bands = approved.filter((p) => p.range && !p.range.unconverted);
  const item = (p) => ({ value: [Date.parse(p.at), p.value], point: p });
  const base = data.baseline;
  const showBaseline = baseline && base.mean !== null && base.mean !== undefined;

  const series = [
    {
      type: "line",
      z: 3,
      name: t("labs.chart.values"),
      symbol: "circle",
      symbolSize: 8,
      lineStyle: { width: 2 },
      data: approved.map(item),
      ...(showBaseline && {
        markArea: {
          silent: true,
          itemStyle: { color: colors.baseline, opacity: 0.12 },
          data: [[{ yAxis: base.low }, { yAxis: base.high }]],
        },
        markLine: {
          silent: true,
          symbol: "none",
          label: { formatter: t("labs.chart.baseline_mean"), position: "insideStartTop" },
          lineStyle: { color: colors.baseline, type: "dashed" },
          data: [{ yAxis: base.mean }],
        },
      }),
    },
    {
      type: "custom",
      z: 1, // under the values
      name: t("labs.chart.range"),
      silent: true,
      tooltip: { show: false },
      clip: true,
      encode: { x: 0, y: [1, 2] },
      data: bands.map((p) => [Date.parse(p.at), p.range.min ?? NaN, p.range.max ?? NaN]),
      renderItem(params, api) {
        const [x, low, high] = [api.value(0), api.value(1), api.value(2)];
        const sys = params.coordSys;
        const top = Number.isFinite(high) ? api.coord([x, high])[1] : sys.y;
        const bottom = Number.isFinite(low) ? api.coord([x, low])[1] : sys.y + sys.height;
        const [cx] = api.coord([x, Number.isFinite(low) ? low : high]);
        return {
          type: "rect",
          shape: { x: cx - BAND_WIDTH / 2, y: top, width: BAND_WIDTH, height: bottom - top },
          style: { fill: colors.band, opacity: 0.22 },
        };
      },
    },
  ];
  if (pending.length) {
    series.push({
      type: "scatter",
      name: t("labs.chart.pending"),
      z: 3,
      symbol: "circle",
      symbolSize: 11,
      // hollow for real: ECharts fills an "emptyCircle" white, which on a dark theme reads as a
      // filled dot. Grey like the pending pill, not a fact's colour
      itemStyle: HOLLOW(colors.pending),
      label: { show: true, position: "top", formatter: t("labs.chart.unverified") },
      data: pending.map(item),
    });
  }
  return {
    animation: false,
    grid: { left: 56, right: 56, top: 36, bottom: 56 }, // room for an "unverified" label at the edge
    legend: { bottom: 0, data: series.filter((s) => s.type !== "custom").map((s) => s.name) },
    tooltip: { trigger: "item", formatter: (params) => pointText(params.data.point, data.unit) },
    xAxis: { type: "time" },
    yAxis: { type: "value", scale: true, name: data.unit ?? "" },
    series,
  };
}

/** Text results on a categorical axis: one row per distinct result, pending ones hollow. */
export function qualitativeOption(data, { colors = {} } = {}) {
  const approved = qualitative(data.points);
  const pending = qualitative(data.pending);
  const categories = [...new Set([...approved, ...pending].map((p) => p.original.text))];
  const item = (p) => ({ value: [Date.parse(p.at), p.original.text], point: p });
  return {
    animation: false,
    grid: { left: 96, right: 24, top: 16, bottom: 48 },
    legend: { bottom: 0 },
    tooltip: { trigger: "item", formatter: (params) => pointText(params.data.point, null) },
    xAxis: { type: "time" },
    yAxis: { type: "category", data: categories },
    series: [
      { type: "scatter", name: t("labs.chart.values"), symbolSize: 10, data: approved.map(item) },
      ...(pending.length
        ? [{ type: "scatter", name: t("labs.chart.pending"), symbolSize: 11, itemStyle: HOLLOW(colors.pending), data: pending.map(item) }]
        : []),
    ],
  };
}

/** Every value for the table under the chart, newest first; pending ones flagged. */
export const tableRows = (data) =>
  [...data.points, ...data.pending].sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
