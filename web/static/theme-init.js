// A classic script in <head>: it runs before the first paint, where a module would run too late
// and flash the other theme. The picker itself is in theme.js.
try {
  const stored = localStorage.getItem("health-os-theme");
  if (stored === "light" || stored === "dark") document.documentElement.dataset.theme = stored;
} catch {
  // storage blocked: follow the system theme
}
