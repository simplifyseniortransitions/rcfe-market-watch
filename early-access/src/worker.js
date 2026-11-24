// RCFE Deal Room early-access list: the public Market Map preview's form posts here, and this Worker
// writes one row to a private Google Sheet through a Google Apps Script web app.
//
// Why a Worker: the preview is a static GitHub Pages site, so it can't hold a secret. The Apps Script
// address and the shared secret live only in this Worker's encrypted secrets (wrangler secret put),
// never in the browser, the repository or GitHub Pages.
//
// What it never does: call Mailchimp or any email platform, send email, or create an account.
//
// Secrets (set with `wrangler secret put`, never in a file):
//   SHEET_WEBHOOK_URL  the Apps Script web app address (https://script.google.com/macros/s/…/exec)
//   SHEET_SECRET       shared secret; the same value is saved in the Apps Script's Script Properties
//   TURNSTILE_SECRET   optional, only if spam ever needs a Cloudflare Turnstile check (see README)

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
// The Market Map preview runs on GitHub Pages inside rcfedealroom.com, so its requests come from the
// GitHub Pages origin. RCFE Deal Room's own domains are allowed so the form can move there later.
export const ALLOWED_ORIGINS = new Set([
  "https://simplifyseniortransitions.github.io",
  "https://rcfedealroom.com",
  "https://www.rcfedealroom.com",
  "https://community.rcfedealroom.com",
  "https://rcfe-deal-room.marblism.me",
]);
// Columns of the "Early Access Leads" worksheet, in order.
export const COLUMNS = [
  "Submission ID", "Submitted At", "First Name", "Last Name", "Email", "Role", "County or Market",
  "Feature Interest", "Consent", "Source Page", "Referrer", "UTM Source", "UTM Medium", "UTM Campaign",
  "UTM Content", "Status", "Internal Notes",
];
export const LIMITS = { name: 60, email: 254, county: 80, url: 300, utm: 100, body: 8192 };
const UTM = ["utm_source", "utm_medium", "utm_campaign", "utm_content"];
const EMAIL = /^[a-z0-9_.!#$%&'*/?^`{|}~][a-z0-9_.!#$%&'*+/=?^`{|}~-]{0,63}@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.[a-z]{2,24}$/;
const SHEET_URL = /^https:\/\/script\.google\.com\/macros\/s\/[A-Za-z0-9_-]{20,}\/exec$/;
const LOCAL = /^http:\/\/(127\.0\.0\.1|localhost):\d{2,5}\//;

/** Plain single-line text: no control characters, single spaces, trimmed. */
export function clean(value) {
  if (typeof value !== "string") return "";
  // eslint-disable-next-line no-control-regex
  return value.normalize("NFC").replace(new RegExp("[\\u0000-\\u001f\\u007f-\\u009f\\u200b-\\u200f\\u2028\\u2029\\ufeff]", "g"), " ").replace(/\s+/g, " ").trim();
}

/** A spreadsheet never runs what someone typed: values that start like a formula become plain text. */
export function cell(value) {
  const v = String(value ?? "");
  return /^[=+\-@\t\r]/.test(v) ? `'${v}` : v;
}

/** Only where the visit came from (scheme, host and path); query strings and fragments are dropped. */
export function pageOnly(value) {
  const v = clean(value);
  if (!v) return "";
  try {
    const u = new URL(v);
    if (u.protocol !== "https:" && u.protocol !== "http:") return "";
    return `${u.origin}${u.pathname}`.slice(0, LIMITS.url);
  } catch { return ""; }
}

/** Checks a submission. Returns { ok, fields: [names with problems], data: normalized values }. */
export function validate(body) {
  const fields = [];
  const first = clean(body.first_name), last = clean(body.last_name);
  const email = clean(body.email).toLowerCase();
  const role = clean(body.role);
  const county = clean(body.county);
  if (!first || first.length > LIMITS.name) fields.push("first_name");
  if (!last || last.length > LIMITS.name) fields.push("last_name");
  if (!email || email.length > LIMITS.email || !EMAIL.test(email)) fields.push("email");
  if (!ROLES.includes(role)) fields.push("role");
  if (county.length > LIMITS.county) fields.push("county");
  let features = [];
  if (body.features != null) {
    if (!Array.isArray(body.features) || body.features.length > FEATURES.length) fields.push("features");
    else {
      features = [...new Set(body.features.map(clean))];
      if (features.some((f) => !FEATURES.includes(f))) fields.push("features");
    }
  }
  if (body.consent !== true) fields.push("consent");
  const utm = {};
  const given = body.utm && typeof body.utm === "object" && !Array.isArray(body.utm) ? body.utm : {};
  for (const k of UTM) {
    const v = clean(given[k]);
    if (v.length > LIMITS.utm) fields.push(k);
    utm[k] = v;
  }
  if (fields.length) return { ok: false, fields };
  // Keep the order the options are listed in, so the Sheet reads consistently.
  features = FEATURES.filter((f) => features.includes(f));
  return {
    ok: true, fields,
    data: { first, last, email, role, county, features, source: pageOnly(body.source_page), referrer: pageOnly(body.referrer), utm },
  };
}

/** The row written to the Sheet. The ID and time are made here; anything the browser sent for them is ignored. */
export function toRow(data, now = new Date(), id = crypto.randomUUID()) {
  const values = {
    "Submission ID": id,
    "Submitted At": now.toISOString(),
    "First Name": data.first,
    "Last Name": data.last,
    "Email": data.email,
    "Role": data.role,
    "County or Market": data.county,
    "Feature Interest": data.features.join("; "),
    "Consent": "Yes",
    "Source Page": data.source,
    "Referrer": data.referrer,
    "UTM Source": data.utm.utm_source,
    "UTM Medium": data.utm.utm_medium,
    "UTM Campaign": data.utm.utm_campaign,
    "UTM Content": data.utm.utm_content,
    "Status": "New",
    "Internal Notes": "",
  };
  return Object.fromEntries(COLUMNS.map((c) => [c, cell(values[c])]));
}

function allowedOrigin(origin, env) {
  if (ALLOWED_ORIGINS.has(origin)) return true;
  // Local testing only: wrangler dev --var EXTRA_ORIGINS:http://127.0.0.1:8000. Never set in production.
  return (env.EXTRA_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean).includes(origin);
}

function reply(status, body, origin) {
  const headers = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "vary": "Origin",
  };
  if (origin) {
    headers["access-control-allow-origin"] = origin;
    headers["access-control-allow-methods"] = "POST, OPTIONS";
    headers["access-control-allow-headers"] = "content-type";
    headers["access-control-max-age"] = "600";
  }
  return new Response(body == null ? null : JSON.stringify(body), { status, headers });
}
// Every failure looks the same to the public: no details about the Sheet, the script or the cause.
const FAIL = { ok: false };
const OK = { ok: true };

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function underLimit(binding, key) {
  if (!binding) return true;               // Not configured (unit tests can supply one).
  try { return (await binding.limit({ key })).success; } catch { return true; }
}

async function turnstileOk(env, token, ip) {
  if (!env.TURNSTILE_SECRET) return true;  // Off unless spam ever makes it necessary.
  if (typeof token !== "string" || !token || token.length > 2048) return false;
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET);
  form.append("response", token);
  if (ip) form.append("remoteip", ip);
  try {
    const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", { method: "POST", body: form, signal: AbortSignal.timeout(8000) });
    return r.ok && (await r.json()).success === true;
  } catch { return false; }
}

async function saveToSheet(env, row) {
  const url = env.SHEET_WEBHOOK_URL || "";
  const local = env.LOCAL_DEV === "1" && LOCAL.test(url);   // Local mock only; see dev/mock-sheet.mjs.
  if (!(SHEET_URL.test(url) || local) || !env.SHEET_SECRET) return false;
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ secret: env.SHEET_SECRET, row }),
      redirect: "follow",                  // Apps Script answers through a one-time googleusercontent address.
      signal: AbortSignal.timeout(15000),
    });
    if (!r.ok) return false;
    const out = await r.json();
    return out && out.ok === true;
  } catch { return false; }
}

export async function handle(request, env) {
  const url = new URL(request.url);
  const origin = request.headers.get("origin") || "";
  const okOrigin = allowedOrigin(origin, env);
  if (url.pathname !== "/submit") return reply(404, FAIL, null);
  if (request.method === "OPTIONS") return okOrigin ? reply(204, null, origin) : reply(403, null, null);
  if (request.method !== "POST") return reply(405, FAIL, okOrigin ? origin : null);
  if (!okOrigin) return reply(403, FAIL, null);
  const cors = origin;

  if (!(request.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) return reply(415, FAIL, cors);
  const size = Number(request.headers.get("content-length") || 0);
  if (size > LIMITS.body) return reply(413, FAIL, cors);
  let body;
  try {
    const text = await request.text();
    if (text.length > LIMITS.body) return reply(413, FAIL, cors);
    body = JSON.parse(text);
  } catch { return reply(400, FAIL, cors); }
  if (!body || typeof body !== "object" || Array.isArray(body)) return reply(400, FAIL, cors);

  // Honeypot: people never see this field; bots fill it. They get a normal-looking answer and nothing is saved.
  if (typeof body.website === "string" && body.website.trim() !== "") return reply(200, OK, cors);

  const ip = request.headers.get("cf-connecting-ip") || "";
  if (!(await underLimit(env.IP_LIMIT, `ip:${ip}`))) return reply(429, FAIL, cors);
  if (!(await turnstileOk(env, body.turnstile, ip))) return reply(400, FAIL, cors);

  const checked = validate(body);
  if (!checked.ok) return reply(400, { ok: false, fields: checked.fields }, cors);

  // The same address sent again within a minute (a double click, a second tab) is acknowledged without
  // another write. The answer is the same as a first sign-up, so it never reveals who is on the list.
  if (!(await underLimit(env.EMAIL_LIMIT, `email:${await sha256(checked.data.email)}`))) return reply(200, OK, cors);

  const saved = await saveToSheet(env, toRow(checked.data));
  if (!saved) {
    console.error("early_access_save_failed");   // No personal details in logs.
    return reply(502, FAIL, cors);
  }
  return reply(200, OK, cors);
}

export default { fetch: (request, env) => handle(request, env) };
