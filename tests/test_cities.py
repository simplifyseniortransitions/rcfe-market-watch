"""Market cities and the "Top California RCFE Markets" rankings (pipeline/cities.py)."""
import json
import re
from pathlib import Path

import pytest

from pipeline import cities

ROOT = Path(__file__).resolve().parent.parent
LA, SAC, FRESNO = "44000", "64000", "27000"


@pytest.fixture
def fake_tables(monkeypatch):
    monkeypatch.setattr(cities, "block_places", lambda: {"B-LA": LA, "B-SAC": SAC, "B-FRESNO": FRESNO})
    monkeypatch.setattr(cities, "places", lambda: {LA: ("Los Angeles", "city"), SAC: ("Sacramento", "city"),
                                                   FRESNO: ("Fresno", "city")})


def rec(i, city="SACRAMENTO", block="B-SAC", status="LICENSED", capacity=6, county="SACRAMENTO", lat=38.5,
        county_cdss=None):
    return {"id": f"{i:09d}", "city": city, "block": block, "status": status, "capacity": capacity,
            "county": county, "county_cdss": county_cdss or county, "lat": lat}


# ---- reference tables ----

def test_census_tables_load():
    assert cities.places()[LA] == ("Los Angeles", "city")
    assert cities.places()["11390"][1] == "community"          # Carmichael CDP
    assert len(cities.block_places()) > 390_000
    assert all(len(b) == 15 for b in list(cities.block_places())[:1000])


def test_alias_list_merges_only_reviewed_spellings():
    assert cities.mailing_city("SACRAMNETO") == "SACRAMENTO"
    assert cities.mailing_city("S SAN FRANCISCO") == "SOUTH SAN FRANCISCO"
    # Real places that merely look like another name are never merged.
    for real in ["CORONADO", "DELANO", "MILL VALLEY", "SANTA PAULA", "EAST SACRAMENTO", "SACRAMENTO"]:
        assert cities.mailing_city(real) == real
    for src, dst in cities.aliases().items():
        assert dst not in cities.aliases(), f"{src} -> {dst} chains to another alias"


# ---- city assignment ----

def test_neighborhood_mailing_names_count_toward_their_city(fake_tables):
    r = cities.assign([rec(1, city="VAN NUYS", block="B-LA", county="LOS ANGELES")])[0]
    assert (r["market_city"], r["market_city_kind"], r["market_city_id"]) == ("Los Angeles", "city", "place-44000")


def test_homes_without_a_location_use_their_mailing_citys_usual_place(fake_tables):
    rs = cities.assign([rec(1, city="VAN NUYS", block="B-LA", county="LOS ANGELES"),
                        rec(2, city="VAN NUYS", block="B-LA", county="LOS ANGELES"),
                        rec(3, city="VAN NUTS", block="", lat=None, county="LOS ANGELES")])
    assert rs[2]["market_city"] == "Los Angeles"   # misspelling corrected, then the usual place


def test_locations_outside_any_place_are_labelled_unincorporated(fake_tables):
    r = cities.assign([rec(1, city="OAKHURST", block="B-NONE", county="MADERA")])[0]
    assert r["market_city"] == "Oakhurst (unincorporated)" and r["market_city_kind"] == "unincorporated"
    assert cities.assign([rec(2, city="", block="", lat=None)])[0]["market_city_id"] == ""


# ---- what is ranked ----

def test_only_active_licenses_rank_by_default(fake_tables):
    rs = cities.assign([rec(1), rec(2, status="PENDING"), rec(3, status="CLOSED"), rec(4, status="ON PROBATION"),
                        rec(5, status="SUSPENDED")])
    active = cities.aggregate(rs, cities.SCOPES["active"][1])["place-64000"]
    pending = cities.aggregate(rs, cities.SCOPES["with_pending"][1])["place-64000"]
    assert active["facilities"] == 2 and pending["facilities"] == 3   # never CLOSED, never an unknown status
    assert cities.DEFAULT_SCOPE == "active"


def test_licensed_capacity_totals_bands_and_missing(fake_tables):
    caps = [1, 6, 7, 15, 16, 49, 50, 120, None]
    rs = cities.assign([rec(i, capacity=c, status="PENDING" if c is None else "LICENSED")
                        for i, c in enumerate(caps)])
    c = cities.aggregate(rs, cities.SCOPES["with_pending"][1])["place-64000"]
    assert c["facilities"] == 9 and c["licensed_capacity"] == sum(x for x in caps if x)
    assert c["capacity_not_listed"] == 1
    assert c["by_capacity_band"] == {"1_6": 2, "7_15": 2, "16_49": 2, "50_plus": 2}


def test_city_county_and_share_of_county(fake_tables):
    rs = cities.assign([rec(1, capacity=10), rec(2, capacity=10), rec(3, city="ELK GROVE", block="B-NONE",
                                                                         capacity=30)])
    c = cities.aggregate(rs, cities.SCOPES["active"][1])["place-64000"]
    assert c["county"] == "SACRAMENTO"
    assert c["county_share"] == {"facilities": round(2 / 3, 4), "licensed_capacity": 0.4}


# ---- ranking ----

def city(cid, f, cap):
    return {"city_id": cid, "name": cid.upper(), "facilities": f, "licensed_capacity": cap}


def test_ties_share_a_rank_and_order_is_stable():
    cs = {c["city_id"]: c for c in [city("a", 10, 50), city("b", 9, 80), city("c", 9, 90), city("d", 7, 10)]}
    rows = cities.rank(cs, "facilities", top=20)
    assert [(r["rank"], r["city_id"], r["tied"]) for r in rows] == [
        (1, "a", False), (2, "c", True), (2, "b", True), (4, "d", False)]
    assert rows == cities.rank(dict(reversed(list(cs.items()))), "facilities", top=20)


def test_every_city_tied_at_the_cutoff_is_kept():
    cs = {c["city_id"]: c for c in [city("a", 10, 1), city("b", 8, 1), city("c", 8, 1), city("d", 8, 1),
                                     city("e", 5, 1)]}
    assert [r["city_id"] for r in cities.rank(cs, "facilities", top=2)] == ["a", "b", "c", "d"]


def test_rankings_for_the_members_file(fake_tables):
    rs = cities.assign([rec(i) for i in range(3)] + [rec(10 + i, block="B-FRESNO", county="FRESNO", capacity=60)
                                                     for i in range(2)])
    out = cities.rankings(rs)
    assert out["title"] == "Top California RCFE Markets" and out["explanation"] == cities.EXPLANATION
    assert [m["id"] for m in out["metrics"]] == ["facilities", "licensed_capacity"]   # hidden ones left out
    active = out["scopes"]["active"]
    assert [r["city_id"] for r in active["lists"]["facilities"]] == ["place-64000", "place-27000"]
    assert [r["city_id"] for r in active["lists"]["licensed_capacity"]] == ["place-27000", "place-64000"]
    assert set(active["cities"]) == {"place-64000", "place-27000"}


def test_public_top_five_has_no_addresses_or_locations(fake_tables):
    rs = cities.assign([rec(i, block="B-SAC") for i in range(3)])
    for r in rs:
        r["street"] = "1 SAMPLE RD"
    top = cities.public_top(rs, "2026-11-15", "CDSS")
    text = json.dumps(top)
    assert "SAMPLE RD" not in text and '"lat"' not in text and '"lon"' not in text and '"block"' not in text
    row = top["lists"]["facilities"][0]
    assert set(row) == {"rank", "tied", "city", "county", "facilities", "licensed_capacity"}
    assert top["explanation"] == cities.EXPLANATION and len(top["lists"]["facilities"]) <= 5


# ---- wording ----

def test_explanation_text_is_exact():
    assert cities.EXPLANATION == (
        "A high facility count does not necessarily indicate market saturation. It may reflect population, "
        "demand, established referral networks or other local conditions. Facility concentration should be "
        "evaluated alongside demographics, occupancy, pricing, staffing, real estate costs and local referral "
        "patterns.")


def test_no_verdict_words_and_no_beds_for_licensed_capacity():
    labels = " ".join([cities.TITLE] + [m["label"] for m in cities.METRICS] + [s[0] for s in cities.SCOPES.values()])
    assert not re.search(r"saturat|undersuppl|oversuppl|\bgood\b|\bbad\b|\bbeds?\b", labels, re.I)
    code = (ROOT / "pipeline" / "cities.py").read_text()
    code = code.replace(cities.EXPLANATION, "")
    assert not re.search(r"\bsaturated\b|undersupplied|oversupplied", code, re.I)
