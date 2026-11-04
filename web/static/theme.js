// The theme picker: auto (follow the system), light or dark. Colours are CSS tokens in styles.css;
// this only sets data-theme on <html>. Anything that can't use tokens directly (a chart's canvas)
// listens for the "themechange" event on document.

import { el } from "./components.js";
import { t } from "./strings.js";

const KEY = "health-os-theme";
const CHOICES = ["auto", "light", "dark"];

function stored() {
  try {
    const choice = localStorage.getItem(KEY);
    return CHOICES.includes(choice) ? choice : "auto";
  } catch {
    return "auto";
  }
}

function apply(choice) {
  if (choice === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = choice;
  document.dispatchEvent(new Event("themechange"));
}

export function setUpThemePicker(container) {
  const select = el("select", {}, ...CHOICES.map((choice) =>
    el("option", { value: choice }, t(`theme.${choice}`))));
  select.value = stored();
  select.addEventListener("change", () => {
    try {
      localStorage.setItem(KEY, select.value);
    } catch {
      // storage blocked: the choice lasts until this page is reloaded
    }
    apply(select.value);
  });
  // chosen in another tab of this UI
  window.addEventListener("storage", (e) => {
    if (e.key !== KEY) return;
    select.value = stored();
    apply(select.value);
  });
  // the system switched while on "auto": CSS follows by itself, a canvas needs telling
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    document.dispatchEvent(new Event("themechange"));
  });
  container.append(el("label", {}, t("theme.label"), " ", select));
}
