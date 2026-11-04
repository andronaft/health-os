// The UI's pages, in menu order. A page that exists adds
//   load: () => import("./pages/<id>.js")
// whose `render(view, args)` fills `view`; until then the frame shows an empty state.

export const PAGES = [
  { id: "overview", title: "nav.overview" },
  { id: "labs", title: "nav.labs" },
  { id: "vitals", title: "nav.vitals" },
  { id: "timeline", title: "nav.timeline" },
  { id: "medications", title: "nav.medications" },
  { id: "diagnoses", title: "nav.diagnoses" },
  { id: "habits", title: "nav.habits" },
  { id: "review", title: "nav.review" },
  { id: "report", title: "nav.report" },
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
