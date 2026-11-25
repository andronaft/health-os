// The UI's pages, in menu order. A page that exists adds
//   load: () => import("./pages/<id>.js")
// whose `render(view, args)` fills `view`; until then the frame shows an empty state.

export const PAGES = [
  { id: "overview", title: "nav.overview", load: () => import("./pages/overview.js") },
  { id: "labs", title: "nav.labs", load: () => import("./pages/labs.js") },
  { id: "vitals", title: "nav.vitals", load: () => import("./pages/vitals.js") },
  { id: "timeline", title: "nav.timeline", load: () => import("./pages/timeline.js") },
  { id: "medications", title: "nav.medications", load: () => import("./pages/medications.js") },
  { id: "diagnoses", title: "nav.diagnoses", load: () => import("./pages/diagnoses.js") },
  { id: "habits", title: "nav.habits", load: () => import("./pages/habits.js") },
  { id: "review", title: "nav.review", load: () => import("./pages/review.js") },
  { id: "report", title: "nav.report", load: () => import("./pages/report.js") },
];

/**
 * "#/labs/ldl" → the labs page with args ["ldl"]; an empty hash → the first page; an unknown id →
 * page undefined. A hash that isn't "#/…" (the skip link's #main) is not a route: null.
 */
export function parseRoute(hash) {
  if (hash && !hash.startsWith("#/")) return null;
  const parts = hash.slice(2).split("/").filter(Boolean);
  try {
    const [id = PAGES[0].id, ...args] = parts.map(decodeURIComponent);
    return { page: PAGES.find((page) => page.id === id), args };
  } catch {
    return { page: undefined, args: [] }; // malformed %-escape
  }
}
