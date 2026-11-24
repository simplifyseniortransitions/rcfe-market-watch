"""California RCFE Weekly Movers: every rule, threshold and fixed wording in one place.

Change a threshold here, not in the comparison code. Each one says why it has its starting value.
Starting values come from the first 6 weekly comparisons (Oct 11 to Nov 22, 2026), set at roughly three
times the largest week seen. Once BASELINE_MIN_WEEKS comparisons exist, a statewide, county or city
threshold becomes "BASELINE_MULTIPLIER times the median of recent weeks", never lower than the floor here.
"""
from pathlib import Path

LABEL = "California RCFE Weekly Movers"
METHODOLOGY_VERSION = "1.0"
SCHEMA = "weekly-movers/1"
SOURCE_NAME = ("California Department of Social Services, Community Care Licensing Division: "
               "Residential Care Facilities for the Elderly licensing file (CC BY)")

# Active = the record's Facility Status is one of these (the same rule as the Top California RCFE Markets
# rankings). Pending applications and closed records are not active.
ACTIVE_STATUSES = ("LICENSED", "ON PROBATION")

# Review states. Only an explicit action in the review screen moves a report out of draft or held.
DRAFT, HELD, APPROVED, REJECTED, SUPERSEDED = "draft", "held", "approved", "rejected", "superseded"
STATE_LABELS = {DRAFT: "Draft", HELD: "Held for data review", APPROVED: "Approved", REJECTED: "Rejected",
                SUPERSEDED: "Superseded"}

# Comparison period: the two files must be about a week apart.
GAP_DAYS = (6, 8)

# Percentage changes are only shown when the previous value is at least this.
PCT_MIN_BASE = 10

# How many movers each list keeps.
TOP_N = 10

# --- Statewide and area thresholds: a trip holds the WHOLE report (statewide) or the area row (city/county).
THRESHOLDS = {
    "statewide_net_active": {
        "floor": 40, "why": "Largest weekly net change in the first 6 weeks was 13."},
    "statewide_newly_or_no_longer": {
        "floor": 60, "why": "Largest weekly count of newly observed or no longer active records was 26."},
    "statewide_net_capacity": {
        "floor": 1500, "why": "Largest weekly net change in recorded capacity was 294."},
    "county_net_active": {
        "floor": 15, "why": "Largest weekly net change in one county was 6."},
    "city_net_active": {
        "floor": 10, "why": "Largest weekly net change in one city was 4."},
}
BASELINE_MIN_WEEKS = 12
BASELINE_MULTIPLIER = 4
BASELINE_WEEKS = 12

# --- File-level checks: any trip holds the whole report.
MAX_ROW_CHANGE = 0.02          # weekly row-count change has stayed under 0.2%; validation already fails at a 10% drop
MAX_ACTIVE_MISSING_FIELDS = 5  # active records with a blank city, county or capacity (1 so far: a blank county)
MAX_NEW_SHARED_ADDRESSES = 5   # addresses holding 2+ active records that didn't last week (52 shared, stable)
MAX_LABEL_CHANGES = 10         # matched records whose city or county label changed (0-1 a week so far)

# --- Facility-level checks: a trip holds only that finding.
LARGE_CAPACITY_CHANGE = 50        # beds, either way
LARGE_CAPACITY_SHARE = 0.5        # or this share of the old capacity...
LARGE_CAPACITY_SHARE_MIN_BASE = 7  # ...for homes of 7 or more
OLDER_LICENSE_DAYS = 60   # newly observed, but License First Date is older than this
LATE_CLOSURE_DAYS = 30    # no longer active, but Closed Date is older than this

# Finding flags. Every flag marks the finding "Requires verification" and holds it from the public report
# until the reviewer includes it.
FLAGS = {
    "older_license": "Newly observed, but the license was first issued more than {days} days earlier",
    "reappeared": "Returned after being missing from at least one earlier file",
    "first_time_in_file": "Facility Number appears in the file for the first time already licensed",
    "missing_from_file": "No longer in the CDSS file at all (it did not turn CLOSED)",
    "late_closure": "Closed Date is more than {days} days before this file",
    "large_capacity_change": "Unusually large change in recorded licensed capacity",
    "possible_relicensing": "A record left and another appeared at the same address or with the same name",
    "possible_duplicate": "Shares an address with another active record, new this week",
    "city_changed_same_address": "City changed while the street address stayed the same",
    "county_changed_same_address": "County changed while the street address stayed the same",
    "missing_required_field": "City, county or capacity is blank",
    "large_area_change": "Unusually large change for this area compared with recent weeks",
}

# Safe wording, used everywhere. The report never says opened, closed, sold, acquired or saturated.
CHANGE_LABELS = {
    "newly_observed": "Newly observed in the active dataset",
    "no_longer_active": "No longer appearing in the active dataset",
    "capacity_increase": "Recorded licensed capacity increased",
    "capacity_decrease": "Recorded licensed capacity decreased",
    "name_change": "Facility record changed: name",
    "address_change": "Facility record changed: street address",
    "city_change": "Facility record changed: city",
    "county_change": "Facility record changed: county",
    "status_change": "Facility record changed: status",
    "possible_relicensing": "Possible rename or relicensing",
    "possible_duplicate": "Possible duplicate",
}
FORBIDDEN_WORDS = ("newly opened", "permanently closed", "sold", "acquired", "changed ownership", "failed",
                   "saturated", "best market", "worst market", "undersupplied", "oversupplied", "profitable")

DISCLAIMER = (
    "California RCFE Weekly Movers reports changes observed between two weekly California Department of Social "
    "Services (CDSS) Community Care Licensing files. A newly observed record does not necessarily mean a facility "
    "opened, and a record no longer appearing as active does not by itself confirm that a facility closed. "
    "Recorded licensed capacity is the license limit, not occupancy. Facility counts and changes do not show "
    "market saturation, demand, occupancy, profitability or investment quality. Record errors can only be "
    "corrected by CDSS. General education only; not legal, financial or investment advice."
)
SPOKEN_DISCLAIMER = (
    "These are changes observed in the latest California CDSS dataset. A newly observed record does not "
    "necessarily mean a facility opened this week, and a record no longer appearing as active does not by itself "
    "confirm that the facility closed."
)
LIMITATIONS = [
    "Weekly history starts with the Oct 11, 2026 file, so \"first observed\" cannot be earlier than that date.",
    "CDSS sometimes leaves records out of a file and adds them back later; a newly observed record does not "
    "necessarily mean a facility opened.",
    "CDSS sometimes records a closure weeks or months after it happened; a record no longer appearing as active "
    "is not a closure this week.",
    "Cities are CDSS mailing cities with known spelling errors corrected. They are not the official Census places "
    "used by the Top California RCFE Markets rankings.",
    "Counties are the CDSS county labels, as on the Market Watch county table. A small number are known to be "
    "wrong at the source.",
    "Recorded licensed capacity is the license limit, not occupancy, staffing or demand.",
]
CITY_NOTE = ("City = the CDSS mailing city with known spelling errors corrected; not the Census place used "
             "by the Top California RCFE Markets rankings.")

MARKET_WATCH_URL = "https://rcfedealroom.com/market-watch"
# The free community is not launched yet. Leave None until Dale approves the link.
COMMUNITY_URL = None

ANALYTICS_EVENTS = ("weekly_movers_viewed", "weekly_movers_period_changed", "weekly_movers_methodology_viewed",
                    "weekly_movers_news_brief_copied")

# Where reports live: the private data repository's movers/ folder. In the weekly job that repository is
# checked out at private-data/; on this Mac the review screen uses a git-ignored clone in the same place.
DEFAULT_STORE = Path(__file__).resolve().parent.parent.parent / "private-data" / "movers"
