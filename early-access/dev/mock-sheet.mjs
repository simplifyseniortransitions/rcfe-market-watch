// Local stand-in for the Google Apps Script web app, for testing the form on this Mac only.
// Runs the real Code.gs against an in-memory sheet and saves the rows to dev/.mock-sheet.json (ignored by git).
//   node dev/mock-sheet.mjs [port]      (default 8790; the local Worker is pointed at http://127.0.0.1:8790/exec)
import { createServer } from "node:http";
import { writeFileSync } from "node:fs";
import { loadAppsScript } from "./fake-google.mjs";

const port = Number(process.argv[2] || 8790);
const secret = process.env.SHEET_SECRET || "local-test-secret";
const g = loadAppsScript({ secret });
g.ctx.setup();
const out = new URL("./.mock-sheet.json", import.meta.url);
const save = () => writeFileSync(out, JSON.stringify({ rows: g.leads().rows(), formulas: g.leads().formulas }, null, 1));
save();
createServer((req, res) => {
  let body = "";
  req.on("data", (c) => { body += c; });
  req.on("end", () => {
    const result = req.method === "POST" && req.url === "/exec" ? g.post(body) : { ok: false };
    if (process.env.MOCK_FAIL === "1") { res.writeHead(500); res.end("{}"); return; }
    save();
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify(result));
  });
}).listen(port, "127.0.0.1", () => console.log(`Mock sheet on http://127.0.0.1:${port}/exec`));
