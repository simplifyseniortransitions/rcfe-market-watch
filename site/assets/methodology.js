import { asOfLine, clear, date, el, fail, getJSON, num } from "./common.js";

const root = document.getElementById("method");

Promise.all([getJSON("pulse.json"), getJSON("feed.json"), getJSON("signals.json"), getJSON("qa-report.json")])
  .then(([pulse, feed, signals, qa]) => { asOfLine(pulse); render(pulse, feed, signals, qa); })
  .catch((err) => fail(root, err));

const ruleTable = (rows) => el("div", { class: "table-wrap" }, el("table", {},
  el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Measure" }), el("th", { scope: "col", text: "Rule" }))),
  el("tbody", {}, rows.map(([label, rule]) => el("tr", {}, el("td", { text: label }), el("td", { text: rule }))))));

function render(pulse, feed, signals, qa) {
  const run = qa.latest_run || {};
  const defs = pulse.definitions;
  const scopeKeys = ["scope", "size_group", "size_band", "licensee_withheld", "week_over_week"];
  const metricRows = Object.entries(defs).filter(([k]) => !scopeKeys.includes(k)).map(([, d]) => [d.label, d.rule]);

  clear(root,
    el("h2", { text: "Source" }),
    el("p", { text: `${pulse.source}. We read the state's file each week, save an unchanged copy, and compute everything from that copy. The current numbers come from the file dated ${date(pulse.as_of)}; week-over-week changes compare it with the file dated ${date(pulse.prior_snapshot_id)}.` }),
    el("p", { text: "Every saved weekly file is kept, so any number on this site can be recounted from the file it came from." }),

    el("h2", { text: "Checks before anything is published" }),
    el("p", { text: "A weekly file is rejected, and the previous week's site stays up, if any of these is true:" }),
    el("ul", {},
      el("li", { text: "A required column is missing." }),
      el("li", { text: "A facility number appears twice, or is blank." }),
      el("li", { text: "A License First Date, Closed Date or Last Visit Date is not a real month/day/year date (blank is allowed)." }),
      el("li", { text: "The file has more than 10% fewer rows than the last accepted week." })),
    el("p", { class: "small muted", text: `Latest check: ${run.status === "pass" ? "passed" : "did not pass"} for the file dated ${date(run.as_of)}, ${num(run.row_count)} rows.` }),

    el("h2", { text: "Which facilities are counted" }),
    ruleTable(scopeKeys.filter((k) => defs[k]).map((k) => [defs[k].label, defs[k].rule])),

    el("h2", { class: "section", text: "Measures" }),
    el("p", { text: "Day windows include both end dates. For example, 90 days for a file dated October 18 runs from July 20 through October 18." }),
    ruleTable(metricRows),

    el("h2", { class: "section", text: "Weekly changes" }),
    el("p", { text: `Each week we compare every facility number with the previous week's file and record one change for each of these. Changes are kept for ${feed.weeks} weeks. Administrator changes are never shown.` }),
    ruleTable(feed.event_types.map((t) => [t.label, t.rule])),

    el("h2", { class: "section", text: "Signals" }),
    el("p", { text: "Each signal is a single published rule. Signals are shown separately; there is no combined score." }),
    ruleTable(signals.rules.map((r) => [r.label, r.rule])),
    el("p", { class: "callout", text: signals.disclaimer }),

    el("h2", { class: "section", text: "Privacy" }),
    el("p", { text: "The state file includes each facility's administrator, phone number and street address. None of these are published anywhere on this site or in its data files. A licensee name or facility name that is also an administrator's name is shown as withheld." }),

    el("h2", { text: "What this site does not do" }),
    el("ul", {},
      el("li", { text: "No AI-written commentary, estimates, valuations or prices." }),
      el("li", { text: "No ads, sponsors, tracking or analytics." })),
    el("h2", { text: "Errors in a record" }),
    el("p", { text: "This site does not change the state's records. If a facility's record is wrong, only the California Department of Social Services, Community Care Licensing Division, can correct it. The correction appears here after the next weekly file." }));
}
