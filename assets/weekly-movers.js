// California RCFE Weekly Movers: the public frame on rcfedealroom.com/market-watch.
// It shows an approved report exactly as published and calculates nothing: every number is read from
// data/weekly-movers/reports/<report id>.json, found through data/weekly-movers/current.json.
// It doesn't load common.js or map-preview.js, and its messages use their own names, so it can't resize or
// confuse the Market Watch frame, the Market Map frame or the early-access form.

const EMPTY = "The first California RCFE Weekly Movers report is being prepared. Check back after the next approved weekly update.";
const FAILED = "Weekly Movers is temporarily unavailable. The rest of RCFE Deal Room Market Watch remains available.";
const COMING_SOON = "COMPLETE REPORT FOR FREE MEMBERS — COMING SOON";
const COMPLETE = "VIEW THE COMPLETE WEEKLY MOVERS REPORT";
const NEWS = "WATCH THE LATEST RCFE DEAL ROOM NEWS";
// Message names used by this frame only.
export const HEIGHT_MESSAGE = "rcfe-weekly-movers-height";
export const ANALYTICS_EVENT = "rcfe_weekly_movers";
const REPORT_PATH = /^reports\/wm-\d{4}-\d{2}-\d{2}-r\d{1,3}\.json$/;
// Links the frame will show: RCFE Deal Room's own sites, and YouTube for news episodes.
const SAFE_LINK = /^https:\/\/((www\.|community\.)?rcfedealroom\.com|rcfe-deal-room\.marblism\.me|(www\.)?youtube\.com|youtu\.be)(\/|$)/;

const $ = (id) => document.getElementById(id);
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null && v !== false) node.setAttribute(k, v === true ? "" : v);
  for (const c of children.flat()) if (c != null && c !== false) node.append(c instanceof Node ? c : String(c));
  return node;
}

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
/** One non-personal analytics event for the host page's Google Tag Manager. */
export function track(action, label = "") {
  if (sent.has(action + label) && (action === "weekly_movers_public_view" || action === "weekly_movers_period_view")) return;
  sent.add(action + label);
  if (origin) window.parent.postMessage({ type: "rcfe-analytics", event: ANALYTICS_EVENT, action, label: String(label).slice(0, 40) }, origin);
}
let lastHeight = 0;
function postHeight() {
  const height = Math.ceil(document.body.getBoundingClientRect().height);
  if (origin && height !== lastHeight) { lastHeight = height; window.parent.postMessage({ type: HEIGHT_MESSAGE, height }, origin); }
}
new ResizeObserver(postHeight).observe(document.body);

// ---- formatting only (no arithmetic on report values) ----
export const fmt = (n) => (typeof n === "number" ? n.toLocaleString("en-US") : "–");
export const signed = (n) => (typeof n !== "number" ? "–" : n > 0 ? `+${fmt(n)}` : n < 0 ? `−${fmt(-n)}` : "No change");
export function niceDate(iso) {
  if (!iso) return "";
  const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return "";
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[m - 1]} ${d}, ${y}`;
}
export function place(name) {
  return String(name || "").toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase());
}

// ---- rendering ----
function card(label, value, detail) {
  return el("div", { class: "wm-card" }, el("b", {}, value), el("span", {}, label), detail ? el("small", {}, detail) : null);
}

function moverItems(list, prevKey, curKey, changeKey, unit) {
  if (!list.length) return [el("li", { class: "wm-none" }, "None this week.")];
  return list.map((r) => el("li", {},
    el("span", { class: "wm-place" }, place(r.area), r.county && r.county !== r.area ? el("small", {}, `${place(r.county)} County`) : null),
    el("span", { class: "wm-vals" }, `${fmt(r[prevKey])} → ${fmt(r[curKey])} ${unit}`),
    el("span", { class: r[changeKey] > 0 ? "wm-chg up" : "wm-chg down" }, signed(r[changeKey]))));
}

export function renderReport(pointer, report) {
  const s = report.statewide;
  if (pointer.test_preview || report.test_preview) {
    $("wm-test").textContent = report.test_label || "TEST PREVIEW — NOT A PUBLISHED REPORT";
    $("wm-test").hidden = false;
  }
  $("wm-correction").hidden = !(pointer.corrected || report.supersedes);
  const approved = report.approval_date ? `Approved ${niceDate(report.approval_date)}` : "Not approved (test preview)";
  $("wm-period").replaceChildren(
    el("p", {}, el("b", {}, "Comparing CDSS files dated "), `${niceDate(report.previous_source_date)} and ${niceDate(report.current_source_date)}`),
    el("p", { class: "wm-meta" }, `Source date ${niceDate(report.current_source_date)} · ${approved} · Methodology ${report.methodology_version} · `,
      el("button", { type: "button", class: "wm-link", id: "wm-method-btn" }, "Methodology")));
  $("wm-cards").replaceChildren(
    card("Net change in active facility records", signed(s.net_active_change), `${fmt(s.previous_active)} → ${fmt(s.current_active)}`),
    card("Newly observed active records", fmt(s.newly_observed), "in the latest CDSS file"),
    card("Records no longer appearing as active", fmt(s.no_longer_active), "in the latest CDSS file"),
    card("Net change in recorded licensed capacity", signed(s.net_capacity_change), `${fmt(s.previous_capacity)} → ${fmt(s.current_capacity)}`));
  const m = report.movers;
  $("wm-city-up").replaceChildren(...moverItems(m.city_count_increases, "previous_count", "current_count", "count_change", "records"));
  $("wm-city-down").replaceChildren(...moverItems(m.city_count_decreases, "previous_count", "current_count", "count_change", "records"));
  $("wm-county-up").replaceChildren(...moverItems(m.county_capacity_increases, "previous_capacity", "current_capacity", "capacity_change", "licensed capacity"));
  $("wm-county-down").replaceChildren(...moverItems(m.county_capacity_decreases, "previous_capacity", "current_capacity", "capacity_change", "licensed capacity"));
  $("wm-city-note").textContent = report.city_note || "";
  $("wm-method-id").textContent = `(version ${report.methodology_version})`;
  $("wm-method-list").replaceChildren(...((report.methodology && report.methodology.summary) || []).map((x) => el("li", {}, x)));
  if (report.disclaimer) $("wm-disclaimer").textContent = report.disclaimer;
  $("wm-method-btn").addEventListener("click", () => { $("wm-method").open = true; $("wm-method").scrollIntoView({ block: "nearest" }); track("weekly_movers_methodology_click"); });
  $("wm-method").addEventListener("toggle", () => { if ($("wm-method").open) track("weekly_movers_methodology_click"); });
  $("wm-status").hidden = true;
  $("wm-report").hidden = false;
  track("weekly_movers_public_view");
  track("weekly_movers_period_view", report.current_source_date);
}

export function renderCtas(pointer) {
  const box = $("wm-ctas");
  const url = pointer && SAFE_LINK.test(pointer.complete_report_url || "") ? pointer.complete_report_url : null;
  const main = url
    ? el("a", { class: "wm-btn primary", href: url, target: "_top" }, COMPLETE)
    : el("span", { class: "wm-btn soon", "aria-disabled": "true" }, COMING_SOON);
  if (url) main.addEventListener("click", () => track("weekly_movers_complete_report_click"));
  const news = pointer && pointer.news && SAFE_LINK.test(pointer.news.url || "") ? pointer.news : null;
  let second = null;
  if (news) {
    second = el("a", { class: "wm-btn secondary", href: news.url, target: "_blank", rel: "noopener" }, NEWS);
    second.addEventListener("click", () => track("weekly_movers_news_click"));
  }
  box.replaceChildren(main, second ? second : "", news ? el("p", { class: "wm-news" }, news.title) : "");
}

function showMessage(text) {
  $("wm-status").textContent = text;
  $("wm-status").hidden = false;
  $("wm-report").hidden = true;
}

export async function load(base = "data/weekly-movers/") {
  let pointer;
  try {
    const r = await fetch(`${base}current.json`, { cache: "no-cache", credentials: "omit" });
    if (!r.ok) throw new Error("pointer");
    pointer = await r.json();
  } catch {
    showMessage(FAILED);
    renderCtas(null);
    return "failed";
  }
  renderCtas(pointer);
  if (pointer.status === "empty" || !pointer.report_id) {
    if (pointer.test_preview) { $("wm-test").textContent = "TEST PREVIEW — EMPTY STATE"; $("wm-test").hidden = false; }
    showMessage(EMPTY);
    return "empty";
  }
  try {
    if (!REPORT_PATH.test(pointer.report_url || "")) throw new Error("path");
    // Report files never change once published, so the browser may keep them.
    const r = await fetch(base + pointer.report_url, { credentials: "omit" });
    if (!r.ok) throw new Error("report");
    const report = await r.json();
    if (report.report_id !== pointer.report_id || !report.statewide || !report.movers) throw new Error("mismatch");
    if (report.status !== "approved" && !(pointer.test_preview && report.test_preview)) throw new Error("status");
    renderReport(pointer, report);
    return "report";
  } catch {
    showMessage(FAILED);
    return "failed";
  }
}

load();
