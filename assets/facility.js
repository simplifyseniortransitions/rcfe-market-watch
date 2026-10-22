import { asOfLine, clear, date, el, fail, getJSON, licenseeText, num, params, place } from "./common.js";

const id = params().get("id") || "";
const root = document.getElementById("facility");

Promise.all([getJSON("facilities.json"), getJSON("signals.json"), getJSON("feed.json"), getJSON("pulse.json")])
  .then(([facilities, signals, feed, pulse]) => {
    asOfLine(facilities);
    const f = facilities.facilities.find((x) => x.facility_number === id);
    if (!f) {
      document.getElementById("facility-name").textContent = "Facility not found";
      document.getElementById("facility-sub").textContent = "";
      clear(root, el("p", { text: `No facility with number ${id} is in the ${date(facilities.as_of)} state file.` }));
      return;
    }
    document.title = `${f.facility_name} | RCFE Market Watch`;
    render(f, signals, feed, pulse);
  })
  .catch((err) => fail(root, err));

const status = (s) => s.charAt(0) + s.slice(1).toLowerCase();

function render(f, signals, feed, pulse) {
  const flagged = signals.facilities.find((x) => x.facility_number === f.facility_number);
  const rules = Object.fromEntries(signals.rules.map((r) => [r.key, r]));
  const labels = Object.fromEntries(feed.event_types.map((t) => [t.key, t.label]));
  const events = feed.events.filter((e) => e.facility_number === f.facility_number);
  const size = f.size_group ? pulse.sizes[f.size_group] : "Capacity not listed";

  const facts = [
    ["Facility number", f.facility_number],
    ["Status", status(f.status)],
    ["Facility type", f.facility_type ? status(f.facility_type) : "Not listed"],
    ["City", place(f.city)],
    ["County", place(f.county)],
    ["Capacity", f.capacity == null ? "Not listed" : `${num(f.capacity)} beds (${size.toLowerCase()})`],
    ["Licensee", licenseeText(f.licensee, f.licensee_withheld)],
    ["License first date", date(f.license_first_date)],
    ["Closed date", date(f.closed_date)],
    ["Last visit date", date(f.last_visit_date)],
    ["Total visits", num(f.total_visits)],
    ["Complaint visits", num(f.complaint_visits)],
    ["Substantiated allegations (all years in the file)", num(f.substantiated_allegations)],
    ["Citations, last 12 months", num(f.citations_12m)],
  ];

  document.getElementById("facility-name").textContent = f.facility_name;
  document.getElementById("facility-sub").textContent =
    `${place(f.city)}, ${place(f.county)} County · ${status(f.status)} · record as of ${date(pulse.as_of)}`;
  clear(root,
    el("div", { class: "two-col" },
      el("section", { class: "card", "aria-labelledby": "rec-h" },
        el("h2", { id: "rec-h", text: "Licensing record" }),
        el("dl", { class: "facts" }, facts.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", {}, v)])),
        el("p", { class: "note", text: "Street address, phone number and administrator are not shown on this site." })),
      el("div", {},
        el("section", { class: "card", "aria-labelledby": "sig-h" },
          el("h2", { id: "sig-h", text: "Signals" }),
          flagged ? el("ul", { class: "rules" }, flagged.flags.map((fl) => el("li", {},
            el("div", {}, el("span", { class: "tag flag", text: rules[fl.rule].label }),
              el("div", { class: "small", text: fl.detail }),
              el("div", { class: "small muted", text: rules[fl.rule].rule })))))
            : el("p", { class: "muted", text: "No signals under the published rules." }),
          el("p", { class: "note", text: signals.disclaimer })),
        el("section", { class: "card", style: "margin-top:12px", "aria-labelledby": "chg-h" },
          el("h2", { id: "chg-h", text: `Changes, last ${feed.weeks} weeks` }),
          events.length ? el("ul", { class: "feed" }, events.map((e) => el("li", {},
            el("span", { class: "tag", text: labels[e.change_type] }),
            e.change_type === "new_facility" ? `New listing, status ${e.new}` : `${e.old ?? "—"} → ${e.new ?? "—"}`,
            el("div", { class: "small muted", text: `week of ${date(e.date)} (compared with ${date(e.prior_snapshot_id)})` }))))
            : el("p", { class: "muted", text: "No changes recorded in our weekly files." })),
        el("p", { class: "note", text: "This record is copied from the state's weekly file. If it is wrong, "
          + "only the California Department of Social Services, Community Care Licensing Division, can correct it; "
          + "the change will appear here after the next weekly file." }))));
}
