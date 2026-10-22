import {
  asOfLine, change, isCore, clear, date, el, fail, facilityLink, getJSON, num, params, place, segmented, select, setParams,
} from "./common.js";

const p = params();
const state = {
  county: p.get("county") || "",
  size: p.get("size") || "all_sizes",
  scope: p.get("scope") || "all",
  week: p.get("week") || "this",
};

const TOTALS = [
  "licensed_facilities", "licensed_beds", "median_licensed_capacity", "pending", "on_probation", "licensees_3plus",
];

let pulse, market, feed;

Promise.all([getJSON("pulse.json"), getJSON("market.json"), getJSON("feed.json")])
  .then(([a, b, c]) => { pulse = a; market = b; feed = c; init(); })
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
    segmented("week", "Show", [["this", "This week"], ["last", "Last week"]], state.week, update("week")));
}

// The numbers for the current selection: statewide from pulse.json, a county from market.json.
function view() {
  if (!state.county) {
    const seg = pulse.segments[state.scope][state.size];
    const signals = {};
    for (const row of market.counties[state.scope][state.size]) {
      for (const [k, v] of Object.entries(row.signals)) signals[k] = (signals[k] || 0) + v;
    }
    return { totals: seg.totals, wow: seg.week_over_week, activity: seg.activity, signals };
  }
  const row = market.counties[state.scope][state.size].find((r) => r.county === state.county);
  if (!row) return null;
  return { totals: row, wow: row.week_over_week, activity: row.activity, signals: row.signals };
}

function label(key) {
  const d = pulse.definitions[key];
  return d ? d.label : key;
}

function stat(key, v, { title, sub, showChange = true } = {}) {
  const last = state.week === "last";
  const value = last ? (v.wow[key] == null ? null : v.totals[key] - v.wow[key]) : v.totals[key];
  return el("div", { class: "card", title: pulse.definitions[key]?.rule },
    el("div", { class: "stat-label", text: title || label(key) }),
    el("div", { class: "stat-value", text: num(value) }),
    sub ? el("div", { class: "stat-sub", text: sub }) : null,
    !last && showChange ? change(v.wow[key]) : null);
}

function activityCard(title, value, sub, rule) {
  return el("div", { class: "card", title: rule },
    el("div", { class: "stat-label", text: title }),
    el("div", { class: "stat-value", text: num(value) }),
    sub ? el("div", { class: "stat-sub", text: sub }) : null);
}

function render() {
  const where = state.county ? `${place(state.county)} County` : "California";
  const week = state.week === "last" ? `week of ${date(pulse.prior_snapshot_id)}` : `week of ${date(pulse.as_of)}`;
  document.getElementById("subtitle").textContent =
    `${where}, ${week}. Compared with ${pulse.prior_snapshot_id ? date(pulse.prior_snapshot_id) : "no earlier file yet"}.`;

  const v = view();
  const totals = document.getElementById("totals");
  if (!v) {
    clear(totals, el("p", { class: "muted", text: "No facilities match this selection." }));
    ["activity", "window", "feed", "signals"].forEach((id) => clear(document.getElementById(id)));
    return;
  }
  const ownersTitle = state.county ? "Licensees with 3+ homes in this county" : label("licensees_3plus");
  clear(totals, TOTALS.map((k) => stat(k, v, k === "licensees_3plus" ? { title: ownersTitle } : {})));

  const act = document.getElementById("activity");
  if (state.week === "last") {
    clear(act,
      stat("new_licenses_7d", v, { title: "New licenses, 7 days", sub: "License First Date in the 7 days to last week's file" }),
      stat("closures_closed_date_7d", v, { title: "Closed Date in the last 7 days" }),
      el("p", { class: "muted small", text: "Week-to-week changes for last week need three weekly files; they will appear here once we have them." }));
  } else {
    const a = v.activity;
    clear(act,
      stat("new_licenses_7d", v, { title: "New licenses, 7 days", sub: "License First Date in the last 7 days" }),
      a ? activityCard("Closures: status changed to CLOSED", a.closures_status_changed, "since last week's file",
        pulse.definitions.closures_status_changed.rule) : null,
      stat("closures_closed_date_7d", v, { title: "Closures: Closed Date in the last 7 days" }),
      a ? activityCard("Ownership changes", a.ownership_changes, "licensee changed since last week",
        pulse.definitions.ownership_changes.rule) : null,
      a ? activityCard("New substantiated allegations", a.new_substantiated_allegations,
        `at ${num(a.facilities_new_substantiated)} facilities`, pulse.definitions.new_substantiated_allegations.rule) : null,
      a ? activityCard("New facility numbers", a.new_facility_numbers, "not in last week's file",
        pulse.definitions.new_facility_numbers.rule) : null,
      a ? null : el("p", { class: "muted small", text: "Week-to-week changes start once there are two weekly files." }));
  }

  clear(document.getElementById("window"),
    stat("new_licenses_90d", v),
    stat("closures_closed_date_90d", v),
    stat("citations_12m", v, { sub: `at ${num(state.week === "last" && v.wow.facilities_with_citations_12m != null
      ? v.totals.facilities_with_citations_12m - v.wow.facilities_with_citations_12m
      : v.totals.facilities_with_citations_12m)} facilities` }));

  renderFeed();
  renderSignals(v.signals);
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
