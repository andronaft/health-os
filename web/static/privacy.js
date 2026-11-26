// Privacy blur (#63): one switch in the header that blurs values, dates and names everywhere, so the
// UI can be shown in a screenshot or a demo. Only a class on <body>; styles.css does the blurring.
// Remembered in this browser (localStorage; blocked storage just means it lasts until a reload).
// Alt+Shift+B toggles it too.

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

export function setUpPrivacyBlur(container) {
  const button = el("button", { type: "button", class: "privacy-toggle", title: t("privacy.hint") });
  const apply = (on) => {
    document.body.classList.toggle(BLUR_CLASS, on);
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
