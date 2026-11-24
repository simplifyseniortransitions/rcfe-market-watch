// Early-access endpoint: validation, abuse controls, the Sheet hand-off and what the public sees.
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { handle, validate, toRow, cell, COLUMNS, ROLES, FEATURES } from "../src/worker.js";
import { loadAppsScript } from "../dev/fake-google.mjs";

const SHEET = "https://script.google.com/macros/s/AKfycbTESTdeploymentIDxxxxxxxxxxxxxxxx/exec";
const ORIGIN = "https://simplifyseniortransitions.github.io";
const SECRET = "s3cret-value-for-tests-only";
let calls, sheetReply, env, realFetch;

const limiter = (max) => { const seen = new Map(); return { limit: async ({ key }) => { const n = (seen.get(key) || 0) + 1; seen.set(key, n); return { success: n <= max }; } }; };
const good = (extra = {}) => ({
  first_name: "  Pat ", last_name: "Lee", email: "  Pat.Lee@Example.COM ", role: "Prospective RCFE buyer",
  county: " Sacramento County ", features: ["Buyer research", "Individual facility map"], consent: true, website: "",
  source_page: "https://www.rcfedealroom.com/market-watch?utm_source=news&token=abc#x", referrer: "https://www.google.com/search?q=rcfe",
  utm: { utm_source: "newsletter", utm_medium: "email", utm_campaign: "map-launch", utm_content: "button" }, ...extra,
});
const post = (body, { origin = ORIGIN, ip = "203.0.113.9", type = "application/json" } = {}) => handle(new Request("https://rcfe-early-access.example.workers.dev/submit", {
  method: "POST", headers: { "content-type": type, origin, "cf-connecting-ip": ip }, body: typeof body === "string" ? body : JSON.stringify(body),
}), env);

beforeEach(() => {
  calls = [];
  sheetReply = async () => new Response(JSON.stringify({ ok: true }), { status: 200 });
  env = { SHEET_WEBHOOK_URL: SHEET, SHEET_SECRET: SECRET, IP_LIMIT: limiter(5), EMAIL_LIMIT: limiter(1) };
  realFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => { calls.push({ url: String(url), init }); return sheetReply(url, init); };
});
afterEach(() => { globalThis.fetch = realFetch; });

// 8. Successful server-side submission
test("a valid sign-up is saved once, with a server-made ID and time", async () => {
  const r = await post(good({ submission_id: "client-id", submitted_at: "1999-01-01" }));
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { ok: true });
  assert.equal(r.headers.get("access-control-allow-origin"), ORIGIN);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, SHEET);
  const sent = JSON.parse(calls[0].init.body);
  assert.equal(sent.secret, SECRET);
  assert.deepEqual(Object.keys(sent.row), COLUMNS);
  const row = sent.row;
  assert.match(row["Submission ID"], /^[0-9a-f-]{36}$/);
  assert.notEqual(row["Submission ID"], "client-id");
  assert.ok(Math.abs(Date.parse(row["Submitted At"]) - Date.now()) < 5000);
  assert.equal(row["First Name"], "Pat");
  assert.equal(row.Email, "pat.lee@example.com");
  assert.equal(row["County or Market"], "Sacramento County");
  assert.equal(row["Feature Interest"], "Individual facility map; Buyer research");
  assert.equal(row.Consent, "Yes");
  assert.equal(row.Status, "New");
  assert.equal(row["Internal Notes"], "");
});

// 1. Required-field validation
test("missing required fields are refused and nothing is saved", async () => {
  for (const [field, value] of [["first_name", ""], ["last_name", "   "], ["email", ""], ["role", ""], ["consent", false]]) {
    const r = await post(good({ [field]: value }), { ip: `198.51.100.${field.length}` });
    assert.equal(r.status, 400, field);
    assert.deepEqual(await r.json(), { ok: false, fields: [field] });
  }
  assert.equal(calls.length, 0);
  assert.deepEqual(validate(good({ consent: "true" })).fields, ["consent"]);
});

test("field lengths are capped", () => {
  assert.deepEqual(validate(good({ first_name: "x".repeat(61) })).fields, ["first_name"]);
  assert.deepEqual(validate(good({ county: "x".repeat(81) })).fields, ["county"]);
  assert.deepEqual(validate(good({ utm: { utm_source: "x".repeat(101) } })).fields, ["utm_source"]);
  assert.equal(validate(good({ first_name: "x".repeat(60) })).ok, true);
});

test("oversized or malformed requests are refused", async () => {
  assert.equal((await post("x".repeat(9000))).status, 413);
  assert.equal((await post("{not json")).status, 400);
  assert.equal((await post("[1,2]")).status, 400);
  assert.equal((await post(good(), { type: "text/plain" })).status, 415);
  assert.equal(calls.length, 0);
});

// 2. Invalid-email rejection
test("invalid email addresses are refused", () => {
  for (const email of ["pat", "pat@", "@example.com", "pat@example", "pat lee@example.com", "pat@exa mple.com", "=cmd@example.com",
    "+1@example.com", "-x@example.com", "pat@@example.com", `${"a".repeat(65)}@example.com`, "pat@example.c"]) {
    assert.deepEqual(validate(good({ email })).fields, ["email"], email);
  }
  for (const email of ["pat@example.com", "pat.lee+map@sub.example.org", "o'neil@example.co"]) assert.equal(validate(good({ email })).ok, true, email);
});

// 3. Allowed role and feature values
test("only the listed roles and features are accepted", () => {
  for (const role of ROLES) assert.equal(validate(good({ role })).ok, true, role);
  assert.deepEqual(validate(good({ role: "Admin" })).fields, ["role"]);
  assert.deepEqual(validate(good({ role: "investor" })).fields, ["role"]);
  assert.equal(validate(good({ features: FEATURES })).ok, true);
  assert.equal(validate(good({ features: [] })).ok, true);
  assert.equal(validate(good({ features: undefined })).ok, true);
  assert.deepEqual(validate(good({ features: ["Buyer research", "Free money"] })).fields, ["features"]);
  assert.deepEqual(validate(good({ features: "Buyer research" })).fields, ["features"]);
  assert.deepEqual(validate(good({ features: Array(8).fill("Other") })).fields, ["features"]);
});

// 4. Honeypot rejection
test("a filled honeypot gets a normal-looking answer and nothing is saved", async () => {
  const r = await post(good({ website: "http://spam.example" }));
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { ok: true });
  assert.equal(calls.length, 0);
});

// 5. Rate limiting
test("too many requests from one address are slowed down", async () => {
  const codes = [];
  for (let i = 0; i < 7; i++) codes.push((await post(good({ email: `p${i}@example.com` }))).status);
  assert.deepEqual(codes, [200, 200, 200, 200, 200, 429, 429]);
  assert.equal(calls.length, 5);
});

test("the same email sent again within a minute is acknowledged without a second write", async () => {
  const a = await post(good(), { ip: "192.0.2.1" });
  const b = await post(good({ email: "PAT.LEE@example.com" }), { ip: "192.0.2.2" });
  assert.deepEqual([a.status, b.status], [200, 200]);
  assert.deepEqual(await b.json(), { ok: true });
  assert.equal(calls.length, 1);
});

test("disallowed origins are refused before anything else", async () => {
  for (const origin of ["https://evil.example.com", "https://rcfedealroom.com.evil.com", "http://www.rcfedealroom.com", "null", ""]) {
    const r = await post(good(), { origin });
    assert.equal(r.status, 403, origin);
    assert.equal(r.headers.get("access-control-allow-origin"), null);
  }
  const pre = await handle(new Request("https://x.workers.dev/submit", { method: "OPTIONS", headers: { origin: "https://www.rcfedealroom.com" } }), env);
  assert.equal(pre.status, 204);
  assert.equal(pre.headers.get("access-control-allow-origin"), "https://www.rcfedealroom.com");
  assert.equal((await handle(new Request("https://x.workers.dev/submit", { method: "OPTIONS", headers: { origin: "https://evil.example" } }), env)).status, 403);
  assert.equal((await handle(new Request("https://x.workers.dev/other", { method: "POST" }), env)).status, 404);
  assert.equal((await handle(new Request("https://x.workers.dev/submit", { method: "GET", headers: { origin: ORIGIN } }), env)).status, 405);
  assert.equal(calls.length, 0);
});

// 6. Formula-injection protection
test("values that look like spreadsheet formulas are stored as plain text", async () => {
  assert.equal(cell("=HYPERLINK(\"http://x\")"), "'=HYPERLINK(\"http://x\")");
  for (const v of ["+1", "-2", "@SUM(A1)", "\tx", "\rx"]) assert.ok(cell(v).startsWith("'"), JSON.stringify(v));
  assert.equal(cell("Sacramento"), "Sacramento");
  const g = loadAppsScript({ secret: SECRET });
  g.ctx.setup();
  sheetReply = async (_u, init) => new Response(JSON.stringify(g.post(init.body)));
  const r = await post(good({ first_name: "=IMPORTXML(\"http://x\")", last_name: "@Lee", county: "+cmd", utm: { utm_source: "-1+1", utm_campaign: "=1" } }));
  assert.equal(r.status, 200);
  const row = g.leads().rows()[0];
  assert.equal(row[2], "=IMPORTXML(\"http://x\")");   // Shown as typed, stored as text.
  assert.equal(g.leads().formulas.length, 0);          // No formula was created on the leads tab.
});

// 7. Source and UTM capture
test("source page, referrer and campaign tags are saved, without query strings", () => {
  const row = toRow(validate(good()).data);
  assert.equal(row["Source Page"], "https://www.rcfedealroom.com/market-watch");
  assert.equal(row.Referrer, "https://www.google.com/search");
  assert.deepEqual([row["UTM Source"], row["UTM Medium"], row["UTM Campaign"], row["UTM Content"]], ["newsletter", "email", "map-launch", "button"]);
  const none = toRow(validate(good({ source_page: "javascript:alert(1)", referrer: "not a url", utm: null })).data);
  assert.deepEqual([none["Source Page"], none.Referrer, none["UTM Source"]], ["", "", ""]);
});

// 9. Google integration failure, 10. Generic public error responses
test("a Sheet failure returns a plain failure with no details", async () => {
  const failures = [
    async () => new Response("Exception: Service Spreadsheets failed at Code.gs:42", { status: 500 }),
    async () => new Response(JSON.stringify({ ok: false }), { status: 200 }),
    async () => new Response("<html>Sign in</html>", { status: 200 }),
    async () => { throw new Error("connect ECONNREFUSED script.google.com"); },
  ];
  for (const [i, f] of failures.entries()) {
    sheetReply = f;
    const r = await post(good({ email: `fail${i}@example.com` }), { ip: `192.0.2.${10 + i}` });
    assert.equal(r.status, 502);
    const text = await r.text();
    assert.equal(text, JSON.stringify({ ok: false }));
  }
});

test("no configured Sheet means a plain failure, and the secret is never echoed", async () => {
  env.SHEET_WEBHOOK_URL = "";
  let r = await post(good());
  assert.equal(r.status, 502);
  assert.equal(calls.length, 0);
  env.SHEET_WEBHOOK_URL = "https://evil.example.com/macros/s/x/exec";
  r = await post(good({ email: "b@example.com" }), { ip: "192.0.2.99" });
  assert.equal(r.status, 502);
  assert.equal(calls.length, 0);
  // Local mock addresses are honored only with LOCAL_DEV=1 (never set in production).
  env.SHEET_WEBHOOK_URL = "http://127.0.0.1:8790/exec";
  r = await post(good({ email: "c@example.com" }), { ip: "192.0.2.98" });
  assert.equal(r.status, 502);
  assert.equal(calls.length, 0);
  for (const body of [good({ first_name: "" }), "{bad"]) {
    const text = await (await post(body, { ip: "192.0.2.97" })).text();
    assert.ok(!text.includes(SECRET) && !text.includes("script.google") && !/stack|error:|exception/i.test(text), text);
  }
});

// 11. Duplicate-email behavior
test("a repeat sign-up updates the same row and keeps its ID, first date, status and notes", async () => {
  const g = loadAppsScript({ secret: SECRET });
  g.ctx.setup();
  sheetReply = async (_u, init) => new Response(JSON.stringify(g.post(init.body)));
  await post(good(), { ip: "192.0.2.50" });
  await post(good({ email: "other@example.com" }), { ip: "192.0.2.51" });
  const first = [...g.leads().rows()[0]];
  // Dale works the lead in the Sheet.
  g.leads()._set(2, 16, "Contacted");
  g.leads()._set(2, 17, "Called 11/25");
  env.EMAIL_LIMIT = limiter(1);   // A minute later.
  const r = await post(good({ email: "PAT.LEE@EXAMPLE.COM", first_name: "Patricia", role: "Investor", county: "Placer", features: ["Seller research"],
    utm: { utm_source: "podcast" } }), { ip: "192.0.2.52" });
  assert.deepEqual(await r.json(), { ok: true });      // Same answer as a first sign-up.
  const rows = g.leads().rows();
  assert.equal(rows.length, 2);
  const row = rows[0];
  assert.deepEqual(row.slice(0, 5), first.slice(0, 5));  // ID, first date, name and email unchanged.
  assert.deepEqual([row[5], row[6], row[7], row[11], row[12]], ["Investor", "Placer", "Seller research", "podcast", ""]);
  assert.deepEqual([row[15], row[16]], ["Contacted", "Called 11/25"]);
});

// 12. Mailchimp is never called
test("the endpoint only ever contacts the Google Apps Script address", async () => {
  await post(good());
  await post(good({ email: "x@example.com" }), { ip: "192.0.2.60" });
  assert.ok(calls.length > 0 && calls.every((c) => c.url === SHEET));
  const src = readFileSync(new URL("../src/worker.js", import.meta.url), "utf8").toLowerCase();
  for (const word of ["mailchimp", "mailchi.mp", "list-manage", "eepurl", "sendgrid", "mailgun", "resend.com", "postmark"]) {
    assert.ok(!src.replace("call mailchimp", "").includes(word), word);
  }
});

test("Turnstile can be switched on later without code changes", async () => {
  env.TURNSTILE_SECRET = "ts";
  sheetReply = async (url) => (String(url).includes("turnstile") ? new Response(JSON.stringify({ success: false })) : new Response(JSON.stringify({ ok: true })));
  assert.equal((await post(good())).status, 400);
  assert.equal(calls.filter((c) => c.url === SHEET).length, 0);
});
