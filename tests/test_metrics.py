import dataclasses
from datetime import date

import pytest

from pipeline import config, metrics
from pipeline.normalize import normalize, parse_complaints
from pipeline.validate import read_csv, validate
from tests import fixture_50


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    prior_path, current_path = fixture_50.write_pair(tmp_path_factory.mktemp("fixture"))
    cur_h, cur_rows = read_csv(current_path)
    pri_h, pri_rows = read_csv(prior_path)
    assert validate(cur_h, cur_rows).ok and len(cur_rows) == 50
    return metrics.compute(normalize(cur_h, cur_rows), fixture_50.AS_OF,
                           normalize(pri_h, pri_rows), fixture_50.PRIOR_AS_OF)


def scope(result, name):
    return result["scopes"][name]


CORE_TOTALS = {
    "licensed_facilities": 31,       # n0-n29 plus n49 (blank type)
    "licensed_beds": 215,            # 20 x 6 + 5 x 4 + 5 x 15; n49's blank capacity counts 0
    "median_licensed_capacity": 6,
    "pending": 5,
    "on_probation": 2,
    "new_licenses_7d": 2,            # n0 (as-of day), n1 (exactly 7 days back)
    "new_licenses_90d": 5,           # n0, n1, n2, n3 (exactly 90 days back), n30; n4 is 91 days back
    "closures_closed_date_7d": 1,    # n37; n45 and n46 never had a license
    "closures_closed_date_90d": 3,   # n37, n38, n40 (exactly 90 days back); n39 is out
    "citations_12m": 3,              # n25 (exactly one year back), n27 x2; n26 is one day too old
    "facilities_with_citations_12m": 2,
    "licensees_3plus": 2,            # BIG CHAIN LLC (4), BCRG (3 spellings); SMALL LLC has 2 licensed
}


@pytest.mark.parametrize("key,expected", CORE_TOTALS.items())
def test_core_totals(result, key, expected):
    assert scope(result, "core")["totals"][key] == expected


def test_all_and_other_scopes(result):
    all_t, other_t = scope(result, "all")["totals"], scope(result, "other")["totals"]
    assert (all_t["licensed_facilities"], all_t["licensed_beds"], all_t["median_licensed_capacity"]) == (33, 415, 6)
    assert (other_t["licensed_facilities"], other_t["licensed_beds"], other_t["median_licensed_capacity"]) == (2, 200, 100)
    assert scope(result, "core")["row_count"] + scope(result, "other")["row_count"] == 50


def test_blank_capacity_counts_zero_beds_and_is_left_out_of_median(result):
    core = scope(result, "core")["totals"]
    assert core["licensed_beds"] == 215 and core["median_licensed_capacity"] == 6  # n49 adds a home, no beds


def test_blank_type_counts_with_regular_rcfes(result):
    counties = {c["county"]: c for c in scope(result, "core")["counties"]}
    assert counties["SAN DIEGO"]["licensed_facilities"] == 1
    assert "SAN DIEGO" not in {c["county"] for c in scope(result, "other")["counties"]}


CORE_WOW = {
    "licensed_facilities": 0,    # prior: 31 (n0 pending, n1 absent, n99 and n37 licensed)
    "licensed_beds": 2,          # prior 213
    "median_licensed_capacity": 0,
    "pending": -2,               # prior: n0 and n45 were also pending
    "on_probation": 0,
    "new_licenses_7d": 1,        # prior window 10/4-10/11: n2 only
    "new_licenses_90d": 1,       # prior: n2, n3, n4, n30
    "closures_closed_date_7d": 1,
    "closures_closed_date_90d": 0,  # prior: n38, n39, n40
    "citations_12m": -1,         # prior window from 10/11/2025: n25, n26, n27 x2
    "facilities_with_citations_12m": -1,
    "licensees_3plus": 0,
}


@pytest.mark.parametrize("key,expected", CORE_WOW.items())
def test_core_week_over_week(result, key, expected):
    assert scope(result, "core")["week_over_week"][key] == expected


CORE_ACTIVITY = {
    "closures_status_changed": 1,       # n37; n45 closed before a license was issued
    "new_facility_numbers": 1,          # n1
    "removed_facility_numbers": 1,      # n99
    "status_changes": 3,                # n0, n37, n45 (PENDING -> CLOSED)
    "ownership_changes": 1,             # n17; n18 is spacing/case only
    "capacity_changes": 1,              # n19
    "facilities_new_substantiated": 2,  # n20, n21
    "new_substantiated_allegations": 4, # +2, +2
    "facilities_substantiated_decreased": 1,  # n22
    "facilities_new_complaint_visits": 1,
    "new_complaint_visits": 2,
}


@pytest.mark.parametrize("key,expected", CORE_ACTIVITY.items())
def test_core_activity(result, key, expected):
    assert scope(result, "core")["activity"][key] == expected


def test_county_table(result):
    counties = {c["county"]: c for c in scope(result, "core")["counties"]}
    la, sac = counties["LOS ANGELES"], counties["SACRAMENTO"]
    assert (la["licensed_facilities"], la["licensed_beds"], la["new_licenses_90d"],
            la["week_over_week"]["licensed_facilities"]) == (10, 60, 4, 2)
    assert (sac["licensed_facilities"], sac["new_licenses_90d"], sac["closures_closed_date_90d"],
            sac["week_over_week"]["licensed_facilities"]) == (15, 1, 3, -2)
    assert counties["ORANGE"]["week_over_week"]["licensed_facilities"] == 0
    # Activity per county adds up to the statewide activity.
    state = scope(result, "core")["activity"]
    for key in state:
        assert sum(c["activity"][key] for c in counties.values()) == state[key], key
    assert la["activity"]["new_facility_numbers"] == 1 and sac["activity"]["closures_status_changed"] == 1
    assert sac["pending"] == 5 and sac["on_probation"] == 2
    all_counties = {c["county"]: c["licensed_facilities"] for c in scope(result, "all")["counties"]}
    assert all_counties["LOS ANGELES"] == 12 and all_counties["SAN DIEGO"] == 1


def test_owners(tmp_path):
    _, current_path = fixture_50.write_pair(tmp_path)
    h, rows = read_csv(current_path)
    owners = metrics.owners([f for f in normalize(h, rows) if f.is_core])
    assert [o["licensee"] for o in owners] == ["BIG CHAIN LLC", "BCRG INC."]
    big, bcrg = owners
    assert big["licensed_homes"] == 4 and big["licensed_beds"] == 24
    assert big["counties"] == ["LOS ANGELES", "ORANGE"]
    assert bcrg["name_variants"] == ["BCRG INC.", "bcrg inc."]


def test_no_prior_snapshot_gives_no_week_over_week(tmp_path):
    _, current_path = fixture_50.write_pair(tmp_path)
    h, rows = read_csv(current_path)
    r = metrics.compute(normalize(h, rows), fixture_50.AS_OF)
    core = r["scopes"]["core"]
    assert core["activity"] is None and set(core["week_over_week"].values()) == {None}


def test_one_year_before_leap_day():
    assert metrics.one_year_before(date(2028, 2, 29)) == date(2027, 2, 28)


def test_every_metric_has_a_published_definition(result):
    keys = set(metrics.TOTAL_KEYS) | set(scope(result, "core")["activity"])
    assert keys <= set(metrics.DEFINITIONS)


def test_facility_records_hold_no_private_fields():
    fields = {f.name for f in dataclasses.fields(normalize.__globals__["Facility"])}
    for col in config.PRIVATE_COLUMNS:
        assert col.lower().replace("facility ", "").replace(" ", "_") not in fields
    assert not {"administrator", "telephone", "phone", "address"} & fields


def test_parse_complaints_groups_of_seven():
    col = "Complaint Info- Date, #Sub A, # Inc A, # Uns A, # Unf A, # TypeA, # TypeB ..."
    row = {col: "09/16/2026", "_overflow": ["1", "0", "4", "0", "0", "1",
                                            "07/14/2026", "2", "0", "1", "0", "0", "0", "", ""]}
    complaints = parse_complaints(row, col)
    assert [c.date for c in complaints] == [date(2026, 9, 16), date(2026, 7, 14)]
    assert sum(c.substantiated for c in complaints) == 3
    assert parse_complaints({col: "No Complaints"}, col) == ()
    assert parse_complaints({col: "09/16/2026", "_overflow": ["1", "0"]}, col) is None


def test_name_words_match_across_order_and_initials():
    from pipeline.normalize import name_words
    assert name_words("RIVERA, MORGAN") == name_words("Morgan  Rivera")
    assert name_words("SAMPLE, Q. JORDAN") == name_words("Jordan Sample")
    assert name_words("O'NEIL, MARY-ANN") == name_words("Mary-Ann O'Neil")
    assert name_words("MORGAN RIVERA LLC") != name_words("MORGAN RIVERA")
    assert name_words("PENDING") is None and name_words("R") is None and name_words("") is None


# ---- Section 5a: activity (12 months) and available supply ----

CORE_5A = {
    "new_licenses_12m": 6,        # n0, n1, n2, n3, n4 (7/19/2026 is inside 12 months), n30
    "closures_12m": 4,            # n37, n38, n39, n40; n45 and n46 never had a license
    "net_change_12m": 2,
    "growth_rate_12m": pytest.approx(6 / 31, abs=1e-6),
    "churn_rate_12m": pytest.approx(4 / 31, abs=1e-6),
    "probation_share": pytest.approx(2 / 33, abs=1e-6),       # 2 on probation / (31 licensed + 2)
    "share_licensed_multi": pytest.approx(7 / 31, abs=1e-6),  # BIG CHAIN (4) + BCRG (3) homes
}


@pytest.mark.parametrize("key,expected", CORE_5A.items())
def test_core_activity_and_supply(result, key, expected):
    assert scope(result, "core")["totals"][key] == expected


def test_12_month_week_over_week(result):
    wow = scope(result, "core")["week_over_week"]
    # Prior week (to 10/11): new n2, n3, n4, n30 = 4; closures n38, n39, n40 = 3.
    assert (wow["new_licenses_12m"], wow["closures_12m"], wow["net_change_12m"]) == (2, 1, 1)


def test_multi_home_share_counts_operators_statewide(result):
    # BIG CHAIN LLC has 2 homes in Los Angeles and 2 in Orange: 4 statewide, so all count.
    counties = {c["county"]: c for c in scope(result, "core")["counties"]}
    assert counties["LOS ANGELES"]["share_licensed_multi"] == pytest.approx(2 / 10)
    assert counties["ORANGE"]["share_licensed_multi"] == pytest.approx(5 / 5)  # n10, n11 + BCRG n12-n14


def test_rates_are_blank_without_licensed_homes():
    assert metrics.rate(3, 0) is None
    assert metrics.totals([], fixture_50.AS_OF)["growth_rate_12m"] is None
