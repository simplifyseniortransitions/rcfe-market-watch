// Shared helpers. Data is read only from this site's data/ folder; there are no third-party scripts.

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

export function change(n, { short = false } = {}) {
  if (n == null) return el("span", { class: "chg flat", text: short ? "—" : "no prior week" });
  const cls = n > 0 ? "up" : n < 0 ? "down" : "flat";
  const sign = n > 0 ? "+" : n < 0 ? "−" : "±";
  return el("span", { class: `chg ${cls}`, text: `${sign}${num(Math.abs(n))}${short ? "" : " vs last week"}` });
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

export function select(label, options, value, onChange, attrs = {}) {
  const s = el("select", { onchange: (e) => onChange(e.target.value), ...attrs },
    options.map(([v, text]) => el("option", { value: v, selected: v === value, text })));
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
