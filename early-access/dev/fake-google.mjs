// A small stand-in for Google Sheets and Apps Script, used by the tests and the local mock endpoint.
// It runs the real apps-script/Code.gs. Like Google Sheets, a value that starts with an apostrophe is
// stored as plain text, and a value that starts with "=" (without one) would become a formula, which
// the tests check never happens on the leads tab.
import { readFileSync } from "node:fs";
import vm from "node:vm";

const CODE = readFileSync(new URL("../apps-script/Code.gs", import.meta.url), "utf8");
const colNum = (letters) => [...letters].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0);

class Sheet {
  constructor(name) { this.name = name; this.grid = []; this.formulas = []; this.frozen = 0; }
  _set(r, c, v) {
    while (this.grid.length < r) this.grid.push([]);
    const row = this.grid[r - 1];
    let value = v;
    if (typeof v === "string" && v.startsWith("'")) value = v.slice(1);       // apostrophe: plain text
    else if (typeof v === "string" && v.startsWith("=")) this.formulas.push({ r, c, v });
    row[c - 1] = value;
  }
  _get(r, c) { return (this.grid[r - 1] || [])[c - 1] ?? ""; }
  getRange(a, b, nr = 1, nc = 1) {
    let r = a, c = b;
    if (typeof a === "string") {
      const [start, end] = a.split(":");
      const p = (s) => { const m = /^([A-Z]+)(\d+)$/.exec(s); return [Number(m[2]), colNum(m[1])]; };
      [r, c] = p(start);
      const [r2, c2] = end ? p(end) : [r, c];
      nr = r2 - r + 1; nc = c2 - c + 1;
    }
    const sheet = this;
    const range = {
      setValues(rows) {
        if (rows.length !== nr || rows.some((x) => x.length !== nc)) throw new Error("range size mismatch");
        rows.forEach((row, i) => row.forEach((v, j) => sheet._set(r + i, c + j, v)));
        return range;
      },
      setValue(v) { sheet._set(r, c, v); return range; },
      getValues() { return Array.from({ length: nr }, (_, i) => Array.from({ length: nc }, (_, j) => sheet._get(r + i, c + j))); },
      setFontWeight() { return range; },
      setDataValidation() { return range; },
      setNumberFormat() { return range; },
    };
    return range;
  }
  getLastRow() {
    for (let i = this.grid.length; i > 0; i--) if ((this.grid[i - 1] || []).some((v) => v !== "" && v != null)) return i;
    return 0;
  }
  getMaxRows() { return 1000; }
  setFrozenRows(n) { this.frozen = n; }
  rows() { return this.grid.slice(1).map((row) => Array.from({ length: 17 }, (_, i) => row[i] ?? "")); }
}

export function loadAppsScript({ secret = "test-secret", lockFails = false } = {}) {
  const sheets = new Map();
  const ss = {
    getSheetByName: (n) => sheets.get(n) || null,
    insertSheet: (n) => { const s = new Sheet(n); sheets.set(n, s); return s; },
  };
  const builder = () => {
    const b = { requireValueInList: () => b, setAllowInvalid: () => b, build: () => ({}) };
    return b;
  };
  const props = new Map(secret ? [["SHARED_SECRET", secret]] : []);
  const ctx = {
    SpreadsheetApp: { getActiveSpreadsheet: () => ss, newDataValidation: builder },
    PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => props.get(k) ?? null }) },
    LockService: { getScriptLock: () => ({ waitLock() { if (lockFails) throw new Error("busy"); }, releaseLock() {} }) },
    ContentService: { MimeType: { JSON: "json" }, createTextOutput: (s) => ({ content: s, setMimeType() { return this; } }) },
    Logger: { log() {} },
  };
  vm.createContext(ctx);
  vm.runInContext(CODE, ctx, { filename: "Code.gs" });
  const post = (body) => JSON.parse(ctx.doPost({ postData: { contents: typeof body === "string" ? body : JSON.stringify(body) } }).content);
  return { ctx, ss, sheets, post, leads: () => sheets.get("Early Access Leads") };
}
