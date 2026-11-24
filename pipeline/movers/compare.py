"""California RCFE Weekly Movers: compare two weekly CDSS snapshots.

Matching (methodology 1.0):
  1. High-confidence match: the same Facility Number in both files. Each changed field is its own finding.
  2. Probable match requiring review: a record no longer active and a newly observed record at the same
     standardized street address, or with the same name in the same city. Shown as "Possible rename or
     relicensing". Never merged: both records stay in every count.
  3. Unmatched: everything else.
  4. Possible duplicate: two or more active records at one standardized address, or with the same name in the
     same city, that were not shared the week before.
Address wording that standardizes to the same address (STREET vs ST, upper/lower case) is not a change.

Street addresses are kept only under a finding's "private" key, for the review screen. They never reach a
public file. Facility names that are an administrator's name are withheld, as on Market Watch.
"""
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from pipeline import config as pipeline_config
from pipeline.address import from_row
from pipeline.cities import mailing_city
from pipeline.movers import config as C
from pipeline.normalize import NAME_WITHHELD, administrator_keys, clean_text, name_words
from pipeline.snapshot import list_snapshots, sha256
from pipeline.validate import parse_date, read_csv

COUNTY_NOT_LISTED = "COUNTY NOT LISTED"
CITY_NOT_LISTED = "CITY NOT LISTED"


@dataclass(frozen=True)
class Rec:
    number: str
    name: str            # public form: withheld when it is an administrator's name
    name_key: str        # upper case, letters and digits only, for matching
    city: str            # cleaned mailing city (blank stays blank)
    county: str
    street: str          # private: standardized street line
    address_key: str     # private: street|city|zip5
    zip5: str
    capacity: Optional[int]
    status: str
    license_first: Optional[date]
    closed: Optional[date]

    @property
    def active(self):
        return self.status in C.ACTIVE_STATUSES


@dataclass
class Snapshot:
    snapshot_id: str
    as_of: date
    path: Path
    header: list
    records: dict          # number -> Rec (every status)
    row_count: int
    sha256: str

    @property
    def active(self):
        return {n: r for n, r in self.records.items() if r.active}


def _key(text):
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def _date(value):
    try:
        return parse_date(value)
    except ValueError:
        return None


def _cap(value):
    value = (value or "").strip()
    return int(value) if value.isdigit() else None


def load(as_of: date, path: Path) -> Snapshot:
    header, rows = read_csv(path)
    admins = administrator_keys(rows)
    records = {}
    for r in rows:
        number = (r.get("Facility Number") or "").strip()
        if not number:
            continue
        addr = from_row(r)
        name = clean_text(r.get("Facility Name"))
        status = clean_text(r.get("Facility Status")).upper()
        records[number] = Rec(
            number=number,
            name=NAME_WITHHELD if name_words(name) in admins else name,
            name_key=_key(name),
            city=mailing_city(addr.city) if addr.city else "",
            county=clean_text(r.get("County Name")).upper(),
            street=addr.street, address_key=addr.key, zip5=addr.zip5,
            capacity=_cap(r.get("Facility Capacity")),
            status=status,
            license_first=_date(r.get("License First Date")),
            closed=_date(r.get("Closed Date")),
        )
    return Snapshot(as_of.isoformat(), as_of, path, header, records, len(rows), sha256(path))


def numbers_in(path: Path):
    """Facility Numbers in a snapshot, any status (for first and last observed)."""
    _, rows = read_csv(path)
    return {(r.get("Facility Number") or "").strip() for r in rows} - {""}


# ---------------------------------------------------------------------------------------------- selection
def select(snapshot_dir: Path, as_of: Optional[date] = None):
    """(current, previous, problems). Snapshots in snapshots/ have all passed validation; rejected files live in
    snapshots/rejected/ and are never listed. Never skips back past the immediately preceding file."""
    snaps = list_snapshots(snapshot_dir)
    problems = []
    if as_of is not None:
        snaps = [s for s in snaps if s[0] <= as_of]
        if not snaps or snaps[-1][0] != as_of:
            return None, None, [f"No saved weekly snapshot for {as_of.isoformat()}."]
    if not snaps:
        return None, None, ["No saved weekly snapshots."]
    current = snaps[-1]
    previous = snaps[-2] if len(snaps) > 1 else None
    if previous is None:
        problems.append("There is no earlier weekly snapshot to compare with.")
    else:
        gap = (current[0] - previous[0]).days
        lo, hi = C.GAP_DAYS
        if not lo <= gap <= hi:
            problems.append(f"The two files are {gap} days apart, not about a week"
                            + (" (a weekly file appears to be missing)." if gap > hi else "."))
    return current, previous, problems


def processing_dates(qa_report: dict):
    """snapshot_id -> generated_at of the latest passing run for that file."""
    out = {}
    for run in (qa_report or {}).get("runs", []):
        if run.get("status") == "pass" and run.get("as_of"):
            out[run["as_of"]] = run.get("generated_at")
    return out


# ---------------------------------------------------------------------------------------------- comparison
def pct(prev, change):
    if prev is None or prev < C.PCT_MIN_BASE:
        return None
    return round(100.0 * change / prev, 1)


def _finding(kind, rec, prev_value, cur_value, **extra):
    return {
        "id": f"{kind}:{rec.number}",
        "change_type": kind,
        "change_label": C.CHANGE_LABELS[kind],
        "facility_number": rec.number,
        "facility_name": rec.name,
        "city": rec.city or CITY_NOT_LISTED,
        "county": rec.county or COUNTY_NOT_LISTED,
        "previous": prev_value,
        "current": cur_value,
        "match_confidence": extra.pop("confidence", "high"),
        "flags": extra.pop("flags", []),
        "contributes_to": extra.pop("contributes_to", None),
        "private": extra.pop("private", {}),
        **extra,
    }


def _large_capacity(old, new):
    if old is None or new is None:
        return False
    d = abs(new - old)
    return d >= C.LARGE_CAPACITY_CHANGE or (old >= C.LARGE_CAPACITY_SHARE_MIN_BASE
                                            and d >= C.LARGE_CAPACITY_SHARE * old)


def _shared(records, key):
    groups = defaultdict(list)
    for r in records.values():
        k = key(r)
        if k:
            groups[k].append(r.number)
    return {k: tuple(sorted(v)) for k, v in groups.items() if len(v) > 1}


def compare(prev: Snapshot, cur: Snapshot, presence=None):
    """Facility-level findings between two snapshots. `presence` maps Facility Number -> sorted snapshot dates
    (ISO) it appears in, up to and including cur, for first and last observed."""
    presence = presence or {}
    A, B = prev.active, cur.active
    findings = []
    days = (cur.as_of - prev.as_of).days

    def observed(number):
        seen = presence.get(number) or []
        return {"first_observed": seen[0] if seen else None, "last_observed": seen[-1] if seen else None,
                "first_observed_is_earliest_file": bool(seen) and seen[0] == presence.get("__earliest__")}

    # Newly observed in the active dataset
    for n in sorted(set(B) - set(A)):
        r, before = B[n], prev.records.get(n)
        flags = []
        seen = presence.get(n) or []
        if before is None:
            if any(d < prev.snapshot_id for d in seen):
                flags.append("reappeared")
            else:
                flags.append("first_time_in_file")
        if r.license_first and (cur.as_of - r.license_first).days > C.OLDER_LICENSE_DAYS:
            flags.append("older_license")
        origin = f"{before.status} to {r.status}" if before else f"not in the previous file; now {r.status}"
        findings.append(_finding("newly_observed", r, before.status if before else None, r.status, flags=flags,
                                 status_origin=origin, capacity=r.capacity,
                                 license_first_date=r.license_first.isoformat() if r.license_first else None,
                                 contributes_to=["count", "capacity"], **observed(n),
                                 private={"street": r.street, "zip5": r.zip5}))

    # No longer appearing in the active dataset
    for n in sorted(set(A) - set(B)):
        r, after = A[n], cur.records.get(n)
        flags = []
        if after is None:
            flags.append("missing_from_file")
        elif after.closed and (cur.as_of - after.closed).days > C.LATE_CLOSURE_DAYS:
            flags.append("late_closure")
        shown = after or r
        findings.append(_finding("no_longer_active", shown, r.status, after.status if after else None,
                                 flags=flags, capacity=r.capacity,
                                 status_origin=f"{r.status} to {after.status}" if after else
                                 f"{r.status}; not in the current file",
                                 closed_date=after.closed.isoformat() if after and after.closed else None,
                                 last_observed_active=prev.snapshot_id,
                                 contributes_to=["count", "capacity"], **observed(n),
                                 private={"street": r.street, "zip5": r.zip5}))

    # Changes on records active in both files (high-confidence matches)
    for n in sorted(set(A) & set(B)):
        a, b = A[n], B[n]
        obs = observed(n)
        if a.capacity != b.capacity:
            kind = "capacity_increase" if (b.capacity or 0) > (a.capacity or 0) else "capacity_decrease"
            findings.append(_finding(kind, b, a.capacity, b.capacity,
                                     flags=["large_capacity_change"] if _large_capacity(a.capacity, b.capacity) else [],
                                     change=(b.capacity or 0) - (a.capacity or 0), contributes_to=["capacity"],
                                     **obs))
        if a.name_key != b.name_key:
            findings.append(_finding("name_change", b, a.name, b.name, **obs))
        if a.status != b.status:
            findings.append(_finding("status_change", b, a.status, b.status, **obs))
        same_street = a.street == b.street and bool(a.street)
        if a.street != b.street or a.zip5 != b.zip5:
            # The street line is private: the public files say only that it changed.
            findings.append(_finding("address_change", b, None, None, **obs, public=False,
                                     private={"previous": f"{a.street} {a.zip5}".strip(),
                                              "current": f"{b.street} {b.zip5}".strip()}))
        if a.city != b.city:
            findings.append(_finding("city_change", b, a.city or CITY_NOT_LISTED, b.city or CITY_NOT_LISTED,
                                     flags=["city_changed_same_address"] if same_street else [],
                                     contributes_to=["count", "capacity"], previous_city=a.city or CITY_NOT_LISTED,
                                     **obs))
        if a.county != b.county:
            findings.append(_finding("county_change", b, a.county or COUNTY_NOT_LISTED, b.county or COUNTY_NOT_LISTED,
                                     flags=["county_changed_same_address"] if same_street else [],
                                     contributes_to=["count", "capacity"],
                                     previous_county=a.county or COUNTY_NOT_LISTED, **obs))

    # Missing required fields on active records
    for n, r in sorted(B.items()):
        if not r.city or not r.county or r.capacity is None:
            for f in findings:
                if f["facility_number"] == n and "missing_required_field" not in f["flags"]:
                    f["flags"].append("missing_required_field")

    # Probable matches requiring review: one record left, another arrived at the same address or name+city.
    gone = {n: A[n] for n in set(A) - set(B)}
    came = {n: B[n] for n in set(B) - set(A)}
    for o, old in sorted(gone.items()):
        for nn, new in sorted(came.items()):
            same_addr = old.address_key and old.address_key == new.address_key
            same_name = old.name_key and old.name_key == new.name_key and old.city == new.city
            if same_addr or same_name:
                findings.append({
                    "id": f"possible_relicensing:{o}-{nn}", "change_type": "possible_relicensing",
                    "change_label": C.CHANGE_LABELS["possible_relicensing"],
                    "facility_number": nn, "facility_name": new.name, "city": new.city or CITY_NOT_LISTED,
                    "county": new.county or COUNTY_NOT_LISTED,
                    "previous": {"facility_number": o, "facility_name": old.name},
                    "current": {"facility_number": nn, "facility_name": new.name},
                    "match_confidence": "probable", "match_basis": "same street address" if same_addr else
                    "same name in the same city",
                    "flags": ["possible_relicensing"], "contributes_to": None, **observed(nn),
                    "private": {"street": new.street, "zip5": new.zip5},
                })
                for f in findings:
                    if f["change_type"] in ("newly_observed", "no_longer_active") and \
                            f["facility_number"] in (o, nn) and "possible_relicensing" not in f["flags"]:
                        f["flags"].append("possible_relicensing")
                        f["match_confidence"] = "probable"

    # Possible duplicates: shared address or same name+city among active records, new this week.
    reported = set()
    for label, key in (("same street address", lambda r: r.address_key),
                       ("same name in the same city", lambda r: f"{r.name_key}|{r.city}" if r.name_key else "")):
        before = set(_shared(A, key).values())
        for k, numbers in sorted(_shared(B, key).items()):
            if numbers in before or numbers in reported:
                continue
            reported.add(numbers)
            first = B[numbers[0]]
            findings.append({
                "id": f"possible_duplicate:{'-'.join(numbers)}", "change_type": "possible_duplicate",
                "change_label": C.CHANGE_LABELS["possible_duplicate"],
                "facility_number": numbers[0], "facility_name": first.name, "city": first.city or CITY_NOT_LISTED,
                "county": first.county or COUNTY_NOT_LISTED, "previous": None,
                "current": [{"facility_number": n, "facility_name": B[n].name} for n in numbers],
                "match_confidence": "possible_duplicate", "match_basis": label,
                "flags": ["possible_duplicate"], "contributes_to": None, **observed(numbers[0]),
                "private": {"street": first.street, "zip5": first.zip5},
            })
            for f in findings:
                if f["facility_number"] in numbers and f["change_type"] in ("newly_observed",) and \
                        "possible_duplicate" not in f["flags"]:
                    f["flags"].append("possible_duplicate")

    for f in findings:
        f["flags"] = sorted(set(f["flags"]))
        f["verification"] = "requires_verification" if f["flags"] else "routine"
        f["held"] = bool(f["flags"])
        f.setdefault("public", True)
    findings.sort(key=lambda f: (f["change_type"], f["county"], f["city"], f["facility_name"], f["id"]))
    return findings, days


# ---------------------------------------------------------------------------------------------- aggregation
def _area_totals(records, key):
    count, cap = Counter(), Counter()
    for r in records.values():
        k = key(r)
        count[k] += 1
        cap[k] += r.capacity or 0
    return count, cap


def areas(prev: Snapshot, cur: Snapshot, findings, kind):
    key = (lambda r: r.city or CITY_NOT_LISTED) if kind == "city" else (lambda r: r.county or COUNTY_NOT_LISTED)
    pc, pcap = _area_totals(prev.active, key)
    cc, ccap = _area_totals(cur.active, key)
    county_of = defaultdict(Counter)
    for r in list(cur.active.values()) + list(prev.active.values()):
        county_of[key(r)][r.county or COUNTY_NOT_LISTED] += 1
    contrib = defaultdict(list)
    for f in findings:
        if not f.get("contributes_to"):
            continue
        here = f["city"] if kind == "city" else f["county"]
        contrib[here].append(f["id"])
        old = f.get("previous_city") if kind == "city" else f.get("previous_county")
        if old and old != here:
            contrib[old].append(f["id"])
    rows = []
    for name in sorted(set(pc) | set(cc)):
        change, cap_change = cc[name] - pc[name], ccap[name] - pcap[name]
        if change == 0 and cap_change == 0 and not contrib.get(name):
            continue
        rows.append({
            "id": f"{kind}:{name}", "area": name, "kind": kind,
            "county": county_of[name].most_common(1)[0][0] if kind == "city" else name,
            "previous_count": pc[name], "current_count": cc[name], "count_change": change,
            "count_pct": pct(pc[name], change),
            "previous_capacity": pcap[name], "current_capacity": ccap[name], "capacity_change": cap_change,
            "capacity_pct": pct(pcap[name], cap_change),
            "record_count": len(set(contrib.get(name, []))), "finding_ids": sorted(set(contrib.get(name, []))),
            "flags": [], "held": False,
        })
    return rows


def movers(rows, n=C.TOP_N):
    def top(field, sign):
        chosen = [r for r in rows if (r[field] > 0 if sign > 0 else r[field] < 0)]
        chosen.sort(key=lambda r: (-sign * r[field], r["area"]))
        return [r["id"] for r in chosen[:n]]
    return {"count_increases": top("count_change", 1), "count_decreases": top("count_change", -1),
            "capacity_increases": top("capacity_change", 1), "capacity_decreases": top("capacity_change", -1)}


def statewide(prev: Snapshot, cur: Snapshot, findings, city_rows, county_rows):
    A, B = prev.active, cur.active
    pcap = sum(r.capacity or 0 for r in A.values())
    ccap = sum(r.capacity or 0 for r in B.values())
    kinds = Counter(f["change_type"] for f in findings)
    return {
        "previous_active": len(A), "current_active": len(B), "net_active_change": len(B) - len(A),
        "net_active_pct": pct(len(A), len(B) - len(A)),
        "newly_observed": kinds["newly_observed"], "no_longer_active": kinds["no_longer_active"],
        "previous_capacity": pcap, "current_capacity": ccap, "net_capacity_change": ccap - pcap,
        "net_capacity_pct": pct(pcap, ccap - pcap),
        "capacity_increases": kinds["capacity_increase"], "capacity_decreases": kinds["capacity_decrease"],
        "counties_with_count_change": sum(1 for r in county_rows if r["count_change"]),
        "cities_with_count_change": sum(1 for r in city_rows if r["count_change"]),
        "findings_held_for_review": sum(1 for f in findings if f["held"]),
        "possible_renames_or_duplicates": kinds["possible_relicensing"] + kinds["possible_duplicate"],
        "previous_rows": prev.row_count, "current_rows": cur.row_count,
    }


# ---------------------------------------------------------------------------------------------- checks
def threshold(name, history_values):
    """Floor, or BASELINE_MULTIPLIER x the median of recent weeks once there's enough history."""
    floor = C.THRESHOLDS[name]["floor"]
    recent = [abs(v) for v in history_values][-C.BASELINE_WEEKS:]
    if len(recent) >= C.BASELINE_MIN_WEEKS:
        return max(floor, C.BASELINE_MULTIPLIER * statistics.median(recent)), "baseline"
    return floor, "starting floor"


def checks(prev: Snapshot, cur: Snapshot, sw, findings, city_rows, county_rows, history, selection_problems):
    """Report-level checks. A failed check whose scope is 'report' holds the whole report."""
    out = []

    def add(code, passed, detail, scope="report", value=None, limit=None):
        out.append({"code": code, "passed": bool(passed), "detail": detail, "scope": scope,
                    "value": value, "threshold": limit})

    for p in selection_problems:
        add("comparison_period", False, p)
    if prev is None:
        return out
    gap = (cur.as_of - prev.as_of).days
    if not selection_problems:
        add("comparison_period", True, f"Files are {gap} days apart.", value=gap, limit=list(C.GAP_DAYS))
    missing_cols = [c for c in pipeline_config.REQUIRED_COLUMNS if c not in cur.header]
    add("required_columns", not missing_cols,
        "All required columns present." if not missing_cols else f"Missing columns: {', '.join(missing_cols)}.")
    schema_same = list(cur.header) == list(prev.header)
    added = [h for h in cur.header if h not in prev.header]
    removed = [h for h in prev.header if h not in cur.header]
    add("source_schema", schema_same, "Same columns as the previous file." if schema_same else
        f"Columns changed. Added: {', '.join(added) or 'none'}. Removed: {', '.join(removed) or 'none'}."
        + ("" if added or removed else " Column order changed."))
    row_change = (cur.row_count - prev.row_count) / prev.row_count if prev.row_count else 1.0
    add("source_row_count", abs(row_change) <= C.MAX_ROW_CHANGE,
        f"{prev.row_count:,} to {cur.row_count:,} rows ({row_change:+.2%}).", value=round(row_change, 4),
        limit=C.MAX_ROW_CHANGE)

    hist = lambda k: [h[k] for h in history]  # noqa: E731
    lim, basis = threshold("statewide_net_active", hist("net_active_change"))
    add("statewide_net_active", abs(sw["net_active_change"]) <= lim,
        f"Net change {sw['net_active_change']:+,} (limit ±{lim:g}, {basis}).", value=sw["net_active_change"], limit=lim)
    lim, basis = threshold("statewide_newly_or_no_longer",
                           hist("newly_observed") + hist("no_longer_active"))
    biggest = max(sw["newly_observed"], sw["no_longer_active"])
    add("statewide_newly_or_no_longer", biggest <= lim,
        f"{sw['newly_observed']} newly observed, {sw['no_longer_active']} no longer active (limit {lim:g}, {basis}).",
        value=biggest, limit=lim)
    lim, basis = threshold("statewide_net_capacity", hist("net_capacity_change"))
    add("statewide_net_capacity", abs(sw["net_capacity_change"]) <= lim,
        f"Net recorded capacity {sw['net_capacity_change']:+,} (limit ±{lim:g}, {basis}).",
        value=sw["net_capacity_change"], limit=lim)

    blanks = sum(1 for r in cur.active.values() if not r.city or not r.county or r.capacity is None)
    add("required_fields", blanks <= C.MAX_ACTIVE_MISSING_FIELDS,
        f"{blanks} active record(s) with a blank city, county or capacity.", value=blanks,
        limit=C.MAX_ACTIVE_MISSING_FIELDS)
    new_dupes = sum(1 for f in findings if f["change_type"] == "possible_duplicate")
    add("duplicate_rate", new_dupes <= C.MAX_NEW_SHARED_ADDRESSES,
        f"{new_dupes} new shared address or name group(s).", value=new_dupes, limit=C.MAX_NEW_SHARED_ADDRESSES)
    label_changes = sum(1 for f in findings if f["change_type"] in ("city_change", "county_change"))
    add("normalization_shift", label_changes <= C.MAX_LABEL_CHANGES,
        f"{label_changes} city or county label change(s) on matched records.", value=label_changes,
        limit=C.MAX_LABEL_CHANGES)

    # Area rows: a large move holds that row (and is shown as an anomaly), not the whole report.
    for rows, name, hist_key in ((county_rows, "county_net_active", "max_county_change"),
                                 (city_rows, "city_net_active", "max_city_change")):
        lim, basis = threshold(name, hist(hist_key))
        for r in rows:
            if abs(r["count_change"]) > lim:
                r["flags"] = ["large_area_change"]
                r["held"] = True
                add(name, False, f"{r['area'].title()}: {r['count_change']:+} (limit ±{lim:g}, {basis}).",
                    scope="area", value=r["count_change"], limit=lim)
    return out


def week_stats(sw, city_rows, county_rows):
    """The numbers later weeks use as their baseline."""
    return {"net_active_change": sw["net_active_change"], "newly_observed": sw["newly_observed"],
            "no_longer_active": sw["no_longer_active"], "net_capacity_change": sw["net_capacity_change"],
            "max_county_change": max([abs(r["count_change"]) for r in county_rows] or [0]),
            "max_city_change": max([abs(r["count_change"]) for r in city_rows] or [0])}
