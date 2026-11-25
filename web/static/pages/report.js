// The doctor-visit report (#60): one A4 page to print or save as PDF with the browser's own print.
// The report has its own language, chosen apart from the UI's; the controls above it speak the UI's
// language and are not printed. Approved values only; the questions box stays in this browser
// (localStorage) and is never sent to the server.

import { api, explain } from "../api.js";
import { el, errorState } from "../components.js";
import { LANG, t } from "../strings.js";
import {
  LANG_KEY, allergyDetail, changeShort, changesSource, changesTitle, diagnosisDetail, footerText,
  groupDiagnoses, loadQuestions, medicationDetail, methodText, miniChart, noOtherChanges, outLead,
  profileLine, reportDate, reportRange, reportUnit, reportValue, resultChange, saveQuestions,
  statusText, streakText, trendLabel, trendSpan,
} from "./report-model.js";
import { LANG_NAMES, REPORT_LANGS, reportLang, translator } from "./report-strings.js";

const SVG = "http://www.w3.org/2000/svg";
const CHART = { width: 200, height: 56 };

function svg(tag, attributes = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  node.append(...children);
  return node;
}

function storage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function savedLang() {
  try {
    return reportLang(storage()?.getItem(LANG_KEY) ?? LANG);
  } catch {
    return reportLang(LANG);
  }
}

const section = (cls, title, ...children) =>
  el("section", { class: `report-section ${cls}` }, el("h2", {}, title), ...children);
const list = (items) => el("ul", { class: "report-list" }, ...items);
const item = (name, detail) => el("li", {}, el("strong", {}, name), detail && el("span", { class: "report-detail" }, ` — ${detail}`));

function allergies(data, tr) {
  const rows = data.allergies;
  return el("section", { class: "report-allergies", "data-none": !rows.length },
    el("h2", {}, el("span", { class: "report-alert-icon", "aria-hidden": "true" }, "⚠"), tr.t("allergies.title")),
    rows.length
      ? list(rows.map((a) => item(a.allergen, allergyDetail(a, tr))))
      : el("p", {}, tr.t("allergies.none")));
}

function medications(data, tr) {
  return section("report-meds", tr.t("meds.title"),
    data.medications.length
      ? list(data.medications.map((m) => item(m.name, medicationDetail(m, tr))))
      : el("p", { class: "quiet" }, tr.t("meds.none")));
}

function diagnoses(data, tr) {
  const groups = groupDiagnoses(data.diagnoses);
  const parts = ["confirmed", "in_question", "past"].filter((key) => groups[key].length).map((key) =>
    el("div", { class: "report-diag-group", "data-group": key },
      el("h3", {}, tr.t(`diag.${key}`)),
      list(groups[key].map((d) => item(d.name, diagnosisDetail(d, tr))))));
  return section("report-diagnoses", tr.t("diag.title"),
    ...(parts.length ? parts : [el("p", { class: "quiet" }, tr.t("diag.none"))]));
}

function outOfRange(data, tr) {
  const { rows } = data.out_of_range;
  const head = ["marker", "value", "range", "date", "since"].map((key) =>
    el("th", { scope: "col" }, tr.t(`out.col.${key}`)));
  return section("report-out", tr.t("out.title"),
    el("p", {}, outLead(data.out_of_range, tr)),
    rows.length > 0 && el("table", { class: "report-table" },
      el("thead", {}, el("tr", {}, ...head)),
      el("tbody", {}, ...rows.map((r) => el("tr", { "data-status": r.status },
        el("th", { scope: "row" }, r.name,
          r.newer_pending && el("span", { class: "report-note" }, tr.t("out.newer_pending"))),
        el("td", { class: "num" }, reportValue(r, tr), " ", el("span", { class: "report-status" }, statusText(r.status, tr))),
        el("td", { class: "num" }, reportRange(r, tr)),
        el("td", {}, reportDate(r.at, tr)),
        el("td", {}, streakText(r, tr)))))));
}

function trendChart(trend, tr) {
  const chart = miniChart(trend, CHART.width, CHART.height);
  const node = svg("svg", {
    class: "report-chart", viewBox: `0 0 ${CHART.width} ${CHART.height}`, role: "img",
    "aria-label": trendLabel(trend, tr), preserveAspectRatio: "none",
  });
  if (chart.band) node.append(svg("rect", { class: "band", x: 0, y: chart.band.y, width: CHART.width, height: chart.band.height }));
  if (chart.points.length > 1) {
    node.append(svg("polyline", { points: chart.points.map((p) => `${p.x},${p.y}`).join(" "), "vector-effect": "non-scaling-stroke" }));
  }
  for (const p of chart.points) node.append(svg("circle", { cx: p.x, cy: p.y, r: 2.6, class: p.out ? "out" : "" }));
  return node;
}

function trends(data, tr) {
  if (!data.trends.length) return null;
  return section("report-trends", tr.t("trends.title"),
    el("div", { class: "report-trend-grid" }, ...data.trends.map((trend) => {
      const last = trend.points.at(-1);
      return el("figure", { class: "report-trend" },
        el("figcaption", {},
          el("strong", {}, trend.name), " ",
          el("span", { class: "report-detail" },
            `${reportValue({ value: last.value, unit: trend.unit }, tr)} · ${trendSpan(trend, tr)}`)),
        trendChart(trend, tr),
        trend.change && el("p", { class: "report-note" }, changeShort(trend.change, tr)));
    })),
    data.trends.some((trend) => trend.ref_min !== null || trend.ref_max !== null) &&
      el("p", { class: "report-note" }, tr.t("trends.band")));
}

function changes(data, tr) {
  const c = data.changes;
  const results = c.results.map((r) => {
    const parts = resultChange(r, tr);
    return el("li", { "data-moved": r.moved ?? false },
      el("strong", {}, r.name), ": ", parts.now,
      parts.status && el("span", { class: "report-status" }, ` ${parts.status}`),
      parts.moved && el("span", { class: "report-moved" }, ` · ${parts.moved}`),
      el("span", { class: "report-detail" }, ` · ${reportDate(r.at, tr)} · ${parts.before}`),
      parts.change && el("span", { class: "report-note" }, parts.change));
  });
  const meds = (key, rows, stopped) => rows.length > 0 && el("div", {},
    el("h3", {}, tr.t(key)),
    list(rows.map((m) => item(m.name, medicationDetail(m, tr, { stopped })))));
  return section("report-changes", changesTitle(c, tr),
    el("p", { class: "report-note" }, changesSource(c, tr)),
    el("h3", {}, tr.t("changes.results")),
    results.length ? list(results) : el("p", { class: "quiet" }, tr.t("changes.results.none", { date: reportDate(c.since, tr) })),
    meds("changes.meds_started", c.medications.started, false),
    meds("changes.meds_stopped", c.medications.stopped, true),
    c.diagnoses.length > 0 && el("div", {},
      el("h3", {}, tr.t("changes.diagnoses")),
      list(c.diagnoses.map((d) => item(d.name, diagnosisDetail(d, tr))))),
    noOtherChanges(c) && el("p", { class: "quiet" }, tr.t("changes.none_else", { date: reportDate(c.since, tr) })));
}

function questions(tr) {
  const store = storage();
  const printed = el("div", { class: "report-questions-print" });
  const box = el("textarea", {
    class: "report-questions-box", rows: "4", placeholder: tr.t("questions.placeholder"),
    "aria-label": tr.t("questions.title"),
  });
  const sync = () => {
    // a textarea prints only what fits in it: the print shows a copy that grows with the text
    printed.textContent = box.value;
    printed.dataset.empty = String(!box.value.trim());
  };
  box.value = loadQuestions(store);
  box.addEventListener("input", () => {
    saveQuestions(store, box.value);
    sync();
  });
  sync();
  return section("report-questions", tr.t("questions.title"), box, printed);
}

function sheet(data, tr) {
  const footer = el("p", { class: "report-footer" }, footerText(data, tr));
  if (data.empty) {
    return el("article", { class: "report-sheet", lang: tr.lang },
      el("h2", {}, tr.t("title")), el("p", {}, tr.t("empty")), footer);
  }
  const body = el("div", { class: "report-body" },
    el("header", { class: "report-head" },
      el("p", { class: "report-title" }, tr.t("title")),
      el("p", { class: "report-profile" }, profileLine(data.profile, tr)),
      el("p", { class: "report-detail" }, tr.t("prepared", { date: reportDate(data.generated_at, tr) }))),
    allergies(data, tr),
    el("div", { class: "report-columns" }, medications(data, tr), diagnoses(data, tr)),
    outOfRange(data, tr),
    trends(data, tr),
    changes(data, tr),
    questions(tr),
    data.rcv.markers.length > 0 && el("p", { class: "report-method" }, methodText(data.rcv, tr)));
  // the footer repeats on every printed page: a fixed element, and an empty table footer of the
  // same height that the browser repeats on each page, so the content never runs under it
  return el("article", { class: "report-sheet", lang: tr.lang },
    el("table", { class: "report-pages", role: "presentation" },
      el("tbody", {}, el("tr", {}, el("td", {}, body))),
      el("tfoot", { "aria-hidden": "true" }, el("tr", {}, el("td", {}, el("div", { class: "report-footer-space" }))))),
    footer);
}

function controls(state, rerender, data) {
  const langSelect = el("select", {
    onchange: (e) => {
      state.lang = e.target.value;
      try {
        storage()?.setItem(LANG_KEY, state.lang);
      } catch {
        // storage blocked: the choice lasts until the page is left
      }
      rerender();
    },
  }, ...REPORT_LANGS.map((code) => el("option", { value: code, lang: code, selected: code === state.lang }, LANG_NAMES[code])));
  const since = el("input", {
    type: "date", value: state.since ?? String(data?.changes?.since ?? "").slice(0, 10),
    onchange: (e) => {
      state.since = e.target.value || null;
      rerender();
    },
  });
  return el("div", { class: "report-controls" },
    el("label", {}, t("report.language"), " ", langSelect),
    el("label", {}, t("report.since"), " ", since),
    state.since && el("button", { type: "button", onclick: () => { state.since = null; rerender(); } }, t("report.since_reset")),
    el("button", { type: "button", class: "report-print", onclick: () => window.print() }, t("report.print")),
    el("p", { class: "quiet" }, t("report.note")));
}

export async function render(view) {
  const state = { lang: savedLang(), since: null };
  const draw = async () => {
    const query = new URLSearchParams({ lang: state.lang });
    if (state.since) query.set("since", state.since);
    const data = await api(`report?${query}`);
    const tr = translator(state.lang);
    view.replaceChildren(el("div", { class: "report" }, controls(state, redraw, data), sheet(data, tr)));
  };
  // a change of language or date: the frame only catches the first render's errors
  const redraw = () => draw().catch((err) => {
    console.error(err);
    view.replaceChildren(errorState({ message: explain(err), onRetry: redraw }));
  });
  await draw();
}
