"""Step 3: one event per change between consecutive snapshots, keyed on Facility Number.

Events carry only public facility fields. Administrator names and phone numbers are not in the
Facility record at all, so they cannot reach an event.
"""
from datetime import timedelta

from pipeline.metrics import size_group

# (key, label, rule) — published on the Methodology page.
EVENT_TYPES = [
    ("new_facility", "New facility", "A Facility Number appears that was not in the prior snapshot."),
    ("status_change", "Status change", "Facility Status differs from the prior snapshot."),
    ("licensee_change", "Licensee change",
     "Licensee name differs from the prior snapshot, ignoring spacing and upper/lower case. "
     "Shows the licensee as listed by the state, except that a licensee name that is also an "
     "administrator's name is withheld."),
    ("capacity_change", "Capacity change", "Facility Capacity differs from the prior snapshot."),
    ("new_substantiated_allegations", "New substantiated allegations",
     "The Substantiated Allegations count is higher than in the prior snapshot."),
    ("new_complaint_visits", "New complaint visits",
     "The Complaint Visits count is higher than in the prior snapshot."),
]
EVENT_ORDER = {key: i for i, (key, *_) in enumerate(EVENT_TYPES)}
FEED_WEEKS = 12


def event(f, as_of, prior_as_of, change_type, old, new):
    return {
        "date": as_of.isoformat(),
        "prior_snapshot_id": prior_as_of.isoformat(),
        "facility_number": f.number,
        "facility_name": f.name,
        "city": f.city,
        "county": f.county,
        "facility_type": f.facility_type,
        "capacity": f.capacity,
        "size_group": size_group(f),
        "change_type": change_type,
        "old": old,
        "new": new,
    }


def diff_events(prior, prior_as_of, current, as_of):
    before = {f.number: f for f in prior}
    events = []
    for f in current:
        b = before.get(f.number)
        if b is None:
            events.append(event(f, as_of, prior_as_of, "new_facility", None, f.status))
            continue
        if b.status != f.status:
            events.append(event(f, as_of, prior_as_of, "status_change", b.status, f.status))
        if b.licensee_key != f.licensee_key:
            events.append(event(f, as_of, prior_as_of, "licensee_change",
                                b.public_licensee, f.public_licensee))
        if b.capacity != f.capacity:
            events.append(event(f, as_of, prior_as_of, "capacity_change", b.capacity, f.capacity))
        if f.substantiated_allegations > b.substantiated_allegations:
            events.append(event(f, as_of, prior_as_of, "new_substantiated_allegations",
                                b.substantiated_allegations, f.substantiated_allegations))
        if f.complaint_visits > b.complaint_visits:
            events.append(event(f, as_of, prior_as_of, "new_complaint_visits",
                                b.complaint_visits, f.complaint_visits))
    return events


def sort_events(events):
    return sorted(events, key=lambda e: (-int(e["date"].replace("-", "")), EVENT_ORDER[e["change_type"]],
                                         e["county"], e["facility_name"], e["facility_number"]))


def all_events(snapshots):
    """Events for every consecutive pair in [(as_of, facilities)], oldest first. Newest events first."""
    events = []
    for (prior_as_of, prior), (as_of, current) in zip(snapshots, snapshots[1:]):
        events += diff_events(prior, prior_as_of, current, as_of)
    return sort_events(events)


def recent(events, as_of, days):
    """Events dated within `days` before as_of (inclusive)."""
    start = (as_of - timedelta(days=days)).isoformat()
    return [e for e in events if start <= e["date"] <= as_of.isoformat()]


def feed_window(events, as_of):
    return recent(events, as_of, FEED_WEEKS * 7)
