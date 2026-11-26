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
import {
  allergyDetail, changeShort, changeText, diagnosisDetail, footerText, groupDiagnoses, loadQuestions,
  medicationDetail, methodText, miniChart, outLead, percentText, profileLine as reportProfile, reportDate, reportRange,
  reportUnit, reportValue, resultChange, saveQuestions, streakText, trendSpan, QUESTIONS_KEY,
  changesNote, noOtherChanges, stoppedMedications, truncatedText,
} from "../web/static/pages/report-model.js";
import { DICTIONARIES, REPORT_LANGS, translator } from "../web/static/pages/report-strings.js";
import {
  amount, amountText, coverageText, dailyValues, energyOption, flagStatus, flagged, mealNote, mealTypeWord,
  normText, pctText, routeDays, sodiumOption, sourceText, timeOf, windowDates,
} from "../web/static/pages/food-model.js";
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

// ---- where a value comes from (the drawer) and the range bar (#64) ----------------------------
import { BAND_FROM, BAND_TO, rangeBar, rangePosition, trackDomain } from "../web/static/pages/range-model.js";
import {
  canonicalRangeText, conversionText, defaultRangeText, documentText, panelText, rangeStatusText, rangeText,
  reviewLines, valueCellView,
} from "../web/static/pages/observation-model.js";

test("the range bar: below, inside, above, with the range in the middle of the track", () => {
  const range = { ref_min: 3.9, ref_max: 5.6, unit: "mmol/L" };
  const inside = rangeBar({ ...range, value: 5 });
  assert.equal(inside.kind, "bar");
  assert.equal(inside.position, "inside");
  assert.deepEqual([inside.band.from, inside.band.to], [BAND_FROM, BAND_TO]);
  assert.ok(inside.at > inside.band.from && inside.at < inside.band.to);
  assert.equal(inside.clamped, null);
  assert.equal(inside.label, "5 mmol/L: inside the range 3.9–5.6 mmol/L");
  assert.equal(rangeBar({ ...range, value: 3.1 }).position, "below");
  assert.equal(rangeBar({ ...range, value: 6.2 }).position, "above");
  assert.equal(rangeBar({ ...range, value: 6.2 }).clamped, null);
  // on a limit is inside, as core.normalize.compute_status says
  assert.equal(rangeBar({ ...range, value: 5.6 }).position, "inside");
  assert.equal(rangeBar({ ...range, value: 3.9 }).position, "inside");
});

test("the range bar: a value far outside is clamped to the edge and says so", () => {
  const far = rangeBar({ value: 60, unit: "mmol/L", ref_min: 3.9, ref_max: 5.6 });
  assert.equal(far.position, "above");
  assert.equal(far.at, 100);
  assert.equal(far.clamped, "high");
  assert.match(far.label, /above the range.*far above/);
  const low = rangeBar({ value: -40, ref_min: 3.9, ref_max: 5.6 });
  assert.deepEqual([low.at, low.clamped, low.position], [0, "low", "below"]);
});

test("the range bar: a missing min or max is an open side of the band", () => {
  const onlyMax = rangeBar({ value: 3.8, unit: "mmol/L", ref_min: null, ref_max: 3.0 });
  assert.equal(onlyMax.position, "above");
  assert.deepEqual([onlyMax.band.from, onlyMax.band.to, onlyMax.band.openLow, onlyMax.band.openHigh],
    [0, BAND_TO, true, false]);
  assert.equal(onlyMax.label, "3.8 mmol/L: above the range ≤ 3 mmol/L");
  const onlyMin = rangeBar({ value: 1.2, ref_min: 1.0, ref_max: null });
  assert.equal(onlyMin.position, "inside");
  assert.deepEqual([onlyMin.band.from, onlyMin.band.to, onlyMin.band.openHigh], [BAND_FROM, 100, true]);
  assert.equal(rangeBar({ value: 0.8, ref_min: 1.0, ref_max: null }).position, "below");
  // a range with no width, and limits at or below zero, still give a track
  assert.deepEqual(trackDomain(5, 5), [0, 10]);
  assert.deepEqual(trackDomain(null, -2), [-8, 0]);
  assert.equal(rangeBar({ value: -1, ref_min: null, ref_max: -2 }).position, "above");
});

test("the range bar: a limit is above only when the limit itself is past the range", () => {
  const range = { ref_min: 30, ref_max: 400, unit: "ng/mL" };
  const above = rangeBar({ ...range, value: 600, comparator: ">" });
  assert.deepEqual([above.position, above.limit], ["above", ">"]);
  assert.equal(above.label, ">600 ng/mL is a limit: above the range 30–400 ng/mL (far above: off the bar)");
  assert.equal(rangeBar({ ...range, value: 450, comparator: ">" }).label, ">450 ng/mL is a limit: above the range 30–400 ng/mL");
  // ">100": the true value could be inside or above
  const unsure = rangeBar({ ...range, value: 100, comparator: ">" });
  assert.equal(unsure.position, "unknown");
  assert.match(unsure.label, /only a limit: whether it is inside .* can't be told/);
  assert.equal(rangePosition(400, ">", 30, 400), "above");
  assert.equal(rangePosition(400, ">=", 30, 400), "unknown");
  assert.equal(rangePosition(50, ">", 30, null), "inside");
  // "<0.5" with a range from 0: a concentration can't be below 0, so it is in range
  assert.equal(rangePosition(0.5, "<", 0, 5), "inside");
  assert.equal(rangePosition(20, "<", 30, 400), "below");
  assert.equal(rangePosition(30, "<", 30, 400), "below");
  assert.equal(rangePosition(30, "<=", 30, 400), "unknown");
  assert.equal(rangePosition(500, "<", 30, 400), "unknown");
});

test("the range bar: no range, or a result in words, draws nothing", () => {
  assert.equal(rangeBar({ value: 5, ref_min: null, ref_max: null }).kind, "none");
  assert.equal(rangeBar({ value: 5, ref_min: null, ref_max: null }).label, "no range on the form");
  assert.equal(rangeBar({ value: null, text: "negative", ref_min: 0, ref_max: 1 }).kind, "none");
  assert.equal(rangeBar({ value: Number.NaN, ref_min: 0, ref_max: 1 }).kind, "none");
  assert.equal(rangePosition(5, null, null, null), "unknown");
});

test("the drawer says how a value was converted, and never invents a conversion", () => {
  const printed = { value: 99, comparator: null, text: null, unit: "mg/dL" };
  const canonical = { value: 5.4945, unit: "mmol/L", state: "converted", factor: 0.0555, offset: null };
  assert.equal(conversionText({ printed, canonical }), "5.4945 mmol/L, converted from mg/dL (× 0.0555).");
  assert.equal(conversionText({ printed, canonical: { ...canonical, factor: null } }),
    "5.4945 mmol/L, converted from mg/dL");
  assert.equal(conversionText({ printed: { ...printed, unit: "degF" }, canonical: { ...canonical, unit: "Cel", factor: 0.555556, offset: -17.777778 } }),
    "5.4945 Cel, converted from degF (× 0.555556 + -17.7778).");
  assert.equal(conversionText({ printed: { ...printed, unit: "ukat/L" }, canonical: { value: null, unit: "U/L", state: "not_converted" } }),
    "Not converted: no conversion from “ukat/L” to U/L. Trends and charts leave it out.");
  assert.equal(conversionText({ printed: { ...printed, unit: null }, canonical: { value: null, unit: null, state: "not_converted" } }),
    "Not converted: no conversion from “no unit” to —. Trends and charts leave it out.");
  assert.equal(conversionText({ printed: { ...printed, comparator: ">", value: 600, unit: "ng/mL" }, canonical: { value: 600, unit: "ng/mL", state: "same_unit" } }),
    ">600 ng/mL: already in the canonical unit, not converted.");
  assert.equal(conversionText({ printed, canonical: { state: "text" } }), "A result in words: there is no number to convert.");
});

test("the drawer says where the range came from; a default is only a hint", () => {
  assert.equal(rangeText({ range: { source: "form", min: 70, max: 100, unit: "mg/dL" } }), "From the form: 70–100 mg/dL");
  assert.equal(rangeText({ range: { source: "none", min: null, max: null } }), "None on the form.");
  assert.equal(defaultRangeText({ min: 120, max: 155, unit: "g/L", kind: "population", sex: "female", condition: null, source: "WHO" }),
    "120–155 g/L · women · WHO");
  assert.equal(defaultRangeText({ min: null, max: 3, unit: "mmol/L", kind: "target", sex: null, condition: null, source: "ESC 2021" }),
    "≤ 3 mmol/L · target · ESC 2021");
  const converted = { state: "converted", unit: "mmol/L" };
  assert.equal(canonicalRangeText({ range: { canonical: { min: 3.885, max: 5.55, unconverted: false } }, canonical: converted, printed: { unit: "mg/dL" } }),
    "In the canonical unit: 3.885–5.55 mmol/L");
  assert.equal(canonicalRangeText({ range: { canonical: null }, canonical: converted, printed: { unit: "mg/dL" } }), "");
  assert.equal(canonicalRangeText({ range: { canonical: { min: 1, max: 2 } }, canonical: { state: "same_unit" }, printed: {} }), "");
});

test("the drawer's review lines: a pending value is never dated as reviewed", () => {
  const review = { status: "pending", channel: "mcp", staged_at: "2026-11-20T10:00:00+00:00", approved_at: null, source_reviewed_at: null, reviewed_by: null };
  assert.deepEqual(reviewLines({ review, pending: true }), [
    "Review status: pending", "Came in by: the assistant, from a form", "Recorded on 2026-11-20", "Not reviewed yet."]);
  // even if a date slipped through, a pending value says it is not reviewed
  assert.equal(reviewLines({ review: { ...review, approved_at: "2026-11-21", source_reviewed_at: "2026-11-21" }, pending: true }).at(-1), "Not reviewed yet.");
  // the row's own approval date, not the source's later one
  assert.equal(reviewLines({ review: { ...review, status: "approved", approved_at: "2026-07-01T09:00:00+00:00", source_reviewed_at: "2026-09-15T09:00:00+00:00", reviewed_by: "human" }, pending: false }).at(-1),
    "Approved on 2026-07-01 by you");
  // no history of its own: the source's date, said as the source's
  assert.equal(reviewLines({ review: { ...review, status: "approved", source_reviewed_at: "2026-09-15T09:00:00+00:00", reviewed_by: "human" }, pending: false }).at(-1),
    "Approved; its source was last approved on 2026-09-15");
  assert.equal(reviewLines({ review: { ...review, status: "approved", approved_at: "2026-11-21T09:00:00+00:00", reviewed_by: "human" }, pending: false }).at(-1),
    "Approved on 2026-11-21 by you");
  assert.equal(reviewLines({ review: { status: "approved", channel: "manual", staged_at: null, approved_at: null, source_reviewed_at: null }, pending: false }).at(-1),
    "No separate review recorded: it was stored as approved.");
  assert.equal(reviewLines({ review: { status: "weird", channel: "fax" }, pending: true })[0], "Review status: weird");
});

test("a value cell is pending only when the caller says so, never from a row's count", () => {
  // the Labs index sends the number of queued values in `pending`: the latest value is approved
  const marker = { id: "o1", name: "Vitamin D 25-OH", value: 22, unit: "ng/mL", pending: 2 };
  assert.equal(valueCellView(marker).pending, false);
  assert.equal(valueCellView({ ...marker, pending: true }).pending, false);
  assert.equal(valueCellView(marker, { pending: true }).pending, true);
  assert.equal(valueCellView(marker, { pending: 2 }).pending, false);
  assert.equal(valueCellView(marker).label, "22 ng/mL Vitamin D 25-OH: where it comes from");
  assert.equal(valueCellView({ value: null, text: null }).text, "—");
});

test("without a range on the form the drawer says what the status rests on", () => {
  assert.equal(rangeStatusText({ range: { source: "none" }, status: null }),
    "Without a range on the form, no status was computed for this value.");
  // a critical value with no range: its status is the threshold's, never "no status"
  assert.match(rangeStatusText({ range: { source: "none" }, status: "critical" }), /critical-value threshold/);
  assert.equal(rangeStatusText({ range: { source: "form" }, status: "high" }), "");
});

test("the drawer's source lines", () => {
  assert.equal(documentText(null), "none stored");
  assert.equal(documentText({ title: "Blood test", date: "2026-10-01", type: "lab_report" }), "Blood test · 2026-10-01 · lab_report");
  assert.equal(documentText({ title: null, date: null, type: null }), "untitled");
  assert.equal(panelText({ date: "2026-10-01", type: "Biochemistry", facility: "Lab", rows_in_document: 3 }),
    "2026-10-01 · Biochemistry · Lab · 3 rows on the form");
  assert.equal(panelText({ date: "2026-10-01", type: null, facility: null, rows_in_document: null }), "2026-10-01");
});

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

// ---- the medical-record pages (#57): timeline, medications, diagnoses, habits -------------------
import {
  allergyLine, clinicalTag, diagnosisDates, doseText, durationText, habitAmount, habitBar, habitStreak, medicationPeriod,
  isActive, medicationTags, paracetamolLines, reviewCount, reviewHint, sortDiagnoses, stopText, verificationTitle,
} from "../web/static/pages/record-model.js";
import {
  eventDetails as timelineDetails, eventLabel, fromDay, fullRange, isPendingEvent, isRefuted, isUncertain, isUndatedEnd,
  lanesOf, packRows, panRange, periodEnd,
  panelLinks, periodDates, periodLabel, tableRows as timelineRows, ticks, toDay, yearCells, yearRange, zoomRange,
} from "../web/static/pages/timeline-model.js";

const record = {
  today: "2026-11-25",
  born: "1985-04-12",
  undated_habits: 0,
  events: [
    { kind: "diagnosis", lane: "diagnoses", id: "d1", date: "2017-11-25", title: "Sample rhinitis", icd10: "J30.1", verification: "confirmed", clinical: "active" },
    { kind: "diagnosis", lane: "diagnoses", id: "d2", date: "2024-05-26", title: "Sample refuted", icd10: null, verification: "refuted", clinical: "inactive" },
    { kind: "panel", lane: "labs", id: "p1", date: "2026-08-20", title: null, facility: "Demo Lab", values: 6, pending: 0, out_of_range: 2, markers: [{ code: "ldl", name: "LDL cholesterol" }] },
    { kind: "panel", lane: "labs", id: "p2", date: "2026-11-22", title: null, facility: "Demo Lab", values: 2, pending: 2, out_of_range: 0, markers: [] },
    { kind: "vaccination", lane: "vaccinations", id: "v1", date: "2010-11-25", title: "Sample vaccine", disease: "Sample", dose_number: 3, facility: null },
  ],
  periods: [
    { kind: "medication", lane: "medications", id: "m1", title: "Sample iron", start: "2022-11-25", end: "2023-05-27", ongoing: false, status: "stopped", detail: "200 mg × 1/day, oral", stop_reason: "course completed" },
    { kind: "medication", lane: "medications", id: "m2", title: "Sample antihistamine", start: "2017-11-25", end: null, ongoing: true, status: "taking", detail: null, stop_reason: null },
    { kind: "medication", lane: "medications", id: "m3", title: "Sample analgesic", start: "2025-05-26", end: null, ongoing: true, status: "taking", detail: null, stop_reason: null },
    { kind: "habit", lane: "habits", id: "h1", title: "smoking", start: "2004-11-24", end: "2014-11-25", ongoing: false, status: "former", detail: null },
  ],
};

test("timeline days are whole UTC days, whatever the time part says", () => {
  assert.equal(toDay("1970-01-02"), 1);
  assert.equal(toDay("2026-11-01T23:30:00+00:00"), toDay("2026-11-01"));
  assert.equal(fromDay(toDay("2026-11-25")), "2026-11-25");
});

test("medication bars that overlap go one above the other; one after another share a row", () => {
  const rows = packRows(record.periods.filter((p) => p.lane === "medications"), toDay(record.today));
  // the antihistamine runs to today, so the iron course and the analgesic can't share its row,
  // but the analgesic starts after the iron course ended: they share the second one
  assert.deepEqual(rows.map((row) => row.map((p) => p.id)), [["m2"], ["m1", "m3"]]);
});

test("only lanes with something in them are drawn, in a fixed order, and a hidden one is left out", () => {
  assert.deepEqual(lanesOf(record).map((lane) => lane.id), ["diagnoses", "labs", "vaccinations", "medications", "habits"]);
  assert.deepEqual(lanesOf(record, new Set(["labs"])).map((lane) => lane.id), ["diagnoses", "vaccinations", "medications", "habits"]);
});

test("the whole record runs from the first record to just past today; zoom and pan stay inside it", () => {
  const bounds = fullRange(record);
  assert.ok(bounds.from < toDay("2004-11-24") && bounds.to > toDay(record.today));
  assert.ok(bounds.to - toDay(record.today) < 120); // a little room for today's mark, not months of future
  const zoomed = zoomRange(bounds, 0.5, bounds);
  assert.ok(Math.abs((zoomed.to - zoomed.from) - (bounds.to - bounds.from) / 2) <= 1);
  assert.deepEqual(zoomRange(zoomed, 4, bounds), bounds); // zooming out never goes past the record
  const tiny = zoomRange(bounds, 0.0001, bounds);
  assert.ok(tiny.to - tiny.from >= 31); // no closer than about a month
  assert.equal(panRange(bounds, -0.5, bounds).from, bounds.from);
  const late = panRange(zoomed, 10, bounds);
  assert.equal(late.to, bounds.to);
  assert.equal(late.to - late.from, zoomed.to - zoomed.from);
});

test("a wide range is ticked by year, a narrow one by month with the year on January", () => {
  const years = ticks({ from: toDay("2004-06-01"), to: toDay("2026-12-01") }, 800);
  assert.ok(years.every((tick) => /^\d{4}$/.test(tick.label)));
  assert.ok(years.length >= 4 && years.length <= 12);
  const months = ticks(yearRange(2026), 1600);
  assert.deepEqual(months.map((tick) => tick.label).slice(0, 3), ["2026", "Feb", "Mar"]);
  assert.ok(months.every((tick) => tick.day >= toDay("2025-12-18")));
  assert.ok(ticks(yearRange(2026), 300).length < months.length); // fewer on a phone
});

test("life in years runs from birth to this year, shaded by how much was recorded", () => {
  const cells = yearCells(record);
  assert.equal(cells[0].year, 1985);
  assert.equal(cells[0].age, 0);
  assert.equal(cells.at(-1).year, 2026);
  assert.equal(cells.find((c) => c.year === 1990).level, 0);
  assert.ok(cells.find((c) => c.year === 2026).level > 0);
  assert.equal(cells.find((c) => c.year === 2026).n, 2); // two panels
  assert.ok(cells.find((c) => c.year === 2020).ongoing); // the antihistamine runs through it
  assert.equal(cells.find((c) => c.year === 1995).ongoing, false);
  // no birth date: it starts at the first record
  assert.equal(yearCells({ ...record, born: null })[0].year, 2004);
});

test("a panel under review is drawn as pending, and links only to markers with an approved value", () => {
  const [, , done, pending] = record.events;
  assert.equal(isPendingEvent(done), false);
  assert.equal(isPendingEvent(pending), true);
  assert.match(eventLabel(pending), /^Lab panel, 2026-11-22: Demo Lab · 2 values · 2 awaiting review$/);
  assert.deepEqual(timelineDetails(done), ["Demo Lab", "6 values", "2 out of range"]);
  assert.deepEqual(panelLinks(done), [{ code: "ldl", name: "LDL cholesterol", href: "#/labs/ldl" }]);
  assert.deepEqual(panelLinks(pending), []);
});

test("a refuted diagnosis is marked so, and a diagnosis says its code and status", () => {
  assert.equal(isRefuted(record.events[1]), true);
  assert.equal(isRefuted(record.events[0]), false);
  assert.deepEqual(timelineDetails(record.events[0]), ["J30.1", "confirmed", "active"]);
});

test("a period says from when to when, and why a medication stopped", () => {
  const [iron, antihistamine] = record.periods;
  assert.equal(periodDates(antihistamine), "2017-11-25 → today");
  assert.equal(periodLabel(iron), "Medication: Sample iron, 2022-11-25 → 2023-05-27 · 200 mg × 1/day, oral · stopped: course completed");
  assert.equal(periodLabel(record.periods[3]), "Habit: smoking, 2004-11-24 → 2014-11-25 · former");
});

test("the timeline's table has every event and period, oldest first", () => {
  const rows = timelineRows(record);
  assert.equal(rows.length, record.events.length + record.periods.length);
  assert.equal(rows[0].date, "2004-11-24");
  assert.equal(rows.find((row) => row.title === "Sample antihistamine").end, "today");
  assert.equal(rows.filter((row) => row.pending).length, 1);
});

test("durations round down and never claim more than there was", () => {
  assert.equal(durationText(1), "1 day");
  assert.equal(durationText(45), "45 days");
  assert.equal(durationText(183), "6 months");
  assert.equal(durationText(toDay("2026-11-25") - toDay("2017-11-25")), "9 years");
  assert.equal(durationText(729), "23 months");
  assert.equal(durationText(null), "");
});

const iron = {
  name: "Sample iron", product_type: "prescription", dose_amount: 200, dose_unit: "mg", route: "oral", times_per_day: 1,
  dosing_pattern: null, start_date: "2022-11-25", end_date: "2023-05-27", status: "stopped", stop_reason: "course completed", days: 183,
};

test("a medication shows only what was recorded about it", () => {
  assert.equal(doseText(iron), "200 mg × 1/day");
  assert.equal(doseText({ dose_amount: null, dose_unit: "mg", times_per_day: 2 }), "2/day");
  assert.equal(doseText({ dose_amount: null, dose_unit: null, times_per_day: null }), "");
  assert.equal(medicationPeriod(iron), "2022-11-25 → 2023-05-27 · 6 months");
  assert.equal(medicationPeriod({ start_date: "2017-11-25", end_date: null, status: "taking", days: 3287 }), "since 2017-11-25 · 9 years");
  assert.deepEqual(medicationTags(iron), ["oral"]);
  assert.deepEqual(medicationTags({ product_type: "otc", route: null, dosing_pattern: "as_needed" }), ["over the counter", "as needed"]);
  assert.deepEqual(medicationTags({ product_type: "new_kind", route: "nasal_spray" }), ["new kind", "nasal spray"]);
});

test("why a medication stopped is said, and a missing reason is not guessed", () => {
  assert.equal(stopText(iron), "course completed");
  assert.equal(stopText({ ...iron, stop_reason: null }), "no reason recorded");
  assert.equal(stopText({ ...iron, status: "paused", stop_reason: null }), "paused: no reason recorded");
  assert.equal(stopText({ ...iron, status: "taking" }), "");
});

test("recorded paracetamol is a sum, never reassurance; a missing dose is named, not counted as 0", () => {
  assert.deepEqual(paracetamolLines(null), []);
  const one = paracetamolLines({ products: ["Paracetamol"], mg_per_day: 1000, missing_dose: [], limit_mg: 4000, over_limit: false });
  assert.match(one[0], /^1000 mg a day, as recorded/);
  assert.equal(one.length, 2);
  for (const line of one) assert.doesNotMatch(line.toLowerCase(), /within|safe to|normal|fine/);
  const gap = paracetamolLines({ products: ["A", "B"], mg_per_day: 1000, missing_dose: ["B"], limit_mg: 4000, over_limit: false });
  assert.match(gap.join(" "), /Not counted.*: B\./);
  const none = paracetamolLines({ products: ["B"], mg_per_day: null, missing_dose: ["B"], limit_mg: 4000, over_limit: false });
  assert.doesNotMatch(none[0], /mg a day/);
  const over = paracetamolLines({ products: ["A", "B"], mg_per_day: 5000, missing_dose: [], limit_mg: 4000, over_limit: true });
  assert.match(over[0], /5000 mg a day across 2 products/);
  assert.match(over.join(" "), /above 4000 mg.*doctor or pharmacist/);
});

test("an allergy reads with its reaction and severity", () => {
  assert.equal(allergyLine({ allergen: "sample", reaction: "rash", severity: "moderate" }), "sample — rash · moderate");
  assert.equal(allergyLine({ allergen: "sample", reaction: null, severity: null }), "sample");
});

test("diagnoses: active first, dates by status, and the review hint is an observation, not advice", () => {
  const rows = [
    { name: "old resolved", clinical_status: "resolved", diagnosed_at: "2025-01-01", resolved_at: "2025-06-01" },
    { name: "active old", clinical_status: "active", diagnosed_at: "2017-11-25", resolved_at: null, review_hint: true },
    { name: "active new", clinical_status: "active", diagnosed_at: "2026-10-26", resolved_at: null },
  ];
  assert.deepEqual(sortDiagnoses(rows).map((d) => d.name), ["active new", "active old", "old resolved"]);
  assert.equal(diagnosisDates(rows[0]), "2025-01-01 → 2025-06-01");
  assert.equal(diagnosisDates(rows[1]), "since 2017-11-25");
  assert.equal(diagnosisDates({ clinical_status: "inactive", diagnosed_at: "2024-05-26" }), "recorded 2024-05-26");
  const hint = reviewHint(rows[1], "2026-11-25");
  assert.match(hint, /this entry hasn't changed since 2017-11-25 \(9 years\)/);
  assert.match(hint, /reviewing with a doctor/);
  assert.equal(reviewHint(rows[2], "2026-11-25"), "");
  assert.equal(reviewCount([{ rows }, { rows: [] }]), 1);
  assert.equal(verificationTitle("suspected"), "Suspected");
  assert.equal(verificationTitle("something_new"), "something new");
});

test("a habit says how long it has run, or how long ago it stopped", () => {
  const running = { status: "current", start_date: "2023-11-25", end_date: null, days: 1096 };
  assert.equal(habitStreak(running), "For 3 years, since 2023-11-25");
  const smoking = { status: "former", start_date: "2004-11-24", end_date: "2014-11-25", days: 3653, days_since_end: 4383 };
  assert.equal(habitStreak(smoking), "Stopped 12 years ago, on 2014-11-25, after 10 years");
  assert.equal(habitStreak({ status: "former", start_date: null, end_date: null }), "Former; no end date recorded");
  assert.equal(habitStreak({ status: "current", start_date: null }), "Current; no start date recorded");
  assert.equal(habitAmount({ cigarettes_per_day: 8, smoking_years: 10 }), "8 cigarettes a day · 10 years of smoking");
  assert.equal(habitAmount({ frequency: "2–3 drinks a week", drinks_per_week: 3 }), "2–3 drinks a week");
  assert.equal(habitAmount({ drinks_per_week: 1 }), "1 drink a week");
  const bar = habitBar(smoking, toDay("1985-04-12"), toDay("2026-11-25"));
  assert.ok(bar.left > 0.4 && bar.left < 0.5 && bar.width > 0.2 && bar.width < 0.3);
  assert.equal(habitBar({ start_date: null }, 0, 1), null);
});

test("every count the record pages put in words has its singular", () => {
  for (const key of ["timeline.year.events", "timeline.panel.values", "timeline.panel.out", "timeline.panel.pending",
    "timeline.panel.pending_note", "timeline.undated_habits", "record.duration.days", "record.duration.months",
    "record.duration.years", "record.paracetamol.total", "record.diagnoses.review_summary", "record.habit.cigarettes",
    "record.habit.drinks", "record.habit.smoking_years"]) {
    assert.notEqual(t(`${key}_one`), `${key}_one`, key);
  }
});

test("the record pages load", () => {
  for (const id of ["timeline", "medications", "diagnoses", "habits"]) {
    assert.ok(PAGES.find((page) => page.id === id).load, id);
    assert.equal(parseRoute(`#/${id}`).page.id, id);
  }
});

test("a diagnosis that is not confirmed is drawn uncertain on the timeline; an unknown value is never a raw key", () => {
  const dx = (verification) => ({ kind: "diagnosis", verification, clinical: "active", icd10: null });
  assert.equal(isUncertain(dx("confirmed")), false);
  assert.equal(isUncertain(dx("refuted")), false);
  for (const v of ["suspected", "provisional", "differential", null, "something_new"]) assert.equal(isUncertain(dx(v)), true, v);
  assert.deepEqual(timelineDetails(dx("something_new")), ["something new", "active"]);
  assert.deepEqual(timelineDetails(dx(null)), ["certainty not recorded", "active"]);
  // refuted but left "active": not active anywhere
  assert.deepEqual(timelineDetails(dx("refuted")), ["refuted"]);
});

test("a period that is over but has no end date never runs to today", () => {
  const today = toDay("2026-11-25");
  const undated = { kind: "habit", lane: "habits", id: "h9", title: "smoking", start: "2004-11-24", end: null, ongoing: false, status: "former" };
  const stopped = { kind: "medication", lane: "medications", id: "m9", title: "Sample", start: "2020-01-01", end: null, ongoing: false, status: "stopped" };
  assert.equal(periodEnd(undated, today), null);
  assert.equal(periodEnd({ ...undated, ongoing: true }, today), today);
  assert.equal(isUndatedEnd(undated), true);
  assert.equal(periodDates(undated), "2004-11-24 → end not recorded");
  assert.match(periodLabel(stopped), /2020-01-01 → end not recorded · stopped$/);
  // it covers only its start day, so a later period can share its row
  const later = { ...stopped, id: "m10", start: "2021-01-01", end: "2021-06-01" };
  assert.equal(packRows([stopped, later], today).length, 1);
  const rows = timelineRows({ events: [], periods: [undated] });
  assert.equal(rows[0].end, "end not recorded");
  const cells = yearCells({ today: "2026-11-25", born: null, events: [], periods: [undated] });
  assert.equal(cells.find((c) => c.year === 2004).ongoing, true);
  assert.equal(cells.find((c) => c.year === 2010).ongoing, false);
  const bar = habitBar({ status: "former", start_date: "2004-11-24", end_date: null }, toDay("2000-01-01"), today);
  assert.equal(bar.undated, true);
  assert.ok(bar.width < 0.01);
  assert.equal(habitBar({ status: "current", start_date: "2004-11-24", end_date: null }, toDay("2000-01-01"), today).undated, false);
  assert.equal(medicationPeriod({ start_date: "2020-01-01", end_date: null, status: "stopped", days: null }), "2020-01-01 → end not recorded");
});

test("a refuted diagnosis is never active, whatever clinical status it was left with", () => {
  const refuted = { name: "r", clinical_status: "active", verification_status: "refuted", diagnosed_at: "2026-01-01", resolved_at: null };
  const active = { name: "a", clinical_status: "active", verification_status: "confirmed", diagnosed_at: "2020-01-01", resolved_at: null };
  assert.equal(isActive(refuted), false);
  assert.equal(clinicalTag(refuted), "");
  assert.equal(clinicalTag(active), "active");
  assert.equal(diagnosisDates(refuted), "recorded 2026-01-01");
  assert.deepEqual(sortDiagnoses([refuted, active]).map((d) => d.name), ["a", "r"]);
});

test("the timeline reaches a record dated after today", () => {
  const bounds = fullRange({ ...record, events: [...record.events, { kind: "visit", lane: "care", id: "f1", date: "2027-03-01", title: "planned" }] });
  assert.ok(bounds.to > toDay("2027-03-01"));
});

// ---- Doctor-visit report (#60) ----------------------------------------------------------------

const en = translator("en");
const uk = translator("uk");
const es = translator("es");

test("every report dictionary has every English word, every plural form its language needs", () => {
  const plain = Object.keys(DICTIONARIES.en).filter((key) => !/_(one|other)$/.test(key));
  const plurals = [...new Set(Object.keys(DICTIONARIES.en).filter((key) => /_other$/.test(key)).map((key) => key.replace(/_other$/, "")))];
  for (const lang of REPORT_LANGS) {
    const dict = DICTIONARIES[lang];
    for (const key of plain) assert.ok(dict[key], `${lang}: ${key}`);
    const forms = new Intl.PluralRules(lang).resolvedOptions().pluralCategories.filter((form) => form !== "many" || lang !== "es");
    for (const key of plurals) for (const form of forms) assert.ok(dict[`${key}_${form}`], `${lang}: ${key}_${form}`);
  }
  assert.equal(translator("fr").lang, "en"); // an unknown language is English, never blank
});

test("the report's words never reassure", () => {
  for (const lang of REPORT_LANGS) {
    for (const text of Object.values(DICTIONARIES[lang])) {
      assert.doesNotMatch(text.toLowerCase(), /everything is normal|all normal|todo normal|все в нормі|no problems/);
    }
  }
  assert.equal(outLead({ lab_markers_seen: 9, rows: [] }, en),
    "Among the 9 lab markers on record, none has its latest value outside the range printed on the form.");
  assert.match(outLead({ lab_markers_seen: 9, rows: [{}] }, es), /^De los 9 parámetros/);
  assert.match(outLead({ lab_markers_seen: 3, rows: [{}] }, uk), /^Серед 3 лабораторних показників/);
});

test("dates, numbers and units in the report's language", () => {
  assert.equal(reportDate("2026-09-26T00:00:00+00:00", en), "26 Sept 2026");
  assert.equal(reportDate("2026-09-26", es), "26 sept 2026");
  assert.equal(reportDate(null, es), "");
  assert.equal(reportValue({ value: 5.8, unit: "mmol/L" }, es), "5,8 mmol/L");
  assert.equal(reportValue({ value: 5.8, unit: "mmol/L" }, uk), "5,8 ммоль/л");
  assert.equal(reportValue({ value: 75, unit: "umol/L" }, en), "75 µmol/L");
  assert.equal(reportValue({ value: 5, comparator: "<", unit: "mg/L" }, uk), "<5 мг/л");
  assert.equal(reportValue({ value: null, text: "negativo" }, es), "negativo");
  assert.equal(reportUnit("IU", es), "UI");
  assert.equal(reportUnit("mmHg", uk), "мм рт. ст.");
  assert.equal(reportUnit("x10^9/L", en), "x10^9/L"); // what it doesn't know stays as printed
  assert.equal(reportRange({ ref_min: 0, ref_max: 5.2 }, es), "0–5,2");
  assert.equal(reportRange({ ref_min: 1.2, ref_max: null }, en), "≥ 1.2");
  assert.equal(reportRange({ ref_min: null, ref_max: null }, en), "");
});

test("the profile line, in the patient's grammatical gender where the language has one", () => {
  const profile = { sex: "female", age: 41, date_of_birth: "1985-04-12", blood_type: "A", rh_factor: "+", height_cm: 168 };
  assert.equal(reportProfile(profile, en), "Female, 41 years (born 12 Apr 1985) · blood type A+ · height 168 cm");
  assert.match(reportProfile(profile, es), /^Mujer, 41 años \(nacida el 12 abr 1985\)/);
  assert.match(reportProfile({ ...profile, sex: "male" }, es), /nacido el/);
  assert.match(reportProfile(profile, uk), /народилася/);
  assert.equal(reportProfile(null, en), "No profile on record.");
  assert.equal(reportProfile({}, es), "No hay perfil registrado.");
});

test("allergies and medications: the records as entered, our own words translated", () => {
  assert.equal(allergyDetail({ reaction: "rash", severity: "moderate", verified: true }, es), "reacción: rash · moderada");
  assert.equal(allergyDetail({ reaction: null, severity: "Anaphylaxis!", verified: false }, en), "Anaphylaxis! · not verified");
  const med = { name: "Vitamin D3", dose_amount: 2000, dose_unit: "IU", times_per_day: 1, product_type: "supplement", start_date: "2026-01-29" };
  assert.equal(medicationDetail(med, en), "2,000 IU, 1× a day · supplement · since 29 Jan 2026");
  assert.equal(medicationDetail(med, es), "2000 UI, 1× al día · suplemento · desde el 29 ene 2026");
  assert.equal(medicationDetail({ ...med, end_date: "2026-11-01" }, en, { stopped: true }),
    "2,000 IU, 1× a day · supplement · 29 Jan 2026 – 1 Nov 2026");
  assert.equal(medicationDetail({ name: "X", product_type: "unknown-type" }, en), "");
});

test("diagnoses by status: confirmed, in question, past; a refuted one is left out", () => {
  const d = (name, clinical, verification) => ({ name, clinical_status: clinical, verification_status: verification, at: "2026-10-26" });
  const groups = groupDiagnoses([
    d("A", "active", "confirmed"), d("B", "active", "suspected"), d("C", "resolved", "confirmed"),
    d("D", "active", "refuted"), d("E", null, null), d("F", "relapse", "provisional"), d("G", "remission", "suspected"),
  ]);
  assert.deepEqual(groups.confirmed.map((x) => x.name), ["A", "E"]);
  assert.deepEqual(groups.in_question.map((x) => x.name), ["B", "F"]);
  assert.deepEqual(groups.past.map((x) => x.name), ["C", "G"]);
  assert.equal(diagnosisDetail({ icd10: "E78.0", clinical_status: "active", verification_status: "suspected", at: "2026-10-26" }, es),
    "E78.0 · sospecha · desde el 26 oct 2026");
  assert.equal(diagnosisDetail({ icd10: null, clinical_status: "resolved", verification_status: "confirmed", at: null }, uk), "вилікуваний");
});

test("a change between two results is called larger than lab noise only when it is", () => {
  const within = { percent: 8.6, rcv: 22.9, significant: false };
  const larger = { percent: -26.7, rcv: 22.9, significant: true };
  assert.equal(percentText(8.6, es), "+8,6 %");
  assert.equal(percentText(-26.7, en), "−26.7 %");
  assert.match(changeText(within, en), /^Last change \+8\.6 %: within the reference change value \(22\.9 %\)/);
  assert.match(changeText(larger, es), /^Último cambio −26,7 %: mayor que/);
  assert.equal(changeText(null, en), ""); // no cited number: no verdict either way
  assert.equal(changeShort(within, uk), "остання зміна +8,6 %, RCV 22,9 %");
  assert.equal(changeShort(null, uk), "");
  assert.match(methodText({ markers: [{ name: "Colesterol LDL" }, { name: "Glucosa" }] }, es), /Solo para: Colesterol LDL, Glucosa\.$/);
});

test("a 'what changed' row: before and now, and whether it crossed its range", () => {
  const row = {
    name: "LDL", value: 3.4, unit: "mmol/L", status: "high", at: "2026-11-20", moved: "out_of_range",
    before: { value: 2.8, unit: "mmol/L", status: "normal", at: "2026-08-27" },
    change: { percent: 21.4, rcv: 22.9, significant: false },
  };
  const parts = resultChange(row, en);
  assert.equal(parts.now, "3.4 mmol/L");
  assert.equal(parts.status, "high");
  assert.equal(parts.before, "before: 2.8 mmol/L, 27 Aug 2026");
  assert.equal(parts.moved, "now out of range");
  assert.equal(resultChange({ ...row, before: null, moved: null, status: "normal", change: null }, es).before, "primera medición");
  assert.equal(resultChange({ ...row, before: null, moved: null, status: "normal" }, es).status, "");
  assert.equal(streakText({ since: "2024-12-05", streak: 4 }, en), "5 Dec 2024 (4 values in a row)");
  assert.equal(streakText({ since: "2024-12-05", streak: 5 }, uk), "5 груд. 2024 р. (5 значень поспіль)");
});

test("the footer says what the report is made of, in the report's language", () => {
  const data = { approved_values: 56, generated_at: "2026-11-25T16:51:37+00:00" };
  assert.equal(footerText(data, en), "Generated from 56 approved values on 25 Nov 2026. Not a medical document. Pending values are not included.");
  assert.match(footerText(data, es), /^Generado a partir de 56 valores aprobados el 25 nov 2026\. No es un documento médico\./);
  assert.match(footerText({ ...data, approved_values: 1 }, en), /^Generated from 1 approved value on/);
  assert.doesNotMatch(footerText(data, uk), /\.\./);
});

test("a trend's mini-chart keeps its range band and its points inside the box", () => {
  const trend = {
    ref_min: 0, ref_max: 3.0,
    points: [{ at: "2024-06-08", value: 2.9, status: "normal" }, { at: "2025-06-03", value: 3.3, status: "high" }, { at: "2026-09-26", value: 3.8, status: "high" }],
  };
  const chart = miniChart(trend, 200, 56);
  assert.equal(chart.points.length, 3);
  for (const p of chart.points) {
    assert.ok(p.x >= 0 && p.x <= 200 && p.y >= 0 && p.y <= 56);
  }
  assert.ok(chart.points[2].y < chart.points[0].y); // higher value, higher on the chart
  assert.deepEqual(chart.points.map((p) => p.out), [false, true, true]);
  assert.ok(chart.band && chart.band.y > chart.points[2].y); // the latest value is above the band
  assert.equal(miniChart({ ...trend, ref_min: null, ref_max: null }, 200, 56).band, null);
  assert.equal(trendSpan(trend, en), "3 values, 8 Jun 2024 – 26 Sept 2026");
});

test("the questions stay in this browser, and blocked storage is no error", () => {
  const store = new Map();
  const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) };
  assert.equal(loadQuestions(storage), "");
  assert.equal(saveQuestions(storage, "¿Repito el LDL?"), true);
  assert.equal(store.get(QUESTIONS_KEY), "¿Repito el LDL?");
  assert.equal(loadQuestions(storage), "¿Repito el LDL?");
  saveQuestions(storage, "");
  assert.equal(store.has(QUESTIONS_KEY), false);
  const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.equal(loadQuestions(blocked), "");
  assert.equal(saveQuestions(blocked, "x"), false);
  assert.equal(loadQuestions(null), "");
});

test("every verification status has its word, 'refuted' included", () => {
  for (const tr of [en, uk, es]) {
    for (const status of ["confirmed", "provisional", "suspected", "differential", "refuted"]) {
      assert.doesNotMatch(tr.t(`verification.${status}`), /^verification\./, `${tr.lang}: ${status}`);
    }
  }
  assert.equal(diagnosisDetail({ icd10: null, clinical_status: "active", verification_status: "refuted", at: null }, es), "descartado");
});

test("a medication stopped on an unrecorded day is listed with the stopped ones, said so", () => {
  const meds = { started: [], stopped: [{ name: "A", start_date: "2024-01-01", end_date: "2026-11-01" }], stopped_undated: [{ name: "B", start_date: "2024-01-01", end_date: null }] };
  assert.deepEqual(stoppedMedications(meds).map((m) => m.name), ["A", "B"]);
  assert.equal(medicationDetail(meds.stopped_undated[0], en, { stopped: true }), "since 1 Jan 2024 · stopped, date unknown");
  assert.equal(medicationDetail({ name: "C" }, es, { stopped: true }), "suspendida, fecha desconocida");
  assert.equal(noOtherChanges({ medications: { started: [], stopped: [], stopped_undated: [{}] }, diagnoses: [] }), false);
  assert.equal(noOtherChanges({ medications: { started: [], stopped: [] }, diagnoses: [] }), true);
});

test("the since date says it is included, and a cut list says it is cut", () => {
  assert.equal(changesNote({ since: "2026-05-27", since_source: "visit" }, en), "the last visit on record · 27 May 2026 itself included.");
  assert.match(changesNote({ since: "2026-05-27", since_source: "default" }, es), /Incluido el propio 27 may 2026\.$/);
  assert.equal(truncatedText({ medications: true, diagnoses: false, limit: 200 }, "medications", en), "Only the first 200 are listed; the record has more.");
  assert.equal(truncatedText({ medications: true, diagnoses: false, limit: 200 }, "diagnoses", en), "");
  assert.equal(truncatedText(undefined, "diagnoses", en), "");
});

test("the report page loads", () => {
  assert.ok(PAGES.find((page) => page.id === "report").load);
  assert.equal(parseRoute("#/report").page.id, "report");
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

// ---- sustained deviations on the Vitals page (#75) ------------------------------------------------
import {
  findingView, shadedRuns, sustainedEmpty, sustainedFootnote, sustainedNotes, sustainedState, withShading,
} from "../web/static/pages/sustained-model.js";
import { SUSTAINED_DICTIONARIES, SUSTAINED_LANGS, sustainedTranslator } from "../web/static/pages/sustained-strings.js";

const SUSTAINED_PARAMS = {
  baseline_days: 60, min_baseline_days: 30, run_days: 3, spread_k: 2,
  daily: { resting_hr: { direction: "up", min_delta: 3 }, hrv: { direction: "down", min_delta: 5 } },
  hr_above_resting: 30, min_minutes: 20,
};
const PAIRED = {
  kind: "days", first_day: "2026-11-03", last_day: "2026-11-06", days: 4, together_days: 3,
  metrics: [
    { code: "resting_hr", direction: "up", first_day: "2026-11-03", last_day: "2026-11-06", days: 4, usual: 59, mean_delta: 7.2 },
    { code: "hrv", direction: "down", first_day: "2026-11-03", last_day: "2026-11-05", days: 3, usual: 46, mean_delta: -12.3 },
  ],
  context: [
    { kind: "workout", day: "2026-11-04", type: "running", minutes: 45 },
    { kind: "beta_blocker", name: "Bisoprolol", atc_code: "C07AB07" },
  ],
};
const STILL = {
  kind: "minutes", start: "2026-11-19T15:05:00+02:00", end: "2026-11-19T15:30:00+02:00", day: "2026-11-19",
  minutes: 25, usual: 58, mean_hr: 95.4, max_hr: 101, context: [],
};

test("a lasting change is said as how far from your usual, with its context", () => {
  const view = findingView(PAIRED);
  assert.equal(view.title, "Resting heart rate and HRV");
  assert.equal(view.period, "2026-11-03 – 2026-11-06 · 4 days");
  assert.deepEqual(view.lines, [
    "Resting heart rate: 7 bpm above your usual 59 bpm on average, 4 days in a row",
    "HRV: 12 ms below your usual 46 ms on average, 3 days in a row",
    "Both on 3 of the same days",
  ]);
  assert.deepEqual(view.chips, [
    "Workout on 2026-11-04: running, 45 min",
    "Bisoprolol: a beta blocker, which lowers heart rate and can hide a rise",
  ]);
  const still = findingView(STILL);
  assert.equal(still.period, "2026-11-19, 15:05–15:30 · 25 min"); // the user's clock, as the API wrote it
  assert.deepEqual(still.lines, ["On average 95 bpm, 37 above your usual resting 58 bpm, with no steps recorded"]);
});

test("Ukrainian and Spanish say the days with their own plural forms", () => {
  assert.match(findingView(PAIRED, "uk").lines[0], /4 дні поспіль$/);
  assert.match(findingView({ ...PAIRED, metrics: [{ ...PAIRED.metrics[0], days: 5 }] }, "uk").lines[0], /5 днів поспіль$/);
  assert.match(findingView(PAIRED, "es").lines[1], /3 días seguidos$/);
  assert.equal(sustainedTranslator("fr").lang, "en");
});

test("an empty list never says everything is normal, and says when nothing could be checked", () => {
  const empty = { findings: [], params: SUSTAINED_PARAMS, days_with_values: { resting_hr: 200, hrv: 0 } };
  assert.equal(sustainedState(empty), "empty");
  assert.match(sustainedEmpty(empty), /for 3 days in a row\. This only covers what the watch recorded\.$/);
  const short = { ...empty, days_with_values: { resting_hr: 12, hrv: 12 } };
  assert.equal(sustainedState(short), "not_enough");
  assert.match(sustainedEmpty(short), /fewer than 30 days of values in the 60 days before/);
  assert.equal(sustainedState(null), "none");
  assert.equal(sustainedState({ ...empty, findings: [STILL] }), "findings");
});

test("the footnote gives the thresholds as initial defaults and what the rule can't see", () => {
  const text = sustainedFootnote({ params: SUSTAINED_PARAMS });
  assert.match(text, /60 days before; 3 days in a row/);
  assert.match(text, /at least 3 bpm, HRV down by at least 5 ms/);
  assert.match(text, /initial defaults, to be reviewed/);
  assert.match(text, /No ECG/);
  assert.doesNotMatch(text, /\{\w+\}/);
  for (const lang of SUSTAINED_LANGS) assert.doesNotMatch(sustainedFootnote({ params: SUSTAINED_PARAMS }, lang), /\{\w+\}/);
});

test("every sustained dictionary has every word and plural form, and none of them alarms or reassures", () => {
  const plain = Object.keys(SUSTAINED_DICTIONARIES.en).filter((key) => !/_(one|other)$/.test(key));
  const plurals = [...new Set(Object.keys(SUSTAINED_DICTIONARIES.en).filter((key) => /_other$/.test(key)).map((key) => key.replace(/_other$/, "")))];
  for (const lang of SUSTAINED_LANGS) {
    const dict = SUSTAINED_DICTIONARIES[lang];
    for (const key of plain) assert.ok(dict[key], `${lang}: ${key}`);
    const forms = new Intl.PluralRules(lang).resolvedOptions().pluralCategories.filter((form) => form !== "many" || lang !== "es");
    for (const key of plurals) for (const form of forms) assert.ok(dict[`${key}_${form}`], `${lang}: ${key}_${form}`);
    for (const text of Object.values(dict)) {
      assert.doesNotMatch(text.toLowerCase(), /everything is normal|all normal|todo normal|все в нормі|nothing to worry|danger|urgent|alarm|тривог|небезпе|peligro|urgente/);
    }
  }
});

test("without recorded workouts the list says step-free exercise may show up in it", () => {
  const base = { findings: [], params: SUSTAINED_PARAMS };
  assert.match(sustainedNotes({ ...base, minutes_rule: "checked", workouts_recorded: false })[0], /No workouts are recorded here/);
  const gym = { kind: "workout", day: "2026-11-04", type: "traditional_strength_training", minutes: 50 };
  assert.deepEqual(findingView({ ...PAIRED, context: [gym] }).chips, ["Workout on 2026-11-04: traditional strength training, 50 min"]);
  assert.match(sustainedNotes({ ...base, minutes_rule: "checked", workouts_recorded: false }, "uk")[0], /Тренувань тут не записано/);
  assert.deepEqual(sustainedNotes({ ...base, minutes_rule: "checked", workouts_recorded: true }), []);
  assert.deepEqual(sustainedNotes({ ...base, minutes_rule: "no_samples", workouts_recorded: false }), []); // Garmin only: no minutes rule
  assert.equal(findingView({ ...PAIRED, metrics: [{ ...PAIRED.metrics[1], code: "hrv_sdnn" }], together_days: null }).title, "HRV (SDNN, Apple)");
});

test("the runs are shaded on their own panels, the last day included", () => {
  const panels = [
    { id: "sleep", series: [{ code: "sleep_duration" }] },
    { id: "hrv", series: [{ code: "hrv" }] },
    { id: "resting_hr", series: [{ code: "resting_hr" }] },
  ];
  const sustained = { findings: [PAIRED, STILL] };
  assert.deepEqual(shadedRuns(sustained, panels), [
    { panel: 2, from: Date.parse("2026-11-03"), to: Date.parse("2026-11-07") },
    { panel: 1, from: Date.parse("2026-11-03"), to: Date.parse("2026-11-06") },
  ]);
  assert.deepEqual(shadedRuns(sustained, panels.slice(0, 1)), []); // a panel that isn't drawn
  const option = { series: [{ name: "own" }] };
  const shaded = withShading(option, sustained, panels, { colors: { sustained: "a", sustainedEdge: "b", muted: "c" } });
  assert.equal(shaded.series.length, 3);
  assert.equal(shaded.series[0].name, "own");
  assert.deepEqual(shaded.series.slice(1).map((s) => [s.xAxisIndex, s.markArea.data.length, s.markArea.label.show]), [[2, 1, true], [1, 1, true]]);
  const weekly = withShading(option, sustained, panels, { colors: {}, bucket: "week" });
  assert.equal(weekly.series[1].markArea.label.show, false);
  assert.equal(withShading(option, { findings: [] }, panels, { colors: {} }), option);
  const windowed = { xAxis: [{ min: Date.parse("2026-11-05") }], series: [] };
  const clipped = withShading(windowed, sustained, panels, { colors: {} });
  assert.deepEqual(clipped.series.map((s) => s.markArea.data[0][0].xAxis), [Date.parse("2026-11-05"), Date.parse("2026-11-05")]);
  const later = { xAxis: [{ min: Date.parse("2026-11-06") }], series: [] };
  assert.equal(withShading(later, sustained, panels, { colors: {} }).series.length, 1); // HRV ended before it
});

test("the vitals page loads", () => {
  assert.ok(PAGES.find((page) => page.id === "vitals").load);
  assert.deepEqual(parseRoute("#/vitals/365").args, ["365"]);
});

// ---- Food -------------------------------------------------------------------------------------

const nutrient = (code, extra = {}) => ({
  code, name: code, unit: "g", rda: null, upper_limit: null, limit_only: false, logged: true,
  avg_per_day: 1, pct_rda: null, flag: null, ...extra,
});

test("the food window comes from the route, and anything unknown is 30 days", () => {
  assert.equal(routeDays(["90"], [7, 30, 90]), 90);
  assert.equal(routeDays(["365"], [7, 30, 90]), 30);
  assert.equal(routeDays([], [7, 30, 90]), 30);
  assert.equal(routeDays(["abc"], [7, 30, 90]), 30);
});

test("the window's dates end today, oldest first, across a month's end", () => {
  assert.deepEqual(windowDates(3, new Date(2026, 10, 1)), ["2026-10-30", "2026-10-31", "2026-11-01"]);
});

test("a day without a meal is a gap; a logged day without the nutrient is none of it", () => {
  const daily = [{ date: "2026-11-01", meals: 2, totals: { energy_kcal: 1800 } }];
  assert.deepEqual(dailyValues(daily, ["2026-10-31", "2026-11-01"], "energy_kcal"), [null, 1800]);
  assert.deepEqual(dailyValues(daily, ["2026-11-01"], "sodium"), [0]);
});

test("amounts: whole numbers from 10 up, one decimal below", () => {
  assert.equal(amount(2361.94), "2362");
  assert.equal(amount(4.25), "4.3");
  assert.equal(amount(0.8), "0.8");
  assert.equal(amount(null), "");
  assert.equal(amountText(1580.2, "mg"), "1580 mg");
});

test("a ceiling-only nutrient reads as a limit, the others as a norm with its maximum", () => {
  assert.equal(normText(nutrient("sodium", { rda: 2300, upper_limit: 2300, limit_only: true, unit: "mg" })), "limit 2300 mg");
  assert.equal(normText(nutrient("calcium", { rda: 1000, upper_limit: 2500, unit: "mg" })), "1000 mg · max 2500");
  assert.equal(normText(nutrient("protein", { rda: 56 })), "56 g");
  assert.equal(normText(nutrient("caffeine", { upper_limit: 400, unit: "mg" })), "limit 400 mg");
  assert.equal(normText(nutrient("mono_fat")), "");
  assert.equal(pctText(nutrient("sugar", { pct_rda: 153, limit_only: true })), "153% of the limit");
  assert.equal(pctText(nutrient("fiber", { pct_rda: 67 })), "67% of the norm");
  assert.equal(pctText(nutrient("x")), "");
});

test("flags: below 70% reads as low, over the limit as high, nothing else gets a pill", () => {
  assert.equal(flagStatus("deficient"), "low");
  assert.equal(flagStatus("excess"), "high");
  assert.equal(flagStatus(null), null);
  const rows = [
    nutrient("a", { flag: "deficient", pct_rda: 60 }), nutrient("b", { flag: "deficient", pct_rda: 4 }),
    nutrient("c", { flag: "excess", avg_per_day: 76, upper_limit: 50 }),
    nutrient("d", { flag: "excess", avg_per_day: 36, upper_limit: 20 }), nutrient("e"),
  ];
  assert.deepEqual(flagged(rows, "deficient").map((n) => n.code), ["b", "a"]);
  assert.deepEqual(flagged(rows, "excess").map((n) => n.code), ["d", "c"]);
});

test("a meal's note: an odd time first, then what was entered after it", () => {
  const meal = { at: "2026-11-03T02:47", date: "2026-11-03", time_check: "night", symptoms: "bloating", wellbeing: null };
  assert.equal(timeOf(meal), "02:47");
  assert.match(mealNote(meal), /^Before 04:00, so it counts toward 2026-11-03\. .* · after: bloating$/);
  assert.equal(mealNote({ ...meal, time_check: null, symptoms: null }), "");
  assert.equal(mealTypeWord("snack"), "Snack");
  assert.equal(mealTypeWord("brunch"), "brunch");
});

test("coverage counts logged days and meals, and estimates say they are estimates", () => {
  assert.equal(coverageText({ days_logged: 18, meals_total: 111, window: { days: 30 } }),
    "Meals logged on 18 of the last 30 days · 111 meals");
  assert.equal(coverageText({ days_logged: 1, meals_total: 1, window: { days: 7 } }),
    "Meals logged on 1 of the last 7 days · 1 meal");
  assert.match(sourceText([{ nutrient_source: "model_estimate" }]), /estimates/);
  assert.equal(sourceText([{ nutrient_source: "model_estimate" }, { nutrient_source: "label" }]),
    "1 of 2 meals have estimated amounts, not measurements.");
  assert.equal(sourceText([{ nutrient_source: "label" }]), "");
});

test("the charts: gaps stay empty, the norm and sodium's limit are dashed lines", () => {
  const data = {
    window: { days: 2 },
    nutrients: [
      nutrient("energy_kcal", { rda: 2500, unit: "kcal" }),
      nutrient("sodium", { rda: 2300, upper_limit: 2300, limit_only: true, unit: "mg" }),
      nutrient("potassium", { rda: 3400, unit: "mg" }),
    ],
    daily: [{ date: "2026-11-02", meals: 3, totals: { energy_kcal: 2100, sodium: 2900, potassium: 1500 } }],
  };
  const dates = ["2026-11-01", "2026-11-02"];
  const energy = energyOption(data, dates, { colors: {} });
  assert.deepEqual(energy.series[0].data, [null, 2100]);
  assert.equal(energy.series[0].markLine.data[0].yAxis, 2500);
  assert.equal(energy.tooltip.valueFormatter(undefined), "not logged");
  const salt = sodiumOption(data, dates, { colors: {} });
  assert.deepEqual(salt.series.map((s) => s.data), [[null, 2900], [null, 1500]]);
  assert.equal(salt.series[0].markLine.data[0].yAxis, 2300);
  assert.equal(salt.series[1].markLine, undefined);
});

// the emergency packet (#74) and the privacy blur (#63)
import { NFC_TAGS, cardSides, copyText, ndefSize, nfcBudget, packetLang, tallerThanCard, utf8Size } from "../web/static/pages/emergency-model.js";
import { hideTitles, isBlurShortcut, restoreTitles } from "../web/static/privacy.js";

test("emergency: the NFC size is the NDEF text record with its wrapping, in UTF-8 bytes", () => {
  // the same figures as core/emergency.py (tests/test_emergency.py)
  assert.deepEqual(NFC_TAGS.map((tag) => tag.capacity), [144, 504, 888]);
  assert.equal(ndefSize("", "en"), 10);
  assert.equal(ndefSize("abc", "en"), 13);
  assert.equal(ndefSize("абв", "uk"), 16);
  assert.equal(utf8Size("ñ"), 2);
  assert.equal(ndefSize("a".repeat(252), "en"), 1 + 3 + 3 + 1 + 255 + 1);
  assert.equal(ndefSize("a".repeat(253), "en"), 3 + 5 + 3 + 253 + 3 + 1);
});

test("emergency: over budget is reported with the overflow, the text is never shortened", () => {
  const edge = "a".repeat(134);
  assert.deepEqual(nfcBudget(edge).tags.map((tag) => tag.fits), [true, true, true]);
  const long = "Ліки: ".repeat(60);
  const budget = nfcBudget(long, "uk");
  assert.equal(budget.chars, [...long].length);
  assert.equal(budget.textBytes, utf8Size(long));
  const ntag215 = budget.tags.find((tag) => tag.tag === "NTAG215");
  assert.equal(ntag215.fits, false);
  assert.equal(ntag215.over, budget.size - 504);
  assert.equal(budget.tags.find((tag) => tag.tag === "NTAG213").over, budget.size - 144);
});

test("emergency: copying falls back when the Clipboard API is missing or refuses", async () => {
  const copied = [];
  assert.equal(await copyText("x", { writeText: async (s) => { copied.push(s); } }, () => false), "copied");
  assert.deepEqual(copied, ["x"]);
  assert.equal(await copyText("y", undefined, (s) => s === "y"), "copied");
  assert.equal(await copyText("z", { writeText: async () => { throw new Error("denied"); } }, () => true), "copied");
  assert.equal(await copyText("z", null, () => false), "failed");
  assert.equal(await copyText("z", null, () => { throw new Error("no execCommand"); }), "failed");
});

test("emergency: every lock-screen field lands on one side of the wallet card", () => {
  const keys = ["conditions", "medications", "allergies", "blood_type", "emergency_contact", "notes", "new_field"];
  const sides = cardSides(keys.map((key) => ({ key })));
  assert.deepEqual(sides.front.map((f) => f.key), ["allergies", "blood_type", "emergency_contact"]);
  assert.deepEqual(sides.back.map((f) => f.key), ["conditions", "medications", "notes", "new_field"]);
  assert.equal(packetLang("es"), "es");
  assert.equal(packetLang("de"), "en");
});

test("emergency: the page comes after the visit report", () => {
  const ids = PAGES.map((page) => page.id);
  assert.equal(ids.indexOf("emergency"), ids.indexOf("report") + 1);
});

test("privacy blur: Alt+Shift+B toggles, but not while typing", () => {
  const key = (target, extra = {}) => ({ altKey: true, shiftKey: true, ctrlKey: false, metaKey: false, code: "KeyB", target, ...extra });
  assert.equal(isBlurShortcut(key({ tagName: "BODY" })), true);
  assert.equal(isBlurShortcut(key({ tagName: "TEXTAREA" })), false);
  assert.equal(isBlurShortcut(key({ tagName: "DIV", isContentEditable: true })), false);
  assert.equal(isBlurShortcut(key({ tagName: "BODY" }, { ctrlKey: true })), false);
  assert.equal(isBlurShortcut(key({ tagName: "BODY" }, { code: "KeyN" })), false);
});

test("emergency: a card side taller than the 54 mm probe is reported, the same height is not", () => {
  assert.equal(tallerThanCard([204.1, 204.1], 204.1), false);
  assert.equal(tallerThanCard([204.1, 313], 204.1), true);
  assert.equal(tallerThanCard([204.5], 204.1), false); // rounding, not overflow
});

test("privacy blur: tooltips are put aside while blurred and given back after", () => {
  // a minimal stand-in for the DOM: elements with attributes, and SVG <title> elements with text
  class Node {
    constructor(localName, attrs = {}, text = "") {
      this.localName = localName;
      this.attrs = new Map(Object.entries(attrs));
      this.textContent = text;
    }
    getAttribute(name) { return this.attrs.get(name) ?? null; }
    setAttribute(name, value) { this.attrs.set(name, String(value)); }
    removeAttribute(name) { this.attrs.delete(name); }
  }
  const year = new Node("button", { title: "1985: born, 3 records" });
  const mark = new Node("title", {}, "Hypothyroidism · 2022-03-01");
  const empty = new Node("title", {}, "");
  const nodes = [year, mark, empty];
  const root = {
    querySelectorAll(selector) {
      const attr = selector.match(/^\[([\w-]+)\]$/);
      if (attr) return nodes.filter((n) => n.attrs.has(attr[1]));
      return nodes.filter((n) => n.localName === selector);
    },
  };
  hideTitles(root);
  assert.equal(year.getAttribute("title"), null);
  assert.equal(mark.textContent, "");
  assert.equal(empty.getAttribute("data-privacy-title"), null);
  hideTitles(root); // again (a redraw): nothing lost
  restoreTitles(root);
  assert.equal(year.getAttribute("title"), "1985: born, 3 records");
  assert.equal(mark.textContent, "Hypothyroidism · 2022-03-01");
  assert.equal(year.getAttribute("data-privacy-title"), null);
});
