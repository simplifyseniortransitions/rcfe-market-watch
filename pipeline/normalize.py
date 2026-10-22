"""Turn raw CSV rows into Facility records. Private columns are dropped here and never leave this module."""
import dataclasses
import re
from dataclasses import dataclass
from typing import Optional

from pipeline.validate import OVERFLOW_KEY, parse_date

CORE_TYPE = "RESIDENTIAL CARE ELDERLY"
CCRC_TYPE = "RCFE-CONTINUING CARE RETIREMENT COMMUNITY"
# Every facility type value seen in the state file. A blank type (pending applications the state has
# not typed yet) is counted with regular RCFEs (Dale, 2026-10-22).
CORE_TYPES = {CORE_TYPE, ""}
KNOWN_TYPES = CORE_TYPES | {CCRC_TYPE}
CLOSED = "CLOSED"
LICENSED = "LICENSED"
PENDING = "PENDING"
ON_PROBATION = "ON PROBATION"

COMPLAINT_INFO_PREFIX = "Complaint Info"
ADMINISTRATOR_COLUMN = "Facility Administrator"
# Shown instead of a licensee name that is also an administrator's name (Dale, 2026-10-21).
# The real name is still used, in memory only, for matching and counting.
WITHHELD = "Name withheld (individual licensee)"
# Shown instead of a facility name that is an administrator's name, e.g. a home listed under its
# operator's own name (Dale, 2026-10-22).
NAME_WITHHELD = "Name withheld (individual)"

COMPLAINT_GROUP = 7  # Date, #Sub A, #Inc A, #Uns A, #Unf A, #TypeA, #TypeB


@dataclass(frozen=True)
class Complaint:
    date: object
    substantiated: int
    inconclusive: int
    unsubstantiated: int
    unfounded: int
    type_a: int
    type_b: int


@dataclass(frozen=True)
class Facility:
    number: str
    name: str
    licensee: str          # display form: trimmed, single-spaced
    licensee_key: str      # match key: display form, upper case
    facility_type: str
    status: str
    county: str
    city: str
    capacity: Optional[int]  # None when blank or non-numeric
    license_first_date: object
    closed_date: object
    last_visit_date: object
    total_visits: int
    complaint_visits: int
    substantiated_allegations: int
    citation_numbers: tuple
    poc_dates: tuple
    complaints: Optional[tuple]  # None when the complaint detail could not be parsed
    licensee_withheld: bool = False  # licensee name matches an administrator name
    name_withheld: bool = False      # facility name matches an administrator name

    @property
    def public_name(self):
        return NAME_WITHHELD if self.name_withheld else self.name

    @property
    def public_licensee(self):
        return WITHHELD if self.licensee_withheld else self.licensee

    @property
    def is_core(self):
        return self.facility_type in CORE_TYPES


def clean_text(value):
    return " ".join((value or "").split())


def to_int(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def to_count(value):
    return to_int(value) or 0


def split_list(value):
    return tuple(t.strip() for t in (value or "").split(",") if t.strip())


def date_list(value):
    """Dates from a comma-separated list; stray non-date tokens are skipped."""
    out = []
    for token in split_list(value):
        try:
            out.append(parse_date(token))
        except ValueError:
            pass
    return tuple(out)


def parse_complaints(row, complaint_col):
    if complaint_col is None:
        return None
    tokens = [(row.get(complaint_col) or "").strip()] + [t.strip() for t in (row.get(OVERFLOW_KEY) or [])]
    while tokens and tokens[-1] == "":
        tokens.pop()
    if tokens in ([], ["No Complaints"]):
        return ()
    if len(tokens) % COMPLAINT_GROUP:
        return None
    complaints = []
    for i in range(0, len(tokens), COMPLAINT_GROUP):
        group = tokens[i:i + COMPLAINT_GROUP]
        try:
            when = parse_date(group[0])
        except ValueError:
            return None
        counts = [to_int(t) for t in group[1:]]
        if when is None or None in counts:
            return None
        complaints.append(Complaint(when, *counts))
    return tuple(complaints)


def name_words(name):
    """A person's name as a set of words, so "RIVERA, MORGAN" and "Morgan Rivera" match.

    Initials and punctuation are ignored. Names with fewer than two words give None (never matched).
    """
    words = frozenset(w for w in re.split(r"[^A-Z'-]+", (name or "").upper()) if len(w.strip("'-")) > 1)
    return words if len(words) >= 2 else None


def administrator_keys(rows):
    """Administrator names as word sets. Used only, in memory, to withhold matching licensee names."""
    return {k for k in (name_words(r.get(ADMINISTRATOR_COLUMN)) for r in rows) if k}


def withhold(facilities, admin_keys):
    """Mark facilities whose licensee name or facility name has the same words as an administrator name."""
    return [dataclasses.replace(f, licensee_withheld=f.licensee_withheld or name_words(f.licensee) in admin_keys,
                                name_withheld=f.name_withheld or name_words(f.name) in admin_keys)
            for f in facilities]


def normalize(header, rows):
    admin_keys = administrator_keys(rows)
    complaint_col = next((h for h in header if h.startswith(COMPLAINT_INFO_PREFIX)), None)
    facilities = []
    for r in rows:
        licensee = clean_text(r.get("Licensee"))
        facilities.append(Facility(
            number=r["Facility Number"].strip(),
            name=clean_text(r.get("Facility Name")),
            licensee=licensee,
            licensee_key=licensee.upper(),
            facility_type=clean_text(r.get("Facility Type")).upper(),
            status=clean_text(r.get("Facility Status")).upper(),
            county=clean_text(r.get("County Name")).upper(),
            city=clean_text(r.get("Facility City")).upper(),
            capacity=to_int(r.get("Facility Capacity")),
            license_first_date=parse_date(r.get("License First Date")),
            closed_date=parse_date(r.get("Closed Date")),
            last_visit_date=parse_date(r.get("Last Visit Date")),
            total_visits=to_count(r.get("Total Visits")),
            complaint_visits=to_count(r.get("Complaint Visits")),
            substantiated_allegations=to_count(r.get("Substantiated Allegations")),
            citation_numbers=split_list(r.get("Citation Numbers")),
            poc_dates=date_list(r.get("POC Dates")),
            complaints=parse_complaints(r, complaint_col),
            licensee_withheld=name_words(licensee) in admin_keys,
            name_withheld=name_words(r.get("Facility Name")) in admin_keys,
        ))
    return facilities
