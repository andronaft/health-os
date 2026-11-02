// health-os browser UI: the session token and the connection check against the local API.

const TOKEN_KEY = "health-os-token";
const TOKEN_HEADER = "X-Health-OS-Token";

// `make ui` opens http://127.0.0.1:PORT/#token=… — the fragment is never sent to the server
// or written to its log. Keep the token for this tab only and take it out of the address bar.
function takeToken() {
  const params = new URLSearchParams(location.hash.slice(1));
  const fromLink = params.get("token");
  if (fromLink) {
    try {
      sessionStorage.setItem(TOKEN_KEY, fromLink);
    } catch {
      // storage blocked: the token still works until this page is reloaded
    }
    params.delete("token");
    const rest = params.toString();
    history.replaceState(null, "", location.pathname + location.search + (rest ? `#${rest}` : ""));
    return fromLink;
  }
  try {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

let token = takeToken();

class ApiError extends Error {
  constructor(status, message = `HTTP ${status}`) {
    super(message);
    this.status = status;
  }
}

const TIMEOUT_MS = 10000;

async function api(path) {
  const res = await fetch(`/api/v1/${path}`, {
    headers: token ? { [TOKEN_HEADER]: token } : {},
    cache: "no-store",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) throw new ApiError(res.status);
  try {
    return await res.json();
  } catch {
    throw new ApiError(res.status, `HTTP ${res.status}, not JSON`);
  }
}

function explain(err) {
  if (err instanceof ApiError && err.status === 403) {
    return "the session token is missing or out of date. Open the link printed by `make ui`.";
  }
  if (err instanceof ApiError) return `unexpected response from the server (${err.message}).`;
  // network error or timeout
  return "the server is not responding. Is `make ui` still running?";
}

async function showStatus() {
  const el = document.getElementById("status");
  try {
    const health = await api("health");
    if (!health.ok) throw new ApiError(200, "health check not ok");
    el.textContent = `connected · version ${health.version}`;
    el.dataset.state = "ok";
  } catch (err) {
    el.textContent = `not connected: ${explain(err)}`;
    el.dataset.state = "error";
  }
}

showStatus();
// pasting a new `make ui` link into an open tab changes only the fragment: no reload
window.addEventListener("hashchange", () => {
  token = takeToken();
  showStatus();
});
// a tab left open after `make ui` stopped must not keep saying "connected"
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") showStatus();
});
