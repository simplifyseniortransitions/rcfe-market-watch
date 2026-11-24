"""California RCFE Weekly Movers. Numbers in brackets are the spec's test items (1-36)."""
import json
import re
import threading
import urllib.request
from datetime import date, datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from pipeline import config, notify
from pipeline.movers import compare as cmp
from pipeline.movers import config as C
from pipeline.movers import outputs
from pipeline.movers.report import build, counts, included, public_artifact
from pipeline.movers.run import make_draft, notice_line
from pipeline.movers.store import ReviewError, Store
from tests.conftest import HEADER, make_row, write_csv

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 24, 1, 0, tzinfo=timezone.utc)
CITIES = [("SACRAMENTO", "SACRAMENTO"), ("ELK GROVE", "SACRAMENTO"), ("FRESNO", "FRESNO")]
D1, D2, D3 = "2026-11-08", "2026-11-15", "2026-11-22"


def row(i, **kw):
    city, county = CITIES[i % 3]
    base = {"Facility City": city, "County Name": county, "Facility Address": f"{100 + i} OAK STREET",
            "Facility Zip": "95814", "License First Date": "3/4/2015"}
    base.update(kw)
    return make_row(i, **base)


def week(n=30, changes=None):
    """n licensed homes; `changes` maps index -> overrides, or None to drop the row."""
    rows, changes = [], changes or {}
    for i in range(n):
        if i in changes and changes[i] is None:
            continue
        rows.append(row(i, **(changes.get(i) or {})))
    return rows


def save(paths, day, rows, header=HEADER):
    paths.snapshots.mkdir(parents=True, exist_ok=True)
    write_csv(paths.snapshots / f"{day}.csv", rows, header)


def qa(paths, *days):
    paths.data.mkdir(parents=True, exist_ok=True)
    runs = [{"as_of": d, "status": "pass", "generated_at": f"{d}T23:30:00+00:00"} for d in days]
    paths.qa_report.write_text(json.dumps({"runs": runs}))


def draft(paths, as_of=None):
    q = json.loads(paths.qa_report.read_text()) if paths.qa_report.exists() else {}
    return build(paths.snapshots, q, as_of=date.fromisoformat(as_of) if as_of else None, now=NOW)


def kinds(report, kind):
    return [f for f in report["findings"] if f["change_type"] == kind]


@pytest.fixture
def two_weeks(paths):
    """A normal week: 2 pending→licensed, 1 licensed→closed, 2 capacity changes, a rename, a status change."""
    save(paths, D1, week(34, {30: {"Facility Status": "PENDING"}, 31: {"Facility Status": "PENDING"},
                                32: {"Facility Status": "CLOSED"}, 33: {"Facility Status": "CLOSED"}}))
    save(paths, D2, week(34, {
        30: {"License First Date": "11/12/2026"}, 31: {"License First Date": "11/13/2026"},
        32: {"Facility Status": "CLOSED"}, 33: {"Facility Status": "CLOSED"},
        5: {"Facility Status": "CLOSED", "Closed Date": "11/12/2026"},
        7: {"Facility Capacity": "8"}, 8: {"Facility Capacity": "4"},
        9: {"Facility Name": "RIVER OAKS CARE"}, 10: {"Facility Status": "ON PROBATION"},
        11: {"Facility Address": "111 OAK ST"}}))   # wording only: not a change
    qa(paths, D1, D2)
    return paths


# ---------------------------------------------------------------------------------------------- selection
def test_current_and_previous_snapshot_selection(paths):  # [1]
    for d in (D1, D2, D3):
        save(paths, d, week(10))
    cur, prev, problems = cmp.select(paths.snapshots)
    assert (cur[0].isoformat(), prev[0].isoformat(), problems) == (D3, D2, [])
    cur, prev, _ = cmp.select(paths.snapshots, date(2026, 11, 15))
    assert (cur[0].isoformat(), prev[0].isoformat()) == (D2, D1)
    # A rejected file is never a baseline.
    (paths.snapshots / "rejected").mkdir()
    write_csv(paths.snapshots / "rejected" / "2026-11-21_x.csv", week(3))
    assert cmp.select(paths.snapshots)[1][0].isoformat() == D2


def test_missing_snapshot_holds_the_report_and_never_skips_silently(paths):  # [2]
    save(paths, D1, week(10))
    save(paths, D3, week(10))   # Nov 15 missing
    r = draft(paths)
    assert r["state"] == C.HELD and r["comparison_days"] == 14
    assert any("missing" in h for h in r["held_reasons"])
    only = Path(paths.snapshots / D1).with_suffix(".csv")
    (paths.snapshots / f"{D3}.csv").unlink()
    r = draft(paths)
    assert r["state"] == C.HELD and r["statewide"] is None and only.exists()
    with pytest.raises(ValueError):
        draft(paths, "2026-11-29")


def test_incomplete_snapshot_is_held(paths):  # [3]
    save(paths, D1, week(100))
    save(paths, D2, week(60))
    r = draft(paths)
    assert r["state"] == C.HELD and any("rows" in h for h in r["held_reasons"])


# ---------------------------------------------------------------------------------------------- matching
def test_facility_matching_and_address_wording(two_weeks):  # [4] [7]
    r = draft(two_weeks)
    assert all(f["match_confidence"] == "high" for f in kinds(r, "capacity_increase") + kinds(r, "name_change"))
    # "OAK STREET" -> "OAK ST" standardizes to the same address: no finding.
    assert not kinds(r, "address_change")


def test_rename_detection(two_weeks):  # [5]
    names = kinds(draft(two_weeks), "name_change")
    assert [(f["facility_number"], f["previous"], f["current"]) for f in names] == \
           [("300000009", "TEST HOME 9", "RIVER OAKS CARE")]


def test_possible_rename_or_relicensing_at_same_address_is_never_merged(paths):  # [5] [6]
    save(paths, D1, week(10))
    save(paths, D2, week(11, {3: {"Facility Status": "CLOSED", "Closed Date": "11/13/2026"},
                                10: {"Facility Address": "103 OAK STREET", "Facility City": "SACRAMENTO",
                                     "County Name": "SACRAMENTO", "Facility Name": "NEW NAME CARE"}}))
    r = draft(paths)
    pair = kinds(r, "possible_relicensing")
    assert len(pair) == 1 and pair[0]["match_confidence"] == "probable" and pair[0]["held"]
    assert pair[0]["previous"]["facility_number"] == "300000003" and pair[0]["current"]["facility_number"] == "300000010"
    # Both records still counted: one newly observed, one no longer active.
    assert r["statewide"]["newly_observed"] == 1 and r["statewide"]["no_longer_active"] == 1
    assert all("possible_relicensing" in f["flags"] for f in kinds(r, "newly_observed") + kinds(r, "no_longer_active"))


def test_duplicate_detection(paths):  # [6]
    save(paths, D1, week(10))
    save(paths, D2, week(10, {4: {"Facility Address": "101 OAK STREET", "Facility City": "ELK GROVE",
                                    "County Name": "SACRAMENTO"}}))
    dupes = kinds(draft(paths), "possible_duplicate")
    assert len(dupes) == 1 and {x["facility_number"] for x in dupes[0]["current"]} == {"300000001", "300000004"}
    assert dupes[0]["held"] and dupes[0]["match_basis"] == "same street address"


def test_address_change_is_review_only(paths):  # [7]
    save(paths, D1, week(10))
    save(paths, D2, week(10, {2: {"Facility Address": "900 PINE AVENUE"}}))
    r = draft(paths)
    (f,) = kinds(r, "address_change")
    assert f["public"] is False and "PINE" in f["private"]["current"]
    art = public_artifact(r)
    assert "address_change" not in art["facility_changes"] and "PINE" not in json.dumps(art)


def test_city_and_county_normalization(paths):  # [8]
    save(paths, D1, week(9, {0: {"Facility City": "SACRAMNETO"}, 3: {"Facility City": "Sacramento,"}}))
    save(paths, D2, week(9))
    r = draft(paths)
    assert not kinds(r, "city_change")                # a known typo and a stray comma are not changes
    snap = cmp.load(date(2026, 11, 8), paths.snapshots / f"{D1}.csv")
    assert snap.records["300000000"].city == "SACRAMENTO"
    save(paths, D3, week(9, {1: {"Facility City": "SACRAMENTO"}, 4: {"County Name": "Placer"}}))
    r = draft(paths)
    (city,) = kinds(r, "city_change")
    assert city["previous"] == "ELK GROVE" and "city_changed_same_address" in city["flags"]
    (county,) = kinds(r, "county_change")
    assert county["current"] == "PLACER" and "county_changed_same_address" in county["flags"]


# ---------------------------------------------------------------------------------------------- changes
def test_newly_observed_records(two_weeks):  # [9]
    new = sorted(kinds(draft(two_weeks), "newly_observed"), key=lambda f: f["facility_number"])
    assert [f["facility_number"] for f in new] == ["300000030", "300000031"]
    assert new[0]["status_origin"] == "PENDING to LICENSED" and not new[0]["flags"] and not new[0]["held"]


def test_older_license_and_first_time_records_are_held(paths):  # [9]
    save(paths, D1, week(10))
    save(paths, D2, week(12, {10: {"License First Date": "1/3/2001"}, 11: {"License First Date": "11/12/2026"}}))
    by = {f["facility_number"]: f for f in kinds(draft(paths), "newly_observed")}
    assert set(by["300000010"]["flags"]) == {"first_time_in_file", "older_license"} and by["300000010"]["held"]
    assert by["300000011"]["flags"] == ["first_time_in_file"]


def test_reappeared_record(paths):  # [9]
    save(paths, D1, week(10))
    save(paths, D2, week(10, {6: None}))
    save(paths, D3, week(10))
    (f,) = kinds(draft(paths), "newly_observed")
    assert "reappeared" in f["flags"] and f["first_observed"] == D1 and f["last_observed"] == D3


def test_records_no_longer_active(two_weeks, paths):  # [10]
    gone = kinds(draft(two_weeks), "no_longer_active")
    assert [(f["facility_number"], f["status_origin"]) for f in gone] == [("300000005", "LICENSED to CLOSED")]
    assert gone[0]["closed_date"] == "2026-11-12" and not gone[0]["flags"]


def test_missing_from_file_and_late_closure(paths):  # [10]
    save(paths, D1, week(10))
    save(paths, D2, week(10, {1: None, 2: {"Facility Status": "CLOSED", "Closed Date": "2/9/2026"}}))
    by = {f["facility_number"]: f for f in kinds(draft(paths), "no_longer_active")}
    assert by["300000001"]["flags"] == ["missing_from_file"] and by["300000002"]["flags"] == ["late_closure"]


def test_capacity_increases_and_decreases(two_weeks):  # [11] [12]
    r = draft(two_weeks)
    (up,), (down,) = kinds(r, "capacity_increase"), kinds(r, "capacity_decrease")
    assert (up["previous"], up["current"], up["change"]) == (6, 8, 2)
    assert (down["previous"], down["current"], down["change"]) == (6, 4, -2)
    assert r["statewide"]["capacity_increases"] == 1 and r["statewide"]["capacity_decreases"] == 1


def test_large_capacity_change_is_held(paths):  # [11] [18]
    save(paths, D1, week(5, {0: {"Facility Capacity": "100"}, 1: {"Facility Capacity": "20"}}))
    save(paths, D2, week(5, {0: {"Facility Capacity": "160"}, 1: {"Facility Capacity": "8"}}))
    r = draft(paths)
    assert all(f["held"] and f["flags"] == ["large_capacity_change"]
               for f in kinds(r, "capacity_increase") + kinds(r, "capacity_decrease"))


def test_status_changes(two_weeks):  # [13]
    (f,) = kinds(draft(two_weeks), "status_change")
    assert (f["previous"], f["current"]) == ("LICENSED", "ON PROBATION")


# ---------------------------------------------------------------------------------------------- aggregates
def test_city_aggregation(two_weeks):  # [14]
    r = draft(two_weeks)
    by = {c["area"]: c for c in r["cities"]}
    # 30 (Sacramento) and 31 (Elk Grove) newly observed; 5 (Fresno) no longer active (-6 beds) and
    # 8 (Fresno) went from 6 to 4 beds.
    assert by["SACRAMENTO"]["count_change"] == 1 and by["ELK GROVE"]["count_change"] == 1
    assert by["FRESNO"]["count_change"] == -1 and by["FRESNO"]["capacity_change"] == -8
    assert by["FRESNO"]["record_count"] == 2
    assert by["SACRAMENTO"]["record_count"] == len(by["SACRAMENTO"]["finding_ids"])
    assert r["movers"]["city"]["count_decreases"] == ["city:FRESNO"]


def test_county_aggregation(two_weeks):  # [15]
    by = {c["area"]: c for c in draft(two_weeks)["counties"]}
    assert by["SACRAMENTO"]["count_change"] == 2 and by["FRESNO"]["count_change"] == -1
    assert by["SACRAMENTO"]["previous_count"] == 20 and by["SACRAMENTO"]["current_count"] == 22


def test_statewide_totals(two_weeks):  # [16]
    s = draft(two_weeks)["statewide"]
    assert (s["previous_active"], s["current_active"], s["net_active_change"]) == (30, 31, 1)
    assert (s["newly_observed"], s["no_longer_active"]) == (2, 1)
    assert (s["previous_capacity"], s["current_capacity"], s["net_capacity_change"]) == (180, 186, 6)
    assert s["counties_with_count_change"] == 2 and s["cities_with_count_change"] == 3


def test_percentage_changes():  # [17]
    assert cmp.pct(200, 3) == 1.5 and cmp.pct(10, -1) == -10.0
    assert cmp.pct(9, 1) is None and cmp.pct(0, 2) is None and cmp.pct(None, 1) is None


# ---------------------------------------------------------------------------------------------- anomalies
def test_thresholds_live_in_one_config_with_reasons_and_use_history():  # [18]
    for name, t in C.THRESHOLDS.items():
        assert t["floor"] > 0 and t["why"]
    assert cmp.threshold("statewide_net_active", [1] * 5) == (40, "starting floor")
    assert cmp.threshold("statewide_net_active", [20] * 12) == (80, "baseline")
    assert cmp.threshold("statewide_net_active", [2] * 12) == (40, "baseline")


def test_large_statewide_change_holds_the_report(paths):  # [18]
    save(paths, D1, week(100, {i: {"Facility Status": "PENDING"} for i in range(45)}))
    save(paths, D2, week(100))
    r = draft(paths)
    assert r["state"] == C.HELD and any("Net change" in h for h in r["held_reasons"])


def test_large_area_change_holds_only_that_row(paths):  # [18]
    save(paths, D1, week(60, {i: {"Facility Status": "PENDING"} for i in range(0, 60, 3)}))
    save(paths, D2, week(60))
    r = draft(paths)
    sac = next(c for c in r["cities"] if c["area"] == "SACRAMENTO")
    assert sac["held"] and sac["flags"] == ["large_area_change"]
    assert not included(sac, {}) and included(sac, {sac["id"]: "include"})


def test_large_source_file_change(paths):  # [19]
    save(paths, D1, week(100))
    save(paths, D2, week(104))
    r = draft(paths)
    check = next(c for c in r["checks"] if c["code"] == "source_row_count")
    assert not check["passed"] and r["state"] == C.HELD


def test_source_schema_change(paths):  # [20]
    save(paths, D1, week(10))
    save(paths, D2, week(10), HEADER + ["New Column"])
    r = draft(paths)
    assert r["state"] == C.HELD and any("New Column" in h for h in r["held_reasons"])


def test_held_report_behavior(paths):  # [21]
    save(paths, D1, week(10))
    save(paths, D2, week(10), HEADER + ["New Column"])
    store = Store(paths.root / "movers")
    run = make_draft(store, paths, now=NOW)
    assert run["outcome"] == C.HELD and notice_line(store, "success") == "Weekly Movers: held for review"
    assert not (store.root / "approved").exists()
    # A held report can still be approved after a person reviews it.
    store.approve(run["report_id"], "Reviewer", True, now=NOW)
    assert store.load(run["report_id"])["state"] == C.APPROVED


# ---------------------------------------------------------------------------------------------- review states
@pytest.fixture
def store(two_weeks):
    s = Store(two_weeks.root / "movers")
    make_draft(s, two_weeks, now=NOW)
    return s


RID = "wm-2026-11-15-r1"


def test_draft_by_default(store):  # [22]
    assert store.load(RID)["state"] == C.DRAFT
    assert json.loads((store.root / "last-run.json").read_text())["outcome"] == "draft"
    assert notice_line(store, "success") == "Weekly Movers: draft created"


def test_approval_needs_a_reviewer_and_an_acknowledgment(store):  # [23]
    with pytest.raises(ReviewError):
        store.approve(RID, "", True)
    with pytest.raises(ReviewError):
        store.approve(RID, "Reviewer", False)
    with pytest.raises(ReviewError):
        store.approve(RID, "Reviewer", "yes")
    assert store.load(RID)["state"] == C.DRAFT
    store.approve(RID, "Reviewer", True, "Looks right", now=NOW)
    r = store.load(RID)
    assert r["state"] == C.APPROVED and r["approved_by"] == "Reviewer"
    with pytest.raises(ReviewError):
        store.approve(RID, "Reviewer", True)        # never twice
    with pytest.raises(ReviewError):
        store.set_decision(RID, r["findings"][0]["id"], "exclude", "Reviewer")   # frozen once approved


def test_weekly_job_has_no_way_to_approve():  # [23] [29]
    src = (ROOT / "pipeline" / "movers" / "run.py").read_text()
    assert ".approve(" not in src and "public_artifact" not in src
    wf = (ROOT / ".github" / "workflows" / "weekly.yml").read_text()
    step = wf[wf.index("- name: Weekly Movers draft"):]
    step = step[:step.index("\n      - name:", 1)]
    assert "pipeline.movers.run draft" in step and "approve" not in step
    assert "site/" not in step and "gh-pages" not in step and "mapbuild" not in step and "r2" not in step


def test_rejection(store):  # [24]
    store.reject(RID, "Reviewer", "Wrong file", now=NOW)
    assert store.load(RID)["state"] == C.REJECTED
    with pytest.raises(ReviewError):
        store.approve(RID, "Reviewer", True)
    assert not (store.root / "approved" / "2026-11-15").exists()


def test_supersession(store, two_weeks):  # [25] [34]
    store.approve(RID, "Reviewer", True, now=NOW)
    first = store.root / "approved" / "2026-11-15" / RID / "report.json"
    before = first.read_bytes()
    with pytest.raises(ReviewError):
        store.create_correction(RID, draft(two_weeks, "2026-11-08") if False else {**draft(two_weeks),
                                "current": {"snapshot_id": "2026-11-08"}}, "Reviewer")
    new = store.create_correction(RID, draft(two_weeks), "Reviewer", now=NOW)
    assert new["report_id"] == "wm-2026-11-15-r2" and new["state"] == C.DRAFT and new["supersedes"] == RID
    assert store.load(RID)["state"] == C.APPROVED          # the old one stays until the correction is approved
    with pytest.raises(ReviewError):
        store.create_correction(RID, draft(two_weeks), "Reviewer")   # only one waiting correction
    store.approve(new["report_id"], "Reviewer", True, now=NOW)
    old = store.load(RID)
    assert old["state"] == C.SUPERSEDED and old["superseded_by"] == "wm-2026-11-15-r2"
    assert first.read_bytes() == before                    # approved files are never rewritten
    marker = json.loads((first.parent / "superseded-by.json").read_text())
    assert marker["superseded_by"] == "wm-2026-11-15-r2"
    index = json.loads((store.root / "approved" / "index.json").read_text())
    assert index["current_report_id"] == "wm-2026-11-15-r2"
    assert {i["status"] for i in index["reports"]} == {"approved", "superseded"}


def test_excluding_questionable_findings_keeps_source_data(store):  # [26]
    r = store.load(RID)
    target = next(f for f in r["findings"] if f["change_type"] == "capacity_increase")
    store.set_decision(RID, target["id"], "exclude", "Reviewer", now=NOW)
    r = store.load(RID)
    assert any(f["id"] == target["id"] for f in r["findings"])       # still in the review copy
    art = public_artifact(r)
    assert target["id"] not in json.dumps(art["facility_changes"])
    assert counts(r)["excluded_by_reviewer"] == 1
    with pytest.raises(ReviewError):
        store.set_decision(RID, "nope:1", "exclude", "Reviewer")


def test_audit_history(store):  # [27]
    r = store.load(RID)
    store.set_decision(RID, r["findings"][0]["id"], "exclude", "Reviewer", now=NOW)
    store.add_note(RID, "Checked with CDSS search", "Reviewer", now=NOW)
    store.approve(RID, "Reviewer", True, "ok", now=NOW)
    log = store.log()
    assert [e["action"] for e in log] == ["created", "exclude_item", "note", "approved"]
    a = log[-1]
    for key in ("user", "at", "report_id", "current_snapshot_id", "previous_snapshot_id", "previous_state",
                "new_state", "included_findings", "excluded_or_held_findings", "acknowledged_reviewed", "note"):
        assert key in a
    assert (a["previous_state"], a["new_state"], a["acknowledged_reviewed"]) == ("draft", "approved", True)
    assert (a["current_snapshot_id"], a["previous_snapshot_id"]) == ("2026-11-15", "2026-11-08")


def test_public_artifacts_exclude_private_notes_and_addresses(store):  # [28]
    store.add_note(RID, "SECRET-NOTE-123", "Reviewer", now=NOW)
    store.approve(RID, "Reviewer", True, "SECRET-DECISION-NOTE", now=NOW)
    folder = store.root / "approved" / "2026-11-15" / RID
    blob = "".join(p.read_text() for p in folder.rglob("*") if p.is_file())
    blob += (store.root / "approved" / "index.json").read_text()
    for secret in ("SECRET-NOTE-123", "SECRET-DECISION-NOTE", "OAK ST", "ADMIN PERSON", "555-0100", "private"):
        assert secret not in blob
    art = json.loads((folder / "report.json").read_text())
    for key in ("report_id", "status", "current_source_date", "previous_source_date", "processing_date",
                "approval_date", "source_name", "methodology_version", "statewide", "city_movers", "county_movers",
                "facility_changes", "counts", "disclaimer", "last_updated"):
        assert key in art
    assert art["status"] == "approved"


def test_withheld_facility_names_stay_withheld(paths):  # [28]
    save(paths, D1, week(6, {5: {"Facility Status": "PENDING"}}))
    save(paths, D2, week(6, {5: {"Facility Name": "Morgan Rivera", "Facility Administrator": "RIVERA, MORGAN"}}))
    (f,) = kinds(draft(paths), "newly_observed")
    assert f["facility_name"] == "Name withheld (individual)"


def test_no_automatic_publication(store):  # [29]
    assert not (store.root / "approved").exists()
    wf = (ROOT / ".github" / "workflows" / "weekly.yml").read_text()
    step = wf[wf.index("- name: Weekly Movers draft"):]
    step = step[:step.index("\n      - name:", 1)]
    assert "--store private-data/movers" in step and "cd private-data" in step
    # Only approved reports ever reach the public folder (publication is a separate, approved-only step).
    for f in (ROOT / "site" / "data" / "weekly-movers").glob("reports/*.json"):
        assert json.loads(f.read_text())["status"] == "approved"


# ---------------------------------------------------------------------------------------------- isolation
def test_runs_last_and_cannot_stop_market_watch_or_the_map():  # [30] [31]
    wf = (ROOT / ".github" / "workflows" / "weekly.yml").read_text()
    order = [wf.index(f"- name: {n}") for n in ("Publish the site", "Members' map file", "Public map preview",
                                                 "Weekly Movers draft", "Summary")]
    assert order == sorted(order)
    step = wf[wf.index("- name: Weekly Movers draft"):]
    step = step[:step.index("\n      - name:", 1)]
    assert "continue-on-error: true" in step and "steps.tests.outcome == 'success'" in step
    assert "MOVERS_OUTCOME: ${{ steps.movers.outcome }}" in wf


def test_forced_failure_leaves_market_watch_and_map_untouched(paths):  # [30] [31]
    save(paths, D1, week(10))
    (paths.snapshots / f"{D2}.csv").write_text("not,a\nreal")         # broken in a way validation would catch
    site = paths.data
    site.mkdir(parents=True)
    (site / "pulse.json").write_text('{"ok": 1}')
    mapbuild = paths.mapbuild / "map"
    mapbuild.mkdir(parents=True)
    (mapbuild / "current.json").write_text('{"key": "x"}')
    store = Store(paths.root / "movers")
    run = make_draft(store, paths, now=NOW)
    assert run["outcome"] in ("failed", "held")
    assert (site / "pulse.json").read_text() == '{"ok": 1}' and (mapbuild / "current.json").read_text() == '{"key": "x"}'
    # And a crash inside the builder is caught and recorded, never raised.
    store2 = Store(paths.root / "movers2")
    run = make_draft(store2, config.Paths(paths.root / "nowhere"), now=NOW)
    assert run["outcome"] == "failed" and notice_line(store2, "success") == "Weekly Movers: did not generate"
    assert list((store2.root / "runs").glob("*.json"))


def test_weekly_notice_line():  # [30]
    pulse = {"as_of": "2026-11-22", "prior_snapshot_id": "2026-11-15", "headline_scope": "all", "segments": {"all": {
        "all_sizes": {"totals": {"licensed_facilities": 1, "licensed_beds": 2, "pending": 3, "on_probation": 4},
                      "week_over_week": {"licensed_facilities": 0, "licensed_beds": 0, "pending": 0, "on_probation": 0},
                      "activity": {}}}}}
    text = notify.weekly_notice("new", True, "main", pulse, movers="Weekly Movers: held for review")
    assert text.rstrip().endswith("Weekly Movers: held for review")
    assert "Weekly Movers" not in notify.weekly_notice("new", True, "main", pulse)
    assert notify.movers_line("") == "" and notify.movers_line("skipped") == ""
    assert notify.movers_line("failure", "/nonexistent") == "Weekly Movers: did not generate"


# ---------------------------------------------------------------------------------------------- outputs
def test_news_brief_uses_only_approved_values(store):  # [32]
    r = store.load(RID)
    cap = next(f for f in r["findings"] if f["change_type"] == "capacity_increase")
    store.set_decision(RID, cap["id"], "exclude", "Reviewer")
    store.approve(RID, "Reviewer", True, now=NOW)
    folder = store.root / "approved" / "2026-11-15" / RID
    brief = (folder / "news-brief.md").read_text()
    art = json.loads((folder / "report.json").read_text())
    assert "TEST HOME 7" not in brief            # the excluded capacity change never reaches the brief
    assert f"{art['statewide']['current_active']:,}" in brief
    for n in range(1, 13):
        assert f"## {n}." in brief
    assert "DRAFT" not in brief.split("## 1.")[0]


def test_required_disclaimer_everywhere(store):  # [33]
    store.approve(RID, "Reviewer", True, now=NOW)
    folder = store.root / "approved" / "2026-11-15" / RID
    for name in ("news-brief.md", "teleprompter-draft.md"):
        assert C.SPOKEN_DISCLAIMER in (folder / name).read_text()
    assert C.DISCLAIMER in (folder / "report.md").read_text()
    assert json.loads((folder / "report.json").read_text())["disclaimer"] == C.DISCLAIMER
    assert outputs.DRAFT_BANNER in (folder / "teleprompter-draft.md").read_text()
    assert outputs.DRAFT_BANNER in (folder / "social-drafts.md").read_text()
    assert "Source and disclaimer" in (folder / "cards" / "source-and-disclaimer.svg").read_text()


def test_safe_terminology_in_every_output(store):  # [33]
    store.approve(RID, "Reviewer", True, now=NOW)
    folder = store.root / "approved" / "2026-11-15" / RID
    for p in folder.rglob("*"):
        if p.is_file():
            text = p.read_text().lower()
            text = text.replace(C.DISCLAIMER.lower(), "")
            for word in C.FORBIDDEN_WORDS:
                assert not re.search(rf"\b{re.escape(word)}\b", text), (p.name, word)


def test_historical_archive_and_methodology_versions(store, two_weeks):  # [34] [35]
    store.approve(RID, "Reviewer", True, now=NOW)
    save(two_weeks, D3, week(34, {30: {"License First Date": "11/12/2026"}, 31: {"License First Date": "11/13/2026"},
                                     32: {"Facility Status": "CLOSED"}, 33: {"Facility Status": "CLOSED"},
                                     5: {"Facility Status": "CLOSED"}}))
    qa(two_weeks, D1, D2, D3)
    later = draft(two_weeks)
    later["methodology_version"] = "2.0"
    store.create_draft(later, now=NOW)
    store.approve(later["report_id"], "Reviewer", True, now=NOW)
    index = json.loads((store.root / "approved" / "index.json").read_text())
    assert [i["source_date"] for i in index["reports"]] == ["2026-11-22", "2026-11-15"]
    assert (store.root / "approved" / "2026-11-22" / "wm-2026-11-22-r1" / "report.json").exists()
    assert index["methodology_note"] and "different methodology versions" in index["methodology_note"]
    assert json.loads((store.root / "approved" / "2026-11-15" / RID / "report.json").read_text())[
        "methodology_version"] == C.METHODOLOGY_VERSION
    with pytest.raises(ReviewError):
        store.create_draft(later)                       # never overwritten


def test_retry_never_replaces_a_report(store, two_weeks):  # [34]
    run = make_draft(store, two_weeks, now=NOW)
    assert run["outcome"] == "exists" and len(store.list()) == 1


def test_methodology_version_is_recorded(two_weeks):  # [35]
    r = draft(two_weeks)
    assert r["methodology_version"] == C.METHODOLOGY_VERSION and public_artifact(r)["methodology_version"] == "1.0"


def test_identical_inputs_give_identical_output(two_weeks, tmp_path):  # [36]
    a, b = Store(tmp_path / "a"), Store(tmp_path / "b")
    make_draft(a, two_weeks, now=NOW)
    make_draft(b, two_weeks, now=NOW)
    for rel in ("drafts/wm-2026-11-15-r1/report.json", "drafts/wm-2026-11-15-r1/preview/news-brief.md",
                "drafts/wm-2026-11-15-r1/preview/cards/top-county-movers.svg"):
        assert (a.root / rel).read_bytes() == (b.root / rel).read_bytes()


def test_source_dates_and_processing_dates(two_weeks):
    r = draft(two_weeks)
    assert r["current"]["source_date"] == D2 and r["previous"]["source_date"] == D1
    assert r["current"]["processing_date"] == f"{D2}T23:30:00+00:00"
    assert r["comparison_period"] == f"{D1} to {D2}" and r["comparison_days"] == 7


# ---------------------------------------------------------------------------------------------- review screen
@pytest.fixture
def server(store):
    import movers_review
    app = movers_review.App(store, token="k" * 30, public_dir=store.root.parent / "public")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), movers_review.make_handler(app))
    httpd.testing = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", app
    httpd.shutdown()


def call(url, body=None, key=None, origin=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json"})
    if key:
        req.add_header("X-Review-Key", key)
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_review_screen_requires_its_key_and_origin(server, store):  # [23]
    base, app = server
    assert call(f"{base}/api/report/{RID}/approve", {"acknowledged": True})[0] == 403
    assert call(f"{base}/api/report/{RID}/approve", {"acknowledged": True}, key="wrong")[0] == 403
    assert call(f"{base}/api/report/{RID}/approve", {"acknowledged": True}, key=app.token,
                origin="https://evil.example")[0] == 403
    assert call(f"{base}/api/report/{RID}/approve", {"acknowledged": False}, key=app.token)[0] == 409
    assert store.load(RID)["state"] == C.DRAFT
    status, body = call(f"{base}/api/report/{RID}/approve", {"acknowledged": True}, key=app.token)
    assert status == 200 and store.load(RID)["state"] == C.APPROVED


def test_review_screen_shows_the_report(server):
    base, app = server
    status, page = call(f"{base}/")
    assert status == 200 and app.token.encode() in page and b"noindex" in page
    status, body = call(f"{base}/api/report/{RID}")
    view = json.loads(body)
    assert view["report"]["report_id"] == RID and "brief" in view["texts"] and view["cards"]
    assert call(f"{base}/api/report/..%2Fx")[0] == 404
