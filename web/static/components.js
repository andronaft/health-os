// The pieces every page is built from: status pill, sortable and filterable table, empty and
// error states. Nothing here touches the page until it is called, so the logic can be tested
// without a browser (tests/web_ui.test.mjs).

import { t } from "./strings.js";

/**
 * Build an element. Text always goes in as text, never parsed as HTML: records can hold anything.
 * The CSP blocks a `style` attribute: use a class.
 */
export function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === undefined || value === null || value === false) continue;
    if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
    else node.setAttribute(name, value === true ? "" : value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined && child !== false));
  return node;
}

// Keys are the values core/normalize.py stores, plus "pending" for a value not yet reviewed.
const STATUS_ICONS = { low: "↓", normal: "↔", high: "↑", pending: "…", unknown: "–" };

/** Anything unrecognised is "unknown": a missing or new status must never pass as in range. */
export function statusKey(status) {
  return Object.hasOwn(STATUS_ICONS, status) ? status : "unknown";
}

export const statusWord = (status) => t(`status.${statusKey(status)}`);

/** The word and the icon say it; the colour only repeats it. */
export function statusPill(status) {
  const key = statusKey(status);
  return el("span", { class: "pill", "data-status": key },
    el("span", { class: "pill-icon", "aria-hidden": "true" }, STATUS_ICONS[key]),
    statusWord(key));
}

/** Nothing to show. The note is on by default: an empty list must never read as "all is well". */
export function emptyState({ title = t("empty.title"), message, note = true } = {}) {
  return el("div", { class: "state" },
    el("p", { class: "state-title" }, title),
    message && el("p", {}, message),
    note && el("p", { class: "state-note" }, t("empty.note")));
}

export function errorState({ title = t("error.title"), message, onRetry } = {}) {
  return el("div", { class: "state state-error", role: "alert" },
    el("p", { class: "state-title" },
      el("span", { class: "state-icon", "aria-hidden": "true" }, "!"), title),
    message && el("p", {}, message),
    onRetry && el("button", { type: "button", onclick: onRetry }, t("error.retry")));
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const isMissing = (value) =>
  value === null || value === undefined || value === "" || Number.isNaN(value);
const fold = (text) => text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();

export const cellValue = (column, row) => (column.value ? column.value(row) : row[column.key]);

/** Missing values go last in both directions: a blank must not look like the lowest result. */
export function sortRows(rows, column, direction = "asc") {
  const sign = direction === "desc" ? -1 : 1;
  return [...rows].sort((x, y) => {
    const a = cellValue(column, x);
    const b = cellValue(column, y);
    if (isMissing(a) || isMissing(b)) return isMissing(a) - isMissing(b);
    if (typeof a === "number" && typeof b === "number") return sign * (a - b);
    return sign * collator.compare(String(a), String(b));
  });
}

/** Rows holding every word of the query somewhere; case and accents don't matter. */
export function filterRows(rows, columns, query) {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return rows;
  return rows.filter((row) => {
    const texts = columns.map((column) =>
      fold(String((column.text ? column.text(row) : cellValue(column, row)) ?? "")));
    return words.every((word) => texts.some((text) => text.includes(word)));
  });
}

/**
 * A table the user can sort (click a header) and filter (text box). Returns { element, setRows };
 * setRows keeps the sort and the filter, for pages with filters of their own.
 *
 * columns: { key, label, value?, text?, render?, numeric?, wrap?, sortable? }
 *   value(row)   what it sorts by (default row[key]); give numbers as numbers, blanks as null
 *   text(row)    what the filter looks at, if not the value (a status: its word)
 *   render(row)  what the cell shows, if not the value: a string or a node
 *   wrap         long text (a note) may wrap; other cells stay on one line, the table scrolls
 * caption:   names the table for screen readers
 * pending:   (row) => true for values not yet reviewed; such a row must not look like a fact
 * empty:     shown instead of the table when there are no rows (default: emptyState())
 * sort:      initial { key, direction }
 */
export function dataTable({ columns, rows, caption, pending, empty = emptyState(), sort }) {
  let data = rows;
  let sortKey = sort?.key;
  let direction = sort?.direction ?? "asc";

  const input = el("input", { type: "search", oninput: draw });
  const count = el("p", { class: "table-count", role: "status" });
  const controls = el("div", { class: "table-controls" },
    el("label", {}, t("table.filter"), " ", input), count);

  const headers = columns.map((column) => {
    const th = el("th", { scope: "col", class: column.numeric ? "num" : null });
    if (column.sortable === false) {
      th.append(column.label);
      return th;
    }
    th.append(el("button", {
      type: "button",
      class: "sort-button",
      onclick: () => {
        direction = sortKey === column.key && direction === "asc" ? "desc" : "asc";
        sortKey = column.key;
        draw();
      },
    }, column.label, el("span", { class: "sort-icon", "aria-hidden": "true" })));
    return th;
  });

  const tbody = el("tbody");
  // scrolls by itself on a phone, so the page doesn't; focusable to scroll it from the keyboard
  const scroller = el("div", { class: "table-scroll", role: "region", "aria-label": caption, tabindex: "0" },
    el("table", {},
      el("caption", { class: "visually-hidden" }, caption),
      el("thead", {}, el("tr", {}, ...headers)),
      tbody));

  const noMatch = el("div", {},
    emptyState({ title: t("table.no_match"), note: false }),
    el("button", {
      type: "button",
      onclick: () => {
        input.value = "";
        draw();
        input.focus();
      },
    }, t("table.clear_filter")));
  const message = el("div", {});

  function renderRow(row) {
    const isPending = Boolean(pending?.(row));
    return el("tr", { "data-pending": isPending }, ...columns.map((column, i) => {
      const content = column.render ? column.render(row) : cellValue(column, row);
      const classes = [column.numeric && "num", column.wrap && "wrap"].filter(Boolean).join(" ");
      return el("td", { class: classes || null },
        isPending && i === 0 && el("span", { class: "visually-hidden" }, `${t("status.pending")}: `),
        isMissing(content) ? "—" : content);
    }));
  }

  function draw() {
    const shown = filterRows(data, columns, input.value);
    const column = columns.find((candidate) => candidate.key === sortKey);
    const ordered = column ? sortRows(shown, column, direction) : shown;
    tbody.replaceChildren(...ordered.map(renderRow));

    columns.forEach((candidate, i) => {
      const sorted = candidate.key === sortKey;
      if (sorted) headers[i].setAttribute("aria-sort", direction === "asc" ? "ascending" : "descending");
      else headers[i].removeAttribute("aria-sort");
      const icon = headers[i].querySelector(".sort-icon");
      if (icon) icon.textContent = sorted ? (direction === "asc" ? "▲" : "▼") : "";
    });

    count.textContent = t("table.count", { shown: ordered.length, total: data.length });
    controls.hidden = !data.length;
    scroller.hidden = !ordered.length;
    if (!data.length) message.replaceChildren(empty);
    else if (!ordered.length) message.replaceChildren(noMatch);
    else message.replaceChildren();
  }

  draw();
  return {
    element: el("div", { class: "data-table" }, controls, scroller, message),
    setRows(next) {
      data = next;
      draw();
    },
  };
}
