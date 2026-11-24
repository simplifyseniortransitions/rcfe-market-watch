// Public California RCFE Market Map preview. Reads only county and city totals (data/map-preview.json)
// and the county outlines; there are no facility locations, names or addresses anywhere on this page.
// It runs in its own frame on rcfedealroom.com/market-watch, so a problem here can't affect Market Watch.
// Like the rest of the site, it builds the page from text nodes only (no raw HTML).
// It doesn't load common.js: that file sends the Market Watch frame's own height message.

import { setupEarlyAccess } from "./early-access.js";

const STEPS = [0, 25, 75, 200, 500];                      // legend breaks, active facilities per county
const COLORS = ["#eef1f4", "#d6e6f4", "#a8cbea", "#5d9fd6", "#0869bd", "#092d4c"];
const SVG = "http://www.w3.org/2000/svg";
const $ = (id) => document.getElementById(id);
const fmt = (n) => Number(n).toLocaleString("en-US");
const title = (s) => String(s || "").toLowerCase().replace(/(^|[\s\-/(&])(\w)/g, (_m, a, c) => a + c.toUpperCase());
const day = (iso) => new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso)
  .toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "America/Los_Angeles" });

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null && c !== false) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}
function svgEl(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) node.setAttribute(k, v);
  for (const c of children) node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return node;
}
const fill = (node, ...children) => { node.replaceChildren(...children.flat().filter((c) => c != null && c !== false)); return node; };

// ---- talking to rcfedealroom.com (only RCFE Deal Room's own pages; see guard.js) ----
const PARENT = /^https:\/\/((www\.)?rcfedealroom\.com|rcfe-deal-room\.marblism\.me)$/;
function parentOrigin() {
  try {
    const a = location.ancestorOrigins;
    const o = a && a.length ? a[0] : (document.referrer ? new URL(document.referrer).origin : "");
    return PARENT.test(o) ? o : null;
  } catch { return null; }
}
const origin = window.self !== window.top ? parentOrigin() : null;
const sent = new Set();
/** One analytics event for the host page's existing Google Tag Manager. Never personal details. */
export function track(action, label = "", once = false) {
  if (once && sent.has(action + label)) return;
  sent.add(action + label);
  if (origin) window.parent.postMessage({ type: "rcfe-analytics", event: "rcfe_map_preview", action, label: String(label).slice(0, 60) }, origin);
}
// Its own height message, so the host page sizes this frame and not the Market Watch frame.
let lastHeight = 0;
function postHeight() {
  const height = Math.ceil(document.body.getBoundingClientRect().height);
  if (origin && height !== lastHeight) { lastHeight = height; window.parent.postMessage({ type: "rcfe-map-height", height }, origin); }
}
new ResizeObserver(postHeight).observe(document.body);

// ---- county map ----
const colorFor = (n) => COLORS[n === 0 ? 0 : STEPS.filter((s) => n > s).length];
let byName = {}, asOf = "";

function drawMap(shapes, counties) {
  byName = Object.fromEntries(counties.map((c) => [c.county, c]));
  const svg = $("mp-svg");
  svg.setAttribute("viewBox", shapes.viewBox.join(" "));
  fill(svg, shapes.counties.map((s) => {
    const c = byName[s.name] || { facilities: 0 };
    const p = svgEl("path", { d: s.d, fill: colorFor(c.facilities), "data-county": s.name },
      svgEl("title", {}, `${title(s.name)} County: ${fmt(c.facilities)} active facilities`));
    p.addEventListener("mouseenter", (e) => showTip(s.name, e));
    p.addEventListener("mousemove", moveTip);
    p.addEventListener("mouseleave", hideTip);
    p.addEventListener("click", () => selectCounty(s.name));
    return p;
  }));
  const sel = $("mp-county");
  Object.keys(byName).sort().forEach((n) => sel.add(new Option(title(n), n)));
  sel.addEventListener("change", () => sel.value && selectCounty(sel.value));

  const labels = ["None", `1–${STEPS[1]}`, `${STEPS[1] + 1}–${STEPS[2]}`, `${STEPS[2] + 1}–${STEPS[3]}`, `${STEPS[3] + 1}–${STEPS[4]}`, `${STEPS[4] + 1}+`];
  fill($("mp-legend"), el("span", { class: "mp-legend-t" }, "Active facilities"),
    labels.map((l, i) => el("span", {}, el("i", { style: `background:${COLORS[i]}` }), l)));
}

function summary(c) {
  return [
    el("b", {}, `${title(c.county)} County`),
    el("span", {}, el("strong", {}, fmt(c.facilities)), " active RCFE facilities"),
    el("span", {}, el("strong", {}, fmt(c.licensed_capacity)), " total licensed capacity"),
    c.capacity_not_listed ? el("span", { class: "mp-muted" }, `Capacity not listed for ${fmt(c.capacity_not_listed)}.`) : null,
    el("span", { class: "mp-muted" }, `CDSS file of ${day(asOf)}`),
  ];
}
function showTip(name, e) {
  const c = byName[name]; if (!c) return;
  const tip = $("mp-tip");
  fill(tip, summary(c));
  tip.hidden = false;
  moveTip(e);
  track("county_hover", title(name), true);
}
function moveTip(e) {
  const box = $("mp-svg").parentElement.getBoundingClientRect(), tip = $("mp-tip");
  const x = Math.min(e.clientX - box.left + 14, box.width - tip.offsetWidth - 4);
  tip.style.left = `${Math.max(4, x)}px`;
  tip.style.top = `${Math.max(4, e.clientY - box.top - tip.offsetHeight - 10)}px`;
}
function hideTip() { $("mp-tip").hidden = true; }
function selectCounty(name) {
  const c = byName[name]; if (!c) return;
  $("mp-county").value = name;
  fill($("mp-summary"), summary(c));
  $("mp-svg").querySelectorAll("path").forEach((p) => p.classList.toggle("sel", p.dataset.county === name));
  track("county_select", title(name));
}

// ---- top five ----
let top = null, metric = "facilities";
function drawRank() {
  const rows = top.lists[metric] || [];
  fill($("mp-rankrows"), rows.map((r) => el("tr", {},
    el("td", {}, `${r.tied ? "T-" : ""}${r.rank}`), el("td", {}, r.city), el("td", {}, title(r.county)),
    el("td", { class: "n" }, fmt(r.facilities)), el("td", { class: "n" }, fmt(r.licensed_capacity)))));
  $("mp-rank-caption").textContent = `Top five cities by ${metric === "facilities" ? "active RCFE facilities" : "licensed capacity"}`;
}
const note = (node, text) => fill(node, el("tr", {}, el("td", { colspan: "5", class: "mp-muted" }, text)));

// ---- demo map in the member preview: county outlines and sample clusters (not real facilities) ----
// Positions are rough metro areas and the numbers are made up; no real facility is drawn here.
const SAMPLE_CLUSTERS = [[175, 330, "1.2k"], [255, 395, "640"], [390, 560, "410"], [560, 760, "2.4k"], [690, 850, "900"], [250, 150, "85"]];
function drawDemo(shapes) {
  const svg = $("mp-demo-svg");
  svg.setAttribute("viewBox", shapes.viewBox.join(" "));
  let seed = 7;
  const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
  const dots = Array.from({ length: 26 }, (_, i) => {
    const [cx, cy] = SAMPLE_CLUSTERS[i % SAMPLE_CLUSTERS.length];
    return svgEl("circle", { class: `dot${i % 7 === 3 ? " p" : ""}`, cx: (cx + (rnd() - 0.5) * 150).toFixed(0), cy: (cy + (rnd() - 0.5) * 150).toFixed(0), r: 11 });
  });
  fill(svg, shapes.counties.map((s) => svgEl("path", { d: s.d })), dots,
    SAMPLE_CLUSTERS.map(([x, y, n]) => svgEl("g", { transform: `translate(${x} ${y})` }, svgEl("circle", { r: n.includes("k") ? 54 : 44 }), svgEl("text", { dy: 10 }, n))));
}

// ---- early-access form: see early-access.js (RCFE Deal Room's own endpoint; never Mailchimp) ----

// ---- link into the Market Watch frame below ----
function openMarket(e) {
  track("open_market_tab");
  try {
    // The Market Watch frame on the same page is this site too, so it can be pointed at the Market tab.
    for (let i = 0; i < window.parent.frames.length; i++) {
      const f = window.parent.frames[i];
      if (f !== window && f.location.pathname.includes("/rcfe-market-watch/")) {
        e.preventDefault();
        f.location.href = new URL("market.html", location.href).href;
        if (origin) window.parent.postMessage({ type: "rcfe-scroll-to-market" }, origin);
        return;
      }
    }
  } catch { /* fall through to the plain link */ }
}

// ---- views of each part, once ----
function watch(node, action) {
  if (!("IntersectionObserver" in window)) return;
  const io = new IntersectionObserver((es) => { if (es.some((x) => x.isIntersecting)) { track(action, "", true); io.disconnect(); } }, { threshold: 0.4 });
  io.observe(node);
}

async function main() {
  watch($("main"), "preview_view");
  watch($("mp-demo"), "member_preview_view");
  $("mp-demo").addEventListener("click", () => track("member_preview_click"));
  $("mp-open-market").addEventListener("click", openMarket);
  ["facilities", "licensed_capacity"].forEach((m) => $(`mp-t-${m}`).addEventListener("click", () => {
    metric = m;
    document.querySelectorAll(".mp-tabs button").forEach((b) => { const on = b.id === `mp-t-${m}`; b.classList.toggle("on", on); b.setAttribute("aria-selected", String(on)); });
    track("ranking_view", m);
    if (top) drawRank();
  }));
  // The form works (or says "opening soon") even if the figures can't load.
  fetch("data/map-cta.json", { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)
    .then((config) => setupEarlyAccess({ config, track, parentOrigin: origin }));

  try {
    const [data, shapes] = await Promise.all([
      fetch("data/map-preview.json", { cache: "no-cache" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
      fetch("assets/ca-counties.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
    ]);
    asOf = data.as_of;
    fill($("mp-dates"), "CDSS source file: ", el("b", {}, day(data.as_of)), " · Processed by Market Watch: ", el("b", {}, day(data.processed_at)), ` · ${data.refresh}`);
    $("mp-s-fac").textContent = fmt(data.statewide.facilities);
    $("mp-s-cap").textContent = fmt(data.statewide.licensed_capacity);
    $("mp-s-cty").textContent = `${data.statewide.counties_with_facilities} of 58`;
    $("mp-stats").hidden = false;
    $("mp-county-rule").textContent = data.county_rule;
    $("mp-source").textContent = `Source: ${data.source}.`;
    top = data.top;
    drawRank();
    drawMap(shapes, data.counties);
    drawDemo(shapes);
  } catch {
    // Calm fallback: the rest of the section (member preview and sign-up) still shows.
    $("mp-dates").textContent = "The county figures are being refreshed. Please check back shortly.";
    note($("mp-rankrows"), "Rankings will appear here after the weekly refresh.");
    document.querySelector(".mp-mapbox").classList.add("empty");
  }
  postHeight();
}
main();
