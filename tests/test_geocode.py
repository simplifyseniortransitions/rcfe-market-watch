"""Geocode cache (pipeline/geocode.py). Uses a fake geocoder: these tests never touch the network."""
from datetime import date, timedelta

import pytest

from pipeline import config, geocode
from pipeline.address import standardize
from pipeline.geocode import CensusGeocoder, GeocodeError, Result, census_request_body, parse_census

TODAY = date(2026, 11, 23)


def row(n, address, status="LICENSED", city="Sample City", zip_code="95000"):
    return {"Facility Number": f"{300000000 + n:09d}", "Facility Status": status,
            "Facility Address": address, "Facility City": city, "Facility Zip": zip_code}


class FakeGeocoder:
    source = "census"

    def __init__(self, miss=(), fail=False):
        self.calls, self.miss, self.fail = [], set(miss), fail

    def geocode(self, addresses):
        self.calls.append([a.key for a in addresses])
        if self.fail:
            raise GeocodeError("service down")
        out = {}
        for i, a in enumerate(addresses):
            if a.street in self.miss:
                out[a.key] = Result(a.key, quality="none", error="no match")
            else:
                out[a.key] = Result(a.key, f"{38 + i / 1000:.6f}", f"{-121 - i / 1000:.6f}", "exact", a.one_line)
        return out


@pytest.fixture
def folder(tmp_path):
    return tmp_path / "geocache"


def test_first_run_looks_up_each_address_once(folder):
    rows = [row(1, "1 Sample Rd"), row(2, "2 Sample Rd"), row(3, "1 Sample Road")]  # 3 is a rewording of 1
    fake = FakeGeocoder()
    s = geocode.run(rows, folder, fake, TODAY, pause=0, log=lambda *_: None)
    assert s["addresses"] == 2 and s["looked_up"] == 2
    assert sorted(k for call in fake.calls for k in call) == ["1 SAMPLE RD|SAMPLE CITY|95000", "2 SAMPLE RD|SAMPLE CITY|95000"]
    cache = geocode.load_cache(folder)
    assert cache["1 SAMPLE RD|SAMPLE CITY|95000"]["match_quality"] == "exact"
    assert (folder / "overrides.csv").exists()


def test_cached_addresses_are_never_looked_up_again(folder):
    rows = [row(1, "1 Sample Rd"), row(2, "2 Sample Rd")]
    geocode.run(rows, folder, FakeGeocoder(), TODAY, pause=0, log=lambda *_: None)
    later = FakeGeocoder()
    # Next week CDSS rewords one address and adds a facility: only the new one is looked up.
    s = geocode.run([row(1, "1 SAMPLE ROAD"), row(2, "2 Sample Rd"), row(4, "4 Sample Rd")], folder, later,
                    TODAY + timedelta(days=7), pause=0, log=lambda *_: None)
    assert later.calls == [["4 SAMPLE RD|SAMPLE CITY|95000"]]
    assert s["already_cached"] == 2 and s["looked_up"] == 1


def test_closed_and_unusable_addresses_are_skipped(folder):
    rows = [row(1, "1 Sample Rd", status="CLOSED"), row(2, "", status="PENDING"), row(3, "3 Sample Rd", zip_code="")]
    fake = FakeGeocoder()
    s = geocode.run(rows, folder, fake, TODAY, pause=0, log=lambda *_: None)
    assert s["addresses"] == 0 and fake.calls == []
    c = geocode.coverage(rows, folder)
    assert c["facilities"] == 2 and c["no_usable_address"] == 2


def test_failed_matches_wait_before_another_try(folder):
    rows = [row(1, "9 Nowhere Ln")]
    geocode.run(rows, folder, FakeGeocoder(miss={"9 NOWHERE LN"}), TODAY, pause=0, log=lambda *_: None)
    entry = geocode.load_cache(folder)["9 NOWHERE LN|SAMPLE CITY|95000"]
    assert entry["lat"] == "" and entry["attempts"] == "1" and entry["retry_after"] == "2026-11-30"
    again = FakeGeocoder()
    geocode.run(rows, folder, again, TODAY + timedelta(days=3), pause=0, log=lambda *_: None)
    assert again.calls == []  # still waiting
    geocode.run(rows, folder, again, TODAY + timedelta(days=7), pause=0, log=lambda *_: None)
    assert again.calls == [["9 NOWHERE LN|SAMPLE CITY|95000"]]
    assert geocode.load_cache(folder)["9 NOWHERE LN|SAMPLE CITY|95000"]["attempts"] == "2"


def test_service_failure_records_nothing_and_keeps_the_cache(folder):
    rows = [row(1, "1 Sample Rd")]
    geocode.run(rows, folder, FakeGeocoder(), TODAY, pause=0, log=lambda *_: None)
    s = geocode.run(rows + [row(2, "2 Sample Rd")], folder, FakeGeocoder(fail=True), TODAY, pause=0, log=lambda *_: None)
    assert s["errors"] == ["service down"] and s["looked_up"] == 0
    cache = geocode.load_cache(folder)
    assert set(cache) == {"1 SAMPLE RD|SAMPLE CITY|95000"}  # the new address simply waits for next time


def test_large_runs_are_split_into_batch_files(folder):
    rows = [row(i, f"{i} Sample Rd") for i in range(1, 8)]
    fake = FakeGeocoder()
    geocode.run(rows, folder, fake, TODAY, chunk=3, pause=0, log=lambda *_: None)
    assert [len(c) for c in fake.calls] == [3, 3, 1]


def test_limit_runs_only_the_first_few(folder):
    fake = FakeGeocoder()
    s = geocode.run([row(i, f"{i} Sample Rd") for i in range(1, 6)], folder, fake, TODAY, limit=2, pause=0,
                    log=lambda *_: None)
    assert s["looked_up"] == 2


def test_census_request_sends_the_street_without_the_unit():
    body, ctype = census_request_body([("1", standardize("700 Sample Blvd Suite 4", "Sample City", "95000-1234"))])
    text = body.decode()
    assert 'name="benchmark"' in text and "Public_AR_Current" in text and 'filename="addresses.csv"' in text
    assert "1,700 SAMPLE BLVD,SAMPLE CITY,CA,95000" in text and "STE" not in text
    assert ctype.startswith("multipart/form-data; boundary=")


def test_census_answer_is_read_into_results():
    answer = "\n".join([
        '"1","1 SAMPLE RD, SAMPLE CITY, CA, 95000","Match","Exact","1 SAMPLE RD, SAMPLE CITY, CA, 95000","-121.4944,38.5816","123","L"',
        '"2","2 SAMPLE RD, SAMPLE CITY, CA, 95000","Match","Non_Exact","2 SAMPLE RD, SAMPLE CITY, CA, 95001","-121.5,38.6","124","R"',
        '"3","3 SAMPLE RD, SAMPLE CITY, CA, 95000","Tie"',
        '"4","4 SAMPLE RD, SAMPLE CITY, CA, 95000","No_Match"',
    ])
    r = parse_census(answer, {"1": "a", "2": "b", "3": "c", "4": "d"})
    assert (r["a"].lat, r["a"].lon, r["a"].quality) == ("38.581600", "-121.494400", "exact")
    assert r["b"].quality == "approximate" and r["b"].matched.endswith("95001")
    assert r["c"].quality == "tie" and r["c"].lat == ""
    assert r["d"].quality == "none" and r["d"].error == "no match"


def test_unreachable_census_is_a_geocode_error(monkeypatch):
    def down(req, timeout):
        raise OSError("connection reset")
    monkeypatch.setattr(geocode.urllib.request, "urlopen", down)
    with pytest.raises(GeocodeError, match="unavailable"):
        CensusGeocoder().geocode([standardize("1 Sample Rd", "Sample City", "95000")])


def test_geocache_is_outside_the_public_site():
    paths = config.DEFAULT_PATHS
    assert paths.root / "site" not in paths.geocache.parents and paths.geocache != paths.root / "site"
    assert "geocache/" in (paths.root / ".gitignore").read_text()


def test_census_answer_carries_the_county_of_the_location():
    answer = ('"1","1 SAMPLE RD, SAMPLE CITY, CA, 95000","Match","Exact","1 SAMPLE RD, SAMPLE CITY, CA, 95000",'
              '"-121.49,38.57","133323757","L","06","067","001103","3028"')
    assert parse_census(answer, {"1": "a"})["a"].county_fips == "06067"
    body, _ = census_request_body([("1", standardize("1 Sample Rd", "Sample City", "95000"))])
    assert b"geographies" not in body and b'name="vintage"' in body and b"Current_Current" in body
    assert "geographies/addressbatch" in geocode.CENSUS_URL


def test_county_names_follow_the_cdss_spelling():
    from pipeline.counties import county_name
    assert county_name("06067") == "SACRAMENTO" and county_name("06037") == "LOS ANGELES"
    assert county_name("32003") == "" and county_name("") == "" and county_name("none") == ""


class CountyGeocoder(FakeGeocoder):
    def __init__(self, fips="06067", miss=()):
        super().__init__(miss=miss)
        self.fips = fips

    def geocode(self, addresses):
        out = super().geocode(addresses)
        for r in out.values():
            if r.lat:
                r.county_fips = self.fips
        return out


def test_places_found_before_counties_are_refreshed_once(folder):
    rows = [row(1, "1 Sample Rd"), row(2, "2 Sample Rd")]
    geocode.run(rows, folder, FakeGeocoder(), TODAY, pause=0, log=lambda *_: None)
    cache = geocode.load_cache(folder)
    for e in cache.values():  # as saved by Phase 1, before counties were recorded
        e["county_fips"] = ""
    geocode.save_cache(folder, cache)
    # One refresh: 1 gets its county; 2 no longer matches, so its location is kept, marked "no county".
    geocode.run(rows, folder, CountyGeocoder(miss={"2 SAMPLE RD"}), TODAY, pause=0, log=lambda *_: None)
    cache = geocode.load_cache(folder)
    one, two = cache["1 SAMPLE RD|SAMPLE CITY|95000"], cache["2 SAMPLE RD|SAMPLE CITY|95000"]
    assert one["county_fips"] == "06067" and one["lat"]
    assert two["county_fips"] == "none" and two["lat"] and two["match_quality"] == "exact"
    later = CountyGeocoder()
    geocode.run(rows, folder, later, TODAY, pause=0, log=lambda *_: None)
    assert later.calls == []  # never again
