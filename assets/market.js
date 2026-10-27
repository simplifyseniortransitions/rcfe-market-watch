import {
  asOfLine, change, changeSince, clear, compareChoice, compareSelect, date, el, fail, getJSON, num, params, place,
  segmented, series, setParams, sparkline,
} from "./common.js";

const p = params();
const state = {
  size: p.get("size") || "all_sizes",
  scope: p.get("scope") || "all",
  q: p.get("q") || "",
  bands: p.get("bands") === "1",
  sort: p.get("sort") || "licensed_facilities",
  dir: p.get("dir") || "desc",
  compare: p.get("compare") || "1",
};

// group: "activity" (last 12 months) or "supply" (as of the latest file). fmt: how the value is shown.
const COLUMNS = [
  { key: "county", label: "County", text: true },
  { key: "new_licenses_12m", label: "New licenses", group: "activity" },
  { key: "closures_12m", label: "Closures", group: "activity" },
  { key: "net_change_12m", label: "Net change", group: "activity", fmt: "signed" },
  { key: "growth_rate_12m", label: "Growth rate", group: "activity", fmt: "pct", rate: true },
  { key: "churn_rate_12m", label: "Churn rate", group: "activity", fmt: "pct", rate: true },
  { key: "licensed_facilities", label: "Licensed homes", group: "supply" },
  { key: "pending", label: "Pending", group: "supply" },
  { key: "on_probation", label: "On probation", group: "supply" },
  { key: "probation_share", label: "Probation share", group: "supply", fmt: "pct2", rate: true },
  { key: "share_licensed_multi", label: "Held by 3+ home licensees", group: "supply", fmt: "pct", rate: true },
  { key: "licensed_beds", label: "Licensed beds", group: "supply" },
  { key: "median_licensed_capacity", label: "Median beds", group: "supply" },
];

const pct = (x, places = 1) => (x == null ? "—" : `${(100 * x).toFixed(places)}%`);

let pulse, market, history;

Promise.all([getJSON("pulse.json"), getJSON("market.json"), getJSON("history.json")])
  .then(([a, b, c]) => { pulse = a; market = b; history = c; asOfLine(pulse); renderControls(); render(); })
  .catch((err) => fail(document.querySelector("#county-table tbody"), err));

const compared = () => compareChoice(history, state.compare).chosen;
const record = (r) => series(history, state.scope, state.size, r.county === "California" ? null : r.county);

function columns() {
  const c = compared();
  const cols = [...COLUMNS];
  const at = cols.findIndex((x) => x.key === "licensed_facilities") + 1;
  const extra = [{
    key: "change", label: c ? `Change since ${date(c.date)}` : "Change", group: "supply", fmt: "change",
    get: (r) => (c ? changeSince(record(r), "licensed_facilities", r.licensed_facilities, c.idx) : null),
  }];
  if (history.weeks.length >= history.chart_min_weeks) {
    extra.push({ key: "trend", label: "Trend", group: "supply", fmt: "spark", nosort: true,
      get: (r) => record(r)?.licensed_facilities || [] });
  }
  cols.splice(at, 0, ...extra);
  const bandCols = market.bands.map((b) => ({
    key: `band_${b.key}`, label: b.label, group: "supply", get: (r) => r.licensed_by_band[b.key] }));
  return state.bands ? [...cols, ...bandCols] : cols;
}

const value = (col, r) => (col.get ? col.get(r) : r[col.key]);

function renderControls() {
  const update = (k) => (v) => { state[k] = v; setParams({ [k]: v }); render(); };
  const search = el("input", {
    type: "search", value: state.q, placeholder: "Type a county name", "aria-label": "Filter counties",
    oninput: (e) => { state.q = e.target.value; setParams({ q: state.q }); render(); },
  });
  const bands = el("input", {
    type: "checkbox", checked: state.bands,
    onchange: (e) => { state.bands = e.target.checked; setParams({ bands: state.bands ? "1" : "" }); render(); },
  });
  clear(document.getElementById("controls"),
    el("label", { class: "control" }, el("span", { text: "Filter counties" }), search),
    segmented("size", "Home size", Object.entries(pulse.sizes), state.size, update("size")),
    segmented("scope", "Facility types", ["all", "core"].map((k) => [k, pulse.scopes[k]]), state.scope, update("scope")),
    compareSelect(history, state.compare, update("compare")),
    el("label", { class: "control" }, el("span", { text: "Capacity bands" }),
      el("span", { class: "small" }, bands, " Show licensed homes by band")));
}

function sortBy(key) {
  if (state.sort === key) state.dir = state.dir === "asc" ? "desc" : "asc";
  else { state.sort = key; state.dir = key === "county" ? "asc" : "desc"; }
  setParams({ sort: state.sort, dir: state.dir });
  render();
}

function render() {
  const cols = columns();
  const sizeLabel = pulse.sizes[state.size].toLowerCase();
  const scopeLabel = pulse.scopes[state.scope].toLowerCase().replace("ccrcs", "CCRCs").replace("rcfes", "RCFEs");
  const c = compared();
  document.getElementById("subtitle").textContent = `Week of ${date(pulse.as_of)} · ${scopeLabel} · ${sizeLabel}. ` +
    (c ? `Change is versus the week of ${date(c.date)} (${c.label.toLowerCase()}).` : "No earlier file to compare yet.");

  const q = state.q.trim().toLowerCase();
  let rows = market.counties[state.scope][state.size].filter((r) => !q || place(r.county).toLowerCase().includes(q));
  const col = cols.find((x) => x.key === state.sort && !x.nosort) || cols.find((x) => x.key === "licensed_facilities");
  const sign = state.dir === "asc" ? 1 : -1;
  const small = (r) => r.licensed_facilities < market.small_base;
  rows = [...rows].sort((a, b) => {
    // On a rate column, small-base counties go after the others in either direction.
    if (col.rate && small(a) !== small(b)) return small(a) ? 1 : -1;
    const x = value(col, a), y = value(col, b);
    if (col.text) return sign * place(x).localeCompare(place(y));
    return sign * ((x ?? -Infinity) - (y ?? -Infinity)) || place(a.county).localeCompare(place(b.county));
  });

  const table = document.getElementById("county-table");
  const groupCount = (g) => cols.filter((c) => c.group === g).length;
  clear(table.tHead,
    el("tr", {},
      el("th", { scope: "col", "aria-hidden": "true" }),
      el("th", { scope: "colgroup", colspan: groupCount("activity"), class: "group",
        text: `Activity, ${date(market.window_12m_start)} to ${date(pulse.as_of)}` }),
      el("th", { scope: "colgroup", colspan: groupCount("supply"), class: "group",
        text: `Available supply, ${date(pulse.as_of)}` })),
    el("tr", {}, cols.map((c) => el("th", {
      class: [c.text ? null : "num", c.group === "supply" && c.key === "licensed_facilities" ? "group-start" : null]
        .filter(Boolean).join(" ") || null,
      scope: "col",
      "aria-sort": c.key === col.key ? (state.dir === "asc" ? "ascending" : "descending") : null,
    }, c.nosort ? c.label : el("button", { type: "button", onclick: () => sortBy(c.key), text: c.label })))));

  clear(table.tBodies[0], rows.length ? rows.map((r) => el("tr", {}, cols.map((c) => {
    if (c.key === "county") {
      const qs = new URLSearchParams({ county: r.county });
      if (state.size !== "all_sizes") qs.set("size", state.size);
      if (state.scope !== "all") qs.set("scope", state.scope);
      return el("td", { style: "white-space:nowrap" }, el("a", { href: `index.html?${qs}`, text: place(r.county) }));
    }
    return cell(c, r, small(r));
  })))
    : el("tr", {}, el("td", { colspan: cols.length, class: "muted", text: "No counties match." })));

  // Statewide row comes from pulse.json, not from adding the table up.
  const seg = pulse.segments[state.scope][state.size];
  const state_row = { ...seg.totals, county: "California",
    licensed_by_band: Object.fromEntries(market.band_totals[state.scope].map((b) => [b.band, b.licensed_facilities])) };
  clear(table.tFoot, q ? null : el("tr", {}, cols.map((c) => {
    if (c.key === "county") return el("td", { text: "All California" });
    if (state.size !== "all_sizes" && c.key.startsWith("band_")) return el("td", { class: "num", text: "—" });
    return cell(c, state_row, false);
  })));

  const d = pulse.definitions;
  clear(document.getElementById("table-notes"),
    el("p", { text: `${d.net_change_12m.label}: ${d.net_change_12m.rule}` }),
    el("p", { text: `${d.closures_12m.label}: ${d.closures_12m.rule}` }),
    el("p", { text: `Growth and churn rates divide by licensed homes in the latest file. ${d.small_base.rule} `
      + "When you sort by a rate, small-base counties are listed after the others." }));

  renderBands();
}

function cell(c, r, smallBase) {
  const v = value(c, r);
  const cls = c.group === "supply" && c.key === "licensed_facilities" ? "num group-start" : "num";
  if (c.fmt === "change") return el("td", { class: cls }, change(v, { short: true }));
  if (c.fmt === "spark") {
    return el("td", {}, sparkline(v, `Licensed homes, ${place(r.county)}: ${v.filter((x) => x != null).map(num).join(", ")}`));
  }
  const text = c.fmt === "pct" ? pct(v) : c.fmt === "pct2" ? pct(v, 2)
    : c.fmt === "signed" ? (v == null ? "—" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${num(Math.abs(v))}`) : num(v);
  return el("td", { class: cls }, text,
    c.rate && smallBase && v != null ? el("div", { class: "small muted", text: "small base" }) : null);
}

function renderBands() {
  const table = document.getElementById("band-table");
  const heads = ["Capacity band", "Licensed homes", "Licensed beds", "New licenses, 90 days", "Closures, 90 days"];
  clear(table.tHead, el("tr", {}, heads.map((h, i) => el("th", { scope: "col", class: i ? "num" : null, text: h }))));
  clear(table.tBodies[0], market.band_totals[state.scope].map((b) => el("tr", {},
    el("td", { text: b.label }),
    el("td", { class: "num", text: num(b.licensed_facilities) }),
    el("td", { class: "num", text: num(b.licensed_beds) }),
    el("td", { class: "num", text: num(b.new_licenses_90d) }),
    el("td", { class: "num", text: num(b.closures_closed_date_90d) }))));
  document.getElementById("bands-note").textContent = `${pulse.definitions.size_band.rule} ${
    pulse.scopes[state.scope]}. This table is not affected by the home size switch.`;
}
