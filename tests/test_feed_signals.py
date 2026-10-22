import dataclasses
from datetime import date

import pytest

from pipeline import config, feed, metrics, signals
from pipeline.normalize import Complaint, normalize
from pipeline.validate import read_csv
from tests import fixture_50

AS_OF, PRIOR = fixture_50.AS_OF, fixture_50.PRIOR_AS_OF


def n(i):
    return f"{400000000 + i:09d}"


@pytest.fixture(scope="module")
def weeks(tmp_path_factory):
    prior_path, current_path = fixture_50.write_pair(tmp_path_factory.mktemp("fx"))
    return [normalize(*read_csv(prior_path)), normalize(*read_csv(current_path))]


@pytest.fixture(scope="module")
def events(weeks):
    return feed.diff_events(weeks[0], PRIOR, weeks[1], AS_OF)


def test_one_event_per_change(events):
    got = sorted((e["facility_number"], e["change_type"], e["old"], e["new"]) for e in events)
    assert got == sorted([
        (n(1), "new_facility", None, "LICENSED"),
        (n(0), "status_change", "PENDING", "LICENSED"),
        (n(37), "status_change", "LICENSED", "CLOSED"),
        (n(45), "status_change", "PENDING", "CLOSED"),
        (n(17), "licensee_change", "OLD OWNER LLC", "NEW OWNER LLC"),
        (n(19), "capacity_change", 4, 6),
        (n(20), "new_substantiated_allegations", 0, 2),
        (n(21), "new_substantiated_allegations", 1, 3),
        (n(20), "new_complaint_visits", 0, 2),
    ])


def test_spacing_only_licensee_change_and_decreases_are_not_events(events):
    numbers = {e["facility_number"] for e in events}
    assert n(18) not in numbers  # "ACME  care inc" -> "ACME CARE INC"
    assert n(22) not in numbers  # substantiated allegations fell 3 -> 1


def test_event_fields(events):
    expected = {"date", "prior_snapshot_id", "facility_number", "facility_name", "city", "county",
                "facility_type", "capacity", "size_group", "change_type", "old", "new"}
    for e in events:
        assert set(e) == expected
        assert e["date"] == "2026-10-18" and e["prior_snapshot_id"] == "2026-10-11"
    assert {e["change_type"] for e in events} <= {k for k, *_ in feed.EVENT_TYPES}


def test_feed_keeps_12_weeks_newest_first(weeks):
    week = lambda d: [(d, weeks[0])]  # noqa: E731
    old, mid = date(2026, 7, 19), date(2026, 7, 26)  # 91 and 84 days before Oct 18
    snaps = week(date(2026, 7, 12)) + [(old, weeks[1])] + [(mid, weeks[0])] + [(AS_OF, weeks[1])]
    events = feed.all_events(snaps)
    kept = feed.feed_window(events, AS_OF)
    assert {e["date"] for e in events} == {"2026-07-19", "2026-07-26", "2026-10-18"}
    assert {e["date"] for e in kept} == {"2026-07-26", "2026-10-18"}
    assert kept[0]["date"] == "2026-10-18"


def test_size_change_is_a_capacity_change_not_a_new_home(weeks):
    prior = [dataclasses.replace(f, capacity=7) if f.number == n(19) else f for f in weeks[0]]
    small = metrics.SIZES["small"][1]
    act = metrics.activity(weeks[1], prior, small)
    assert act["new_facility_numbers"] == 1  # still only n1
    assert act["capacity_changes"] == 1
    large = metrics.activity(weeks[1], prior, metrics.SIZES["large"][1])
    assert large["removed_facility_numbers"] == 0


# ---- signals ----

def fac(weeks, i, **changes):
    f = next(f for f in weeks[1] if f.number == n(i))
    return dataclasses.replace(f, **changes)


def complaint(d, sub=0):
    return Complaint(d, sub, 0, 0, 0, 0, 0)


def rules(flags):
    return [f["rule"] for f in flags]


def test_on_probation(weeks):
    assert rules(signals.facility_flags(fac(weeks, 35), AS_OF, [])) == ["on_probation"]


def test_substantiated_12m_uses_complaint_dates(weeks):
    f = fac(weeks, 5, complaints=(complaint(date(2025, 10, 18), 2), complaint(date(2025, 10, 17), 5)))
    flags = signals.facility_flags(f, AS_OF, [])
    assert rules(flags) == ["substantiated_12m"] and flags[0]["count"] == 2


def test_complaint_threshold(weeks):
    two = tuple(complaint(date(2026, 5, d)) for d in (1, 2))
    three = two + (complaint(date(2026, 5, 3)),)
    assert signals.facility_flags(fac(weeks, 5, complaints=two), AS_OF, []) == []
    flags = signals.facility_flags(fac(weeks, 5, complaints=three), AS_OF, [])
    assert rules(flags) == ["complaints_12m"] and flags[0]["count"] == config.COMPLAINT_THRESHOLD == 3


def test_closed_facilities_get_no_complaint_flags(weeks):
    many = tuple(complaint(date(2026, 5, d), 1) for d in (1, 2, 3, 4))
    f = fac(weeks, 42, complaints=many)  # closed 3/1/2020
    assert signals.facility_flags(f, AS_OF, []) == []


def test_unparsed_complaint_detail_gives_no_complaint_flags(weeks):
    assert signals.facility_flags(fac(weeks, 5, complaints=None), AS_OF, []) == []


def test_recent_status_change(weeks, events):
    flagged = signals.compute(weeks[1], AS_OF, events)
    assert "recent_status_change" in rules(flagged[n(0)])   # PENDING -> LICENSED this week
    assert "recent_status_change" in rules(flagged[n(37)])  # closed 10/16
    assert "recent_status_change" in rules(flagged[n(40)])  # Closed Date exactly 90 days back
    assert n(39) not in flagged                              # 91 days back
    assert n(46) not in flagged                              # closed 10/17 but never licensed
    assert rules(flagged[n(45)]) == ["recent_status_change"]  # its status change still counts


def test_every_rule_is_published():
    for key, label, rule in signals.RULES:
        assert label and len(rule) > 40
