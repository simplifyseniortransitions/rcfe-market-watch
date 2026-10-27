"""Step 2 metrics. Every number here is a count or sum over snapshot rows under a rule in DEFINITIONS."""
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from pipeline.normalize import CLOSED, LICENSED, ON_PROBATION, PENDING, WITHHELD

SCOPES = {
    "all": ("All RCFEs", lambda f: True),
    "core": ("Excluding CCRCs", lambda f: f.is_core),
    "other": ("CCRCs only", lambda f: not f.is_core),
}
# Headline numbers cover every facility in the file; core is shown as a secondary breakdown
# (Dale, 2026-10-21).
HEADLINE_SCOPE = "all"

# Rates for areas with fewer licensed homes than this are marked "small base" on the Market page.
SMALL_BASE = 20

SMALL_MAX = 6
SIZES = {
    "small": ("6 beds or fewer", lambda f: f.capacity is not None and f.capacity <= SMALL_MAX),
    "large": ("7 beds or more", lambda f: f.capacity is not None and f.capacity > SMALL_MAX),
}
# (key, label, low, high); high None means no upper limit.
BANDS = [
    ("6_or_fewer", "6 or fewer beds", 0, 6),
    ("7_15", "7-15 beds", 7, 15),
    ("16_49", "16-49 beds", 16, 49),
    ("50_99", "50-99 beds", 50, 99),
    ("100_plus", "100+ beds", 100, None),
]


def size_group(f):
    return next((k for k, (_, keep) in SIZES.items() if keep(f)), None)


def band(f):
    if f.capacity is None:
        return None
    return next(k for k, _, lo, hi in BANDS if lo <= f.capacity and (hi is None or f.capacity <= hi))

# Published on the Methodology page. Keep the wording in step with the code below.
DEFINITIONS = {
    "licensee_withheld": ("Withheld names",
                          "Where a licensee name is the same person's name as a facility administrator "
                          "anywhere in the state file, it is shown as withheld, because this site does not "
                          "publish administrator names. Names match when they have the same words in any "
                          "order (for example \"LAST, FIRST\" and \"FIRST LAST\"), ignoring initials and "
                          "punctuation. The facility is still counted everywhere. A facility name that is "
                          "an administrator's name (a home listed under a person's own name) is withheld "
                          "the same way."),
    "scope": ("Which facilities are counted",
              "Headline numbers count every facility in the state RCFE file. The \"Excluding CCRCs\" "
              "view leaves out continuing care retirement communities (Facility Type RCFE-CONTINUING "
              "CARE RETIREMENT COMMUNITY): RCFE-licensed campuses that also sell continuing-care "
              "contracts. Facilities with a blank Facility Type, which are pending applications the "
              "state has not typed yet, are counted with the other RCFEs."),
    "size_group": ("Home size groups",
                   "6 beds or fewer, or 7 beds or more, by the Facility Capacity in the current snapshot. "
                   "Week-to-week changes follow each facility's current size, so a home that changes "
                   "capacity is counted in its new group and shows as a capacity change. Facilities with "
                   "a blank capacity are in neither group."),
    "size_band": ("Capacity bands",
                  "Facility Capacity grouped as 6 or fewer, 7-15, 16-49, 50-99, and 100 or more beds."),
    "licensed_facilities": ("Licensed facilities", "Count of facilities with Facility Status = LICENSED."),
    "licensed_beds": ("Licensed beds",
                      "Sum of Facility Capacity for LICENSED facilities. A blank capacity counts as 0 beds."),
    "median_licensed_capacity": ("Median home size",
                                 "Median Facility Capacity of LICENSED facilities, in beds. "
                                 "Facilities with a blank capacity are left out."),
    "pending": ("Pending", "Count of facilities with Facility Status = PENDING."),
    "on_probation": ("On probation", "Count of facilities with Facility Status = ON PROBATION."),
    "new_licenses_7d": ("New licenses, 7 days",
                        "Facilities whose License First Date is on or between the as-of date minus 7 days "
                        "and the as-of date (any current status)."),
    "new_licenses_90d": ("New licenses, 90 days",
                         "Facilities whose License First Date is on or between the as-of date minus 90 days "
                         "and the as-of date (any current status)."),
    "closures_closed_date_7d": ("Closures by Closed Date, 7 days",
                                "Facilities that had a License First Date and whose Closed Date is on or "
                                "between the as-of date minus 7 days and the as-of date. Applications that "
                                "closed before a license was issued are not counted."),
    "closures_closed_date_90d": ("Closures by Closed Date, 90 days",
                                 "Facilities that had a License First Date and whose Closed Date is on or "
                                 "between the as-of date minus 90 days and the as-of date. Applications that "
                                 "closed before a license was issued are not counted."),
    "citations_12m": ("Citations, last 12 months",
                      "Count of POC (plan of correction) dates on or after the same calendar day one year "
                      "before the as-of date. Each citation in the file has a POC date; the citation "
                      "numbers themselves carry no date."),
    "facilities_with_citations_12m": ("Facilities with a citation, last 12 months",
                                      "Facilities with at least one POC date in the 12-month window above."),
    "licensees_3plus": ("Licensees with 3+ homes",
                        "Licensee names with 3 or more LICENSED facilities. Names are matched after "
                        "trimming, collapsing repeated spaces and ignoring upper/lower case; no other "
                        "merging is done. A licensee name that is also an administrator's name is "
                        "counted but shown as withheld."),
    "closures_status_changed": ("Closures by status change",
                                "Facilities with a License First Date whose status was not CLOSED in the "
                                "prior snapshot and is CLOSED in this one. Applications that closed before a "
                                "license was issued are not counted."),
    "new_facility_numbers": ("New facility numbers",
                             "Facility Numbers in this snapshot that were not in the prior snapshot."),
    "removed_facility_numbers": ("Facility numbers no longer listed",
                                 "Facility Numbers in the prior snapshot that are missing from this one."),
    "status_changes": ("Status changes", "Facilities in both snapshots whose Facility Status differs."),
    "ownership_changes": ("Ownership changes",
                          "Facilities in both snapshots whose Licensee name differs, using the same name "
                          "matching as Licensees with 3+ homes (spacing and case changes do not count)."),
    "capacity_changes": ("Capacity changes", "Facilities in both snapshots whose Facility Capacity differs."),
    "facilities_new_substantiated": ("Facilities with new substantiated allegations",
                                     "Facilities in both snapshots whose Substantiated Allegations count rose."),
    "new_substantiated_allegations": ("New substantiated allegations",
                                      "Sum of the increases above. Decreases are not subtracted; "
                                      "they are counted separately in QA."),
    "facilities_substantiated_decreased": ("Facilities whose substantiated allegations count fell (QA)",
                                           "Facilities in both snapshots whose Substantiated Allegations "
                                           "count dropped. Shown for quality checking only."),
    "facilities_new_complaint_visits": ("Facilities with new complaint visits",
                                        "Facilities in both snapshots whose Complaint Visits count rose."),
    "new_complaint_visits": ("New complaint visits", "Sum of the increases above."),
    "window_12m": ("12-month window",
                   "From the same calendar day one year before the as-of date through the as-of date, both "
                   "days included."),
    "new_licenses_12m": ("New licenses, 12 months",
                         "Facilities whose License First Date is in the 12-month window (any current status)."),
    "closures_12m": ("Closures, 12 months",
                     "Facilities that had a License First Date and whose Closed Date is in the 12-month window. "
                     "Applications that closed before a license was issued are not counted."),
    "net_change_12m": ("Net change, 12 months",
                       "New licenses, 12 months, minus closures, 12 months. This is not the same as the change "
                       "in licensed homes: new licenses include homes that are now closed or still pending, and "
                       "homes also move on and off probation."),
    "growth_rate_12m": ("Growth rate, 12 months",
                        "New licenses, 12 months, divided by licensed homes (Facility Status = LICENSED) in the "
                        "current file."),
    "churn_rate_12m": ("Churn rate, 12 months",
                       "Closures, 12 months, divided by licensed homes (Facility Status = LICENSED) in the "
                       "current file."),
    "probation_share": ("Probation share",
                        "Facilities ON PROBATION divided by facilities LICENSED or ON PROBATION. Homes on "
                        "probation are still operating but are not in the licensed count, so they are added "
                        "to the denominator."),
    "share_licensed_multi": ("Share held by licensees with 3+ homes",
                             "Licensed homes whose licensee has 3 or more LICENSED homes anywhere in the state "
                             "(all facility types and sizes), divided by licensed homes. Licensee names are "
                             "matched as for Licensees with 3+ homes."),
    "small_base": ("Small base",
                   f"Rates for an area with fewer than {SMALL_BASE} licensed homes are marked \"small base\": a "
                   "few homes opening or closing moves them a lot."),
    "compare_with": ("Compare with",
                     "A change is this week's file minus the chosen earlier week's file, both counted under "
                     "the same rules. Activity since an earlier week adds up the week-to-week comparisons in "
                     "between. New licenses and closures by date add up each week's 7-day count, and are shown "
                     "only when the weekly files are exactly 7 days apart. Comparisons reach back to the first "
                     "saved weekly file, October 11, 2026."),
    "trends": ("Trend charts",
               "One point per weekly state file, counted under the same rules as the current week. "
               "Charts appear once four weekly files are on hand."),
    "week_over_week": ("Week-over-week change",
                       "This snapshot's value minus the prior snapshot's value, each computed from its own "
                       "file with windows measured from its own as-of date."),
}

TOTAL_KEYS = [
    "licensed_facilities", "licensed_beds", "median_licensed_capacity", "pending", "on_probation",
    "new_licenses_7d", "new_licenses_90d", "closures_closed_date_7d", "closures_closed_date_90d",
    "citations_12m", "facilities_with_citations_12m", "licensees_3plus",
    "new_licenses_12m", "closures_12m", "net_change_12m", "growth_rate_12m", "churn_rate_12m",
    "probation_share", "share_licensed_multi",
]


def in_window(d, as_of, days):
    return d is not None and as_of - timedelta(days=days) <= d <= as_of


def one_year_before(as_of):
    try:
        return as_of.replace(year=as_of.year - 1)
    except ValueError:  # Feb 29
        return as_of.replace(year=as_of.year - 1, day=28)


def is_closure(f, as_of, days):
    """A closure: Closed Date in the window, for a facility that had been licensed (Dale, 2026-10-22)."""
    return f.license_first_date is not None and in_window(f.closed_date, as_of, days)


def in_year(d, as_of):
    return d is not None and one_year_before(as_of) <= d <= as_of


def rate(part, whole):
    return None if not whole else round(part / whole, 6)


def multi_home_numbers(facilities):
    """Facility numbers of LICENSED homes whose licensee has 3+ LICENSED homes in the whole file."""
    return frozenset(f.number for homes in owner_groups(facilities).values() for f in homes)


def median(values):
    if not values:
        return None
    m = statistics.median(values)
    return int(m) if m == int(m) else round(m, 1)


def licensed(facilities):
    return [f for f in facilities if f.status == LICENSED]


def owner_groups(facilities):
    """{licensee_key: [LICENSED facilities]} for keys with 3 or more LICENSED homes."""
    groups = defaultdict(list)
    for f in licensed(facilities):
        if f.licensee_key:
            groups[f.licensee_key].append(f)
    return {k: v for k, v in groups.items() if len(v) >= 3}


def totals(facilities, as_of, multi=frozenset()):
    """multi: multi_home_numbers() of the whole snapshot, so a county's share counts statewide operators."""
    lic = licensed(facilities)
    probation = sum(f.status == ON_PROBATION for f in facilities)
    new_12m = sum(in_year(f.license_first_date, as_of) for f in facilities)
    closed_12m = sum(f.license_first_date is not None and in_year(f.closed_date, as_of) for f in facilities)
    year_ago = one_year_before(as_of)
    cites = [sum(1 for d in f.poc_dates if year_ago <= d <= as_of) for f in facilities]
    return {
        "licensed_facilities": len(lic),
        "licensed_beds": sum(f.capacity or 0 for f in lic),
        "median_licensed_capacity": median([f.capacity for f in lic if f.capacity is not None]),
        "pending": sum(f.status == PENDING for f in facilities),
        "on_probation": probation,
        "new_licenses_7d": sum(in_window(f.license_first_date, as_of, 7) for f in facilities),
        "new_licenses_90d": sum(in_window(f.license_first_date, as_of, 90) for f in facilities),
        "closures_closed_date_7d": sum(is_closure(f, as_of, 7) for f in facilities),
        "closures_closed_date_90d": sum(is_closure(f, as_of, 90) for f in facilities),
        "citations_12m": sum(cites),
        "facilities_with_citations_12m": sum(1 for c in cites if c),
        "licensees_3plus": len(owner_groups(facilities)),
        "new_licenses_12m": new_12m,
        "closures_12m": closed_12m,
        "net_change_12m": new_12m - closed_12m,
        "growth_rate_12m": rate(new_12m, len(lic)),
        "churn_rate_12m": rate(closed_12m, len(lic)),
        "probation_share": rate(probation, len(lic) + probation),
        "share_licensed_multi": rate(sum(f.number in multi for f in lic), len(lic)),
    }


def activity(current, prior, keep=lambda f: True):
    """Snapshot-to-snapshot changes, keyed on Facility Number.

    keep() picks the facilities to count, judged on the current record (the prior record for
    facilities no longer listed), so a home that changes size or type is not counted as new.
    """
    before = {f.number: f for f in prior}
    now = {f.number: f for f in current}
    both = [(before[n], f) for n, f in now.items() if n in before and keep(f)]
    sub_up = [(b, a) for b, a in both if a.substantiated_allegations > b.substantiated_allegations]
    cv_up = [(b, a) for b, a in both if a.complaint_visits > b.complaint_visits]
    return {
        "closures_status_changed": sum(b.status != CLOSED and a.status == CLOSED and a.license_first_date is not None
                                       for b, a in both),
        "new_facility_numbers": sum(n not in before and keep(f) for n, f in now.items()),
        "removed_facility_numbers": sum(n not in now and keep(f) for n, f in before.items()),
        "status_changes": sum(b.status != a.status for b, a in both),
        "ownership_changes": sum(b.licensee_key != a.licensee_key for b, a in both),
        "capacity_changes": sum(b.capacity != a.capacity for b, a in both),
        "facilities_new_substantiated": len(sub_up),
        "new_substantiated_allegations": sum(a.substantiated_allegations - b.substantiated_allegations
                                             for b, a in sub_up),
        "facilities_substantiated_decreased": sum(a.substantiated_allegations < b.substantiated_allegations
                                                  for b, a in both),
        "facilities_new_complaint_visits": len(cv_up),
        "new_complaint_visits": sum(a.complaint_visits - b.complaint_visits for b, a in cv_up),
    }


def county_table(current, as_of, prior=None, prior_as_of=None, keep=lambda f: True,
                 multi=(frozenset(), frozenset())):
    """One row per county: the same totals, week-over-week change and activity as statewide."""
    cur_by = defaultdict(list)
    for f in current:
        cur_by[f.county or "(BLANK)"].append(f)
    pri_by = defaultdict(list)
    numbers_now = {f.number: f.county or "(BLANK)" for f in current}
    for f in prior or []:
        # A facility is counted in the county it is in now; one no longer listed, where it was.
        pri_by[numbers_now.get(f.number, f.county or "(BLANK)")].append(f)
    rows = []
    for county in sorted(set(cur_by) | set(pri_by)):
        cur = [f for f in cur_by[county] if keep(f)]
        pri = [f for f in pri_by[county] if keep(f)] if prior is not None else None
        if not cur and not pri:
            continue
        t = totals(cur, as_of, multi[0])
        pt = totals(pri, prior_as_of, multi[1]) if pri is not None else None
        bands = Counter(band(f) for f in licensed(cur))
        rows.append({
            "county": county,
            **t,
            "week_over_week": {k: (None if pt is None or t[k] is None or pt[k] is None else t[k] - pt[k])
                               for k in TOTAL_KEYS},
            "activity": activity(cur_by[county], pri_by[county], keep) if prior is not None else None,
            "licensed_by_band": {k: bands[k] for k, *_ in BANDS},
        })
    return rows


def band_table(facilities, as_of):
    """Statewide rows for each capacity band."""
    rows = []
    for key, label, *_ in BANDS:
        fs = [f for f in facilities if band(f) == key]
        lic = licensed(fs)
        rows.append({
            "band": key,
            "label": label,
            "licensed_facilities": len(lic),
            "licensed_beds": sum(f.capacity or 0 for f in lic),
            "new_licenses_90d": sum(in_window(f.license_first_date, as_of, 90) for f in fs),
            "closures_closed_date_90d": sum(is_closure(f, as_of, 90) for f in fs),
        })
    return rows


def owners(facilities):
    out = []
    for key, homes in owner_groups(facilities).items():
        names = Counter(f.public_licensee for f in homes)
        withheld = any(f.licensee_withheld for f in homes)
        sizes = Counter(size_group(f) for f in homes)
        out.append({
            "licensee": WITHHELD if withheld else names.most_common(1)[0][0],
            "licensee_withheld": withheld,
            "name_variants": [] if withheld else sorted(names),
            "licensed_homes": len(homes),
            "licensed_homes_small": sizes["small"],
            "licensed_homes_large": sizes["large"],
            "licensed_beds": sum(f.capacity or 0 for f in homes),
            "counties": sorted({f.county for f in homes}),
            "statuses": dict(Counter(f.status for f in facilities if f.licensee_key == key)),
        })
    return sorted(out, key=lambda o: (-o["licensed_homes"], o["licensee"]))


def segment(current, as_of, prior, prior_as_of, keep, multi):
    cur = [f for f in current if keep(f)]
    pri = [f for f in prior if keep(f)] if prior is not None else None
    t = totals(cur, as_of, multi[0])
    pt = totals(pri, prior_as_of, multi[1]) if pri is not None else None
    return {
        "row_count": len(cur),
        "totals": t,
        "week_over_week": {k: (None if pt is None or t[k] is None or pt[k] is None else t[k] - pt[k])
                           for k in TOTAL_KEYS},
        "activity": activity(current, prior, keep) if prior is not None else None,
        "counties": county_table(current, as_of, prior, prior_as_of, keep, multi),
    }


def compute(current, as_of: date, prior=None, prior_as_of: date = None):
    """All Step 2 metrics for each scope and size group, with week-over-week change where possible."""
    result = {"as_of": as_of.isoformat(), "prior_as_of": prior_as_of.isoformat() if prior_as_of else None,
              "headline_scope": HEADLINE_SCOPE, "small_base": SMALL_BASE, "scopes": {}}
    multi = (multi_home_numbers(current), multi_home_numbers(prior) if prior is not None else frozenset())
    for scope, (label, in_scope) in SCOPES.items():
        seg = segment(current, as_of, prior, prior_as_of, in_scope, multi)
        seg["label"] = label
        seg["by_size"] = {}
        for size, (size_label, in_size) in SIZES.items():
            sub = segment(current, as_of, prior, prior_as_of,
                          lambda f, a=in_scope, b=in_size: a(f) and b(f), multi)
            sub["label"] = size_label
            seg["by_size"][size] = sub
        seg["bands"] = band_table([f for f in current if in_scope(f)], as_of)
        result["scopes"][scope] = seg
    return result
