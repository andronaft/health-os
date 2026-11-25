// What the Vitals page says and draws, from what /api/v1/vitals sends. Nothing here touches the
// page, so it can be tested without a browser (tests/web_ui.test.mjs).

import { formatDate } from "../components.js";
import { t } from "../strings.js";

const DAY_MS = 86400000;
const BUCKET_MS = { day: DAY_MS, week: 7 * DAY_MS, month: 31 * DAY_MS };

/** "#/vitals/90" for each window the API offers; the current one marked. */
export function windowLinks({ days, options }) {
  return options.map((option) => ({
    days: option,
    href: `#/vitals/${option}`,
    current: option === days,
    label: t(`vitals.window.${option}`),
  }));
}

const whole = (value) => (value === null || value === undefined ? "—" : String(Math.round(value)));

/** "133/83": blood pressure is read in whole mmHg; more decimals would be false precision. */
export const pressure = (mean) => (mean ? `${whole(mean.systolic)}/${whole(mean.diastolic)}` : "—");

/** A diary's protocol check, as the card says it. Only a diary that followed it has a mean. */
export function diaryView(diary, protocol) {
  const per = protocol.readings_per_session;
  const lines = [
    t("vitals.bp.diary.complete", { n: diary.complete_days, days: diary.days, per }),
    t("vitals.bp.diary.sessions", { n: diary.full_sessions, total: diary.sessions, per }),
  ];
  if (diary.other_readings) lines.push(t("vitals.bp.diary.other", { n: diary.other_readings }));
  if (diary.earlier_days) lines.push(t("vitals.bp.diary.earlier", { n: diary.earlier_days, max: protocol.max_days }));
  const view = {
    period: t("vitals.bp.diary.period", {
      first: formatDate(diary.first_day), last: formatDate(diary.last_day), days: diary.days,
    }),
    followed: diary.followed,
    verdict: t(diary.followed ? "vitals.bp.diary.followed" : "vitals.bp.diary.not_followed"),
    lines,
    mean: null,
    sessions: null,
  };
  if (diary.followed && diary.mean) {
    view.mean = pressure(diary.mean);
    view.meanNote = t("vitals.bp.diary.mean_of", { n: diary.mean.n, from: formatDate(diary.mean.from_day) });
    view.sessions = t("vitals.bp.diary.by_session", {
      morning: pressure(diary.mean.morning), evening: pressure(diary.mean.evening),
    });
  } else {
    view.noMean = t("vitals.bp.diary.no_mean", { min: protocol.min_days, n: diary.counted_days });
  }
  return view;
}

const SESSIONS = ["morning", "evening", "other"];

/** [t, value] pairs with a break (null) wherever two points are further apart than `gap` ms, so
 * a line never bridges weeks without readings as if they had been measured. */
export function withGaps(pairs, gap) {
  const out = [];
  pairs.forEach(([time, value], i) => {
    if (i && time - pairs[i - 1][0] > gap) out.push([(time + pairs[i - 1][0]) / 2, null]);
    out.push([time, value]);
  });
  return out;
}

/** The chart's key: which sessions it draws, and how systolic and diastolic differ. */
export function bpKey(points) {
  const sessions = SESSIONS.filter((session) => points.some((p) => p.session === session));
  return {
    sessions: sessions.map((session) => ({ session, label: t(`vitals.session.${session}`) })),
    shapes: [t("vitals.bp.key.systolic"), t("vitals.bp.key.diastolic")],
  };
}

export function bpTooltip(point) {
  const when = point.n > 1
    ? t("vitals.bp.tip.bucket", { date: formatDate(point.at), n: point.n })
    : String(point.at).slice(0, 16).replace("T", " ");
  return `${when}\n${t(`vitals.session.${point.session}`)}: ${pressure(point)} mmHg`;
}

/**
 * The blood pressure chart: morning and evening as separate lines (systolic solid, diastolic
 * dashed), readings outside those hours as grey dots, each diary shaded, and the ESH home
 * threshold as two dashed lines labelled with their source.
 */
export function bpOption(bp, window, { colors }) {
  const gap = window.bucket === "day" ? 2.5 * DAY_MS : 1.5 * BUCKET_MS[window.bucket];
  const color = { morning: colors.morning, evening: colors.evening, other: colors.muted };
  const series = [];
  for (const session of SESSIONS) {
    const points = bp.points.filter((p) => p.session === session);
    if (!points.length) continue;
    for (const [key, dashed] of [["systolic", false], ["diastolic", true]]) {
      const pairs = points.filter((p) => p[key] !== null).map((p) => [Date.parse(p.at), p[key], p]);
      const byTime = new Map(pairs.map(([time, , p]) => [time, p]));
      series.push({
        type: session === "other" ? "scatter" : "line",
        name: t(`vitals.bp.series.${session}.${key}`),
        color: color[session],
        symbol: dashed ? "triangle" : "circle",
        symbolSize: 7,
        showSymbol: true,
        lineStyle: { width: 2, type: dashed ? "dashed" : "solid" },
        connectNulls: false,
        data: withGaps(pairs.map(([time, value]) => [time, value]), gap).map(([time, value]) => ({
          value: [time, value],
          tip: byTime.has(time) ? bpTooltip(byTime.get(time)) : "",
        })),
      });
    }
  }
  const from = Date.parse(window.from);
  const to = Date.parse(window.to) + DAY_MS;
  const shaded = bp.diaries
    .filter((d) => Date.parse(d.last_day) + DAY_MS > from)
    .map((d) => [
      { xAxis: Math.max(from, Date.parse(d.first_day)), name: t(d.followed ? "vitals.bp.area.followed" : "vitals.bp.area.not_followed") },
      { xAxis: Date.parse(d.last_day) + DAY_MS },
    ]);
  const { systolic, diastolic } = bp.protocol.threshold;
  series.push({
    type: "line",
    name: t("vitals.bp.threshold.series"),
    data: [],
    color: colors.muted,
    markLine: {
      silent: true,
      symbol: "none",
      lineStyle: { type: [6, 4], color: colors.muted, width: 1 },
      label: { color: colors.muted, formatter: "{b}", position: "insideStartTop" },
      data: [
        { yAxis: systolic, name: t("vitals.bp.threshold.line", { value: systolic }) },
        { yAxis: diastolic, name: t("vitals.bp.threshold.line", { value: diastolic }) },
      ],
    },
    markArea: shaded.length ? {
      silent: true,
      itemStyle: { color: colors.area },
      // in a long window the diaries are narrow strips: their labels would overlap
      label: { show: window.bucket === "day", color: colors.muted, position: "insideTop", fontSize: 11 },
      data: shaded,
    } : undefined,
  });
  return {
    animation: false,
    // the key is HTML beside the chart (bpKey): a canvas legend wraps over the plot on a phone
    grid: { left: 44, right: 16, top: 32, bottom: 36 },
    xAxis: { type: "time", min: from, max: to, axisLabel: { hideOverlap: true } },
    yAxis: { type: "value", name: "mmHg", scale: true, min: (v) => Math.floor((Math.min(v.min, diastolic) - 5) / 10) * 10,
      max: (v) => Math.ceil((Math.max(v.max, systolic) + 5) / 10) * 10 },
    tooltip: { trigger: "item", formatter: (p) => p.data?.tip || p.name },
    series,
  };
}

// The synchronized charts, top to bottom. A panel is drawn only if one of its codes has data.
export const PANELS = [
  { id: "sleep", codes: ["sleep_duration", "sleep_deep", "sleep_rem"], bars: ["sleep_deep", "sleep_rem"] },
  { id: "sleep_score", codes: ["sleep_score"] },
  { id: "hrv", codes: ["hrv"] },
  { id: "resting_hr", codes: ["resting_hr"] },
  { id: "stress", codes: ["stress_avg"] },
  { id: "body_battery", codes: ["body_battery_high", "body_battery_low"] },
  { id: "steps", codes: ["steps"], bars: ["steps"] },
  { id: "load", load: true },
  { id: "vo2max", codes: ["vo2max"] },
];

/** A series' short name inside its panel ("Deep", "Low"); the API's marker name if there is none. */
export function seriesName({ code, name }) {
  const key = `vitals.series.${code}`;
  const short = t(key);
  return short === key ? name : short;
}

// "score" is no unit to print after a number: a score is its own scale
const shownUnit = (unit) => (unit && unit !== "score" ? unit : "");

/** The panels that have something to draw, each with its series in the API's own shape. */
export function wearablePanels(wearables, load) {
  const byCode = new Map(wearables.map((w) => [w.code, w]));
  const out = [];
  for (const panel of PANELS) {
    if (panel.load) {
      if (!load) continue;
      out.push({
        id: panel.id,
        unit: load.unit,
        series: load.lines.filter((line) => line.points.length).map((line) => ({
          code: `load_${line.key}`,
          name: t(`vitals.load.${line.key}`, { days: load[`${line.key}_days`] }),
          unit: load.unit,
          points: line.points,
          bar: false,
        })),
      });
      continue;
    }
    const series = panel.codes.filter((code) => byCode.has(code)).map((code) => ({
      ...byCode.get(code), name: seriesName(byCode.get(code)), bar: Boolean(panel.bars?.includes(code)),
    }));
    if (series.length) out.push({ id: panel.id, unit: series[0].unit, series });
  }
  return out;
}

export const panelTitle = (panel) => {
  const title = t(`vitals.panel.${panel.id}`);
  return shownUnit(panel.unit) ? `${title} (${panel.unit})` : title;
};

const PANEL_HEIGHT = 92; // px per panel, the gap above it included
const PANEL_GAP = 30;
const TOP = 8;
const BOTTOM = 64; // the shared time axis and the zoom slider

export const wearableHeight = (panels) => TOP + panels.length * PANEL_HEIGHT + BOTTOM;

/**
 * One canvas, one panel per measure, all on one time axis: zooming or moving the pointer in one
 * moves them all. The pointer's values are spelled out by readoutAt, outside the canvas.
 */
export function wearableOption(panels, window, { colors }) {
  const from = Date.parse(window.from);
  const to = Date.parse(window.to) + DAY_MS;
  const palette = [colors.c1, colors.c2, colors.c3, colors.c4];
  const indices = panels.map((_, i) => i);
  const last = panels.length - 1;
  const top = (i) => TOP + i * PANEL_HEIGHT + PANEL_GAP;
  const gap = window.bucket === "day" ? 1.5 * DAY_MS : 1.5 * BUCKET_MS[window.bucket];
  return {
    animation: false,
    title: panels.map((panel, i) => ({
      text: panelTitle(panel), top: top(i) - 22, left: 48, textStyle: { fontSize: 12, fontWeight: 600 },
    })),
    grid: panels.map((_, i) => ({ left: 48, right: 16, top: top(i), height: PANEL_HEIGHT - PANEL_GAP })),
    xAxis: panels.map((_, i) => ({
      type: "time", gridIndex: i, min: from, max: to,
      axisLabel: { show: i === last, hideOverlap: true }, axisTick: { show: i === last },
    })),
    yAxis: panels.map((_, i) => ({ type: "value", gridIndex: i, scale: true, splitNumber: 2 })),
    axisPointer: { link: [{ xAxisIndex: "all" }], label: { show: false } },
    tooltip: { trigger: "axis", showContent: false },
    dataZoom: [
      { type: "inside", xAxisIndex: indices },
      { type: "slider", xAxisIndex: indices, bottom: 8, height: 20 },
    ],
    series: panels.flatMap((panel, i) => panel.series.map((s, k) => {
      const pairs = s.points.map((p) => [Date.parse(p.at), p.value]);
      return {
        type: s.bar ? "bar" : "line",
        name: s.name,
        xAxisIndex: i,
        yAxisIndex: i,
        color: palette[k % palette.length],
        stack: s.bar && panel.id === "sleep" ? "stages" : undefined,
        barMaxWidth: 8,
        showSymbol: pairs.length < 20,
        symbolSize: 5,
        lineStyle: { width: 1.5 },
        connectNulls: false,
        data: s.bar ? pairs : withGaps(pairs, gap),
      };
    })),
  };
}

const formatNumber = (value, unit) => {
  const rounded = Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return [rounded.toLocaleString("en"), shownUnit(unit)].filter(Boolean).join(" ");
};

/** The pointer's day (or week, or month) and each panel's values there, as lines of text. */
export function readoutAt(panels, time, bucket = "day") {
  const half = BUCKET_MS[bucket] / 2;
  const lines = [];
  let at = null;
  for (const panel of panels) {
    const parts = [];
    for (const s of panel.series) {
      const near = s.points.reduce((best, p) => {
        const d = Math.abs(Date.parse(p.at) - time);
        return d <= half && (!best || d < best.d) ? { p, d } : best;
      }, null);
      if (!near) continue;
      at ??= near.p.at;
      parts.push(panel.series.length > 1 ? `${s.name} ${formatNumber(near.p.value, s.unit)}` : formatNumber(near.p.value, s.unit));
    }
    if (parts.length) lines.push(`${t(`vitals.panel.${panel.id}`)}: ${parts.join(", ")}`);
  }
  if (!at) return { title: t("vitals.readout.none"), lines: [] };
  const date = formatDate(at);
  return { title: bucket === "day" ? date : t(`vitals.readout.${bucket}`, { date }), lines };
}

/** The values of a year of days, and where their middle half lies — what the colours mean. */
export function quartiles(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return null;
  const at = (share) => sorted[Math.min(sorted.length - 1, Math.floor(share * (sorted.length - 1) + 0.5))];
  return { low: sorted[0], q1: at(0.25), median: at(0.5), q3: at(0.75), high: sorted.at(-1) };
}

export function heatmapSummary(heatmap) {
  const q = quartiles(heatmap.days.map(([, value]) => value));
  const span = Math.round((Date.parse(heatmap.to) - Date.parse(heatmap.from)) / DAY_MS) + 1;
  return t("vitals.heatmap.summary", {
    n: heatmap.days.length,
    days: span,
    q1: formatNumber(q.q1, ""),
    q3: formatNumber(q.q3, ""),
    unit: shownUnit(heatmap.unit),
  }).trim();
}

/** A GitHub-style year: one square a day, darker = more. A day without a value stays empty. */
export function heatmapOption(heatmap, { colors }) {
  const q = quartiles(heatmap.days.map(([, value]) => value));
  return {
    animation: false,
    tooltip: {
      formatter: (p) => `${formatDate(p.value[0])}: ${formatNumber(p.value[1], heatmap.unit)}`,
    },
    visualMap: {
      // the year's own lowest to highest: the colours compare days with each other, not with a norm
      min: q.low, max: q.high,
      calculable: false,
      orient: "horizontal", left: "center", bottom: 0, itemHeight: 120, itemWidth: 10,
      text: [t("vitals.heatmap.more"), t("vitals.heatmap.less")],
      inRange: { color: [colors.low, colors.high] },
      textStyle: { color: colors.muted },
    },
    calendar: {
      range: [formatDate(heatmap.from), formatDate(heatmap.to)],
      top: 24, left: 36, right: 8, bottom: 40,
      cellSize: ["auto", 12],
      splitLine: { show: false },
      itemStyle: { color: colors.empty, borderColor: colors.bg, borderWidth: 2 },
      dayLabel: { firstDay: 1, nameMap: ["S", "M", "T", "W", "T", "F", "S"], color: colors.muted, fontSize: 10 },
      monthLabel: { color: colors.muted, fontSize: 10, nameMap: "EN" },
      yearLabel: { show: false },
    },
    series: [{ type: "heatmap", coordinateSystem: "calendar", data: heatmap.days.map(([day, value]) => [formatDate(day), value]) }],
  };
}
