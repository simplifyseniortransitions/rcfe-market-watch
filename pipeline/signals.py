"""Rule-based flags. Each rule is published as written; there is no combined score."""
from pipeline import config
from pipeline.metrics import is_closure, one_year_before
from pipeline.normalize import CLOSED, ON_PROBATION

RULES = [
    ("on_probation", "On probation", "Facility Status is ON PROBATION in the current snapshot."),
    ("substantiated_12m", "Substantiated allegations, last 12 months",
     "The facility is not closed and the state's complaint detail lists at least one substantiated "
     "allegation on a complaint dated on or after the same calendar day one year before the as-of date."),
    ("recent_status_change", "Closed or changed status, last 90 days",
     "The facility had a License First Date and its Closed Date is within the last 90 days, or our weekly "
     "comparison recorded a status change within the last 90 days. Weekly comparisons start with the "
     "first snapshot we hold."),
    ("complaints_12m", f"{config.COMPLAINT_THRESHOLD}+ complaints, last 12 months",
     f"The facility is not closed and the state's complaint detail lists {config.COMPLAINT_THRESHOLD} or "
     "more complaints dated in the last 12 months. This counts complaints, not complaint visits, because "
     "only the complaint detail carries dates."),
]

DISCLAIMER = (
    "Flags come from public state records, may be out of date, and do not indicate a facility's quality "
    "or value. Each flag is shown on its own; they are not added together. "
    "Errors in a record can only be corrected by the California Department of Social Services."
)


def complaints_in_year(f, as_of):
    year_ago = one_year_before(as_of)
    return [c for c in f.complaints if year_ago <= c.date <= as_of]


def facility_flags(f, as_of, status_events):
    """[{rule, detail}] for one facility. status_events: this facility's status_change events in the last 90 days."""
    flags = []
    if f.status == ON_PROBATION:
        flags.append({"rule": "on_probation", "detail": "Status: ON PROBATION"})
    open_with_detail = f.status != CLOSED and f.complaints is not None
    year = complaints_in_year(f, as_of) if open_with_detail else []
    substantiated = sum(c.substantiated for c in year)
    if substantiated:
        flags.append({"rule": "substantiated_12m", "count": substantiated,
                      "detail": f"{substantiated} substantiated allegation(s) on complaints in the last 12 months"})
    reasons = []
    if is_closure(f, as_of, 90):
        reasons.append(f"Closed Date {f.closed_date.isoformat()}")
    reasons += [f"{e['old']} to {e['new']} (week of {e['date']})" for e in status_events]
    if reasons:
        flags.append({"rule": "recent_status_change", "detail": "; ".join(reasons)})
    if open_with_detail and len(year) >= config.COMPLAINT_THRESHOLD:
        flags.append({"rule": "complaints_12m", "count": len(year),
                      "detail": f"{len(year)} complaints in the last 12 months"})
    return flags


def compute(facilities, as_of, events_90d):
    """{facility_number: flags} for every facility with at least one flag."""
    by_number = {}
    for e in events_90d:
        if e["change_type"] == "status_change":
            by_number.setdefault(e["facility_number"], []).append(e)
    out = {}
    for f in facilities:
        flags = facility_flags(f, as_of, by_number.get(f.number, []))
        if flags:
            out[f.number] = flags
    return out
