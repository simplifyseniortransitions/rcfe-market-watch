import {
  asOfLine, change, changeSince, clear, compareChoice, compareSelect, date, el, evenlyWeekly, fail, facilityLink,
  getJSON, isCore, lineChart, num, params, place, segmented, select, series, setParams, sumSince,
} from "./common.js";

const p = params();
const state = {
  county: p.get("county") || "",
  size: p.get("size") || "all_sizes",
  scope: p.get("scope") || "all",
  compare: p.get("compare") || "1",
};

// Trend charts: [history key, chart title]
const TRENDS = [
  ["licensed_facilities", "Licensed facilities"],
  ["licensed_beds", "Licensed beds"],
  ["pending", "Pending"],
  ["on_probation", "On probation"],
  ["new_licenses_7d", "New licenses per week"],
  ["closures_closed_date_7d", "Closures per week (Closed Date)"],
];

const TOTALS = [
  "licensed_facilities", "licensed_beds", "median_licensed_capacity", "pending", "on_probation", "licensees_3plus",
];

let pulse, market, feed, history;

Promise.all([getJSON("pulse.json"), getJSON("market.json"), getJSON("feed.json"), getJSON("history.json")])
  .then(([a, b, c, d]) => { pulse = a; market = b; feed = c; history = d; init(); })
  .catch((err) => fail(document.getElementById("totals"), err));

function init() {
  asOfLine(pulse);
  const counties = market.counties.all.all_sizes.map((r) => r.county).filter((c) => c !== "(BLANK)");
  clear(document.getElementById("signup-county"),
    el("option", { text: "All California" }), counties.map((c) => el("option", { text: place(c) })));
  renderControls(counties);
  render();
}

function renderControls(counties) {
  const update = (k) => (v) => { state[k] = v; setParams({ [k]: v }); render(); };
  clear(document.getElementById("controls"),
    select("County", [["", "All California"], ...counties.map((c) => [c, place(c)])], state.county, update("county")),
    segmented("size", "Home size", Object.entries(pulse.sizes), state.size, update("size")),
    segmented("scope", "Facility types", ["all", "core"].map((k) => [k, pulse.scopes[k]]), state.scope, update("scope")),
    compareSelect(history, state.compare, update("compare")));
}

// The numbers for the current selection: statewide from pulse.json, a county from market.json,
// and the week-by-week record for the same selection from history.json.
function view() {
  const rec = series(history, state.scope, state.size, state.county);
  if (!state.county) {
    const seg = pulse.segments[state.scope][state.size];
    const signals = {};
    for (const row of market.counties[state.scope][state.size]) {
      for (const [k, v] of Object.entries(row.signals)) signals[k] = (signals[k] || 0) + v;
    }
    return { totals: seg.totals, activity: seg.activity, signals, rec };
  }
  const row = market.counties[state.scope][state.size].find((r) => r.county === state.county);
  if (!row) return null;
  return { totals: row, activity: row.activity, signals: row.signals, rec };
}

const compared = () => compareChoice(history, state.compare).chosen;

function label(key) {
  const d = pulse.definitions[key];
  return d ? d.label : key;
}

function stat(key, v, { title, sub, showChange = true } = {}) {
  const c = compared();
  return el("div", { class: "card", title: pulse.definitions[key]?.rule },
    el("div", { class: "stat-label", text: title || label(key) }),
    el("div", { class: "stat-value", text: num(v.totals[key]) }),
    sub ? el("div", { class: "stat-sub", text: sub }) : null,
    showChange ? change(c ? changeSince(v.rec, key, v.totals[key], c.idx) : null, { since: c ? date(c.date) : "" }) : null);
}

function activityCard(title, value, sub, rule) {
  return el("div", { class: "card", title: rule },
    el("div", { class: "stat-label", text: title }),
    el("div", { class: "stat-value", text: num(value) }),
    sub ? el("div", { class: "stat-sub", text: sub }) : null);
}

function render() {
  const where = state.county ? `${place(state.county)} County` : "California";
  const c = compared();
  document.getElementById("subtitle").textContent = `${where}, week of ${date(pulse.as_of)}. ` +
    (c ? `Compared with the week of ${date(c.date)} (${c.label.toLowerCase()}).` : "No earlier file to compare yet.");

  const v = view();
  const totals = document.getElementById("totals");
  if (!v) {
    clear(totals, el("p", { class: "muted", text: "No facilities match this selection." }));
    ["activity", "window", "feed", "signals", "trends"].forEach((id) => clear(document.getElementById(id)));
    return;
  }
  const ownersTitle = state.county ? "Licensees with 3+ homes in this county" : label("licensees_3plus");
  clear(totals, TOTALS.map((k) => stat(k, v, k === "licensees_3plus" ? { title: ownersTitle } : {})));

  renderActivity(v, c);
  clear(document.getElementById("window"),
    stat("new_licenses_90d", v),
    stat("closures_closed_date_90d", v),
    stat("citations_12m", v, { sub: `at ${num(v.totals.facilities_with_citations_12m)} facilities` }));
  renderTrends(v);
  renderFeed();
  renderSignals(v.signals);
}

// Weekly activity for the comparison period: one week's changes for "last week", otherwise the
// weekly changes added up week by week since the chosen week.
function renderActivity(v, c) {
  const act = document.getElementById("activity");
  document.getElementById("activity-h").textContent = c && c.weeks_back !== 1 ? `Activity since ${date(c.date)}` : "Weekly activity";
  if (!c) {
    clear(act, el("p", { class: "muted small", text: "Week-to-week changes start once there are two weekly files." }));
    return;
  }
  const one = c.weeks_back === 1;
  const weeks = history.weeks.length - 1 - c.idx;
  const since = one ? "since last week's file" : `in ${weeks} weekly comparisons since ${date(c.date)}`;
  const d = pulse.definitions;
  const summed = (key) => sumSince(v.rec, key, c.idx);
  const dated = (key) => (evenlyWeekly(history.weeks, c.idx) ? summed(key) : null);
  const card = (title, value, sub, rule) => el("div", { class: "card", title: rule },
    el("div", { class: "stat-label", text: title }),
    el("div", { class: "stat-value", text: num(value) }),
    sub ? el("div", { class: "stat-sub", text: sub }) : null);
  clear(act,
    card(one ? "New licenses, 7 days" : `New licenses since ${date(c.date)}`,
      one ? v.totals.new_licenses_7d : dated("new_licenses_7d"),
      one ? "License First Date in the last 7 days" : "License First Date, each week's 7 days added up", d.new_licenses_7d.rule),
    card("Closures: status changed to CLOSED", summed("closures_status_changed"), since, d.closures_status_changed.rule),
    card(one ? "Closures: Closed Date in the last 7 days" : `Closures by Closed Date since ${date(c.date)}`,
      one ? v.totals.closures_closed_date_7d : dated("closures_closed_date_7d"),
      one ? null : "each week's 7 days added up", d.closures_closed_date_7d.rule),
    card("Ownership changes", summed("ownership_changes"), since, d.ownership_changes.rule),
    card("New substantiated allegations", summed("new_substantiated_allegations"),
      one && v.activity ? `at ${num(v.activity.facilities_new_substantiated)} facilities` : since, d.new_substantiated_allegations.rule),
    card("New facility numbers", summed("new_facility_numbers"), since, d.new_facility_numbers.rule));
}

function renderTrends(v) {
  const box = document.getElementById("trends");
  const have = history.weeks.length, need = history.chart_min_weeks;
  if (have < need || !v.rec) {
    clear(box);
    document.getElementById("trends-note").textContent =
      `Trend charts start once ${need} weekly files are on hand (${have} so far: ${history.weeks.map(date).join(", ")}).`;
    return;
  }
  clear(box, TRENDS.map(([key, title]) => lineChart(title, v.rec[key] || [], history.weeks)));
  document.getElementById("trends-note").textContent =
    `One point per weekly state file, ${date(history.weeks[0])} to ${date(history.weeks[have - 1])}. ${pulse.definitions.compare_with?.rule || ""}`;
}

function matches(e) {
  if (state.county && e.county !== state.county) return false;
  if (state.size !== "all_sizes" && e.size_group !== state.size) return false;
  if (state.scope === "core" && !isCore(e.facility_type)) return false;
  return true;
}

function describe(e) {
  if (e.change_type === "new_facility") return `New listing, status ${e.new}`;
  return `${e.old ?? "—"} → ${e.new ?? "—"}`;
}

function renderFeed() {
  const labels = Object.fromEntries(pulse.event_types.map((t) => [t.key, t.label]));
  const events = feed.events.filter(matches).slice(0, 10);
  const list = document.getElementById("feed");
  if (!events.length) {
    clear(list, el("li", { class: "muted", text: "No changes for this selection yet." }));
    return;
  }
  clear(list, events.map((e) => el("li", {},
    el("div", {}, el("span", { class: "tag", text: labels[e.change_type] }), facilityLink(e.facility_number, e.facility_name)),
    el("div", { class: "small muted" },
      `${describe(e)} · ${e.city ? `${place(e.city)}, ` : ""}${place(e.county)} · week of ${date(e.date)}`))));
}

function renderSignals(counts) {
  const qs = new URLSearchParams();
  if (state.county) qs.set("county", state.county);
  if (state.size !== "all_sizes") qs.set("size", state.size);
  if (state.scope !== "all") qs.set("scope", state.scope);
  clear(document.getElementById("signals"), pulse.signal_rules.map((r) => {
    const q = new URLSearchParams(qs);
    q.set("signal", r.key);
    return el("li", {},
      el("div", {},
        el("div", {}, el("a", { href: `facilities.html?${q}`, text: r.label })),
        el("div", { class: "small muted", text: r.rule })),
      el("span", { class: "count", text: num(counts[r.key] || 0) }));
  }));
  document.getElementById("signals-note").textContent = `Facilities flagged, current file. ${pulse.signal_disclaimer}`;
}
