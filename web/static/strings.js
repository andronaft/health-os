// Every word the UI shows, by key. Pages call t("key") instead of hard-coding text, so adding a
// language (#59) replaces this table and leaves the pages alone.

const EN = {
  "nav.overview": "Overview",
  "nav.labs": "Labs",
  "nav.vitals": "Vitals",
  "nav.timeline": "Timeline",
  "nav.medications": "Medications",
  "nav.diagnoses": "Diagnoses",
  "nav.habits": "Habits",
  "nav.review": "Review queue",
  "nav.report": "Visit report",

  "theme.label": "Theme",
  "theme.auto": "Auto",
  "theme.light": "Light",
  "theme.dark": "Dark",

  // "normal" is the stored value; on screen a value is only ever in or out of its range
  "status.low": "low",
  "status.normal": "in range",
  "status.high": "high",
  "status.pending": "pending",
  "status.unknown": "no status",

  "table.filter": "Filter",
  "table.count": "{shown} of {total} rows",
  "table.no_match": "No rows match this filter.",
  "table.clear_filter": "Clear filter",

  "empty.title": "Nothing here yet",
  "empty.note": "An empty page says nothing about your health: it only means there is nothing to show here.",
  "empty.not_built": "This page is not built yet.",

  "error.title": "Something went wrong",
  "error.retry": "Try again",
  "error.not_found_title": "No such page",
  "error.not_found": "There is no page at this address. Choose one from the menu.",
  "error.token": "The session token is missing or out of date. Open the link printed by `make ui`.",
  "error.server": "Unexpected response from the server ({detail}).",
  "error.network": "The server is not responding. Is `make ui` still running?",
  "error.page": "This page could not be displayed.",

  "connection.ok": "connected · version {version}",
  "connection.lost": "Not connected",
};

export function t(key, vars = {}) {
  return (EN[key] ?? key).replace(/\{(\w+)\}/g, (whole, name) => vars[name] ?? whole);
}
