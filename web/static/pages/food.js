// The Food page: #/food is the last 30 days of the food diary, #/food/7 and #/food/90 other windows.
// The averages and flags are nutrition_report's; the amounts are what was logged with each meal,
// usually estimates. Read-only: meals are logged and fixed through the MCP client.

import { api } from "../api.js";
import { dataTable, el, emptyState, statusIcon } from "../components.js";
import { LANG, t } from "../strings.js";
import {
  CATEGORIES, TILE_CODES, amount, amountText, categoryWord, coverageText, energyLabel, energyOption, flagStatus,
  flagWord, flagged, mealNote, mealTypeWord, normText, pctText, periodHref, routeDays, sodiumLabel,
  sodiumOption, sourceText, timeOf, windowDates,
} from "./food-model.js";

const CHOICES = [7, 30, 90];
const quiet = (text) => el("p", { class: "quiet" }, text);
const section = (title, ...children) =>
  el("section", { class: "labs-section" }, el("h2", {}, title), ...children);

/** The word and the icon say it; the colour only repeats it (as the status pill). */
function flagPill(flag) {
  const status = flagStatus(flag);
  if (!status) return "";
  return el("span", { class: "pill", "data-status": status },
    el("span", { class: "pill-icon", "aria-hidden": "true" }, statusIcon(status)), flagWord(flag));
}

function periodNav(days, choices) {
  return el("nav", { class: "food-period", "aria-label": t("food.period.label") },
    ...choices.map((choice) => el("a", {
      href: periodHref(choice),
      "aria-current": choice === days ? "page" : null,
    }, t("food.period.days", { days: choice }))));
}

function tile(nutrient) {
  return el("article", { class: "tile" },
    el("h3", {}, nutrient.name),
    nutrient.logged
      ? el("p", { class: "tile-value" }, el("strong", {}, amount(nutrient.avg_per_day)), ` ${nutrient.unit}`)
      : quiet(t("food.not_logged")),
    el("p", { class: "quiet" }, [pctText(nutrient), normText(nutrient)].filter(Boolean).join(" · ")),
    nutrient.flag && el("p", {}, flagPill(nutrient.flag)));
}

function flagList(nutrients, flag) {
  const rows = flagged(nutrients, flag);
  if (!rows.length) return null;
  return el("div", {},
    el("h3", {}, tn(`food.flagged.${flag}`, rows.length)),
    el("ul", { class: "plain food-flagged" }, ...rows.map((n) =>
      el("li", {}, flagPill(n.flag), " ", el("strong", {}, n.name), " ",
        amountText(n.avg_per_day, n.unit), " ", el("span", { class: "quiet" }, `(${[pctText(n), normText(n)].filter(Boolean).join(" · ")})`)))));
}

const tn = (key, n) => t(n === 1 ? `${key}_one` : key, { n });

function nutrientTable(nutrients) {
  const select = el("select", {},
    el("option", { value: "" }, t("food.category.all")),
    ...CATEGORIES.filter((c) => nutrients.some((n) => n.category === c))
      .map((c) => el("option", { value: c }, categoryWord(c))));
  const table = dataTable({
    caption: t("food.caption.nutrients"),
    rows: nutrients,
    columns: [
      { key: "name", label: t("food.col.nutrient") },
      { key: "category", label: t("food.col.category"), value: (n) => categoryWord(n.category) },
      {
        key: "avg",
        label: t("food.col.average"),
        numeric: true,
        value: (n) => n.avg_per_day,
        render: (n) => (n.logged ? amountText(n.avg_per_day, n.unit) : el("span", { class: "quiet" }, t("food.not_logged"))),
        text: (n) => (n.logged ? amountText(n.avg_per_day, n.unit) : t("food.not_logged")),
      },
      { key: "norm", label: t("food.col.norm"), value: normText, sortable: false },
      { key: "pct", label: t("food.col.pct"), numeric: true, value: (n) => n.pct_rda, render: (n) => (n.pct_rda === null ? "" : `${n.pct_rda}%`) },
      { key: "flag", label: t("food.col.flag"), value: (n) => flagWord(n.flag) || null, render: (n) => flagPill(n.flag) },
    ],
  });
  select.addEventListener("change", () =>
    table.setRows(select.value ? nutrients.filter((n) => n.category === select.value) : nutrients));
  return el("div", {},
    el("div", { class: "labs-filters" }, el("label", {}, t("food.col.category"), " ", select)),
    table.element);
}

function mealTable(meals) {
  const nutrient = (code, label) => ({
    key: code,
    label,
    numeric: true,
    value: (m) => m.nutrients[code],
    render: (m) => amount(m.nutrients[code]),
  });
  return dataTable({
    caption: t("food.caption.meals"),
    rows: meals,
    sort: { key: "at", direction: "desc" },
    empty: emptyState({ message: t("food.none") }),
    columns: [
      { key: "at", label: t("food.col.when"), render: (m) => el("span", { class: "nowrap" }, `${m.at.slice(0, 10)} ${timeOf(m)}`) },
      { key: "meal_type", label: t("food.col.type"), value: (m) => mealTypeWord(m.meal_type) },
      {
        key: "description",
        label: t("food.col.meal"),
        wrap: true,
        text: (m) => [m.description, m.portion].filter(Boolean).join(" "),
        render: (m) => el("span", {}, m.description, m.portion && el("br"), m.portion && el("span", { class: "quiet" }, m.portion)),
      },
      nutrient("energy_kcal", "kcal"),
      nutrient("protein", t("food.col.protein")),
      nutrient("carbs", t("food.col.carbs")),
      nutrient("fat", t("food.col.fat")),
      nutrient("sugar", t("food.col.sugar")),
      nutrient("sodium", t("food.col.sodium")),
      { key: "note", label: t("food.col.note"), wrap: true, value: (m) => mealNote(m) || null },
    ],
  }).element;
}

function wellbeingTable(rows) {
  if (!rows.length) return null;
  return section(t("food.wellbeing.title"),
    quiet(t("food.wellbeing.note")),
    dataTable({
      caption: t("food.wellbeing.title"),
      rows,
      filterable: false,
      columns: [
        { key: "wellbeing", label: t("food.col.wellbeing") },
        { key: "meals", label: t("food.col.meals"), numeric: true },
        { key: "avg_gi", label: t("food.col.gi"), numeric: true },
        { key: "avg_sugar", label: t("food.col.sugar_g"), numeric: true },
        { key: "avg_sodium", label: t("food.col.sodium_mg"), numeric: true },
      ],
    }).element);
}

async function drawCharts(data, dates, energyBox, sodiumBox) {
  const { drawChart, tokenColor } = await import("../chart.js"); // 1 MB: only when there is a chart
  await drawChart(energyBox, energyOption(data, dates, {
    colors: { bar: tokenColor("--chart-1"), norm: tokenColor("--muted") },
  }), { label: energyLabel(data) });
  await drawChart(sodiumBox, sodiumOption(data, dates, {
    colors: { sodium: tokenColor("--chart-2"), potassium: tokenColor("--chart-3"), limit: tokenColor("--high") },
  }), { label: sodiumLabel(data) });
}

export async function render(view, args) {
  const days = routeDays(args, CHOICES);
  const data = await api(`food?lang=${LANG}&days=${days}`);
  if (!view.isConnected) return;
  const nav = periodNav(data.window.days, data.window.choices);
  if (!data.meals_total) {
    view.replaceChildren(el("div", { class: "labs" }, nav,
      emptyState({ message: t("food.none_in_window", { days: data.window.days }) })));
    return;
  }
  const nutrients = data.nutrients;
  const byCode = new Map(nutrients.map((n) => [n.code, n]));
  const dates = windowDates(data.window.days);
  const energyBox = el("div", { class: "labs-chart" });
  const sodiumBox = el("div", { class: "labs-chart" });
  const deficient = flagList(nutrients, "deficient");
  const excess = flagList(nutrients, "excess");

  view.replaceChildren(el("div", { class: "labs food" },
    nav,
    el("p", { class: "figure" }, coverageText(data)),
    quiet(t("food.note.averages")),
    sourceText(data.meals) && quiet(sourceText(data.meals)),
    quiet(t("food.read_only")),
    section(t("food.averages.title"),
      el("div", { class: "tiles" }, ...TILE_CODES.map((code) => byCode.get(code)).filter(Boolean).map(tile))),
    (deficient || excess) && section(t("food.flagged.title"), deficient, excess,
      quiet(t("food.flagged.note"))),
    section(t("food.chart.energy_title"), energyBox, quiet(t("food.chart.gaps"))),
    section(t("food.chart.sodium_title"), sodiumBox, quiet(t("food.chart.sodium_note"))),
    section(t("food.nutrients.title"), nutrientTable(nutrients)),
    section(t("food.meals.title"),
      data.meals_truncated && quiet(t("food.meals.truncated", { n: data.meals.length })),
      mealTable(data.meals)),
    wellbeingTable(data.wellbeing)));
  await drawCharts(data, dates, energyBox, sodiumBox);
}
