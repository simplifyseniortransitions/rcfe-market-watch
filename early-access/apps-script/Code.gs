/**
 * RCFE Deal Room - Market Tools Early Access (Google Apps Script, bound to the private Sheet).
 *
 * Receives one early-access sign-up at a time from the RCFE Deal Room Cloudflare Worker and writes it
 * to the "Early Access Leads" worksheet. Only the Worker knows the shared secret, so nobody else can
 * add rows. Deploying this as a web app does not make the Sheet public: the Sheet's own sharing
 * setting stays "Restricted".
 *
 * It never sends email, never calls Mailchimp or any other service, and never creates an account.
 *
 * One-time setup (see README.md in the early-access folder):
 *   1. Project Settings → Script Properties → add SHARED_SECRET (the value the Worker uses).
 *   2. Run setup() once and allow access to this spreadsheet.
 *   3. Deploy → New deployment → Web app → Execute as: Me, Who has access: Anyone.
 */

var SHEET_NAME = "Early Access Leads";
var DASHBOARD_NAME = "Dashboard";
var HEADERS = [
  "Submission ID", "Submitted At", "First Name", "Last Name", "Email", "Role", "County or Market",
  "Feature Interest", "Consent", "Source Page", "Referrer", "UTM Source", "UTM Medium", "UTM Campaign",
  "UTM Content", "Status", "Internal Notes",
];
var STATUSES = ["New", "Contacted", "Qualified", "Not a fit", "Archived"];
// A repeat sign-up refreshes these (columns 6–15, side by side). The ID, first date, name, email,
// Status and Internal Notes are never changed.
var UPDATE_FROM = 6, UPDATE_TO = 15;
var EMAIL_COL = 5;
var MAX_CELL = 500;

function setup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME, 0);
  sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight("bold");
  sh.setFrozenRows(1);
  var rule = SpreadsheetApp.newDataValidation().requireValueInList(STATUSES, true).setAllowInvalid(false).build();
  sh.getRange(2, 16, sh.getMaxRows() - 1, 1).setDataValidation(rule);
  setupDashboard_(ss);
  if (!PropertiesService.getScriptProperties().getProperty("SHARED_SECRET")) {
    Logger.log("Setup done. Next: add the SHARED_SECRET script property (Project Settings → Script Properties).");
  } else {
    Logger.log("Setup done. The shared secret is in place.");
  }
}

/** Optional summary tab for later review. Formulas only; it reads the leads tab and writes nothing back. */
function setupDashboard_(ss) {
  if (ss.getSheetByName(DASHBOARD_NAME)) return;
  var d = ss.insertSheet(DASHBOARD_NAME);
  var L = "'" + SHEET_NAME + "'!";
  var group = function (col, label) {
    return "=IFERROR(QUERY(" + L + "A2:Q, \"select " + col + ", count(A) where A is not null group by " + col +
      " order by count(A) desc label " + col + " '" + label + "', count(A) 'Leads'\", 0), \"No leads yet\")";
  };
  d.getRange("A1:B3").setValues([
    ["RCFE Deal Room - Market Tools Early Access", ""],
    ["Total submissions", "=COUNTA(" + L + "A2:A)"],
    ["New submissions", "=COUNTIF(" + L + "P2:P, \"New\")"],
  ]);
  d.getRange("A1").setFontWeight("bold");
  d.getRange("A5").setValue(group("F", "Role"));
  d.getRange("D5").setValue(group("G", "County or Market"));
  d.getRange("G5").setValue(group("L", "UTM Source"));
  d.getRange("J5").setValue(group("P", "Status"));
  var features = ["Individual facility map", "City and ZIP-code searches", "Local competition and concentration",
    "Market trends and weekly changes", "Buyer research", "Seller research", "Other"];
  d.getRange("M5:N5").setValues([["Feature interest", "Leads"]]);
  d.getRange(6, 13, features.length, 2).setValues(features.map(function (f, i) {
    return [f, "=COUNTIF(" + L + "H2:H, \"*" + f + "*\")"];
  }));
}

function doGet() {
  return json_({ ok: false });
}

function doPost(e) {
  var body;
  try { body = JSON.parse(e && e.postData && e.postData.contents); } catch (err) { return json_({ ok: false }); }
  var secret = PropertiesService.getScriptProperties().getProperty("SHARED_SECRET");
  if (!body || !secret || typeof body.secret !== "string" || !same_(body.secret, secret)) return json_({ ok: false });
  var row = body.row;
  if (!row || typeof row !== "object") return json_({ ok: false });
  var values = [];
  for (var i = 0; i < HEADERS.length; i++) {
    var v = row[HEADERS[i]];
    if (typeof v !== "string" || v.length > MAX_CELL) return json_({ ok: false });
    values.push(cell_(v));
  }
  var email = String(row["Email"]).trim().toLowerCase();
  if (!email) return json_({ ok: false });

  var lock = LockService.getScriptLock();
  try { lock.waitLock(20000); } catch (err) { return json_({ ok: false }); }
  try {
    var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
    if (!sh) return json_({ ok: false });
    var last = sh.getLastRow();
    var found = 0;
    if (last >= 2) {
      var emails = sh.getRange(2, EMAIL_COL, last - 1, 1).getValues();
      for (var r = emails.length - 1; r >= 0; r--) {
        if (String(emails[r][0]).trim().toLowerCase() === email) { found = r + 2; break; }
      }
    }
    if (found) {
      sh.getRange(found, UPDATE_FROM, 1, UPDATE_TO - UPDATE_FROM + 1).setValues([values.slice(UPDATE_FROM - 1, UPDATE_TO)]);
      return json_({ ok: true });
    }
    values[15] = "New";
    values[16] = "";
    sh.getRange(last + 1, 1, 1, HEADERS.length).setValues([values]);
    return json_({ ok: true });
  } finally {
    lock.releaseLock();
  }
}

/** Formula-looking text is stored as plain text (the Worker already does this; this is a second check). */
function cell_(v) {
  return /^[=+\-@\t\r]/.test(v) ? "'" + v : v;
}

function same_(a, b) {
  if (a.length !== b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
