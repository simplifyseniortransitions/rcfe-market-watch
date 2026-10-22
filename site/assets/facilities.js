import {
  asOfLine, clear, isCore, date, el, fail, facilityLink, getJSON, licenseeText, num, params, place, select, setParams,
} from "./common.js";

const PAGE = 50;
const p = params();
const state = {
  q: p.get("q") || "",
  city: p.get("city") || "",
  county: p.get("county") || "",
  status: p.get("status") || "",
  size: p.get("size") || "",
  scope: p.get("scope") || "",
  signal: p.get("signal") || "",
  min: p.get("min") || "",
  max: p.get("max") || "",
  sort: p.get("sort") || "name",
  page: Number(p.get("page") || 1),
};

let all = [], pulse;

Promise.all([getJSON("facilities.json"), getJSON("pulse.json")])
  .then(([f, pl]) => { all = f.facilities; pulse = pl; asOfLine(f); renderFilters(); render(); })
  .catch((err) => fail(document.getElementById("count"), err));

function renderFilters() {
  const set = (k) => (v) => { state[k] = v; state.page = 1; setParams({ [k]: v, page: "" }); render(); };
  const text = (k, label, attrs = {}) => el("label", { class: "control" }, el("span", { text: label }),
    el("input", { type: attrs.type || "search", value: state[k], ...attrs,
      oninput: (e) => set(k)(e.target.value.trim()) }));
  const counties = [...new Set(all.map((f) => f.county))].filter(Boolean).sort();
  const statuses = [...new Set(all.map((f) => f.status))].sort();
  clear(document.getElementById("filters"),
    text("q", "Name, licensee or facility number", { placeholder: "e.g. Sunrise or 157209529" }),
    text("city", "City", { type: "text" }),
    select("County", [["", "All counties"], ...counties.map((c) => [c, place(c)])], state.county, set("county")),
    select("Status", [["", "Any status"], ...statuses.map((s) => [s, s.charAt(0) + s.slice(1).toLowerCase()])],
      state.status, set("status")),
    select("Home size", [["", "All sizes"], ...Object.entries(pulse.sizes).filter(([k]) => k !== "all_sizes")],
      state.size, set("size")),
    el("fieldset", { class: "control" }, el("legend", { text: "Capacity (beds)" }),
      el("div", { style: "display:flex;gap:6px;align-items:center" },
        el("input", { type: "number", min: 0, value: state.min, "aria-label": "Minimum beds", placeholder: "min",
          oninput: (e) => set("min")(e.target.value) }),
        "to",
        el("input", { type: "number", min: 0, value: state.max, "aria-label": "Maximum beds", placeholder: "max",
          oninput: (e) => set("max")(e.target.value) }))),
    select("Signal", [["", "Any or none"], ...pulse.signal_rules.map((r) => [r.key, r.label])], state.signal, set("signal")),
    select("Facility type", [["", pulse.scopes.all], ["core", pulse.scopes.core], ["other", pulse.scopes.other]],
      state.scope, set("scope")),
    select("Sort by", [["name", "Name"], ["capacity", "Capacity, largest first"], ["newest", "Licensed most recently"]],
      state.sort, set("sort")));
}

function filtered() {
  const q = state.q.toLowerCase(), city = state.city.toLowerCase();
  const min = state.min === "" ? null : Number(state.min), max = state.max === "" ? null : Number(state.max);
  const rows = all.filter((f) => {
    if (q && !(f.facility_name.toLowerCase().includes(q) || (f.licensee || "").toLowerCase().includes(q)
      || f.facility_number.includes(q))) return false;
    if (city && !f.city.toLowerCase().includes(city)) return false;
    if (state.county && f.county !== state.county) return false;
    if (state.status && f.status !== state.status) return false;
    if (state.size && f.size_group !== state.size) return false;
    if (state.scope === "core" && !isCore(f.facility_type)) return false;
    if (state.scope === "other" && isCore(f.facility_type)) return false;
    if (state.signal && !f.signals.includes(state.signal)) return false;
    if (min != null && (f.capacity == null || f.capacity < min)) return false;
    if (max != null && (f.capacity == null || f.capacity > max)) return false;
    return true;
  });
  if (state.sort === "capacity") rows.sort((a, b) => (b.capacity ?? -1) - (a.capacity ?? -1));
  if (state.sort === "newest") rows.sort((a, b) => (b.license_first_date || "").localeCompare(a.license_first_date || ""));
  return rows;
}

const status = (s) => s.charAt(0) + s.slice(1).toLowerCase();

function render() {
  const rows = filtered();
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  state.page = Math.min(Math.max(1, state.page), pages);
  const shown = rows.slice((state.page - 1) * PAGE, state.page * PAGE);
  document.getElementById("count").textContent =
    `${num(rows.length)} of ${num(all.length)} facilities` + (rows.length > PAGE ? ` · page ${state.page} of ${pages}` : "");

  const table = document.getElementById("results");
  const heads = [["Facility", ""], ["Facility number", ""], ["City", ""], ["County", ""], ["Capacity", "num"],
    ["Status", ""], ["License first date", ""], ["Licensee", ""], ["Last visit", ""], ["Substantiated allegations", "num"]];
  clear(table.tHead, el("tr", {}, heads.map(([h, c]) => el("th", { scope: "col", class: c || null, text: h }))));
  clear(table.tBodies[0], shown.map((f) => el("tr", {},
    el("td", {}, facilityLink(f.facility_number, f.facility_name),
      f.signals.length ? el("div", {}, f.signals.map((s) => el("span", { class: "tag flag",
        text: pulse.signal_rules.find((r) => r.key === s).label }))) : null),
    el("td", { text: f.facility_number }),
    el("td", { text: place(f.city) }),
    el("td", { text: place(f.county) }),
    el("td", { class: "num", text: num(f.capacity) }),
    el("td", { text: status(f.status) }),
    el("td", { text: date(f.license_first_date) }),
    el("td", {}, licenseeText(f.licensee, f.licensee_withheld)),
    el("td", { text: date(f.last_visit_date) }),
    el("td", { class: "num", text: num(f.substantiated_allegations) }))));

  const go = (n) => { state.page = n; setParams({ page: n > 1 ? n : "" }); render(); window.scrollTo(0, 0); };
  clear(document.getElementById("pager"), pages > 1 ? [
    el("button", { type: "button", class: "secondary", disabled: state.page <= 1, onclick: () => go(state.page - 1), text: "Previous" }),
    el("span", { class: "small muted", text: `Page ${state.page} of ${pages}` }),
    el("button", { type: "button", class: "secondary", disabled: state.page >= pages, onclick: () => go(state.page + 1), text: "Next" }),
  ] : []);
}
