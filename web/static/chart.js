// Charts: Apache ECharts from vendor/, loaded only when a page draws one. It paints on a canvas,
// which can't use CSS variables, so it gets the tokens' current colours as an ECharts theme, and
// again whenever the theme changes.

let library;
const loadECharts = () => (library ??= import("./vendor/echarts/echarts.esm.min.js"));

const live = new Map(); // element → ECharts instance
const resizer = new ResizeObserver((entries) => {
  for (const { target } of entries) live.get(target)?.resize();
});

/** A CSS colour token's current value, for what paints on a canvas. */
export function tokenColor(name) {
  const probe = document.createElement("span");
  probe.style.color = `var(${name})`; // setting it from a script is fine under the CSP
  document.body.append(probe);
  const color = getComputedStyle(probe).color;
  probe.remove();
  return color;
}

// One theme for every chart, from the same tokens as the page: quiet grid, axes as strong as a
// table's rules, the text sizes of the type scale, tooltips like a raised card.
function chartTheme() {
  const fg = tokenColor("--fg");
  const muted = tokenColor("--muted");
  const grid = tokenColor("--chart-grid");
  const axisColor = tokenColor("--chart-axis");
  const surface = tokenColor("--surface");
  const accent = tokenColor("--accent");
  const fontFamily = getComputedStyle(document.body).fontFamily;
  const axis = {
    axisLine: { lineStyle: { color: axisColor } },
    axisTick: { lineStyle: { color: axisColor } },
    axisLabel: { color: muted, fontSize: 11 },
    splitLine: { lineStyle: { color: [grid] } },
    nameTextStyle: { color: muted, fontSize: 11 },
  };
  return {
    color: ["--chart-1", "--chart-2", "--chart-3", "--chart-4"].map((name) => tokenColor(name)),
    backgroundColor: "transparent",
    textStyle: { color: fg, fontFamily, fontSize: 12 },
    title: { textStyle: { color: fg, fontSize: 13, fontWeight: 600 }, subtextStyle: { color: muted } },
    legend: { textStyle: { color: fg, fontSize: 12 }, itemWidth: 14, itemHeight: 8 },
    tooltip: {
      // painted on the canvas. The default HTML tooltip writes markup with style attributes, which
      // the CSP blocks (it comes out unformatted); and records must never be parsed as HTML
      renderMode: "richText",
      backgroundColor: surface,
      borderColor: axisColor,
      borderWidth: 1,
      padding: [6, 10],
      textStyle: { color: fg, fontSize: 12 },
      axisPointer: {
        lineStyle: { color: muted, type: "dashed", width: 1 },
        crossStyle: { color: muted },
      },
    },
    axisPointer: {
      lineStyle: { color: muted, type: "dashed", width: 1 },
      label: { backgroundColor: muted, color: surface },
    },
    line: { lineStyle: { width: 2 }, symbolSize: 5, emphasis: { lineStyle: { width: 2.5 } } },
    bar: { itemStyle: { borderRadius: [2, 2, 0, 0] } },
    markLine: { label: { color: muted }, lineStyle: { color: muted } },
    dataZoom: {
      borderColor: axisColor,
      fillerColor: tokenColor("--accent-soft"),
      handleStyle: { color: surface, borderColor: accent },
      moveHandleStyle: { color: axisColor },
      dataBackground: { lineStyle: { color: axisColor }, areaStyle: { color: grid } },
      selectedDataBackground: { lineStyle: { color: accent }, areaStyle: { color: tokenColor("--accent-soft") } },
      textStyle: { color: muted },
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

// Paper is light whatever the screen's theme: the print styles switch the page's tokens to light,
// and the canvases are repainted with them for the print, then back.
let themeBeforePrint;
window.addEventListener("beforeprint", () => {
  if (!live.size) return;
  const root = document.documentElement;
  themeBeforePrint = root.dataset.theme ?? null;
  root.dataset.theme = "light";
  document.dispatchEvent(new Event("themechange"));
  for (const instance of live.values()) instance.resize();
});
window.addEventListener("afterprint", () => {
  if (themeBeforePrint === undefined) return;
  const root = document.documentElement;
  if (themeBeforePrint === null) delete root.dataset.theme;
  else root.dataset.theme = themeBeforePrint;
  themeBeforePrint = undefined;
  document.dispatchEvent(new Event("themechange"));
  for (const instance of live.values()) instance.resize();
});
