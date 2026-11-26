// "Where does this value come from": a side drawer (a bottom sheet on a phone) for one observation,
// opened by a click on, or Enter on, a lab value. A modal <dialog>: the page behind it is inert,
// Tab stays inside, Esc closes it, and focus goes back to the value that opened it.
// Everything from the record goes in as text (el()), never as HTML: notes and titles can hold
// anything.

import { ApiError, api, explain } from "../api.js";
import { el, errorState, formatValue, statusPill, statusWord } from "../components.js";
import { LANG, t } from "../strings.js";
import {
  atText, canonicalRangeText, rangeStatusText, valueCellView, conversionText, defaultRangeText, documentText, panelText, printedText,
  rangeText, reviewLines,
} from "./observation-model.js";
import { rangeBarElement } from "./range-bar.js";

let dialog;
let body;
let opener;
let request = 0;

const FOCUSABLE = "a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex='-1'])";

function trapTab(event) {
  if (event.key !== "Tab") return;
  const items = [...dialog.querySelectorAll(FOCUSABLE)].filter((node) => !node.hidden && node.offsetParent !== null);
  if (!items.length) return;
  const [first, last] = [items[0], items.at(-1)];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function ensureDialog() {
  if (dialog?.isConnected) return dialog;
  body = el("div", { class: "obs-body" });
  dialog = el("dialog", {
    class: "obs-drawer",
    "aria-labelledby": "obs-title",
    onkeydown: trapTab,
    onclose: () => {
      request += 1; // a reply still on its way must not refill a closed drawer
      body.replaceChildren();
      if (opener?.isConnected) opener.focus();
      opener = null;
    },
    // a click on the backdrop (outside the panel) closes it, like Esc
    onclick: (event) => {
      if (event.target === dialog) dialog.close();
    },
  },
  el("div", { class: "obs-panel" },
    el("div", { class: "obs-head" },
      el("h2", { id: "obs-title", tabindex: "-1" }, t("obs.title")),
      el("button", { type: "button", class: "obs-close", onclick: () => dialog.close() },
        el("span", { "aria-hidden": "true" }, "✕"), el("span", { class: "visually-hidden" }, t("obs.close")))),
    body));
  document.body.append(dialog);
  // the routed page is about to change under it: a drawer of the old page must not stay open
  window.addEventListener("hashchange", () => dialog.open && dialog.close());
  return dialog;
}

const part = (title, ...children) =>
  el("section", { class: "obs-part" }, el("h3", {}, title), ...children);
const line = (text, className) => (text ? el("p", { class: className ?? null }, text) : null);

function statusLine(data) {
  if (data.pending) {
    return el("p", {}, statusPill("pending"), " ",
      data.status && el("span", { class: "quiet" }, t("obs.status.from_form", { status: statusWord(data.status) })));
  }
  return el("p", {}, statusPill(data.status),
    data.result_status && data.result_status !== "final" && el("span", { class: "quiet" }, ` ${t("obs.result_status", { status: data.result_status })}`));
}

function otherValue(row) {
  return el("li", { "data-pending": row.pending },
    valueButton(row.id, el("span", {}, row.name), { label: t("obs.open_other", { name: row.name }) }),
    " ",
    el("span", { class: row.pending ? "value-pending nowrap" : "nowrap" }, formatValue(row) || "—"),
    " ",
    row.pending ? statusPill("pending") : statusPill(row.status),
    rangeBarElement(row, { pending: row.pending }));
}

function content(data) {
  const others = data.panel?.others ?? [];
  const canonicalRange = canonicalRangeText(data);
  return [
    el("p", { class: "obs-name" }, el("strong", {}, data.name), " · ", el("span", { class: "nowrap" }, atText(data))),
    data.pending && el("div", { class: "obs-pending", role: "note" },
      statusPill("pending"), " ", t("obs.pending"), " ", el("a", { href: "#/review" }, t("overview.pending.queue"))),
    part(t("obs.form.title"),
      line(data.raw_name && t("obs.form.raw_name", { name: data.raw_name })),
      el("p", { class: "obs-value" }, el("span", { class: data.pending ? "value-pending" : null }, printedText(data) || "—")),
      statusLine(data),
      rangeBarElement({ ...data.printed, ref_min: data.range.min, ref_max: data.range.max }, { wide: true, pending: data.pending })),
    part(t("obs.stored.title"),
      line(conversionText(data)),
      data.unmapped && line(t("obs.unmapped"))),
    part(t("obs.range.title"),
      line(rangeText(data)),
      line(canonicalRange, "quiet"),
      line(rangeStatusText(data), "quiet"),
      data.range.defaults.length > 0 && el("div", {},
        el("p", {}, t("obs.range.defaults")),
        el("ul", { class: "plain" }, ...data.range.defaults.map((d) => el("li", {}, defaultRangeText(d)))))),
    part(t("obs.review.title"),
      ...reviewLines(data).map((text) => line(text))),
    data.notes && part(t("obs.notes.title"), el("p", { class: "obs-notes" }, data.notes)),
    part(t("obs.source.title"),
      line(t("obs.doc.label", { doc: documentText(data.document) })),
      data.panel ? line(t("obs.panel.label", { panel: panelText(data.panel) })) : line(t("obs.panel.none"))),
    data.panel && part(t("obs.others.title", { n: others.length }),
      others.length
        ? el("ul", { class: "obs-others" }, ...others.map(otherValue))
        : line(t("obs.others.none"), "quiet")),
  ];
}

async function load(id) {
  const mine = ++request;
  body.replaceChildren(el("p", { class: "quiet", role: "status" }, t("obs.loading")));
  let data;
  try {
    data = await api(`observations/${encodeURIComponent(id)}?lang=${LANG}`);
  } catch (err) {
    if (mine !== request) return;
    body.replaceChildren(err instanceof ApiError && err.status === 404
      ? errorState({ title: t("obs.not_found") })
      : errorState({ message: explain(err), onRetry: () => load(id) }));
    return;
  }
  if (mine !== request) return;
  body.replaceChildren(...content(data).filter(Boolean));
  dialog.querySelector("#obs-title").focus();
}

/** Open the drawer for one observation; `from` gets the focus back when it closes. */
export function openObservation(id, from = document.activeElement) {
  ensureDialog();
  if (!dialog.open) {
    opener = from;
    dialog.showModal();
  }
  dialog.scrollTop = 0;
  return load(id);
}

/**
 * A value that opens its drawer: a real button, so a click, Enter and Space all work and screen
 * readers announce it. Without an id (an old payload, a computed number) it is plain text.
 */
export function valueButton(id, content, { label } = {}) {
  if (!id) return content;
  return el("button", {
    type: "button",
    class: "value-link",
    "aria-haspopup": "dialog",
    "aria-label": label ?? null,
    title: t("obs.open"),
    onclick: (event) => openObservation(id, event.currentTarget),
  }, content);
}

/**
 * A table cell's value as a drawer button. Pending only when the caller says so: a row's own
 * `pending` field may be something else (the Labs index sends a count of queued values there).
 */
export function valueCell(row, { pending = false } = {}) {
  const view = valueCellView(row, { pending });
  return valueButton(row.id, el("span", { class: view.pending ? "value-pending" : null }, view.text),
    { label: view.label });
}
