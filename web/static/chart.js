// Charts: Apache ECharts from vendor/, loaded only when a page draws one. It paints on a canvas,
// which can't use CSS variables, so it gets the tokens' current colours as an ECharts theme, and
// again whenever the theme changes.

let library;
const loadECharts = () => (library ??= import("./vendor/echarts/echarts.esm.min.js"));

const live = new Map(); // element → ECharts instance
const resizer = new ResizeObserver((entries) => {
  for (const { target } of entries) live.get(target)?.resize();
});

function tokenColor(name) {
  const probe = document.createElement("span");
  probe.style.color = `var(${name})`; // setting it from a script is fine under the CSP
  document.body.append(probe);
  const color = getComputedStyle(probe).color;
  probe.remove();
  return color;
}

function chartTheme() {
  const fg = tokenColor("--fg");
  const muted = tokenColor("--muted");
  const border = tokenColor("--border");
  const axis = {
    axisLine: { lineStyle: { color: border } },
    axisTick: { lineStyle: { color: border } },
    axisLabel: { color: muted },
    splitLine: { lineStyle: { color: [border] } },
  };
  return {
    color: ["--chart-1", "--chart-2", "--chart-3", "--chart-4"].map((name) => tokenColor(name)),
    backgroundColor: "transparent",
    textStyle: { color: fg, fontFamily: getComputedStyle(document.body).fontFamily },
    title: { textStyle: { color: fg }, subtextStyle: { color: muted } },
    legend: { textStyle: { color: fg } },
    tooltip: {
      // painted on the canvas. The default HTML tooltip writes markup with style attributes, which
      // the CSP blocks (it comes out unformatted); and records must never be parsed as HTML
      renderMode: "richText",
      backgroundColor: tokenColor("--surface"),
      borderColor: border,
      textStyle: { color: fg },
    },
    categoryAxis: axis,
    valueAxis: axis,
    timeAxis: axis,
    logAxis: axis,
  };
}

// the charts of a page the user has left: nothing else frees them
function disposeDetached() {
  for (const [element, instance] of live) {
    if (element.isConnected) continue;
    resizer.unobserve(element);
    instance.dispose();
    live.delete(element);
  }
}

/**
 * Draw an ECharts option into an element that is in the page. `label` says what the chart shows,
 * for screen readers. Returns the instance, or null if the user left the page while it loaded.
 */
export async function drawChart(element, option, { label }) {
  const echarts = await loadECharts();
  if (!element.isConnected) return null;
  disposeDetached();
  element.classList.add("chart");
  element.setAttribute("role", "img");
  element.setAttribute("aria-label", label);
  const instance = echarts.init(element, chartTheme());
  instance.setOption(option);
  live.set(element, instance);
  resizer.observe(element);
  return instance;
}

document.addEventListener("themechange", () => {
  disposeDetached();
  const theme = chartTheme();
  for (const instance of live.values()) instance.setTheme(theme);
});
