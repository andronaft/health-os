// The session token and the read-only JSON API of the local server.

import { t } from "./strings.js";

export const TOKEN_KEY = "health-os-token";
const TOKEN_HEADER = "X-Health-OS-Token";

// `make ui` opens http://127.0.0.1:PORT/#token=… — the fragment is never sent to the server
// or written to its log. Take it out of the address bar and keep it in localStorage, so other
// tabs and bookmarks of this UI work while this run lasts. localStorage belongs to one origin,
// port included (a cookie would also go to every other server on 127.0.0.1); a token left there
// from an earlier run is useless, since every run makes a new one.
function takeToken() {
  const params = new URLSearchParams(location.hash.slice(1));
  const fromLink = params.get("token");
  if (fromLink) {
    try {
      localStorage.setItem(TOKEN_KEY, fromLink);
    } catch {
      // storage blocked: the token still works until this page is reloaded
    }
    params.delete("token");
    const rest = params.toString();
    history.replaceState(null, "", location.pathname + location.search + (rest ? `#${rest}` : ""));
    return fromLink;
  }
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

let token = takeToken();

/** Look for a newer token (a link pasted here or opened in another tab). True if it changed. */
export function reloadToken() {
  const latest = takeToken();
  const changed = latest !== token;
  token = latest;
  return changed;
}

export class ApiError extends Error {
  // status 0: no answer at all (network error or timeout)
  constructor(status, message = `HTTP ${status}`) {
    super(message);
    this.status = status;
  }
}

const TIMEOUT_MS = 10000;

export async function api(path) {
  let res;
  try {
    res = await fetch(`/api/v1/${path}`, {
      headers: token ? { [TOKEN_HEADER]: token } : {},
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (err) {
    throw new ApiError(0, err.message);
  }
  if (!res.ok) throw new ApiError(res.status);
  try {
    return await res.json();
  } catch {
    throw new ApiError(res.status, `HTTP ${res.status}, not JSON`);
  }
}

export function explain(err) {
  if (!(err instanceof ApiError)) return t("error.page"); // a bug in the page, not the server
  if (err.status === 403) return t("error.token");
  if (err.status === 0) return t("error.network");
  if (err.status === 503) return t("error.database");
  return t("error.server", { detail: err.message });
}
