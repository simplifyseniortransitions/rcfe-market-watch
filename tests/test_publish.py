import json
import shutil
from datetime import date, timedelta

import pytest

from pipeline import config, publish
from pipeline.run import process_inbox
from tests import fixture_50
from tests.conftest import write_csv

META = {"as_of", "source", "generated_at", "snapshot_id"}
REQUIRED = {"pulse.json", "feed.json", "signals.json", "owners.json", "market.json", "facilities.json",
            "history.json", "qa-report.json"}


def load(paths, name):
    return json.loads((paths.data / name).read_text())


@pytest.fixture
def published(paths):
    fixture_50.write_pair(paths.inbox)
    runs = process_inbox(paths)
    assert [r["status"] for r in runs] == ["pass", "pass"], runs[-1]["errors"]
    return paths


def test_all_outputs_written_with_meta(published):
    names = {p.name for p in published.data.glob("*.json")}
    assert names == REQUIRED
    for name in names:
        data = load(published, name)
        assert META <= data.keys(), name
        assert data["snapshot_id"] == "2026-10-18" and data["as_of"] == "2026-10-18"
    assert not (published.data / ".staging").exists()


def test_pulse_headline_and_breakdowns(published):
    pulse = load(published, "pulse.json")
    assert pulse["headline_scope"] == "all"
    seg = pulse["segments"]
    assert seg["all"]["all_sizes"]["totals"]["licensed_facilities"] == 33
    assert seg["core"]["all_sizes"]["totals"]["licensed_facilities"] == 31  # includes blank-type n49
    assert seg["core"]["small"]["totals"]["licensed_facilities"] == 25   # n0-n24
    assert seg["core"]["large"]["totals"]["licensed_facilities"] == 5    # n25-n29
    assert seg["all"]["large"]["totals"]["licensed_facilities"] == 7     # + 2 CCRCs
    assert seg["core"]["small"]["totals"]["licensed_beds"] == 140
    assert seg["all"]["all_sizes"]["activity"]["closures_status_changed"] == 1
    assert len(pulse["recent_events"]) == 9
    assert "size_group" in pulse["definitions"] and "scope" in pulse["definitions"]


def test_market_bands_and_counties(published):
    market = load(published, "market.json")
    bands = {b["band"]: b["licensed_facilities"] for b in market["band_totals"]["all"]}
    assert bands == {"6_or_fewer": 25, "7_15": 5, "16_49": 0, "50_99": 0, "100_plus": 2}
    la = next(c for c in market["counties"]["all"]["all_sizes"] if c["county"] == "LOS ANGELES")
    assert la["licensed_facilities"] == 12 and la["licensed_by_band"]["100_plus"] == 2
    la_small = next(c for c in market["counties"]["all"]["small"] if c["county"] == "LOS ANGELES")
    assert la_small["licensed_facilities"] == 10
    sac = next(c for c in market["counties"]["all"]["all_sizes"] if c["county"] == "SACRAMENTO")
    assert sac["signals"]["on_probation"] == 2 and la["signals"]["on_probation"] == 0


def test_owners_signals_facilities(published):
    owners = load(published, "owners.json")["owners"]
    assert [o["licensee"] for o in owners] == ["BIG CHAIN LLC", "BCRG INC."]
    assert owners[0]["licensed_homes_small"] == 4
    sig = load(published, "signals.json")
    assert sig["counts"]["all_sizes"]["on_probation"] == 2
    assert all(r["flags"] for r in sig["facilities"])
    facilities = load(published, "facilities.json")["facilities"]
    assert len(facilities) == 50
    n0 = next(f for f in facilities if f["facility_number"] == "400000000")
    assert n0["size_group"] == "small" and n0["signals"] == ["recent_status_change"]


def test_no_private_data_in_any_output(published):
    for p in published.data.glob("*.json"):
        text = p.read_text()
        for col in config.PRIVATE_COLUMNS:
            assert col not in text, f"{col} in {p.name}"
        for value in ("ADMIN PERSON", "555-0100", "TEST ST"):
            assert value not in text, f"{value} in {p.name}"
        assert '"administrator' not in text.lower() and "telephone" not in text.lower()


def test_history_has_every_week_and_matches_the_current_numbers(published):
    h = load(published, "history.json")
    assert h["weeks"] == ["2026-10-11", "2026-10-18"]
    assert h["chart_min_weeks"] == 4
    assert [o["key"] for o in h["compare_options"]] == ["1", "4", "13", "52", "first"]
    assert set(h["series"]) == {f"{s}|{z}" for s in ("all", "core") for z in ("all_sizes", "small", "large")}
    ca = h["series"]["all|all_sizes"]["California"]
    seg = load(published, "pulse.json")["segments"]["all"]["all_sizes"]
    assert ca["licensed_facilities"][-1] == seg["totals"]["licensed_facilities"] == 33
    assert ca["licensed_facilities"][-1] - ca["licensed_facilities"][0] == seg["week_over_week"]["licensed_facilities"]
    # The first week has nothing to compare with; the second holds that week's changes.
    assert ca["new_facility_numbers"] == [None, 1] and ca["closures_status_changed"] == [None, 1]
    # County records match the Market table for the same scope and size.
    row = next(r for r in load(published, "market.json")["counties"]["core"]["small"] if r["county"] == "LOS ANGELES")
    assert h["series"]["core|small"]["LOS ANGELES"]["licensed_facilities"][-1] == row["licensed_facilities"]


def test_history_over_four_weeks(published):
    snap = published.snapshots
    for days in (14, 21):
        shutil.copy2(snap / "2026-10-11.csv", snap / f"{(date(2026, 10, 18) - timedelta(days=days)).isoformat()}.csv")
    publish.publish(published, "2026-10-21T00:00:00+00:00")
    h = load(published, "history.json")
    assert h["weeks"] == ["2026-09-27", "2026-10-04", "2026-10-11", "2026-10-18"]
    ca = h["series"]["all|all_sizes"]["California"]
    assert ca["licensed_facilities"][-1] == 33
    # Three identical weekly files: no changes between them, then the real changes into Oct 18.
    assert ca["new_facility_numbers"] == [None, 0, 0, 1]
    assert sum(ca["new_facility_numbers"][1:]) == 1
    assert h["series"]["all|small"]["California"]["licensed_facilities"][-1] == 25


def test_failed_validation_keeps_last_good_site(published):
    before = {p.name: p.read_bytes() for p in published.data.glob("*.json") if p.name != "qa-report.json"}
    rows = fixture_50.current_rows()
    rows[0]["Closed Date"] = "2026-10-25"
    write_csv(published.inbox / "ResidentialElderCareFacility10252026.csv", rows)
    assert process_inbox(published)[0]["status"] == "fail"
    after = {p.name: p.read_bytes() for p in published.data.glob("*.json") if p.name != "qa-report.json"}
    assert before == after
    qa = load(published, "qa-report.json")
    assert qa["status"] == "fail" and qa["last_good_snapshot_id"] == "2026-10-18"


def test_publish_error_keeps_last_good_site(published, monkeypatch):
    before = (published.data / "pulse.json").read_bytes()

    def boom(*a, **k):
        raise ValueError("simulated")
    monkeypatch.setattr(publish, "build", boom)
    write_csv(published.inbox / "ResidentialElderCareFacility10252026.csv", fixture_50.current_rows())
    run = process_inbox(published)[0]
    assert run["status"] == "fail" and "publish failed" in run["errors"][0]
    assert (published.data / "pulse.json").read_bytes() == before
    assert (published.inbox / "ResidentialElderCareFacility10252026.csv").exists()  # retried next run


def test_licensee_names_matching_administrators_are_withheld(paths):
    # Dale, 2026-10-21: withhold a licensee name that is also an administrator's name.
    from pipeline.normalize import WITHHELD
    prior, current = fixture_50.prior_rows(), fixture_50.current_rows()
    by_n = lambda rows, i: next(r for r in rows if r["Facility Number"] == f"{400000000 + i:09d}")  # noqa: E731
    # n5 and n6 (BIG CHAIN LLC homes) become a sole proprietor who also runs n8.
    for rows in (prior, current):
        for i in (5, 6, 10, 11):
            by_n(rows, i)["Licensee"] = "PAT SAMPLE"
        by_n(rows, 8)["Facility Administrator"] = "Pat  Sample"
    # n17 changes hands to a person who administers n9, only in the prior week.
    by_n(prior, 9)["Facility Administrator"] = "LEE OWNER"
    by_n(current, 17)["Licensee"] = "LEE OWNER"
    # The same person written last-name-first as licensee of n23, first-name-first as administrator of n24.
    by_n(current, 23)["Licensee"] = "RIVERA, MORGAN"
    by_n(current, 24)["Facility Administrator"] = "Morgan Rivera"
    # A home listed under its administrator's own name (n2, run by LEE OWNER in the prior week).
    by_n(current, 2)["Facility Name"] = "Owner, Lee"
    # An administrator who is not a licensee anywhere must never appear either.
    by_n(current, 3)["Facility Administrator"] = "ONLY ADMIN NAME"
    write_csv(paths.inbox / "ResidentialElderCareFacility10112026.csv", prior)
    write_csv(paths.inbox / "ResidentialElderCareFacility10182026.csv", current)
    assert [r["status"] for r in process_inbox(paths)] == ["pass", "pass"]

    for p in paths.data.glob("*.json"):
        text = p.read_text().upper()
        for name in ("PAT SAMPLE", "LEE OWNER", "ONLY ADMIN NAME", "RIVERA", "MORGAN"):
            assert name not in text, f"{name} in {p.name}"
    facilities = {f["facility_number"]: f for f in load(paths, "facilities.json")["facilities"]}
    assert facilities["400000005"]["licensee"] == WITHHELD and facilities["400000005"]["licensee_withheld"]
    assert facilities["400000012"]["licensee_withheld"] is False
    assert facilities["400000023"]["licensee"] == WITHHELD
    assert facilities["400000002"]["facility_name"] == "Name withheld (individual)"
    assert facilities["400000003"]["facility_name"] == "HOME 3"
    owners = load(paths, "owners.json")["owners"]
    assert owners[0]["licensee"] == WITHHELD and owners[0]["licensed_homes"] == 4 and owners[0]["name_variants"] == []
    change = next(e for e in load(paths, "feed.json")["events"] if e["change_type"] == "licensee_change")
    assert (change["old"], change["new"]) == ("OLD OWNER LLC", WITHHELD)
