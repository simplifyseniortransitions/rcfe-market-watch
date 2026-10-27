// Shared helpers. Data is read only from this site's data/ folder; there are no third-party scripts.

// Inside the RCFE Deal Room site's frame, tell that page this page's height so the frame fits
// without an inner scroll bar. The message carries only a number.
if (window.parent !== window) {
  let last = 0;
  const sendHeight = () => {
    const height = Math.ceil(document.body.getBoundingClientRect().height);
    if (height !== last) {
      last = height;
      window.parent.postMessage({ type: "rcfe-height", height }, "*");
    }
  };
  new ResizeObserver(sendHeight).observe(document.body);
  window.addEventListener("load", sendHeight);
}

// Mirrors Facility.is_core in pipeline/normalize.py: blank type counts with regular RCFEs.
const CORE_TYPES = ["RESIDENTIAL CARE ELDERLY", ""];
export const isCore = (type) => CORE_TYPES.includes(type || "");

const cache = new Map();
export function getJSON(name) {
  if (!cache.has(name)) {
    cache.set(name, fetch(`data/${name}`, { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`${name}: ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(name);
}

// Build DOM nodes without innerHTML, so data values are always treated as text.
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function clear(node, ...children) {
  node.replaceChildren(...children.flat().filter((c) => c != null));
}

export const num = (n) => (n == null ? "—" : Number(n).toLocaleString("en-US"));

export function change(n, { short = false, since = "last week" } = {}) {
  if (n == null) return el("span", { class: "chg flat", text: short ? "—" : "no earlier file to compare" });
  const cls = n > 0 ? "up" : n < 0 ? "down" : "flat";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "±";
  return el("span", { class: `chg ${cls}`, text: `${sign}${num(Math.abs(n))}${short ? "" : ` since ${since}`}` });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function date(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${MONTHS[m - 1]} ${d}, ${y}`;
}

export function place(county) {
  if (!county || county === "(BLANK)") return "County not listed";
  return county.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase());
}

export function params() {
  return new URLSearchParams(location.search);
}

export function setParams(values) {
  const p = params();
  for (const [k, v] of Object.entries(values)) {
    if (v == null || v === "" || v === "all" || v === "all_sizes") p.delete(k);
    else p.set(k, v);
  }
  const qs = p.toString();
  history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
}

// Segmented radio control. options: [[value, label]]
export function segmented(name, legend, options, value, onChange) {
  return el("fieldset", { class: "control" },
    el("legend", { text: legend }),
    el("div", { class: "seg" }, options.map(([v, label]) =>
      el("label", {},
        el("input", { type: "radio", name, value: v, checked: v === value, onchange: () => onChange(v) }),
        el("span", { text: label })))));
}

// options: [[value, text]] or [[value, text, disabled]]
export function select(label, options, value, onChange, attrs = {}) {
  const s = el("select", { onchange: (e) => onChange(e.target.value), ...attrs },
    options.map(([v, text, disabled]) => el("option", { value: v, selected: v === value, disabled: !!disabled, text })));
  return el("label", { class: "control" }, el("span", { text: label }), s);
}

export function asOfLine(meta) {
  const line = document.querySelector("[data-as-of]");
  if (line) line.textContent = `Data as of ${date(meta.as_of)} · updated ${date(meta.generated_at)}`;
}

export function fail(node, err) {
  clear(node, el("p", { class: "error", text: `Could not load the data (${err.message}). Please try again later.` }));
}

export function facilityLink(number, name) {
  return el("a", { href: `facility.html?id=${encodeURIComponent(number)}`, text: name || number });
}

export function licenseeText(name, withheld) {
  return withheld ? el("span", { class: "withheld", text: name }) : name;
}

// ---- Comparing with an earlier week (data/history.json) ----
// Every number is this week's file minus the chosen week's file, or the sum of the weekly changes
// in between; nothing is estimated.

export function compareChoice(history, key) {
  const last = history.weeks.length - 1;
  const choices = history.compare_options.map((o) => {
    const idx = o.weeks_back == null ? 0 : last - o.weeks_back;
    return { ...o, idx, available: idx >= 0 && idx < last, date: history.weeks[Math.max(idx, 0)] };
  });
  const chosen = choices.find((c) => c.key === key && c.available) || choices.find((c) => c.available) || null;
  return { chosen, choices };
}

export function compareSelect(history, key, onChange) {
  const { choices } = compareChoice(history, key);
  const have = history.weeks.length;
  return select("Compare with", choices.map((c) => [c.key,
    c.available ? `${c.label} (${date(c.date)})` : `${c.label} (needs ${c.weeks_back ? c.weeks_back + 1 : 2} weekly files; ${have} so far)`,
    !c.available]), compareChoice(history, key).chosen?.key, onChange);
}

// The week-by-week record for one area ("California" or a county) of one scope and size.
export function series(history, scope, size, area) {
  return history.series[`${scope}|${size}`]?.[area || "California"] || null;
}

export function changeSince(rec, key, current, idx) {
  const base = rec?.[key]?.[idx];
  return base == null || current == null ? null : current - base;
}

// Sum of a weekly count for the weeks after idx, up to the current week. null if any week is missing.
export function sumSince(rec, key, idx) {
  const values = (rec?.[key] || []).slice(idx + 1);
  return values.length && values.every((v) => v != null) ? values.reduce((a, b) => a + b, 0) : null;
}

// True when the weekly files from idx to the current one are each exactly 7 days apart, so adding up
// each week's 7-day count covers every day in between once.
export function evenlyWeekly(weeks, idx) {
  const days = (d) => Date.UTC(...d.split("-").map((x, i) => (i === 1 ? x - 1 : +x))) / 86400000;
  for (let i = idx + 1; i < weeks.length; i++) if (days(weeks[i]) - days(weeks[i - 1]) !== 7) return false;
  return true;
}

// ---- Small charts drawn as SVG by this site (no chart library) ----
const SVG = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
  for (const c of children.flat()) if (c != null) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}

function points(values, w, h, pad) {
  const known = values.filter((v) => v != null);
  const lo = Math.min(...known), hi = Math.max(...known);
  const span = hi - lo || 1;
  const step = values.length > 1 ? (w - pad.l - pad.r) / (values.length - 1) : 0;
  return { lo, hi, xy: values.map((v, i) => (v == null ? null
    : [pad.l + i * step, pad.t + (h - pad.t - pad.b) * (1 - (hi === lo ? 0.5 : (v - lo) / span))])) };
}

function path(xy) {
  let d = "", pen = false;
  for (const p of xy) {
    if (!p) { pen = false; continue; }
    d += `${pen ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`;
    pen = true;
  }
  return d;
}

export function lineChart(title, values, weeks) {
  const w = 320, h = 120, pad = { l: 8, r: 8, t: 10, b: 22 };
  const { lo, hi, xy } = points(values, w, h, pad);
  const known = values.map((v, i) => [v, i]).filter(([v]) => v != null);
  const [first, firstI] = known[0] || [null, 0];
  const [last, lastI] = known[known.length - 1] || [null, 0];
  const summary = `${title}: ${num(first)} in the week of ${date(weeks[firstI])}, ${num(last)} in the week of ${date(weeks[lastI])}; low ${num(lo)}, high ${num(hi)}.`;
  return el("figure", { class: "card chart" },
    el("figcaption", {},
      el("span", { class: "stat-label", text: title }),
      el("span", { class: "chart-now", text: num(last) })),
    svg("svg", { viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": summary },
      svg("title", {}, summary),
      svg("line", { x1: pad.l, x2: w - pad.r, y1: h - pad.b, y2: h - pad.b, class: "axis" }),
      svg("path", { d: path(xy), class: "line" }),
      xy.map((p, i) => (p ? svg("circle", { cx: p[0], cy: p[1], r: i === lastI ? 3.5 : 2.5, class: i === lastI ? "dot now" : "dot" }) : null)),
      svg("text", { x: pad.l, y: h - 6, class: "tick" }, date(weeks[0])),
      svg("text", { x: w - pad.r, y: h - 6, class: "tick", "text-anchor": "end" }, date(weeks[weeks.length - 1]))),
    el("div", { class: "stat-sub", text: `Low ${num(lo)} · high ${num(hi)} · ${known.length} weeks` }));
}

export function sparkline(values, label) {
  const w = 90, h = 24, pad = { l: 2, r: 4, t: 3, b: 3 };
  if (values.filter((v) => v != null).length < 2) return el("span", { class: "muted", text: "—" });
  const { xy } = points(values, w, h, pad);
  const end = [...xy].reverse().find(Boolean);
  return svg("svg", { viewBox: `0 0 ${w} ${h}`, width: w, height: h, class: "spark", role: "img", "aria-label": label },
    svg("title", {}, label),
    svg("path", { d: path(xy), class: "line" }),
    end ? svg("circle", { cx: end[0], cy: end[1], r: 2.2, class: "dot now" }) : null);
}
