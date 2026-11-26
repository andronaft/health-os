// Privacy blur (#63): one switch in the header that blurs values, dates and names everywhere, so the
// UI can be shown in a screenshot or a demo. Only a class on <body>; styles.css does the blurring.
// Remembered in this browser (localStorage; blocked storage just means it lasts until a reload).
// Alt+Shift+B toggles it too. A blurred element's tooltip would still say what it hides, so while
// the blur is on every `title` in the page (an attribute, or an SVG <title> element) is put aside and
// given back when it is turned off; content drawn later is covered too.

import { el } from "./components.js";
import { t } from "./strings.js";

export const BLUR_KEY = "health-os-privacy-blur";
export const BLUR_CLASS = "privacy-blur";

function stored() {
  try {
    return localStorage.getItem(BLUR_KEY) === "on";
  } catch {
    return false;
  }
}

/** Alt+Shift+B, but not while typing (a textarea, an input, a select). */
export function isBlurShortcut(e) {
  if (!e.altKey || !e.shiftKey || e.ctrlKey || e.metaKey || e.code !== "KeyB") return false;
  const tag = e.target?.tagName;
  return !["INPUT", "TEXTAREA", "SELECT"].includes(tag) && !e.target?.isContentEditable;
}

const STASH = "data-privacy-title";

/** Put every tooltip under `root` aside: title attributes and SVG <title> texts. */
export function hideTitles(root) {
  for (const node of root.querySelectorAll("[title]")) {
    node.setAttribute(STASH, node.getAttribute("title"));
    node.removeAttribute("title");
  }
  for (const node of root.querySelectorAll("title")) {
    if (!node.textContent) continue;
    node.setAttribute(STASH, node.textContent);
    node.textContent = "";
  }
}

/** Give them back. */
export function restoreTitles(root) {
  for (const node of root.querySelectorAll(`[${STASH}]`)) {
    const value = node.getAttribute(STASH);
    if (node.localName === "title") node.textContent = value;
    else node.setAttribute("title", value);
    node.removeAttribute(STASH);
  }
}

export function setUpPrivacyBlur(container) {
  const button = el("button", { type: "button", class: "privacy-toggle", title: t("privacy.hint") });
  const main = document.getElementById("main");
  // pages drawn (or redrawn) while the blur is on
  const observer = new MutationObserver(() => hideTitles(main));
  const apply = (on) => {
    document.body.classList.toggle(BLUR_CLASS, on);
    if (main && on) {
      hideTitles(main);
      observer.observe(main, { subtree: true, childList: true, attributes: true, attributeFilter: ["title"] });
    } else if (main) {
      observer.disconnect();
      restoreTitles(main);
    }
    button.setAttribute("aria-pressed", String(on));
    button.textContent = t(on ? "privacy.blur_on" : "privacy.blur");
  };
  const set = (on) => {
    try {
      localStorage.setItem(BLUR_KEY, on ? "on" : "off");
    } catch {
      // storage blocked: the choice lasts until this page is reloaded
    }
    apply(on);
  };
  button.addEventListener("click", () => set(!document.body.classList.contains(BLUR_CLASS)));
  document.addEventListener("keydown", (e) => {
    if (!isBlurShortcut(e)) return;
    e.preventDefault();
    set(!document.body.classList.contains(BLUR_CLASS));
  });
  // switched in another tab of this UI
  window.addEventListener("storage", (e) => {
    if (e.key === BLUR_KEY) apply(stored());
  });
  apply(stored());
  container.append(button);
}
