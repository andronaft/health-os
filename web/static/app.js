// health-os browser UI: the frame every page shares — navigation, routing, connection status.

import { ApiError, TOKEN_KEY, api, explain, reloadToken } from "./api.js";
import { el, emptyState, errorState } from "./components.js";
import { PAGES, parseRoute } from "./pages.js";
import { t } from "./strings.js";
import { setUpThemePicker } from "./theme.js";

const main = document.getElementById("main");
const navLinks = new Map();

function buildNav() {
  const items = PAGES.map((page) => {
    const link = el("a", { href: `#/${page.id}` }, t(page.title));
    navLinks.set(page.id, link);
    return el("li", {}, link);
  });
  document.getElementById("nav").append(el("ul", {}, ...items));
}

function markCurrentPage(id) {
  for (const [pageId, link] of navLinks) {
    if (pageId === id) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
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
  try {
    const page = await route.page.load();
    await page.render(view, route.args);
  } catch (err) {
    console.error(err);
    view.replaceChildren(errorState({ message: explain(err), onRetry: () => render(route) }));
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
