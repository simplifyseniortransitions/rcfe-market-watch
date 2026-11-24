// The Google Apps Script that writes to the private Sheet (run against a stand-in Sheet).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { loadAppsScript } from "../dev/fake-google.mjs";
import { COLUMNS, toRow, validate } from "../src/worker.js";

const row = (email = "pat@example.com") => toRow(validate({ first_name: "Pat", last_name: "Lee", email, role: "Investor", consent: true }).data);

test("setup creates the leads tab with the exact columns and a Dashboard tab", () => {
  const g = loadAppsScript();
  g.ctx.setup();
  assert.deepEqual(g.leads().grid[0], COLUMNS);
  assert.equal(g.leads().frozen, 1);
  assert.ok(g.sheets.get("Dashboard"));
  g.ctx.setup();   // Running it again is harmless.
  assert.equal(g.leads().getLastRow(), 1);
});

test("rows are written only with the shared secret", () => {
  const g = loadAppsScript({ secret: "right" });
  g.ctx.setup();
  assert.deepEqual(g.post({ secret: "wrong", row: row() }), { ok: false });
  assert.deepEqual(g.post({ row: row() }), { ok: false });
  assert.deepEqual(g.post("not json"), { ok: false });
  assert.equal(g.leads().getLastRow(), 1);
  assert.deepEqual(g.post({ secret: "right", row: row() }), { ok: true });
  assert.equal(g.leads().getLastRow(), 2);
  assert.deepEqual(JSON.parse(g.ctx.doGet().content), { ok: false });
});

test("no secret configured means nothing is written", () => {
  const g = loadAppsScript({ secret: null });
  g.ctx.setup();
  assert.deepEqual(g.post({ secret: "", row: row() }), { ok: false });
  assert.equal(g.leads().getLastRow(), 1);
});

test("rows with missing, extra-long or non-text values are refused", () => {
  const g = loadAppsScript({ secret: "k" });
  g.ctx.setup();
  const r = row();
  delete r.Role;
  assert.deepEqual(g.post({ secret: "k", row: r }), { ok: false });
  assert.deepEqual(g.post({ secret: "k", row: { ...row(), Role: "x".repeat(501) } }), { ok: false });
  assert.deepEqual(g.post({ secret: "k", row: { ...row(), Role: 5 } }), { ok: false });
  assert.equal(g.leads().getLastRow(), 1);
});

test("a new row is always Status New with empty notes, whatever was sent", () => {
  const g = loadAppsScript({ secret: "k" });
  g.ctx.setup();
  g.post({ secret: "k", row: { ...row(), Status: "Qualified", "Internal Notes": "=HACK()" } });
  const saved = g.leads().rows()[0];
  assert.deepEqual([saved[15], saved[16]], ["New", ""]);
  assert.equal(g.leads().formulas.length, 0);
});

test("formula-looking values are stored as text even if they reach the script directly", () => {
  const g = loadAppsScript({ secret: "k" });
  g.ctx.setup();
  g.post({ secret: "k", row: { ...row(), "County or Market": "=1+1", "UTM Source": "@x" } });
  assert.equal(g.leads().formulas.length, 0);
  assert.equal(g.leads().rows()[0][6], "=1+1");
});

test("a busy Sheet fails cleanly", () => {
  const g = loadAppsScript({ secret: "k", lockFails: true });
  g.ctx.setup();
  assert.deepEqual(g.post({ secret: "k", row: row() }), { ok: false });
});

test("the script sends no email and calls no outside service", () => {
  const code = readFileSync(new URL("../apps-script/Code.gs", import.meta.url), "utf8");
  for (const api of ["MailApp", "GmailApp", "UrlFetchApp", "mailchi", "list-manage"]) assert.ok(!code.includes(api), api);
});
