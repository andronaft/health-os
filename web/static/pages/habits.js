// The habits page (#57): each habit with its amount and how long it has run (or how long ago it
// stopped), and one strip over the years with a bar per habit. Date arithmetic on what was
// recorded, nothing more: no score and no judgement.

import { api } from "../api.js";
import { el } from "../components.js";
import { LANG, t } from "../strings.js";
import { tn } from "./labs-model.js";
import { habitAmount, habitBar, habitStreak, word } from "./record-model.js";
import { toDay } from "./timeline-model.js";

const NS = "http://www.w3.org/2000/svg";
const svg = (tag, attributes = {}, ...children) => {
  const node = document.createElementNS(NS, tag);
  for (const [name, value] of Object.entries(attributes)) if (value !== null && value !== undefined) node.setAttribute(name, value);
  node.append(...children.filter(Boolean));
  return node;
};

const ROW = 30;

/** One strip over the years, a bar per dated habit. Drawn at the column's real width (and again
 * when it changes), so the year labels are never stretched. */
function strip(data, view) {
  const dated = data.habits.filter((h) => h.start_date);
  if (!dated.length) return null;
  const today = toDay(data.today);
  const from = Math.min(data.born ? toDay(data.born) : Infinity, ...dated.map((h) => toDay(h.start_date)));
  const firstYear = new Date(from * 86400000).getUTCFullYear();
  const lastYear = new Date(today * 86400000).getUTCFullYear();
  const height = 22 + dated.length * ROW;
  const plot = el("div", { class: "hb-plot" });

  function draw() {
    const width = Math.max(200, plot.clientWidth || 600);
    const step = (lastYear - firstYear) / (width / 60) > 5 ? 10 : 5;
    const x = (day) => ((day - from) / Math.max(1, today - from)) * width;
    const grid = [];
    for (let year = Math.ceil(firstYear / step) * step; year <= lastYear; year += step) {
      const gx = x(Date.UTC(year, 0, 1) / 86400000);
      grid.push(svg("line", { class: "hb-grid", x1: gx, x2: gx, y1: 18, y2: height }),
        gx + 36 <= width && svg("text", { class: "hb-year", x: gx + 4, y: 13 }, String(year)));
    }
    const bars = dated.map((h, i) => {
      const bar = habitBar(h, from, today);
      return svg("rect", { class: `hb-bar hb-${h.status}${bar.undated ? " hb-undated" : ""}`, x: bar.left * width, y: 22 + i * ROW + 5,
        width: bar.undated ? 10 : bar.width * width, height: ROW - 10, rx: 4 });
    });
    plot.replaceChildren(svg("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img",
      "aria-label": t("record.habits.strip_label") }, ...grid, ...bars));
  }

  let lastWidth = 0;
  const observer = new ResizeObserver(() => {
    if (!view.isConnected) {
      observer.disconnect();
      return;
    }
    if (plot.clientWidth !== lastWidth) {
      lastWidth = plot.clientWidth;
      draw();
    }
  });
  observer.observe(plot);
  // the names sit in HTML beside the strip, one per bar
  return el("figure", { class: "hb-strip" },
    el("ol", { class: "hb-names", "aria-hidden": "true" }, ...dated.map((h) => el("li", {}, h.habit_type))),
    plot,
    el("figcaption", { class: "quiet" }, t("record.habits.strip_note", { year: firstYear })));
}

function habitCard(h) {
  const amount = habitAmount(h);
  return el("li", { class: `card rec-habit hb-${h.status}` },
    el("h3", {}, h.habit_type, el("span", { class: "rec-tag" }, word("habit_status", h.status))),
    el("p", { class: "rec-streak" }, habitStreak(h)),
    amount && el("p", {}, amount),
    h.notes && el("p", { class: "quiet" }, h.notes));
}

export async function render(view) {
  const data = await api(`habits?lang=${LANG}`);
  if (!data.habits.length) {
    view.replaceChildren(el("div", { class: "record" },
      el("p", {}, t("record.habits.none")),
      el("p", { class: "quiet" }, t("empty.note"))));
    return;
  }
  const current = data.habits.filter((h) => h.status === "current");
  const rest = data.habits.filter((h) => h.status !== "current");
  view.replaceChildren(el("div", { class: "record" },
    el("p", { class: "quiet" }, t("record.habits.note")),
    strip(data, view),
    el("section", {},
      el("h2", {}, t("record.habits.current", { n: current.length })),
      current.length ? el("ul", { class: "rec-cards" }, ...current.map(habitCard)) : el("p", { class: "quiet" }, t("record.habits.current_none"))),
    rest.length > 0 && el("section", {},
      el("h2", {}, t("record.habits.past", { n: rest.length })),
      el("ul", { class: "rec-cards" }, ...rest.map(habitCard))),
    el("p", {}, el("a", { href: "#/timeline" }, t("record.open_timeline")))));
}
