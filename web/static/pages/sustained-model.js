// The Vitals page's "Worth checking" list and the shaded days on the watch's charts (#75), from
// the `sustained` block of /api/v1/vitals. Nothing here touches the page (tests/web_ui.test.mjs).

import { formatDate } from "../components.js";
import { sustainedTranslator } from "./sustained-strings.js";

const DAY_MS = 86400000;

const whole = (value) => String(Math.round(Math.abs(value)));
// "15:05" of an ISO time the API wrote in the user's zone: read as written, not re-zoned
const clock = (iso) => String(iso).slice(11, 16);

function contextChip(item, t) {
  if (item.kind === "workout") {
    const day = formatDate(item.day);
    return item.type && item.minutes
      ? t("context.workout_detail", { day, type: item.type, minutes: item.minutes })
      : t("context.workout", { day });
  }
  if (item.kind === "beta_blocker") return t("context.beta_blocker", { name: item.name || item.atc_code });
  return null;
}

/** One finding as the list says it: a heading, a period, a line per measure, context chips. */
export function findingView(finding, lang = "en") {
  const { t, tn } = sustainedTranslator(lang);
  const chips = finding.context.map((item) => contextChip(item, t)).filter(Boolean);
  if (finding.kind === "minutes") {
    const delta = finding.mean_hr - finding.usual;
    return {
      kind: "minutes",
      title: t("metric.heart_rate"),
      period: t("minutes", {
        date: formatDate(finding.start), from: clock(finding.start), to: clock(finding.end), n: finding.minutes,
      }),
      lines: [t("minutes.line", { mean: whole(finding.mean_hr), delta: whole(delta), usual: whole(finding.usual) })],
      chips,
    };
  }
  const lines = finding.metrics.map((m) => t(m.direction === "up" ? "up" : "down", {
    metric: t(`metric.${m.code}`),
    delta: whole(m.mean_delta),
    usual: whole(m.usual),
    unit: t(`unit.${m.code}`),
    days: tn("days", { n: m.days }),
  }));
  if (finding.together_days) lines.push(tn("together", { n: finding.together_days }));
  return {
    kind: "days",
    title: finding.metrics.map((m) => t(`metric.${m.code}`)).join(t("and")),
    period: `${t("period", { first: formatDate(finding.first_day), last: formatDate(finding.last_day) })} · ${tn("days", { n: finding.days })}`,
    lines,
    chips,
  };
}

/** The list's state: findings, nothing found, or not checked for want of a usual range. */
export function sustainedState(sustained) {
  if (!sustained) return "none";
  if (sustained.findings.length) return "findings";
  const min = sustained.params.min_baseline_days;
  const enough = Object.values(sustained.days_with_values ?? {}).some((n) => n >= min);
  return enough ? "empty" : "not_enough";
}

/** The sentence under the list: how it is found, its thresholds, and what it can't see. */
export function sustainedFootnote(sustained, lang = "en") {
  const { t, tn } = sustainedTranslator(lang);
  const p = sustained.params;
  return t("footnote", {
    baseline: p.baseline_days, days: tn("days", { n: p.run_days }),
    rhr: p.daily.resting_hr?.min_delta ?? "—", hrv: p.daily.hrv?.min_delta ?? "—",
    above: p.hr_above_resting, minutes: p.min_minutes, limits: t("limits"),
  });
}

/** Sentences about what the list can't tell apart: no workouts recorded while the minutes rule ran. */
export function sustainedNotes(sustained, lang = "en") {
  const { t } = sustainedTranslator(lang);
  return sustained.minutes_rule === "checked" && sustained.workouts_recorded === false ? [t("no_workouts")] : [];
}

/** The empty or not-checked sentence. */
export function sustainedEmpty(sustained, lang = "en") {
  const { t, tn } = sustainedTranslator(lang);
  const p = sustained.params;
  return sustainedState(sustained) === "not_enough"
    ? t("not_enough", { min: p.min_baseline_days, days: p.baseline_days })
    : t("empty", { days: tn("days", { n: p.run_days }) });
}

/**
 * The days of each run, per panel of the synchronized chart: [{ panel, from, to }] in ms, the
 * last day included (to = its next midnight). Only the panels that are drawn.
 */
export function shadedRuns(sustained, panels) {
  if (!sustained) return [];
  const panelOf = new Map();
  panels.forEach((panel, i) => panel.series.forEach((s) => panelOf.set(s.code, i)));
  const out = [];
  for (const finding of sustained.findings) {
    if (finding.kind !== "days") continue;
    for (const m of finding.metrics) {
      if (!panelOf.has(m.code)) continue;
      out.push({ panel: panelOf.get(m.code), from: Date.parse(m.first_day), to: Date.parse(m.last_day) + DAY_MS });
    }
  }
  return out;
}

/**
 * The wearable chart's option with the runs shaded: one empty series per shaded panel, carrying
 * the markArea on that panel's axes. The option's own series are left as they are.
 */
export function withShading(option, sustained, panels, { colors, lang = "en", bucket = "day" }) {
  // a run that began before the window is shaded from the window's first day, as BP diaries are
  const start = option.xAxis?.[0]?.min ?? -Infinity;
  const runs = shadedRuns(sustained, panels).filter((run) => run.to > start)
    .map((run) => ({ ...run, from: Math.max(run.from, start) }));
  if (!runs.length) return option;
  const { t } = sustainedTranslator(lang);
  const byPanel = new Map();
  for (const run of runs) byPanel.set(run.panel, [...(byPanel.get(run.panel) ?? []), run]);
  const extra = [...byPanel].map(([panel, list]) => ({
    type: "line",
    name: `sustained-${panel}`,
    xAxisIndex: panel,
    yAxisIndex: panel,
    data: [],
    silent: true,
    markArea: {
      silent: true,
      itemStyle: { color: colors.sustained, borderColor: colors.sustainedEdge, borderWidth: 1 },
      // in a long window a run is a narrow strip: its label would run off it
      label: { show: bucket === "day", position: "insideTopLeft", color: colors.muted, fontSize: 10 },
      data: list.map((run) => [{ xAxis: run.from, name: t("area") }, { xAxis: run.to }]),
    },
  }));
  return { ...option, series: [...option.series, ...extra] };
}
