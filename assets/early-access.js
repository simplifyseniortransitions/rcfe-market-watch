// Early-access form for the public Market Map preview (map.html).
// Sends the form to RCFE Deal Room's own endpoint (a Cloudflare Worker), which saves it to a private
// Google Sheet. Nothing here talks to Google, Mailchimp or any email platform, and nothing here holds a
// key or secret: the only setting is the endpoint address in data/map-cta.json.
// Analytics events carry the step only (opened, started, submitted, success, error), never form values.

export const ROLES = [
  "Current RCFE owner or operator",
  "Prospective RCFE buyer",
  "RCFE seller",
  "Aspiring RCFE operator",
  "Investor",
  "Industry professional or service provider",
  "Other",
];
export const FEATURES = [
  "Individual facility map",
  "City and ZIP-code searches",
  "Local competition and concentration",
  "Market trends and weekly changes",
  "Buyer research",
  "Seller research",
  "Other",
];
export const LIMITS = { name: 60, email: 254, county: 80, utm: 100 };
export const MESSAGES = {
  success: "You’re on the early-access list. We’ll contact you when the expanded RCFE market tools become available.",
  error: "We couldn’t save your request. Please try again in a moment.",
  first_name: "Enter your first name.",
  last_name: "Enter your last name.",
  email: "Enter a valid email address, like name@example.com.",
  role: "Choose the role that fits you best.",
  county: `Keep this under ${LIMITS.county} characters.`,
  consent: "Check the box to agree before joining the list.",
};
const UTM = ["utm_source", "utm_medium", "utm_campaign", "utm_content"];
const EMAIL = /^[^\s@=+\-][^\s@]{0,63}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.[A-Za-z]{2,24}$/;

const trim = (v) => String(v ?? "").replace(/\s+/g, " ").trim();

/** Endpoint from data/map-cta.json: RCFE Deal Room's https endpoint, or a local one while testing on this Mac. */
export function endpointFrom(config, pageHost = "") {
  const url = config && typeof config.endpoint === "string" ? config.endpoint : "";
  if (/^https:\/\/[a-z0-9.-]+\/submit$/.test(url)) return url;
  const local = /^(localhost|127\.0\.0\.1)$/.test(pageHost);
  if (local && /^http:\/\/(localhost|127\.0\.0\.1):\d{2,5}\/submit$/.test(url)) return url;
  return null;
}

/** Field problems, in form order. */
export function check(v) {
  const bad = [];
  const first = trim(v.first_name), last = trim(v.last_name), email = trim(v.email);
  if (!first || first.length > LIMITS.name) bad.push("first_name");
  if (!last || last.length > LIMITS.name) bad.push("last_name");
  if (!email || email.length > LIMITS.email || !EMAIL.test(email)) bad.push("email");
  if (!ROLES.includes(v.role)) bad.push("role");
  if (trim(v.county).length > LIMITS.county) bad.push("county");
  if (v.consent !== true) bad.push("consent");
  return bad;
}

/** Scheme, host and path only: query strings (which can hold private tokens) are never sent. */
export function pageOnly(value) {
  try {
    const u = new URL(String(value || ""));
    return /^https?:$/.test(u.protocol) ? `${u.origin}${u.pathname}` : "";
  } catch { return ""; }
}

/** Where the visit came from. The host page (rcfedealroom.com) supplies it when it can; otherwise this frame's own view. */
export function visitContext(host, own) {
  const utm = {};
  const fromHost = host && host.utm && typeof host.utm === "object" ? host.utm : null;
  const ownQuery = new URLSearchParams(own.search || "");
  for (const k of UTM) utm[k] = trim(fromHost ? fromHost[k] : ownQuery.get(k)).slice(0, LIMITS.utm);
  return {
    source_page: pageOnly(host && host.page) || pageOnly(own.referrer) || pageOnly(own.href),
    referrer: pageOnly(host ? host.referrer : ""),
    utm,
  };
}

/** What is sent to the endpoint. The submission ID and time are set by the server, not here. */
export function payload(v, ctx) {
  return {
    first_name: trim(v.first_name),
    last_name: trim(v.last_name),
    email: trim(v.email).toLowerCase(),
    role: v.role,
    county: trim(v.county),
    features: FEATURES.filter((f) => (v.features || []).includes(f)),
    consent: v.consent === true,
    website: v.website || "",
    source_page: ctx.source_page,
    referrer: ctx.referrer,
    utm: ctx.utm,
  };
}

// ---- page wiring ----
const $ = (id) => document.getElementById(id);

function values(form) {
  const f = form.elements;
  return {
    first_name: f.first_name.value,
    last_name: f.last_name.value,
    email: f.email.value,
    role: f.role.value,
    county: f.county.value,
    features: [...form.querySelectorAll('input[name="features"]:checked')].map((x) => x.value),
    consent: f.consent.checked,
    website: f.website.value,
  };
}

function showErrors(form, bad) {
  const names = ["first_name", "last_name", "email", "role", "county", "consent"];
  for (const name of names) {
    const input = form.elements[name], msg = $(`ea-${name}-err`);
    const on = bad.includes(name);
    input.setAttribute("aria-invalid", String(on));
    msg.textContent = on ? MESSAGES[name] : "";
    msg.hidden = !on;
  }
  const summary = $("ea-errors");
  if (!bad.length) { summary.hidden = true; summary.replaceChildren(); return; }
  const list = document.createElement("ul");
  for (const name of bad) {
    const li = document.createElement("li"), a = document.createElement("a");
    a.href = `#ea-${name}`;
    a.textContent = MESSAGES[name];
    a.addEventListener("click", (e) => { e.preventDefault(); form.elements[name].focus(); });
    li.append(a);
    list.append(li);
  }
  const p = document.createElement("p");
  p.textContent = bad.length === 1 ? "Please fix 1 item:" : `Please fix ${bad.length} items:`;
  summary.replaceChildren(p, list);
  summary.hidden = false;
  form.elements[bad[0]].focus();
}

/**
 * Wires the form. `track(action, label)` is the preview's analytics helper; `parentOrigin` is the host
 * page's origin (or null when not framed by rcfedealroom.com).
 */
export function setupEarlyAccess({ config, track, parentOrigin }) {
  const opener = $("mp-cta-btn"), panel = $("ea-panel"), form = $("ea-form"), done = $("ea-done");
  const status = $("ea-status"), submit = $("ea-submit");
  const endpoint = endpointFrom(config, location.hostname);
  if (!endpoint) {
    opener.disabled = true;
    opener.textContent = "Early-access signup opens soon";
    opener.classList.add("soon");
    return;
  }
  opener.disabled = false;

  // The host page tells this frame where the visit came from (its address and campaign tags), if it can.
  let hostContext = null;
  window.addEventListener("message", (e) => {
    if (!parentOrigin || e.origin !== parentOrigin || e.source !== window.parent) return;
    const d = e.data || {};
    if (d.type === "rcfe-map-context") hostContext = { page: d.page, referrer: d.referrer, utm: d.utm };
  });
  if (parentOrigin) window.parent.postMessage({ type: "rcfe-map-ready" }, parentOrigin);

  const open = () => {
    panel.hidden = false;
    opener.setAttribute("aria-expanded", "true");
    form.elements.first_name.focus();
    track("early_access_form_opened");
  };
  const close = () => {
    panel.hidden = true;
    opener.setAttribute("aria-expanded", "false");
    opener.focus();
  };
  opener.addEventListener("click", () => (panel.hidden ? open() : close()));
  $("ea-close").addEventListener("click", close);
  panel.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); close(); } });

  let started = false;
  form.addEventListener("input", () => { if (!started) { started = true; track("early_access_form_started"); } });

  let busy = false;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    status.textContent = "";
    const v = values(form);
    const bad = check(v);
    showErrors(form, bad);
    if (bad.length) return;
    busy = true;
    submit.disabled = true;
    submit.textContent = "Saving…";
    track("early_access_form_submitted");
    const ctx = visitContext(hostContext, { search: location.search, referrer: document.referrer, href: location.href });
    let reason = "";
    try {
      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload(v, ctx)),
        credentials: "omit",
        cache: "no-store",
        signal: AbortSignal.timeout ? AbortSignal.timeout(20000) : undefined,
      });
      const out = await r.json().catch(() => ({}));
      if (r.ok && out.ok === true) {
        form.hidden = true;
        done.hidden = false;
        done.focus();
        track("early_access_form_success");
        return;
      }
      if (r.status === 400 && Array.isArray(out.fields) && out.fields.length) {
        const known = out.fields.filter((f) => f in MESSAGES);
        if (known.length) { showErrors(form, known); reason = "invalid"; }
      }
      reason = reason || (r.status === 429 ? "busy" : "server");
    } catch {
      reason = "network";
    }
    // Same calm message whatever went wrong; no technical details on screen.
    if (reason !== "invalid") {
      status.textContent = MESSAGES.error;
    }
    track("early_access_form_error", reason);
    busy = false;
    submit.disabled = false;
    submit.textContent = "Join the Early-Access List";
  });
}
