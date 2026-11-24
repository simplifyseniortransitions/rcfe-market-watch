// The public form's own logic (site/assets/early-access.js): checks, what it sends, and its analytics.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { check, payload, visitContext, endpointFrom, ROLES, FEATURES } from "../../site/assets/early-access.js";
import * as server from "../src/worker.js";

const SITE = fileURLToPath(new URL("../../site/", import.meta.url));
const JS = readFileSync(join(SITE, "assets/early-access.js"), "utf8");
const form = (x = {}) => ({ first_name: "Pat", last_name: "Lee", email: "pat@example.com", role: "Investor", county: "", features: [], consent: true, website: "", ...x });

test("the form and the endpoint list the same roles and features", () => {
  assert.deepEqual(ROLES, server.ROLES);
  assert.deepEqual(FEATURES, server.FEATURES);
  const html = readFileSync(join(SITE, "map.html"), "utf8");
  for (const r of ROLES) assert.ok(html.includes(`<option>${r}</option>`), r);
  for (const f of FEATURES) assert.ok(html.includes(`value="${f}"`), f);
});

test("the form checks required fields and email before sending", () => {
  assert.deepEqual(check(form()), []);
  assert.deepEqual(check(form({ first_name: " ", email: "nope", role: "", consent: false })), ["first_name", "email", "role", "consent"]);
  assert.deepEqual(check(form({ county: "x".repeat(81) })), ["county"]);
});

test("what the form sends is what the endpoint accepts", () => {
  const ctx = visitContext({ page: "https://www.rcfedealroom.com/market-watch?utm_source=a&secret=1", referrer: "https://news.example/p?id=9", utm: { utm_source: "newsletter", utm_medium: "email" } },
    { search: "", referrer: "", href: "https://simplifyseniortransitions.github.io/rcfe-market-watch/map.html" });
  assert.equal(ctx.source_page, "https://www.rcfedealroom.com/market-watch");
  assert.equal(ctx.referrer, "https://news.example/p");
  assert.deepEqual(ctx.utm, { utm_source: "newsletter", utm_medium: "email", utm_campaign: "", utm_content: "" });
  const body = payload(form({ email: " Pat@Example.com ", features: ["Seller research", "Individual facility map"] }), ctx);
  assert.equal(body.email, "pat@example.com");
  assert.deepEqual(body.features, ["Individual facility map", "Seller research"]);
  assert.ok(!("submission_id" in body) && !("submitted_at" in body));
  assert.equal(server.validate(body).ok, true);
});

test("without the host page's help, the frame's own address and tags are used", () => {
  const ctx = visitContext(null, { search: "?utm_source=qr&utm_campaign=flyer", referrer: "https://www.rcfedealroom.com/", href: "https://x/map.html" });
  assert.equal(ctx.source_page, "https://www.rcfedealroom.com/");
  assert.deepEqual(ctx.utm, { utm_source: "qr", utm_medium: "", utm_campaign: "flyer", utm_content: "" });
});

test("the form only sends to RCFE Deal Room's own https endpoint", () => {
  assert.equal(endpointFrom({ endpoint: "https://rcfe-early-access.example.workers.dev/submit" }), "https://rcfe-early-access.example.workers.dev/submit");
  for (const endpoint of ["http://rcfe-early-access.example.workers.dev/submit", "https://mailchi.mp/x/y", "javascript:alert(1)", null])
    assert.equal(endpointFrom({ endpoint }), null, String(endpoint));
  assert.equal(endpointFrom({ url: "https://mailchi.mp/simplifyseniortransitions/w69iux4ks6" }), null);   // The old Mailchimp setting is ignored.
  assert.equal(endpointFrom({ endpoint: "http://127.0.0.1:8787/submit" }, "example.com"), null);
  assert.equal(endpointFrom({ endpoint: "http://127.0.0.1:8787/submit" }, "127.0.0.1"), "http://127.0.0.1:8787/submit");
});

// 14. Analytics events contain no personal information
test("analytics events carry only the step and a fixed reason, never form values", () => {
  const code = JS.split("\n").filter((l) => !/^\s*(\*|\/\/|\/\*\*)/.test(l)).join("\n");   // Code only, not comments.
  const calls = [...code.matchAll(/track\(([^)]*)\)/g)].map((m) => m[1]);
  assert.deepEqual(calls.sort(), [
    '"early_access_form_error", reason', '"early_access_form_opened"', '"early_access_form_started"',
    '"early_access_form_submitted"', '"early_access_form_success"',
  ]);
  const reasons = code.split("\n").filter((l) => /\breason = /.test(l) && !/let reason = ""/.test(l)).join(" ");
  assert.match(reasons, /"invalid"/);
  for (const r of reasons.match(/"[^"]*"/g)) assert.ok(['"invalid"', '"busy"', '"server"', '"network"'].includes(r), r);
});

// 12 and 13. No Mailchimp and no secrets anywhere in the public site
test("the public site holds no secrets and never mentions Mailchimp as a destination", () => {
  const files = [];
  const walk = (d) => readdirSync(d).forEach((n) => { const p = join(d, n); statSync(p).isDirectory() ? walk(p) : files.push(p); });
  walk(SITE);
  const patterns = [/script\.google\.com/i, /AKfyc[A-Za-z0-9_-]{10,}/, /SHEET_SECRET|SHARED_SECRET|SHEET_WEBHOOK_URL|TURNSTILE_SECRET/,
    /AIza[0-9A-Za-z_-]{20,}/, /ya29\./, /-----BEGIN [A-Z ]*PRIVATE KEY-----/, /"private_key"/, /client_secret/i, /\bcfat_|\bcfut_/,
    /mailchi\.mp|list-manage\.com|eepurl\.com|mc\.us\d+/i];
  for (const f of files) {
    if (/\.(png|jpe?g|gif|ico|woff2?)$/.test(f)) continue;
    const text = readFileSync(f, "utf8");
    for (const p of patterns) assert.ok(!p.test(text), `${p} in ${f}`);
  }
});
