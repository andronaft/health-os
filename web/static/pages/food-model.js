// What the Food page says and draws, from what /api/v1/food sends. Nothing here touches the page,
// so it can be tested without a browser (tests/web_ui.test.mjs).

import { formatDate } from "../components.js";
import { t } from "../strings.js";
import { tn } from "./labs-model.js";

export const DEFAULT_DAYS = 30;
export const MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack", "drink"];
export const CATEGORIES = ["energy", "macro", "fat", "mineral", "vitamin", "other"];
// the tiles: the averages most people look for first
export const TILE_CODES = ["energy_kcal", "protein", "carbs", "fat", "fiber", "sugar", "sodium"];

/** #/food/90 → 90; anything else → the default window. */
export function routeDays(args, choices) {
  const days = Number.parseInt(args?.[0], 10);
  return choices.includes(days) ? days : DEFAULT_DAYS;
}

export const periodHref = (days) => `#/food/${days}`;

/** Every date of the window, oldest first, ending today ("YYYY-MM-DD" in local time). */
export function windowDates(days, today = new Date()) {
  const out = [];
  for (let i = days - 1; i >= 0; i--) {
    const day = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
    const pad = (n) => String(n).padStart(2, "0");
    out.push(`${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`);
  }
  return out;
}

/** One nutrient's daily totals lined up with `dates`: null on a day with no meal logged. */
export function dailyValues(daily, dates, code) {
  const byDate = new Map(daily.map((day) => [formatDate(day.date), day]));
  return dates.map((date) => {
    const day = byDate.get(date);
    if (!day) return null;
    return day.totals[code] ?? 0; // a logged day without this nutrient: none of it was logged
  });
}

/** Whole numbers from 10 up; one decimal below, without a trailing ".0". */
export function amount(value) {
  if (value === null || value === undefined) return "";
  const rounded = Math.abs(value) >= 10 ? Math.round(value) : Math.round(value * 10) / 10;
  return String(rounded);
}

export const amountText = (value, unit) => (value === null || value === undefined ? "" : `${amount(value)} ${unit}`);

/** The catalog's daily norm: "56 g", "1000 mg · max 2500"; a ceiling-only nutrient "limit 2300 mg". */
export function normText({ rda, upper_limit: limit, limit_only: limitOnly, unit }) {
  if (limitOnly) return t("food.norm.limit", { value: amount(limit), unit });
  if (rda === null && limit !== null) return t("food.norm.limit", { value: amount(limit), unit });
  if (rda === null) return "";
  const norm = `${amount(rda)} ${unit}`;
  return limit !== null ? `${norm} · ${t("food.norm.max", { value: amount(limit) })}` : norm;
}

/** "153% of the norm" / "98% of the limit"; "" when there is no norm or nothing was logged. */
export function pctText({ pct_rda: pct, limit_only: limitOnly }) {
  if (pct === null || pct === undefined) return "";
  return t(limitOnly ? "food.pct.limit" : "food.pct.norm", { pct });
}

/** The flag's pill: below 70% of the norm reads as low, above the safe limit as high. */
export function flagStatus(flag) {
  if (flag === "deficient") return "low";
  if (flag === "excess") return "high";
  return null;
}

export const flagWord = (flag) => (flag ? t(`food.flag.${flag}`) : "");

export const mealTypeWord = (type) => (MEAL_TYPES.includes(type) ? t(`food.meal.${type}`) : type ?? "");

export const categoryWord = (category) =>
  (CATEGORIES.includes(category) ? t(`food.category.${category}`) : category ?? "");

/** "HH:MM" of a meal's wall-clock time. */
export const timeOf = (meal) => String(meal.at ?? "").slice(11, 16);

/** What the meal row notes: an odd time first, then symptoms and wellbeing as entered. */
export function mealNote(meal) {
  const parts = [];
  if (meal.time_check) parts.push(t(`food.check.${meal.time_check}`, { date: formatDate(meal.date) }));
  if (meal.symptoms) parts.push(t("food.note.symptoms", { text: meal.symptoms }));
  if (meal.wellbeing) parts.push(t("food.note.wellbeing", { text: meal.wellbeing }));
  return parts.join(" · ");
}

/** "Logged on 18 of the last 30 days · 111 meals" — and never a judgement of the diet. */
export function coverageText({ days_logged: logged, meals_total: meals, window: { days } }) {
  return `${t("food.coverage", { logged, days })} · ${tn("food.meals", { n: meals })}`;
}

/** Where the amounts came from: estimates made when the meal was logged, unless a source says so. */
export function sourceText(meals) {
  if (!meals.length) return "";
  const estimated = meals.filter((meal) => meal.nutrient_source === "model_estimate").length;
  if (estimated === meals.length) return t("food.source.all_estimates");
  if (!estimated) return "";
  return t("food.source.some_estimates", { n: estimated, total: meals.length });
}

/** The nutrients with a flag, worst first: lowest share of the norm, then furthest over the limit. */
export function flagged(nutrients, flag) {
  const rows = nutrients.filter((n) => n.flag === flag);
  return flag === "deficient"
    ? rows.sort((a, b) => a.pct_rda - b.pct_rda)
    : rows.sort((a, b) => b.avg_per_day / b.upper_limit - a.avg_per_day / a.upper_limit);
}

const byCode = (nutrients) => new Map(nutrients.map((n) => [n.code, n]));

/** Bars per day; days with no meal logged stay empty, and the catalog's norm is a dashed line. */
export function energyOption(data, dates, { colors }) {
  const energy = byCode(data.nutrients).get("energy_kcal");
  const values = dailyValues(data.daily, dates, "energy_kcal");
  return {
    animation: false,
    grid: { left: 48, right: 16, top: 24, bottom: 32 },
    tooltip: { trigger: "axis", valueFormatter: (v) => (v === null || v === undefined ? t("food.chart.not_logged") : `${amount(v)} kcal`) },
    xAxis: { type: "category", data: dates, axisLabel: { formatter: (d) => d.slice(5) } },
    yAxis: { type: "value", name: "kcal" },
    series: [{
      type: "bar",
      name: energy?.name ?? "kcal",
      data: values,
      itemStyle: { color: colors.bar },
      markLine: energy?.rda ? {
        silent: true,
        symbol: "none",
        lineStyle: { type: "dashed", color: colors.norm },
        label: { position: "insideEndTop", formatter: t("food.chart.norm_line", { value: amount(energy.rda) }), color: colors.norm },
        data: [{ yAxis: energy.rda }],
      } : undefined,
    }],
  };
}

/** Sodium and potassium per day in mg, with sodium's safe upper limit as a dashed line. */
export function sodiumOption(data, dates, { colors }) {
  const nutrients = byCode(data.nutrients);
  const sodium = nutrients.get("sodium");
  const potassium = nutrients.get("potassium");
  const line = (nutrient, color, extra = {}) => ({
    type: "line",
    name: nutrient?.name ?? "",
    data: dailyValues(data.daily, dates, nutrient?.code),
    connectNulls: false,
    symbolSize: 6,
    itemStyle: { color },
    lineStyle: { color, width: 2 },
    ...extra,
  });
  return {
    animation: false,
    grid: { left: 56, right: 16, top: 40, bottom: 32 },
    legend: { top: 0 },
    tooltip: { trigger: "axis", valueFormatter: (v) => (v === null || v === undefined ? t("food.chart.not_logged") : `${amount(v)} mg`) },
    xAxis: { type: "category", data: dates, axisLabel: { formatter: (d) => d.slice(5) } },
    yAxis: { type: "value", name: "mg" },
    series: [
      line(sodium, colors.sodium, sodium?.upper_limit ? {
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed", color: colors.limit },
          label: { position: "insideEndTop", formatter: t("food.chart.limit_line", { value: amount(sodium.upper_limit) }), color: colors.limit },
          data: [{ yAxis: sodium.upper_limit }],
        },
      } : {}),
      line(potassium, colors.potassium),
    ],
  };
}

export const energyLabel = (data) => t("food.chart.energy_label", { days: data.window.days });
export const sodiumLabel = (data) => t("food.chart.sodium_label", { days: data.window.days });
