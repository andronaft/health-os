// The browser UI's logic that needs no browser: run by test_web.py with `node --test`. Made-up
// values only.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  chartRange, filterRows, formatDate, formatRange, formatValue, sortRows, statusKey, statusWord,
} from "../web/static/components.js";
import { PAGES, parseRoute } from "../web/static/pages.js";
import {
  allergyText, coverageLines, diagnosisText, eventDetails, habitText, kindWord, lastPanelText,
  markerHref, medicationText,
  pendingName, pendingNote, profileLine, profileProblems, readoutAt, sparklineOption, staleText,
  tileEmptyLines, tileHeadline, tileNote,
  outNote,
} from "../web/static/pages/overview-model.js";
import {
  baselineText, cellText, detailOption, filterMarkers, historyText, isOutOfRange, pointText,
  qualitative, qualitativeOption, sparkPoints, specimenOptions, specimenWord, tableRows, tn, trendLines,
  unconverted,
} from "../web/static/pages/labs-model.js";
import { printedAs, sourceMeta, sourceTitle } from "../web/static/pages/review-model.js";
import {
  bpKey, bpOption, diaryState, diaryView, heatmapOption, heatmapSummary, panelTitle, pressure, quartiles, readoutAt as vitalsReadout,
  seriesName, wearableOption, wearablePanels, windowLinks, withGaps,
} from "../web/static/pages/vitals-model.js";
import { t } from "../web/static/strings.js";

test("the stored statuses have their own word; 'normal' is shown as 'in range'", () => {
  assert.equal(statusWord("low"), "low");
  assert.equal(statusWord("normal"), "in range");
  assert.equal(statusWord("high"), "high");
  assert.equal(statusWord("critical"), "critical");
  assert.equal(statusWord("pending"), "pending");
});

test("values, ranges and dates as a page shows them", () => {
  assert.equal(formatValue({ value: 3.8, unit: "mmol/L" }), "3.8 mmol/L");
  assert.equal(formatValue({ value: 5, comparator: "<", unit: "mg/L" }), "<5 mg/L");
  assert.equal(formatValue({ value: 0, unit: null }), "0");
  assert.equal(formatValue({ value: null, text: "negative" }), "negative");
  assert.equal(formatValue({ value: null, text: null }), "");
  assert.equal(formatRange({ ref_min: 0, ref_max: 5.2 }), "0–5.2");
  assert.equal(formatRange({ ref_min: null, ref_max: 5.2 }), "≤ 5.2");
  assert.equal(formatRange({ ref_min: 1.2, ref_max: null }), "≥ 1.2");
  assert.equal(formatRange({ ref_min: null, ref_max: null }), "");
  // the offset the API sent decides the date, not this machine's zone: as in get_health_summary
  assert.equal(formatDate("2026-11-01T00:00:00+00:00"), "2026-11-01");
  assert.equal(formatDate("2026-11-01"), "2026-11-01");
  assert.equal(formatDate(null), "");
});

test("the coverage line counts what it can see and never reassures", () => {
  const all = coverageLines({ recorded: 5, in_range: 5, out_of_range: 0, no_range: 0 });
  assert.equal(all.sentence, "5 of 5 recorded markers in range");
  const some = coverageLines({ recorded: 12, in_range: 6, out_of_range: 3, no_range: 3 });
  assert.equal(some.sentence, "6 of 12 recorded markers in range");
  assert.deepEqual(some.rest, ["3 out of range", "3 with no range to compare with"]);
  assert.equal(coverageLines({ recorded: 0, in_range: 0, out_of_range: 0, no_range: 0 }).sentence,
    "No markers recorded yet.");
  for (const text of [all.sentence, ...some.rest, t("overview.coverage.note"), t("overview.out.none", { n: 3 })]) {
    assert.doesNotMatch(text.toLowerCase(), /everything|all normal|healthy|no problems/);
  }
});

test("a missing date of birth or sex says what that breaks", () => {
  assert.deepEqual(profileProblems({ missing: [] }), []);
  for (const missing of [["date_of_birth"], ["sex"], ["date_of_birth", "sex"]]) {
    const problems = profileProblems({ missing }).join(" ");
    assert.match(problems, /Screening/);
    assert.match(problems, /range/i);
    assert.equal(/Date of birth is missing/.test(problems), missing.includes("date_of_birth"));
    assert.equal(/Sex is missing/.test(problems), missing.includes("sex"));
  }
});

test("the profile line leaves out what isn't known", () => {
  assert.equal(profileLine({ age: 41, sex: "female", blood_type: "A", rh_factor: "+", height_cm: 168 }),
    "41 yr · female · blood type A+ · 168 cm");
  assert.equal(profileLine({ age: null, sex: null, blood_type: null, rh_factor: null, height_cm: null }), "");
  assert.equal(profileLine({ age: 0, sex: "other", blood_type: "B", rh_factor: "positive", height_cm: null }),
    "0 yr · other · blood type B positive");
});

test("the user's records read as in get_health_summary, with their doubts", () => {
  assert.equal(allergyText({ allergen: "sample", reaction: "rash", verified: true }), "sample — rash");
  assert.match(allergyText({ allergen: "sample", reaction: null, verified: false }), /unverified/);
  assert.equal(diagnosisText({ diagnosis_name: "Sample", icd10_code: "X1", verification_status: "confirmed" }),
    "Sample [X1]");
  assert.match(diagnosisText({ diagnosis_name: "Sample", icd10_code: null, verification_status: "suspected" }),
    /suspected, not certain/);
  assert.match(diagnosisText({ diagnosis_name: "Sample", icd10_code: null, verification_status: null }),
    /not certain/);
  assert.equal(medicationText({ medication_name: "Sample", dose_amount: 2000, dose_unit: "IU", times_per_day: 1, product_type: "supplement" }),
    "Sample 2000 IU ×1/day (supplement)");
  assert.equal(medicationText({ medication_name: "Sample", dose_amount: null, dose_unit: null, times_per_day: null, product_type: "prescription" }),
    "Sample");
  assert.equal(habitText({ habit_type: "smoking", status: "former", frequency: null, start_date: "2001-01-01", end_date: "2002-02-02" }),
    "smoking — former, since 2001-01-01, until 2002-02-02");
});

test("an unreviewed panel and unrecognized values say so", () => {
  assert.match(lastPanelText({ last_panel: "2026-11-01", last_panel_pending: true }), /2026-11-01.*awaiting review/);
  assert.doesNotMatch(lastPanelText({ last_panel: "2026-11-01", last_panel_pending: false }), /awaiting/);
  assert.match(lastPanelText({ last_panel: null }), /none in the system/);
  assert.match(pendingNote({ critical: true }), /Critical/);
  assert.match(pendingNote({ unverifiable: true }), /critical check impossible/);
  assert.match(pendingNote({ unmapped: true }), /not checked for critical values/);
  assert.equal(pendingNote({}), "");
  assert.equal(pendingName({ unmapped: true, raw_name: "Sample X", name: "Sample X" }), "“Sample X”");
  assert.equal(pendingName({ unmapped: false, raw_name: "ldl", name: "LDL" }), "LDL");
});

test("old checks say when, and an unknown event kind still shows", () => {
  assert.equal(staleText({ name: "Sample", last: "2024-01-02T00:00:00+00:00", months: 34 }),
    "Sample: last on 2024-01-02, about 34 months ago");
  assert.equal(staleText({ name: "Sample", last: null, months: null }), "Sample: never measured in the system");
  assert.equal(kindWord("panel"), "Lab panel");
  assert.equal(kindWord("something_new"), "something_new");
});

const bp = {
  average_days: 7,
  readings: 7,
  unit: "mmHg",
  values: [{ value: 133.3 }, { value: 84.6 }],
  series: [
    { name: "Upper", points: [{ at: "2026-11-01T08:00:00+00:00", value: 130.4 }, { at: "2026-11-03T08:00:00+00:00", value: 133.3 }] },
    { name: "Lower", points: [{ at: "2026-11-01T08:00:00+00:00", value: 80.2 }, { at: "2026-11-03T08:00:00+00:00", value: 84.6 }] },
  ],
};

test("a blood pressure tile reads in whole mmHg and names its average", () => {
  assert.equal(tileHeadline(bp), "133/85");
  assert.equal(tileNote(bp), "7-day average, 7 readings");
  assert.equal(readoutAt(bp, Date.parse("2026-11-01T09:00:00Z")), "2026-11-01: 130/80 mmHg");
  assert.equal(readoutAt(bp, Date.parse("2026-11-05T09:00:00Z")), "2026-11-03: 133/85 mmHg");
});

test("a single-value tile keeps its decimals; an empty one says when there last was a value", () => {
  const weight = { average_days: null, unit: "kg", values: [{ value: 68.45 }], series: [{ points: [{ at: "2026-11-01", value: 68.45 }] }] };
  assert.equal(tileHeadline(weight), "68.45");
  assert.equal(tileNote(weight), "Latest value");
  assert.deepEqual(tileEmptyLines({ last_recorded: null }, 30), ["No values in the last 30 days."]);
  assert.deepEqual(
    tileEmptyLines({ last_recorded: { values: [72], unit: "bpm", at: "2025-03-01T00:00:00+00:00" } }, 30),
    ["No values in the last 30 days.", "Last recorded: 72 bpm on 2025-03-01."]);
});

test("a sparkline spans the whole window, and sparse data gets dots", () => {
  const window = { from: "2026-10-05T00:00:00+00:00", to: "2026-11-04T00:00:00+00:00" };
  const option = sparklineOption(bp, window);
  assert.equal(option.xAxis.min, Date.parse(window.from));
  assert.equal(option.xAxis.max, Date.parse(window.to));
  assert.equal(option.series.length, 2);
  assert.deepEqual(option.series[0].data.map((point) => point.symbol), ["circle", "circle"]);
  assert.equal(option.series[0].data[1].value[1], 133.3);
  const points = Array.from({ length: 14 }, (_, i) => ({ at: `2026-10-${10 + i}T08:00:00+00:00`, value: i }));
  const symbols = sparklineOption({ series: [{ name: "x", points }] }, window).series[0].data.map((point) => point.symbol);
  assert.equal(symbols.filter((symbol) => symbol === "circle").length, 1);
  assert.equal(symbols.at(-1), "circle");
});

test("a missing or unrecognised status never passes as in range", () => {
  for (const status of [null, undefined, "", "NORMAL", "ok", "constructor", "__proto__"]) {
    assert.equal(statusKey(status), "unknown");
    assert.notEqual(statusWord(status), statusWord("normal"));
  }
});

const value = { key: "value" };
const values = (rows) => rows.map((row) => row.value);

test("numbers sort as numbers, not as text", () => {
  const rows = [{ value: 10 }, { value: 9 }, { value: 100 }];
  assert.deepEqual(values(sortRows(rows, value)), [9, 10, 100]);
  assert.deepEqual(values(sortRows(rows, value, "desc")), [100, 10, 9]);
});

test("missing values go last in both directions", () => {
  const rows = [{ value: null }, { value: 2 }, { value: undefined }, { value: 1 }, { value: "" }];
  assert.deepEqual(values(sortRows(rows, value)).slice(0, 2), [1, 2]);
  assert.deepEqual(values(sortRows(rows, value, "desc")).slice(0, 2), [2, 1]);
});

test("text sorts with numbers inside it in order, and equal rows keep their order", () => {
  const rows = [{ value: "b10", n: 1 }, { value: "b9", n: 2 }, { value: "a", n: 3 }, { value: "B9", n: 4 }];
  assert.deepEqual(sortRows(rows, value).map((row) => row.n), [3, 2, 4, 1]);
  assert.deepEqual(sortRows(rows, value, "desc").map((row) => row.n), [1, 2, 4, 3]);
});

test("sorting leaves the original rows alone and can use a column's value()", () => {
  const rows = [{ a: { n: 2 } }, { a: { n: 1 } }];
  const sorted = sortRows(rows, { key: "a", value: (row) => row.a.n });
  assert.equal(sorted[0].a.n, 1);
  assert.equal(rows[0].a.n, 2);
});

const columns = [
  { key: "name" },
  { key: "status", text: (row) => statusWord(row.status) },
  { key: "note" },
];
const rows = [
  { name: "Sample Alpha", status: "normal", note: null },
  { name: "Sample Núñez", status: "high", note: "fasting" },
  { name: "Other", status: "pending" },
];
const names = (found) => found.map((row) => row.name);

test("the filter ignores case and accents, and an empty query shows everything", () => {
  assert.deepEqual(names(filterRows(rows, columns, "NUNEZ")), ["Sample Núñez"]);
  assert.equal(filterRows(rows, columns, "   ").length, 3);
});

test("every word of the query must match, in any column", () => {
  assert.deepEqual(names(filterRows(rows, columns, "sample high")), ["Sample Núñez"]);
  assert.deepEqual(names(filterRows(rows, columns, "other high")), []);
});

test("the filter sees a status by its word, and blanks don't match as 'null'", () => {
  assert.deepEqual(names(filterRows(rows, columns, "in range")), ["Sample Alpha"]);
  assert.deepEqual(filterRows(rows, columns, "null"), []);
  assert.deepEqual(filterRows(rows, columns, "undefined"), []);
});

test("routes", () => {
  assert.equal(parseRoute("").page.id, "overview");
  assert.equal(parseRoute("#/").page.id, "overview");
  assert.equal(parseRoute("#/labs").page.id, "labs");
  assert.deepEqual(parseRoute("#/labs/a%20b/").args, ["a b"]);
  assert.equal(parseRoute("#/nope").page, undefined);
  assert.equal(parseRoute("#/%E0%A4%A").page, undefined); // malformed escape: not a crash
  assert.equal(parseRoute("#main"), null); // the skip link
});

test("every page has a title in the table, and t() fills in values", () => {
  for (const page of PAGES) assert.notEqual(t(page.title), page.title);
  assert.equal(t("table.count", { shown: 0, total: 3 }), "0 of 3 rows");
  assert.equal(t("no.such.key"), "no.such.key");
});

// ---- Labs (#55) -------------------------------------------------------------------------------

const point = (at, value, extra = {}) => ({
  at,
  value,
  original: { value, comparator: null, text: null, unit: "mmol/L", ref_min: 3.9, ref_max: 5.6 },
  range: { min: 3.9, max: 5.6, unconverted: false },
  status: "normal",
  pending: false,
  ...extra,
});

const marker = (code, status, specimen = "serum") => ({ code, name: code, status, specimen, spark: [] });

test("the out-of-range filter keeps low, high and critical; the specimen filter one specimen", () => {
  const markers = [marker("a", "normal"), marker("b", "high"), marker("c", "low", "whole_blood"),
    marker("d", "critical"), marker("e", null, null)];
  assert.deepEqual(filterMarkers(markers, { outOfRangeOnly: true }).map((m) => m.code), ["b", "c", "d"]);
  assert.deepEqual(filterMarkers(markers, { specimen: "whole_blood" }).map((m) => m.code), ["c"]);
  assert.deepEqual(filterMarkers(markers, { specimen: "" }).length, 5);
  assert.equal(isOutOfRange(marker("x", undefined)), false); // no status is not "out of range" …
  assert.equal(specimenWord(null), "Other"); // … and no specimen is still a group
  assert.equal(specimenWord("whole_blood"), "Whole blood");
  assert.equal(specimenWord("sweat"), "sweat"); // added later: its code, not a key
  assert.deepEqual(specimenOptions(markers).map((o) => o.code), ["", "serum", "whole_blood"]);
});

test("the history column counts values and says since when", () => {
  assert.equal(historyText({ n: 5, first_at: "2024-05-31T00:00:00+00:00" }), "5 since 2024-05-31");
  assert.equal(historyText({ n: 1, first_at: "2026-01-02T00:00:00+00:00", at: "2026-01-02T00:00:00+00:00" }), "1, on 2026-01-02");
});

test("sparkline points: by date across, higher values up, a flat or single series in the middle", () => {
  const pts = sparkPoints([{ at: "2026-01-01", value: 1 }, { at: "2026-01-03", value: 3 }, { at: "2026-01-02", value: 2 }], 100, 20, 0);
  assert.deepEqual(pts, [[0, 20], [100, 0], [50, 10]]);
  assert.deepEqual(sparkPoints([{ at: "2026-01-01", value: 7 }], 100, 20), [[50, 10]]);
  assert.deepEqual(sparkPoints([{ at: "2026-01-01", value: 7 }, { at: "2026-01-02", value: 7 }], 100, 20, 0).map(([, y]) => y), [10, 10]);
  assert.deepEqual(sparkPoints([], 100, 20), []);
});

test("a matrix cell shows the value without its unit, with its comparator", () => {
  assert.equal(cellText({ value: 5.2, comparator: null, text: null, unit: "mmol/L" }), "5.2");
  assert.equal(cellText({ value: 5, comparator: "<", unit: "mg/L" }), "<5");
  assert.equal(cellText({ value: null, text: "negative", unit: null }), "negative");
  assert.equal(cellText(undefined), "");
});

test("the trend says what it was computed on, and nothing with too few values", () => {
  const base = { n: 6, min_n: 5, from: "2024-01-01 00:00:00+00:00", to: "2026-01-01 00:00:00+00:00" };
  assert.deepEqual(trendLines({ ...base, direction: "increasing", p: 0.0123, slope_per_year: 0.21345 }, "mmol/L"), [
    "Rising over 6 approved values, from 2024-01-01 to 2026-01-01.",
    "Mann-Kendall test: p ≈ 0.012.",
    "Theil–Sen slope: +0.213 mmol/L per year.",
  ]);
  assert.equal(trendLines({ ...base, direction: "decreasing", p: 0.0001, slope_per_year: -2 }, "g/L")[1], "Mann-Kendall test: p < 0.001.");
  assert.equal(trendLines({ ...base, direction: "decreasing", p: 0.0001, slope_per_year: -2 }, "g/L")[2], "Theil–Sen slope: -2 g/L per year.");
  assert.match(trendLines({ ...base, direction: "no_trend", p: 0.4, slope_per_year: 0 }, "x")[0], /^No statistically significant change/);
  assert.deepEqual(trendLines({ ...base, n: 2, direction: "no_trend", p: null, slope_per_year: null }, "x"),
    ["Not enough approved values for a trend: 2, at least 5 are needed."]);
  assert.deepEqual(trendLines(null, "x"), ["Not enough approved values for a trend: 0, at least 5 are needed."]);
});

test("the baseline is described as your own history, or says why there is none", () => {
  assert.equal(baselineText({ n: 3, min_n: 5, mean: null, low: null, high: null, sigmas: 2 }, "mmol/L"),
    "A personal baseline needs at least 5 approved values; there are 3.");
  assert.equal(baselineText({ n: 6, min_n: 5, mean: 5.0, low: 4.4, high: 5.6, sigmas: 2 }, "mmol/L"),
    "Mean ± 2σ of your approved values: 4.4–5.6 mmol/L (mean 5, 6 values).");
  assert.match(t("labs.baseline.note"), /not what is healthy/);
});

test("the tooltip gives the form's value and range, and says a pending value is not a fact", () => {
  const converted = point("2026-01-02T00:00:00+00:00", 5.27, {
    original: { value: 95, comparator: null, text: null, unit: "mg/dL", ref_min: 70, ref_max: 100 },
    range: { min: 3.89, max: 5.55, unconverted: false },
  });
  assert.equal(pointText(converted, "mmol/L"),
    "2026-01-02: 5.27 mmol/L\non the form: 95 mg/dL\nrange on the form: 70–100 mg/dL\nin range");
  // same unit: no "on the form" line repeating the value
  assert.equal(pointText(point("2026-01-02", 5, { status: "high" }), "mmol/L"),
    "2026-01-02: 5 mmol/L\nrange on the form: 3.9–5.6 mmol/L\nhigh");
  const pending = point("2026-01-03", 2, { pending: true, status: "low" });
  assert.match(pointText(pending, "mmol/L"), /pending: not reviewed, not a fact yet$/);
  assert.doesNotMatch(pointText(pending, "mmol/L"), /\blow\b/);
  const noRange = point("2026-01-04", 5, { original: { value: 5, unit: "mmol/L", ref_min: null, ref_max: null }, range: null });
  assert.match(pointText(noRange, "mmol/L"), /no range on the form/);
  const odd = point("2026-01-05", 5, { range: { min: null, max: null, unconverted: true } });
  assert.match(pointText(odd, "mmol/L"), /cannot be drawn in this unit/);
});

test("the detail chart: a band per approved point, pending values hollow and apart", () => {
  const data = {
    name: "Glucose",
    unit: "mmol/L",
    points: [
      point("2026-01-01", 5.0, { range: { min: 3.9, max: 5.6, unconverted: false } }),
      point("2026-02-01", 5.4, { range: { min: 4.1, max: null, unconverted: false } }),
      point("2026-03-01", 5.1, { range: { min: null, max: null, unconverted: true } }),
      point("2026-04-01", null, { original: { value: 95, unit: "furlongs" } }), // not convertible
    ],
    pending: [point("2026-05-01", 9.9, { pending: true })],
    baseline: { n: 3, min_n: 5, mean: null, low: null, high: null, sigmas: 2 },
  };
  const option = detailOption(data, { colors: { band: "green", baseline: "orange", pending: "grey" } });
  const [line, bands, pending] = option.series;
  assert.ok(line.z > bands.z); // the values are drawn over the ranges
  // ranges differ between labs: one band per point, at that point, never one for the whole chart
  assert.deepEqual(bands.data.map(([x, low, high]) => [x, low, Number.isNaN(high) ? "open" : high]), [
    [Date.parse("2026-01-01"), 3.9, 5.6],
    [Date.parse("2026-02-01"), 4.1, "open"],
  ]);
  assert.equal(bands.silent, true);
  assert.deepEqual(line.data.map((d) => d.value[1]), [5.0, 5.4, 5.1]);
  assert.equal(detailOption(data, { baseline: true }).series[0].markArea, undefined); // too few values
  // hollow on any background: no fill, a grey ring
  assert.deepEqual(pending.itemStyle, { color: "transparent", borderColor: "grey", borderWidth: 2 });
  assert.equal(pending.label.formatter, "unverified");
  assert.deepEqual(pending.data.map((d) => d.value[1]), [9.9]);
  assert.ok(line.data.every((d) => !d.point.pending) && pending.data.every((d) => d.point.pending));
  assert.equal(option.yAxis.name, "mmol/L");
  assert.match(option.tooltip.formatter({ data: pending.data[0] }), /not a fact/);
  assert.equal(unconverted(data.points).length, 1);
});

test("the baseline goes on the chart only when asked and when there is one", () => {
  const data = {
    name: "Glucose",
    unit: "mmol/L",
    points: [point("2026-01-01", 5.0)],
    pending: [],
    baseline: { n: 6, min_n: 5, mean: 5.0, low: 4.4, high: 5.6, sigmas: 2 },
  };
  assert.equal(detailOption(data).series[0].markArea, undefined);
  const on = detailOption(data, { baseline: true, colors: { band: "g", baseline: "o" } }).series[0];
  assert.deepEqual(on.markArea.data, [[{ yAxis: 4.4 }, { yAxis: 5.6 }]]);
  assert.deepEqual(on.markLine.data, [{ yAxis: 5.0 }]);
  assert.equal(detailOption(data).series.length, 2); // no pending series when nothing is pending
});

test("text results go on a categorical axis; the values table is newest first", () => {
  const text = (at, value, pending = false) => ({ at, value: null, pending, original: { value: null, text: value }, status: null });
  const data = { name: "HBsAg", unit: null, points: [text("2025-01-01", "negative"), text("2026-01-01", "positive")], pending: [text("2026-06-01", "negative", true)] };
  assert.equal(qualitative(data.points).length, 2);
  const option = qualitativeOption(data, { colors: { pending: "grey" } });
  assert.deepEqual(option.yAxis.data, ["negative", "positive"]);
  assert.equal(option.series[1].itemStyle.color, "transparent");
  assert.deepEqual(tableRows(data).map((row) => row.at), ["2026-06-01", "2026-01-01", "2025-01-01"]);
});

test("counts read as one or many", () => {
  assert.equal(tn("labs.pending_note", { n: 1 }).startsWith("1 lab value is"), true);
  assert.equal(tn("labs.pending_note", { n: 2 }).startsWith("2 lab values are"), true);
  assert.equal(tn("labs.detail.unconverted", { n: 1, unit: "g/L" }).startsWith("1 value could not"), true);
});

// ---- small charts don't exaggerate; events and links -----------------------------------------

test("a small chart's axis spans at least 5% of the values, so a tiny change stays small", () => {
  const [low, high] = chartRange([68.35, 68.4]);
  assert.ok(high - low >= 68.375 * 0.05 - 1e-9);
  assert.ok(low < 68.35 && high > 68.4);
  assert.deepEqual(chartRange([1, 3, 2]), [1, 3]); // a real change keeps its own range
  assert.deepEqual(chartRange([0, 0]), [0, 0]); // nothing to scale: flat, on the middle line
  assert.equal(chartRange([]), null);
  assert.deepEqual(chartRange([NaN, 5, 5]).map((n) => Math.round(n * 1000) / 1000), [4.875, 5.125]);
  // the weight tile from the demo: 68.35 → 68.4 kg was drawn as a line across the whole height
  const tile = { series: [{ name: "Weight", points: [{ at: "2026-11-11", value: 68.35 }, { at: "2026-11-18", value: 68.4 }] }] };
  const { yAxis } = sparklineOption(tile, { from: "2026-10-19", to: "2026-11-18" });
  assert.ok(yAxis.max - yAxis.min > 3);
  // and the Labs table's sparkline: HDL 1.5 → 1.3 is a slope, not top to bottom
  const ys = sparkPoints([{ at: "2025-01-01", value: 1.5 }, { at: "2026-01-01", value: 1.48 }], 100, 20, 0).map(([, y]) => y);
  assert.ok(Math.abs(ys[0] - ys[1]) < 20);
});

test("a lab panel in the events says its size and what is out of range", () => {
  assert.equal(eventDetails({ kind: "panel", title: null, values: 6, out_of_range: 2, pending: false }), "6 values, 2 out of range");
  assert.equal(eventDetails({ kind: "panel", title: null, values: 6, out_of_range: 0, pending: false }), "6 values");
  // under review: its size only; "out of range" of unreviewed values would read as a fact
  assert.equal(eventDetails({ kind: "panel", title: null, values: 2, out_of_range: 1, pending: true }), "2 values");
  assert.equal(eventDetails({ kind: "panel", title: "Lipid panel", values: 4, out_of_range: 1 }), "Lipid panel");
  assert.equal(eventDetails({ kind: "diagnosis", title: "Hypercholesterolemia", values: null }), "Hypercholesterolemia");
  assert.equal(eventDetails({ kind: "visit", title: null }), "");
});

test("only a lab marker's name links to its Labs page", () => {
  assert.equal(markerHref({ code: "ldl", category: "lab" }), "#/labs/ldl");
  assert.equal(markerHref({ code: "systolic_bp", category: "vital" }), null);
  assert.equal(markerHref({ code: "a b", category: "lab" }), "#/labs/a%20b");
});

test("a value given only as a limit says why the critical check is impossible", () => {
  assert.equal(pendingNote({ unverifiable: true, limit: true }), "Only a limit on the form: critical check impossible");
  assert.equal(pendingNote({ unverifiable: true, limit: false }), "Unit not recognized: critical check impossible");
  assert.equal(pendingNote({ critical: true, limit: true }), "Critical: see the top of this page");
});

test("an out-of-range row says how long it has been out of range and if a newer value waits", () => {
  assert.equal(outNote({ streak: 3, since: "2024-12-01", newer_pending: false }), `Out of range 3 times in a row, since ${formatDate("2024-12-01")}`);
  assert.equal(outNote({ streak: 1, since: "2026-01-01", newer_pending: false }), "");
  assert.equal(outNote({ streak: 1, since: "2026-01-01", newer_pending: true }), "A newer value is under review");
  assert.equal(outNote({ streak: null, since: null, newer_pending: false }), ""); // a vital: no run
});

// ---- Review queue (#58) -----------------------------------------------------------------------

const staging = (extra = {}) => ({
  source_id: "00000000-0000-0000-0000-000000000001",
  channel: "mcp",
  staged_at: "2026-11-18T10:00:00+00:00",
  panel_date: "2026-11-17",
  panel_type: null,
  facility: "Demo Lab",
  document: null,
  total: 3,
  unmapped: 0,
  alarming: 0,
  ...extra,
});

test("a staging is named by its panel, its lab and its document", () => {
  assert.equal(sourceTitle(staging()), "Lab panel, 2026-11-17 · Demo Lab");
  assert.equal(sourceTitle(staging({ panel_type: "Lipids", document: "scan.pdf" })), "Lipids, 2026-11-17 · Demo Lab · scan.pdf");
  assert.equal(sourceTitle(staging({ panel_date: null, facility: null })), "Staged on 2026-11-18");
});

test("a staging says how many values, how many unrecognized and how many cannot wait", () => {
  assert.equal(sourceMeta(staging()), "3 values · staged 2026-11-18 via mcp");
  assert.equal(sourceMeta(staging({ total: 1, unmapped: 1, alarming: 1, channel: null })),
    "1 value · 1 not recognized · 1 cannot wait · staged 2026-11-18");
});

test("the printed name shows only when the marker it was matched to is named otherwise", () => {
  assert.equal(printedAs({ raw_name: "Калій", name: "Potassium", unmapped: false }), "on the form: “Калій”");
  assert.equal(printedAs({ raw_name: "potassium ", name: "Potassium", unmapped: false }), "");
  assert.equal(printedAs({ raw_name: "Mystery", name: "Mystery", unmapped: true }), "");
  assert.equal(printedAs({ raw_name: null, name: "Potassium", unmapped: false }), "");
});

test("the review page loads", () => {
  assert.ok(PAGES.find((page) => page.id === "review").load);
  assert.equal(parseRoute("#/review").page.id, "review");
});

// ---- Vitals (#56) ---------------------------------------------------------------------------------

const PROTOCOL = {
  morning: [4, 12], evening: [16, 24], max_days: 7, min_days: 3, readings_per_session: 2,
  threshold: { systolic: 135, diastolic: 85 }, source: { label: "ESH 2021", url: "https://example.org" },
};
const COLORS = {
  morning: "#1", evening: "#2", muted: "#3", c1: "#a", c2: "#b", c3: "#c", c4: "#d", area: "#e",
  low: "#f", high: "#g", empty: "#h", bg: "#i",
};
const diary = (extra = {}) => ({
  first_day: "2026-11-19", last_day: "2026-11-25", days: 7, earlier_days: 0, complete_days: 7,
  counted_days: 6, sessions: 14, full_sessions: 14, other_readings: 0, followed: true,
  mean: {
    systolic: 133.5, diastolic: 83.04, n: 24, from_day: "2026-11-20",
    morning: { systolic: 135.5, diastolic: 85.8, n: 12 }, evening: { systolic: 131.4, diastolic: 80.3, n: 12 },
  },
  ...extra,
});

test("the window switch offers the API's windows and marks the current one", () => {
  const links = windowLinks({ days: 90, options: [7, 30, 90, 365] });
  assert.deepEqual(links.map((l) => l.href), ["#/vitals/7", "#/vitals/30", "#/vitals/90", "#/vitals/365"]);
  assert.deepEqual(links.filter((l) => l.current).map((l) => l.days), [90]);
  assert.equal(links[3].label, "1 year");
});

test("blood pressure is shown in whole mmHg", () => {
  assert.equal(pressure({ systolic: 133.5, diastolic: 83.04 }), "134/83");
  assert.equal(pressure({ systolic: 133, diastolic: null }), "133/—");
  assert.equal(pressure(null), "—");
});

test("a followed diary has a mean; one that wasn't says why there is none", () => {
  const followed = diaryView(diary(), PROTOCOL);
  assert.equal(followed.mean, "134/83");
  assert.equal(followed.verdict, "Protocol followed");
  assert.match(followed.meanNote, /24 morning and evening readings from 2026-11-20; the first day is left out/);
  assert.equal(followed.sessions, "Morning 136/86 · evening 131/80 mmHg");
  const missed = diaryView(diary({
    followed: false, mean: null, complete_days: 2, counted_days: 1, other_readings: 2, earlier_days: 3,
  }), PROTOCOL);
  assert.equal(missed.mean, null);
  assert.equal(missed.verdict, "Protocol not followed");
  assert.match(missed.noMean, /needs 3 complete days after the first one, and this diary has 1/);
  assert.ok(missed.lines.some((line) => line.includes("2 readings taken outside")));
  assert.ok(missed.lines.some((line) => line.includes("3 earlier days")));
});

test("a diary whose values have no time of day is not judged, and its mean says what it is", () => {
  const dated = {
    first_day: "2026-06-28", last_day: "2026-07-02", days: 5, earlier_days: 0, timing: "unrecorded",
    followed: null, value_days: 5, untimed_readings: 10, incomplete_readings: 0,
    mean: { systolic: 136.4, diastolic: 83.6, n: 8, days: 4, from_day: "2026-06-29" },
  };
  assert.equal(diaryState(dated), "unrecorded");
  const view = diaryView(dated, PROTOCOL);
  assert.equal(view.verdict, "Time of day not recorded");
  assert.equal(view.icon, "?");
  assert.equal(view.followed, false);
  assert.equal(view.mean, "136/84");
  assert.match(view.meanNote, /Plain mean of 8 values on 4 days from 2026-06-29.*Not a protocol check/);
  assert.equal(view.sessions, null);
  assert.match(view.lines[0], /10 values on 5 days, each with a date but no time/);
  assert.ok(!view.lines.some((line) => line.includes("morning and 2 evening")));
  assert.equal(diaryView({ ...dated, mean: null }, PROTOCOL).noMean, "No mean: only the first day has values.");
});

test("incomplete readings and readings without a time in a timed diary are said, not used", () => {
  const view = diaryView(diary({ incomplete_readings: 2, untimed_readings: 3 }), PROTOCOL);
  assert.ok(view.lines.includes("2 readings with only a systolic or only a diastolic value are not used"));
  assert.ok(view.lines.includes("3 readings without a time of day are not used"));
  assert.equal(diaryState(diary({ followed: false })), "not_followed");
});

test("a diary that followed the protocol but somehow has no mean shows none", () => {
  assert.equal(diaryView(diary({ mean: null }), PROTOCOL).mean, null);
});

test("lines break across gaps instead of bridging them", () => {
  assert.deepEqual(withGaps([[0, 1], [1, 2], [10, 3]], 5), [[0, 1], [1, 2], [5.5, null], [10, 3]]);
  assert.deepEqual(withGaps([], 5), []);
});

const window = { days: 30, from: "2026-10-27", to: "2026-11-25", bucket: "day" };
const reading = (at, session, systolic, diastolic) => ({ at, session, systolic, diastolic, n: 1 });

test("the BP chart: sessions apart, the threshold labelled, the diaries shaded", () => {
  const bp = {
    points: [reading("2026-11-20T07:05:00+00:00", "morning", 136, 86), reading("2026-11-20T21:05:00+00:00", "evening", 130, 80),
      reading("2026-11-05T14:30:00+00:00", "other", 128, 80), reading("2026-11-10", "untimed", 138, 86)],
    diaries: [diary(), diary({ first_day: "2026-08-01", last_day: "2026-08-04", followed: false })],
    protocol: PROTOCOL,
  };
  const option = bpOption(bp, window, { colors: COLORS });
  const names = option.series.map((s) => s.name);
  assert.ok(names.includes("Morning systolic") && names.includes("Evening diastolic") && names.includes("Other time, systolic"));
  assert.equal(option.series.find((s) => s.name === "Other time, systolic").type, "scatter");
  const dated = option.series.find((s) => s.name === "No time of day, systolic");
  assert.equal(dated.type, "scatter");
  assert.match(dated.data[0].tip, /^2026-11-10\nTime of day not recorded: 138\/86 mmHg$/);
  const threshold = option.series.at(-1);
  assert.deepEqual(threshold.markLine.data.map((d) => d.yAxis), [135, 85]);
  assert.equal(threshold.markLine.data[0].name, "ESH home threshold 135");
  assert.equal(threshold.markArea.data.length, 1); // the August diary is outside the window
  const morning = option.series.find((s) => s.name === "Morning systolic");
  assert.match(morning.data[0].tip, /Morning: 136\/86 mmHg/);
  assert.deepEqual(bpKey(bp.points).sessions.map((k) => k.label), ["Morning", "Evening", "Other time of day", "Time of day not recorded"]);
  assert.deepEqual(bpKey(bp.points.slice(0, 1)).sessions.map((k) => k.session), ["morning"]);
  // the axis always reaches both threshold lines
  assert.equal(option.yAxis.min({ min: 120, max: 130 }), 80);
  assert.equal(option.yAxis.max({ min: 120, max: 130 }), 140);
});

const day = (at, value) => ({ at, value, n: 1 });
const wearables = [
  { code: "sleep_duration", name: "Sleep duration", unit: "h", days: 2, points: [day("2026-11-24", 7.2), day("2026-11-25", 6.8)] },
  { code: "sleep_deep", name: "Deep sleep", unit: "h", days: 2, points: [day("2026-11-24", 1.2), day("2026-11-25", 1.0)] },
  { code: "hrv", name: "Heart rate variability", unit: "ms", days: 1, points: [day("2026-11-25", 48)] },
  { code: "sleep_score", name: "Sleep score", unit: "score", days: 1, points: [day("2026-11-24", 81)] },
  { code: "steps", name: "Steps", unit: "steps", days: 1, points: [day("2026-11-25", 10234)] },
];

test("panels appear only for measures with values, in a fixed order", () => {
  const panels = wearablePanels(wearables, null);
  assert.deepEqual(panels.map((p) => p.id), ["sleep", "sleep_score", "hrv", "steps"]);
  assert.deepEqual(panels[0].series.map((s) => [s.name, s.bar]), [["Total", false], ["Deep", true]]);
  assert.equal(panelTitle(panels[0]), "Sleep (h)");
  assert.equal(panelTitle(panels[1]), "Sleep score"); // a score is no unit
  assert.deepEqual(wearablePanels([], null), []);
  assert.equal(seriesName({ code: "unknown_code", name: "Its own name" }), "Its own name");
});

test("training load becomes its own panel with two lines", () => {
  const load = {
    unit: "min", acute_days: 7, chronic_days: 28,
    lines: [{ key: "acute", points: [day("2026-11-25", 30)] }, { key: "chronic", points: [] }],
  };
  const [panel] = wearablePanels([], load);
  assert.equal(panel.id, "load");
  assert.deepEqual(panel.series.map((s) => s.name), ["Acute (7-day mean)"]); // an empty line is left out
});

test("the synchronized chart: one grid per panel, one shared zoom and pointer", () => {
  const panels = wearablePanels(wearables, null);
  const option = wearableOption(panels, window, { colors: COLORS });
  assert.equal(option.grid.length, 4);
  assert.deepEqual(option.dataZoom.map((z) => z.xAxisIndex), [[0, 1, 2, 3], [0, 1, 2, 3]]);
  assert.deepEqual(option.axisPointer.link, [{ xAxisIndex: "all" }]);
  assert.deepEqual(option.xAxis.map((x) => x.axisLabel.show), [false, false, false, true]);
  const deep = option.series.find((s) => s.name === "Deep");
  assert.equal(deep.type, "bar");
  assert.equal(deep.stack, "stages");
  assert.equal(option.series.find((s) => s.name === "Steps").type, "bar");
});

test("the readout spells out every panel's value at the pointer", () => {
  const panels = wearablePanels(wearables, null);
  const at = vitalsReadout(panels, Date.parse("2026-11-25"));
  assert.equal(at.title, "2026-11-25");
  assert.deepEqual(at.lines, ["Sleep: Total 6.8 h, Deep 1 h", "HRV: 48 ms", "Steps: 10,234 steps"]);
  assert.equal(vitalsReadout(panels, Date.parse("2026-01-01")).title, "No value at this point");
  const weekly = vitalsReadout(panels, Date.parse("2026-11-26"), "week");
  assert.equal(weekly.title, "Week of 2026-11-25");
});

const heatmap = {
  code: "steps", name: "Steps", unit: "steps", from: "2025-11-26", to: "2026-11-25",
  days: [["2026-11-23", 4000], ["2026-11-24", 8000], ["2026-11-25", 12000], ["2026-11-22", 6000]],
};

test("quartiles and the heatmap's own summary", () => {
  assert.deepEqual(quartiles([4, 1, 3, 2, 5]), { low: 1, q1: 2, median: 3, q3: 4, high: 5 });
  assert.equal(quartiles([]), null);
  assert.equal(heatmapSummary(heatmap), "4 of 365 days have a value; the middle half lies between 6,000 and 8,000 steps");
  assert.equal(heatmapSummary({ ...heatmap, unit: "score" }), "4 of 365 days have a value; the middle half lies between 6,000 and 8,000");
});

test("the heatmap is a calendar of the year, coloured from its own lowest to highest day", () => {
  const option = heatmapOption(heatmap, { colors: COLORS });
  assert.deepEqual(option.calendar.range, ["2025-11-26", "2026-11-25"]);
  assert.equal(option.visualMap.min, 4000);
  assert.equal(option.visualMap.max, 12000);
  assert.equal(option.series[0].coordinateSystem, "calendar");
  assert.equal(option.series[0].data.length, 4); // a day without a value is not sent as zero
});

test("the vitals page loads", () => {
  assert.ok(PAGES.find((page) => page.id === "vitals").load);
  assert.deepEqual(parseRoute("#/vitals/365").args, ["365"]);
});
