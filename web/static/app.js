// health-os browser UI: the frame every page shares — navigation, routing, connection status.

import { ApiError, TOKEN_KEY, api, explain, reloadToken } from "./api.js";
import { el, emptyState, errorState } from "./components.js";
import { PAGES, parseRoute } from "./pages.js";
import { t } from "./strings.js";
import { setUpThemePicker } from "./theme.js";

const main = document.getElementById("main");
const navLinks = new Map();

// The menu in groups, so a dozen pages stay easy to scan. A page not named here (a new one) goes in
// the last group until it is given a place.
const NAV_GROUPS = [
  { title: "nav.group.today", ids: ["overview", "review"] },
  { title: "nav.group.results", ids: ["labs", "vitals", "food"] },
  { title: "nav.group.record", ids: ["timeline", "medications", "diagnoses", "habits"] },
  { title: "nav.group.tools", ids: ["report"] },
];

function groupPages(pages, groups = NAV_GROUPS) {
  const placed = new Set(groups.flatMap((group) => group.ids));
  return groups.map((group, i) => ({
    title: group.title,
    pages: [
      ...group.ids.map((id) => pages.find((page) => page.id === id)).filter(Boolean),
      ...(i === groups.length - 1 ? pages.filter((page) => !placed.has(page.id)) : []),
    ],
  })).filter((group) => group.pages.length);
}

const sidebar = document.querySelector(".sidebar");
const menuLabel = el("span", { class: "menu-toggle-label" }, t("nav.menu"));
const menuToggle = el("button", {
  type: "button",
  class: "menu-toggle",
  "aria-expanded": "false",
  "aria-controls": "nav",
  onclick: () => setMenuOpen(menuToggle.getAttribute("aria-expanded") !== "true"),
}, el("span", { class: "menu-toggle-icon", "aria-hidden": "true" }), menuLabel);

// the phone header's menu; on a wide window the CSS shows the menu whatever this says
function setMenuOpen(open) {
  menuToggle.setAttribute("aria-expanded", String(open));
  sidebar.toggleAttribute("data-open", open);
}

function buildNav() {
  const groups = groupPages(PAGES).map((group, i) => {
    const titleId = `nav-group-${i}`;
    const items = group.pages.map((page) => {
      // a page still to come is in the menu, but says so before it is opened
      const link = el("a", { href: `#/${page.id}`, "data-soon": !page.load },
        t(page.title),
        !page.load && el("span", { class: "nav-soon" }, ` · ${t("nav.soon")}`));
      navLinks.set(page.id, link);
      return el("li", {}, link);
    });
    return el("li", { class: "nav-group" },
      el("p", { class: "nav-group-title", id: titleId }, t(group.title)),
      el("ul", { "aria-labelledby": titleId }, ...items));
  });
  document.getElementById("nav").append(el("ul", {}, ...groups));
  // a tap on any link folds the phone menu, the current page's too (its hash doesn't change)
  document.getElementById("nav").addEventListener("click", (e) => {
    if (e.target.closest("a")) setMenuOpen(false);
  });
  document.querySelector(".brand").after(menuToggle);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sidebar.hasAttribute("data-open")) {
      setMenuOpen(false);
      menuToggle.focus();
    }
  });
}

function markCurrentPage(id) {
  for (const [pageId, link] of navLinks) {
    if (pageId === id) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  const page = PAGES.find((candidate) => candidate.id === id);
  menuLabel.textContent = page ? t(page.title) : t("nav.menu");
  menuToggle.setAttribute("aria-label", page ? `${t("nav.menu")}: ${t(page.title)}` : t("nav.menu"));
  setMenuOpen(false);
}

const currentRoute = () => parseRoute(location.hash) ?? parseRoute("");

let firstRender = true;

async function render(route) {
  const heading = el("h1", { tabindex: "-1" }, t(route.page?.title ?? "error.not_found_title"));
  // each render fills its own element: a slow page that finishes after the user has moved on
  // writes into a detached node, not over the new page
  const view = el("div", { class: "view" });
  main.replaceChildren(heading, view);
  document.title = `${heading.textContent} · health-os`;
  window.scrollTo(0, 0);
  markCurrentPage(route.page?.id);
  if (!firstRender) heading.focus({ preventScroll: true }); // screen readers follow the change
  firstRender = false;

  if (!route.page) {
    view.append(errorState({ title: t("error.not_found") }));
    return;
  }
  if (!route.page.load) {
    view.append(emptyState({ message: t("empty.not_built") }));
    return;
  }
  // a page that takes more than a moment shows where its content will be; a fast one never
  // flashes it. The page's own replaceChildren drops it.
  view.setAttribute("aria-busy", "true");
  const skeleton = setTimeout(() => {
    if (!view.childElementCount) {
      view.append(el("div", { class: "skeleton", "aria-hidden": "true" }, el("div"), el("div"), el("div")));
    }
  }, 200);
  try {
    const page = await route.page.load();
    await page.render(view, route.args);
  } catch (err) {
    console.error(err);
    view.replaceChildren(errorState({ message: explain(err), onRetry: () => render(route) }));
  } finally {
    clearTimeout(skeleton);
    view.removeAttribute("aria-busy");
    view.querySelector(":scope > .skeleton")?.remove();
  }
}

let statusCheck = 0;

async function showStatus() {
  const check = ++statusCheck; // only the latest check may speak: a slow old one is out of date
  const status = document.getElementById("status");
  const problem = document.getElementById("connection-problem");
  try {
    const health = await api("health");
    if (!health.ok) throw new ApiError(200, "health check not ok");
    if (check !== statusCheck) return;
    status.textContent = t("connection.ok", { version: health.version });
    status.dataset.state = "ok";
    problem.replaceChildren();
  } catch (err) {
    if (check !== statusCheck) return;
    status.textContent = t("connection.lost");
    status.dataset.state = "error";
    problem.replaceChildren(errorState({
      title: t("connection.lost"),
      message: explain(err),
      onRetry: showStatus,
    }));
  }
}

buildNav();
setUpThemePicker(document.getElementById("theme-picker"));
render(currentRoute());
showStatus();

// a menu link or back/forward; also a new `make ui` link pasted into an open tab, which changes
// only the fragment: no reload
window.addEventListener("hashchange", () => {
  if (reloadToken()) showStatus();
  const route = parseRoute(location.hash);
  if (route) render(route); // otherwise the skip link's #main: the browser handles that
});
// a new link opened in another tab (after `make ui` was restarted) reaches this one too
window.addEventListener("storage", (e) => {
  if (e.key !== TOKEN_KEY || !e.newValue || !reloadToken()) return;
  showStatus();
  render(currentRoute());
});
// a tab left open after `make ui` stopped must not keep saying "connected"
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") showStatus();
});
