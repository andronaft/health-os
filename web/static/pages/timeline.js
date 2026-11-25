// The timeline page (#57): the whole record on one axis. Lanes of events (diagnoses, care, lab
// panels, vaccinations, documents) and periods drawn as bars (medications start → stop, habits),
// a "life in years" strip to jump to a year, zoom and pan by button, key or drag, and the same
// record as a table for screen readers and print. A panel with values under review is hollow.

import { api } from "../api.js";
import { dataTable, el, emptyState, formatDate } from "../components.js";
import { LANG, t } from "../strings.js";
import { tn } from "./labs-model.js";
import {
  canZoomIn, eventDetails, eventLabel, eventTitle, fullRange, isPendingEvent, isRefuted, isWhole, kindWord,
  lanesOf, laneWord, panRange, panelLinks, periodDates, periodDetails, periodLabel, presentLanes, rangeText,
  scaleX, tableRows, ticks, toDay, yearCellLabel, yearCells, yearRange, zoomRange,
} from "./timeline-model.js";

const NS = "http://www.w3.org/2000/svg";
const AXIS = 26;
const LANE_HEAD = 20;
const ROW = 26;
const LANE_GAP = 10;
const BAR = 18;
const CHAR = 6.6; // px per character of the 12px label font, near enough to decide what fits

function svg(tag, attributes = {}, ...children) {
  const node = document.createElementNS(NS, tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === undefined || value === null || value === false) continue;
    if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else node.setAttribute(name, value === true ? "" : value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined && child !== false));
  return node;
}

// a shape per lane, so the kind never rests on colour alone
function mark(lane, x, y) {
  const r = 6.5;
  switch (lane) {
    case "diagnoses":
      return svg("path", { class: "tl-mark", d: `M${x},${y - r - 1}L${x + r + 1},${y}L${x},${y + r + 1}L${x - r - 1},${y}Z` });
    case "labs":
      return svg("rect", { class: "tl-mark", x: x - r + 0.5, y: y - r + 0.5, width: 2 * r - 1, height: 2 * r - 1, rx: 1.5 });
    case "vaccinations":
      return svg("path", { class: "tl-mark", d: `M${x},${y - r - 1}L${x + r + 1},${y + r - 0.5}L${x - r - 1},${y + r - 0.5}Z` });
    case "documents":
      return svg("path", { class: "tl-mark", d: `M${x - 5},${y - 7}h7l3,3v11h-10Z` });
    default:
      return svg("circle", { class: "tl-mark", cx: x, cy: y, r });
  }
}

/**
 * A bar's name: inside it when it fits, else beside it (right, then left) where its row has
 * room, else as much as fits inside. The full name is always in the bar's label and tooltip.
 */
function barLabel(title, { x1, x2, tip, y, width, before, after }) {
  const need = (title.length + 1) * CHAR;
  const inside = Math.max(x1, 0);
  const visibleWidth = Math.min(x2, width) - inside;
  if (need < visibleWidth - 8) return svg("text", { class: "tl-label", x: inside + 6, y }, title);
  if (x2 + tip + 6 + need < Math.min(after, width)) return svg("text", { class: "tl-label", x: x2 + tip + 6, y }, title);
  if (x1 - 6 - need > Math.max(before, 0)) return svg("text", { class: "tl-label", x: x1 - 6, y, "text-anchor": "end" }, title);
  const chars = Math.floor((visibleWidth - 12) / CHAR);
  return chars >= 3 ? svg("text", { class: "tl-label", x: inside + 6, y }, `${title.slice(0, chars - 1)}…`) : null;
}

// decades and the year of birth; a decade right after the birth year would sit on top of it
const showYearLabel = ({ year, age }) => age === 0 || (year % 10 === 0 && (age === null || age >= 5));

const keyOf = (item) => `${item.kind}:${item.id}`;

function legendSwatch(lane) {
  const bar = lane === "medications" || lane === "habits";
  return svg("svg", { class: `tl-swatch tl-lane-${lane}`, width: 18, height: 16, viewBox: "0 0 18 16", "aria-hidden": "true" },
    bar ? svg("rect", { class: "tl-bar", x: 1, y: 4, width: 16, height: 8, rx: 2 }) : mark(lane, 9, 8));
}

function detailCard(item) {
  if (!item) return el("p", { class: "quiet" }, t("timeline.select_hint"));
  if (item.start) {
    return el("div", { class: "card tl-detail" },
      el("p", { class: "tl-detail-kind" }, kindWord(item.kind)),
      el("h2", {}, item.title),
      el("p", {}, periodDates(item)),
      ...periodDetails(item).map((text) => el("p", { class: "quiet" }, text)),
      el("p", {}, el("a", { href: item.kind === "medication" ? "#/medications" : "#/habits" },
        t(item.kind === "medication" ? "timeline.open_medications" : "timeline.open_habits"))));
  }
  const links = panelLinks(item);
  return el("div", { class: "card tl-detail" },
    el("p", { class: "tl-detail-kind" }, kindWord(item.kind), " · ", formatDate(item.date)),
    el("h2", { class: isRefuted(item) ? "tl-refuted-text" : null }, eventTitle(item)),
    ...eventDetails(item).map((text) => el("p", { class: "quiet" }, text)),
    isPendingEvent(item) && el("p", { class: "labs-pending" }, tn("timeline.panel.pending_note", { n: item.pending })),
    links.length > 0 && el("p", {}, t("timeline.panel.open")),
    links.length > 0 && el("ul", { class: "tl-links" },
      ...links.map((link) => el("li", {}, el("a", { href: link.href }, link.name)))),
    item.kind === "diagnosis" && el("p", {}, el("a", { href: "#/diagnoses" }, t("timeline.open_diagnoses"))));
}

export async function render(view) {
  const data = await api(`timeline?lang=${LANG}`);
  if (!data.events.length && !data.periods.length) {
    view.replaceChildren(emptyState({ message: t("timeline.none") }));
    return;
  }

  const bounds = fullRange(data);
  const today = toDay(data.today);
  const born = data.born ? toDay(data.born) : null;
  const items = new Map([...data.events, ...data.periods].map((item) => [keyOf(item), item]));
  let range = bounds;
  let drawnWidth = 0;
  let year = null;
  let selected = null;
  const hidden = new Set();

  const chart = el("div", { class: "tl-chart" });
  const detail = el("div", { class: "tl-detail-box", "aria-live": "polite" });
  const caption = el("p", { class: "quiet tl-caption", role: "status" });
  const strip = el("div", { class: "tl-years", role: "group", "aria-label": t("timeline.years.label") });

  const buttons = {
    whole: el("button", { type: "button", onclick: () => setRange(bounds, null) }, t("timeline.whole")),
    out: el("button", { type: "button", onclick: () => setRange(zoomRange(range, 2, bounds), null), "aria-label": t("timeline.zoom_out") }, "−"),
    in: el("button", { type: "button", onclick: () => setRange(zoomRange(range, 0.5, bounds), null), "aria-label": t("timeline.zoom_in") }, "+"),
    earlier: el("button", { type: "button", onclick: () => setRange(panRange(range, -0.5, bounds), year) }, `← ${t("timeline.earlier")}`),
    later: el("button", { type: "button", onclick: () => setRange(panRange(range, 0.5, bounds), year) }, `${t("timeline.later")} →`),
  };

  function setRange(next, nextYear) {
    range = next;
    year = nextYear;
    draw();
  }

  function select(key) {
    selected = selected === key ? null : key;
    detail.replaceChildren(detailCard(items.get(selected)));
    for (const node of chart.querySelectorAll(".tl-item")) {
      node.setAttribute("aria-pressed", String(node.dataset.key === selected));
    }
  }

  function interactive(item, label, ...children) {
    const key = keyOf(item);
    return svg("g", {
      class: "tl-item",
      tabindex: "0",
      role: "button",
      "aria-label": label,
      "aria-pressed": String(key === selected),
      "data-key": key,
      onclick: () => select(key),
      onkeydown: (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          select(key);
        }
      },
    }, svg("title", {}, label), ...children);
  }

  function drawYears() {
    strip.replaceChildren(...yearCells(data).map((cell) => el("button", {
      type: "button",
      class: "tl-year",
      "data-level": cell.level,
      "data-ongoing": cell.ongoing,
      "aria-pressed": String(year === cell.year),
      "aria-label": yearCellLabel(cell),
      title: yearCellLabel(cell),
      onclick: () => (year === cell.year ? setRange(bounds, null) : setRange(yearRange(cell.year), cell.year)),
    }, el("span", { class: showYearLabel(cell) ? "tl-year-label" : "visually-hidden", "aria-hidden": "true" },
      cell.age === 0 ? `${cell.year} ★` : String(cell.year)))));
  }

  function draw() {
    const width = Math.max(300, chart.clientWidth || 800);
    drawnWidth = chart.clientWidth;
    const x = scaleX(range, width);
    const visible = (day) => day >= range.from - 1 && day <= range.to + 1;
    const lanes = lanesOf(data, hidden);

    let y = AXIS;
    const body = [];
    for (const lane of lanes) {
      body.push(svg("text", { class: "tl-lane-name", x: 4, y: y + 14 }, laneWord(lane.id)));
      y += LANE_HEAD;
      const group = svg("g", { class: `tl-lane tl-lane-${lane.id}` });
      if (lane.events.length) {
        const cy = y + ROW / 2;
        group.append(svg("line", { class: "tl-track", x1: 0, x2: width, y1: cy, y2: cy, "aria-hidden": "true" }));
        const shown = lane.events.filter((event) => visible(toDay(event.date)));
        shown.forEach((event, i) => {
          const cx = x(toDay(event.date));
          const nextX = i + 1 < shown.length ? x(toDay(shown[i + 1].date)) : width;
          const title = eventTitle(event);
          const room = nextX - cx - 14;
          const label = room > Math.min(title.length, 6) * CHAR
            ? svg("text", { class: "tl-label", x: cx + 10, y: cy + 4 }, title.length * CHAR > room ? `${title.slice(0, Math.max(3, Math.floor(room / CHAR) - 1))}…` : title)
            : null;
          group.append(interactive(event, eventLabel(event),
            svg("g", { class: [isPendingEvent(event) && "tl-pending", isRefuted(event) && "tl-refuted"].filter(Boolean).join(" ") || null },
              mark(lane.id, cx, cy)),
            label));
        });
        y += ROW;
      }
      for (const row of lane.rows) {
        const spans = row.map((period) => ({ period, start: toDay(period.start), end: period.end ? toDay(period.end) : today }));
        spans.forEach(({ period, start, end }, i) => {
          if (end < range.from || start > range.to) return;
          const x1 = Math.max(x(start), -4);
          const x2 = Math.min(x(end), width + 4);
          const barY = y + (ROW - BAR) / 2;
          const w = Math.max(3, x2 - x1);
          const tip = period.ongoing && x(end) <= width ? 9 : 0;
          group.append(interactive(period, periodLabel(period),
            svg("rect", { class: `tl-bar${period.ongoing ? " tl-ongoing" : ""}`, x: x1, y: barY, width: w, height: BAR, rx: 3 }),
            tip > 0 && svg("path", { class: "tl-arrow", d: `M${x2},${barY - 2}l7,${BAR / 2 + 2}l-7,${BAR / 2 + 2}Z` }),
            barLabel(period.title, {
              x1, x2, tip, y: barY + 13, width,
              // the room beside the bar, up to its neighbours in the same row
              before: i > 0 ? x(spans[i - 1].end) + 4 : 0,
              after: i + 1 < spans.length ? x(spans[i + 1].start) - 4 : width,
            })));
        });
        y += ROW;
      }
      body.push(group);
      y += LANE_GAP;
    }
    const height = y;

    const todayX = x(today);
    const axis = ticks(range, width).map((tick) => svg("g", { class: tick.major ? "tl-tick tl-major" : "tl-tick", "aria-hidden": "true" },
      svg("line", { x1: x(tick.day), x2: x(tick.day), y1: AXIS - 6, y2: height }),
      // a tick label under the "today" one would be unreadable: the line still shows
      (x(tick.day) + 3 > todayX + 4 || x(tick.day) + 3 + tick.label.length * CHAR < todayX - 40) &&
        x(tick.day) + 3 + tick.label.length * CHAR <= width &&
        svg("text", { x: x(tick.day) + 3, y: 14 }, tick.label)));
    const marks = [];
    if (visible(today)) {
      marks.push(svg("g", { class: "tl-today", "aria-hidden": "true" },
        svg("line", { x1: x(today), x2: x(today), y1: AXIS - 4, y2: height }),
        svg("text", { x: x(today) - 3, y: 14, "text-anchor": "end" }, t("timeline.today"))));
    }
    if (born !== null && visible(born)) {
      marks.push(svg("g", { class: "tl-born", "aria-hidden": "true" },
        svg("line", { x1: x(born), x2: x(born), y1: AXIS - 4, y2: height }),
        svg("text", { x: x(born) + 3, y: AXIS - 8 }, t("timeline.born"))));
    }

    const plot = svg("svg", {
      class: "tl-svg",
      width,
      height,
      viewBox: `0 0 ${width} ${height}`,
      role: "group",
      "aria-label": `${t("timeline.chart_label")}. ${rangeText(range)}`,
    }, svg("g", { "aria-hidden": "true" }, ...axis), ...marks, ...body);
    // a redraw (a key, a button) must not drop the keyboard user's place: refocus the same mark
    const focused = chart.contains(document.activeElement) ? document.activeElement.dataset?.key : null;
    chart.replaceChildren(plot);
    if (focused) (chart.querySelector(`[data-key="${CSS.escape(focused)}"]`) ?? frame).focus({ preventScroll: true });

    caption.textContent = rangeText(range);
    buttons.whole.disabled = isWhole(range, bounds);
    buttons.out.disabled = isWhole(range, bounds);
    buttons.in.disabled = !canZoomIn(range);
    buttons.earlier.disabled = range.from <= bounds.from;
    buttons.later.disabled = range.to >= bounds.to;
    drawYears();
  }

  // drag to pan; the buttons and keys do the same for those who don't drag
  let drag = null;
  chart.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest(".tl-item")) return;
    drag = { x: e.clientX, range };
    chart.setPointerCapture(e.pointerId);
  });
  chart.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const share = -(e.clientX - drag.x) / Math.max(1, chart.clientWidth);
    const next = panRange(drag.range, share, bounds);
    if (next.from !== range.from) setRange(next, null);
  });
  const endDrag = () => { drag = null; };
  chart.addEventListener("pointerup", endDrag);
  chart.addEventListener("pointercancel", endDrag);

  const frame = el("div", {
    class: "tl-frame",
    tabindex: "0",
    role: "region",
    "aria-label": t("timeline.chart_label"),
    "aria-describedby": "tl-keys",
    onkeydown: (e) => {
      const actions = {
        "+": () => zoomRange(range, 0.5, bounds),
        "=": () => zoomRange(range, 0.5, bounds),
        "-": () => zoomRange(range, 2, bounds),
        ArrowLeft: () => panRange(range, -0.25, bounds),
        ArrowRight: () => panRange(range, 0.25, bounds),
        Home: () => bounds,
      };
      if (!actions[e.key] || e.altKey || e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      setRange(actions[e.key](), null);
    },
  }, chart);

  const legend = el("fieldset", { class: "tl-legend" },
    el("legend", {}, t("timeline.lanes")),
    ...presentLanes(data).map((lane) => el("label", {},
      el("input", {
        type: "checkbox",
        checked: true,
        onchange: (e) => {
          if (e.target.checked) hidden.delete(lane);
          else hidden.add(lane);
          draw();
        },
      }),
      legendSwatch(lane), " ", laneWord(lane))),
    el("span", { class: "tl-key-pending" },
      svg("svg", { class: "tl-swatch tl-lane-labs", width: 18, height: 16, viewBox: "0 0 18 16", "aria-hidden": "true" },
        svg("g", { class: "tl-pending" }, mark("labs", 9, 8))), " ", t("timeline.key.pending")));

  const table = dataTable({
    caption: t("timeline.table.caption"),
    rows: tableRows(data),
    pending: (row) => row.pending,
    columns: [
      { key: "date", label: t("timeline.col.date") },
      { key: "end", label: t("timeline.col.end") },
      { key: "lane", label: t("timeline.col.lane") },
      { key: "title", label: t("timeline.col.title"), wrap: true },
      { key: "details", label: t("timeline.col.details"), wrap: true, sortable: false },
    ],
  });

  const undated = data.undated_habits > 0 && el("p", { class: "quiet" },
    tn("timeline.undated_habits", { n: data.undated_habits }), " ", el("a", { href: "#/habits" }, t("timeline.open_habits")));

  view.replaceChildren(el("div", { class: "timeline" },
    el("p", { class: "quiet" }, t("timeline.note")),
    el("section", { class: "tl-life" },
      el("h2", {}, t("timeline.years.title")),
      el("p", { class: "quiet" }, t("timeline.years.note")),
      strip),
    el("div", { class: "tl-toolbar" },
      el("div", { class: "tl-buttons" }, buttons.whole, buttons.out, buttons.in, buttons.earlier, buttons.later),
      caption),
    legend,
    frame,
    el("p", { class: "quiet", id: "tl-keys" }, t("timeline.keys")),
    undated,
    detail,
    el("details", { class: "tl-table" },
      el("summary", {}, t("timeline.table.summary", { n: tableRows(data).length })),
      table.element)));

  detail.replaceChildren(detailCard(null));
  draw();
  // the page's scroll bar can appear after the first draw: redraw at the width there is
  const observer = new ResizeObserver(() => {
    if (!view.isConnected) {
      observer.disconnect();
      return;
    }
    if (chart.clientWidth !== drawnWidth) draw();
  });
  observer.observe(chart);
}
