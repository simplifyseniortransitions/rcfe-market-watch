"""Members' map file (pipeline/mapdata.py). No network: the geocode cache is written by hand."""
import json
import re
from pathlib import Path

import pytest

from pipeline import geocode, mapdata
from pipeline.address import from_row
from pipeline.normalize import NAME_WITHHELD, WITHHELD
from tests.conftest import make_row, write_csv

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def built(paths):
    paths.snapshots.mkdir(parents=True)
    # Last week: an administrator named Morgan Rivera. This week that person is a licensee (withheld).
    write_csv(paths.snapshots / "2026-11-08.csv", [make_row(1, **{"Facility Administrator": "MORGAN RIVERA"})])
    rows = [
        make_row(1, **{"Facility Address": "1 Sample Road"}),
        make_row(2, **{"Facility Address": "2 Sample Rd", "Licensee": "Rivera, Morgan", "County Name": "NAPA"}),
        make_row(3, **{"Facility Address": "3 Sample Rd", "Facility Status": "CLOSED"}),
        make_row(4, **{"Facility Address": "4 Sample Rd", "Facility Status": "PENDING", "Facility Capacity": "60"}),
        make_row(5, **{"Facility Address": "", "Facility Status": "PENDING"}),
        make_row(6, **{"Facility Address": "6 Sample Rd", "Facility Name": "MORGAN RIVERA"}),
    ]
    for r in rows:
        r["Facility Zip"] = "95814"
    write_csv(paths.snapshots / "2026-11-15.csv", rows)
    cache = {}
    place = {1: ("38.5", "-121.4", "exact", "06067"), 2: ("34.0", "-118.0", "approximate", "06037"),
             6: ("38.6", "-121.5", "exact", "none")}
    for i, (lat, lon, q, fips) in place.items():
        a = from_row(rows[i - 1])
        cache[a.key] = {"address_key": a.key, "street": a.street, "city": a.city, "zip5": a.zip5, "lat": lat,
                        "lon": lon, "match_quality": q, "county_fips": fips}
    geocode.save_cache(paths.geocache, cache)
    data = mapdata.build(paths, processed_at="2026-11-16T23:40:00+00:00")
    return paths, data, {f["id"]: f for f in data["facilities"]}


def test_map_file_shape_and_dates(built):
    _, data, _ = built
    assert data["as_of"] == "2026-11-15" and data["processed_at"] == "2026-11-16T23:40:00+00:00"
    assert "Department of Social Services" in data["source"] and data["geocoder"]
    for f in data["facilities"]:
        assert list(f) == mapdata.FACILITY_FIELDS


def test_closed_facilities_are_left_off(built):
    _, data, by_id = built
    assert "300000003" not in by_id
    assert data["counts"]["facilities"] == 5


def test_withheld_names_stay_withheld(built):
    _, _, by_id = built
    assert by_id["300000002"]["licensee"] == WITHHELD   # matched an administrator in an earlier week
    assert by_id["300000006"]["name"] == NAME_WITHHELD


def test_no_administrator_or_phone_in_the_file(built):
    _, data, _ = built
    text = json.dumps(data)
    assert "ADMIN PERSON" not in text and "555" not in text and "MORGAN" not in text.upper().replace(
        "NAME WITHHELD", "")


def test_county_is_where_the_location_falls(built):
    _, data, by_id = built
    two = by_id["300000002"]
    assert (two["county"], two["county_cdss"]) == ("LOS ANGELES", "NAPA")
    # No county from the geocoder, or no location yet: the state's label.
    assert by_id["300000006"]["county"] == "SACRAMENTO" and by_id["300000004"]["county"] == "SACRAMENTO"
    assert data["counts"]["county_differs"] == 1


def test_unplaced_facilities_are_listed_as_pending(built):
    _, data, by_id = built
    assert by_id["300000004"]["lat"] is None and by_id["300000004"]["quality"] == "pending"
    assert by_id["300000005"]["street"] == "" and by_id["300000005"]["quality"] == "pending"
    c = data["counts"]
    assert (c["placed"], c["pending_location"], c["exact"], c["approximate"]) == (3, 2, 2, 1)
    assert by_id["300000004"]["size"] == "large" and by_id["300000001"]["size"] == "small"


def test_manual_override_wins(built):
    paths, _, _ = built
    with open(paths.geocache / "overrides.csv", "a", encoding="utf-8") as f:
        f.write("300000004,,37.1,-120.1,checked on site,Dale,2026-11-23\n")
    by_id = {f["id"]: f for f in mapdata.build(paths)["facilities"]}
    assert (by_id["300000004"]["lat"], by_id["300000004"]["quality"]) == (37.1, "manual")


def test_written_outside_the_public_site(built):
    paths, data, _ = built
    key, version = mapdata.write(data, paths.mapbuild)
    assert key == "map/v/2026-11-15.json" and version.exists()
    pointer = json.loads((paths.mapbuild / "map" / "current.json").read_text())
    assert pointer["key"] == key and pointer["counts"] == data["counts"]
    assert paths.root / "site" not in version.parents
    assert "mapbuild/" in (ROOT / ".gitignore").read_text()


def test_map_step_cannot_block_the_public_update():
    wf = (ROOT / ".github" / "workflows" / "weekly.yml").read_text()
    step = wf[wf.index("- name: Members' map file"):]
    step = step[:step.index("\n      - name:", 1)]
    assert wf.index("- name: Publish the site") < wf.index("- name: Members' map file")
    assert "continue-on-error: true" in step and "vars.MAP_PUBLISH == 'on'" in step
    assert "site/" not in step


def test_map_wording_rules():
    # Facility concentration is one market factor, never a verdict (Dale, 2026-11-23).
    for path in [ROOT / "pipeline" / "mapdata.py", ROOT / "pipeline" / "geocode.py"]:
        assert not re.search(r"saturat|oversupplied|you should open", path.read_text(), re.I)
