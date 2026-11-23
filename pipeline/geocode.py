"""Geocode cache for the members' map (private; nothing here is ever written to site/).

Each standardized address (pipeline/address.py) is geocoded once and its coordinates kept in
geocache/addresses.csv. A later week only looks up addresses the cache hasn't seen, or ones that
failed and are due for another try.

    python -m pipeline.geocode                      geocode not-closed facilities in the newest snapshot
    python -m pipeline.geocode --snapshot X.csv     a specific snapshot
    python -m pipeline.geocode --limit 50           only the first 50 new addresses (a test run)
    python -m pipeline.geocode --dry-run            count what would be looked up; no network
"""
import argparse
import csv
import io
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from pipeline import config
from pipeline.address import Address, from_row
from pipeline.snapshot import list_snapshots
from pipeline.validate import read_csv

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
CENSUS_BENCHMARK = "Public_AR_Current"
USER_AGENT = "RCFE-Market-Watch/1.0 (members' map geocoding; github.com/simplifyseniortransitions/rcfe-market-watch)"
CHUNK = 2000            # the Census limit is 10,000 per file; smaller files finish faster and fail smaller
PAUSE_SECONDS = 5       # between files, to be polite to a free service
RETRY_DAYS = (7, 14, 28, 56)  # wait after the 1st, 2nd, 3rd and later failed lookups

FIELDS = ["address_key", "street", "unit", "city", "zip5", "lat", "lon", "source", "match_quality",
          "matched_address", "first_geocoded", "last_checked", "attempts", "last_error", "retry_after"]
OVERRIDE_FIELDS = ["facility_number", "address_key", "lat", "lon", "reason", "set_by", "set_on"]


@dataclass
class Result:
    key: str
    lat: str = ""
    lon: str = ""
    quality: str = "none"     # exact, approximate, tie, none
    matched: str = ""
    error: str = ""


class GeocodeError(Exception):
    """The geocoder couldn't be reached or answered with something unreadable."""


# ---- cache files ----

def load_rows(path: Path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_cache(folder: Path):
    return {r["address_key"]: r for r in load_rows(folder / "addresses.csv")}


def load_overrides(folder: Path):
    """Manual corrections; they always win over the geocoder when the map file is built."""
    return load_rows(folder / "overrides.csv")


def save_cache(folder: Path, cache):
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "addresses.csv.tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for k in sorted(cache):
            w.writerow({f_: cache[k].get(f_, "") for f_ in FIELDS})
    tmp.replace(folder / "addresses.csv")
    overrides = folder / "overrides.csv"
    if not overrides.exists():
        with open(overrides, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(OVERRIDE_FIELDS)


def needs_lookup(entry, today: date) -> bool:
    """New address, or a failed one whose wait is over. A placed address is never looked up again."""
    if entry is None:
        return True
    if entry.get("lat") and entry.get("lon"):
        return False
    retry = entry.get("retry_after") or ""
    return not retry or date.fromisoformat(retry) <= today


def record(cache, address: Address, result: Result, source: str, today: date):
    old = cache.get(address.key, {})
    attempts = int(old.get("attempts") or 0) + 1
    placed = bool(result.lat and result.lon)
    cache[address.key] = {
        "address_key": address.key, "street": address.street, "unit": address.unit, "city": address.city,
        "zip5": address.zip5, "lat": result.lat, "lon": result.lon, "source": source if placed else "",
        "match_quality": result.quality, "matched_address": result.matched,
        "first_geocoded": old.get("first_geocoded") or (today.isoformat() if placed else ""),
        "last_checked": today.isoformat(), "attempts": str(attempts), "last_error": result.error,
        "retry_after": "" if placed else (today + timedelta(days=RETRY_DAYS[min(attempts, len(RETRY_DAYS)) - 1])).isoformat(),
    }


# ---- Census batch geocoder ----

def census_request_body(records):
    """(body bytes, content type) for one batch file: id, street (no unit), city, state, ZIP."""
    rows = io.StringIO()
    w = csv.writer(rows, lineterminator="\n")
    for rid, a in records:
        w.writerow([rid, a.street, a.city, "CA", a.zip5])
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="benchmark"\r\n\r\n{CENSUS_BENCHMARK}\r\n'.encode(),
        f'--{boundary}\r\nContent-Disposition: form-data; name="addressFile"; filename="addresses.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n".encode() + rows.getvalue().encode() + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def parse_census(text, ids_to_keys):
    """Results from the Census answer: "id","input","Match|No_Match|Tie","Exact|Non_Exact","matched","lon,lat",…"""
    out = {}
    for row in csv.reader(io.StringIO(text)):
        if not row or row[0] not in ids_to_keys:
            continue
        key = ids_to_keys[row[0]]
        status = row[2].strip() if len(row) > 2 else ""
        if status == "Match" and len(row) >= 6 and "," in row[5]:
            lon, lat = (v.strip() for v in row[5].split(",", 1))
            quality = "exact" if row[3].strip() == "Exact" else "approximate"
            out[key] = Result(key, f"{float(lat):.6f}", f"{float(lon):.6f}", quality, row[4].strip())
        elif status == "Tie":
            out[key] = Result(key, quality="tie", error="more than one possible match")
        else:
            out[key] = Result(key, quality="none", error="no match")
    return out


class CensusGeocoder:
    source = "census"

    def __init__(self, timeout=900):
        self.timeout = timeout

    def geocode(self, addresses):
        """{key: Result} for a list of Address. Raises GeocodeError if the service can't be used."""
        ids = {str(i): a.key for i, a in enumerate(addresses, start=1)}
        body, ctype = census_request_body([(str(i), a) for i, a in enumerate(addresses, start=1)])
        req = urllib.request.Request(CENSUS_URL, data=body, method="POST",
                                     headers={"Content-Type": ctype, "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
        except OSError as e:
            raise GeocodeError(f"Census geocoder unavailable: {e}") from e
        results = parse_census(text, ids)
        if addresses and not results:
            raise GeocodeError("Census geocoder answered with no readable results")
        return results


# ---- one run ----

def addresses_to_geocode(rows, cache, today):
    """(all addresses by key, keys that need a lookup) for not-closed facilities with a usable address."""
    by_key = {}
    for r in rows:
        if (r.get("Facility Status") or "").strip().upper() == "CLOSED":
            continue
        a = from_row(r)
        if a.key and a.zip5:
            by_key.setdefault(a.key, a)
    todo = [k for k in sorted(by_key) if needs_lookup(cache.get(k), today)]
    return by_key, todo


def run(rows, folder: Path, geocoder, today: date, limit=None, chunk=CHUNK, pause=PAUSE_SECONDS, log=print):
    """Geocode what's new, saving the cache after every batch file. Returns a summary dict."""
    cache = load_cache(folder)
    by_key, todo = addresses_to_geocode(rows, cache, today)
    todo = todo[:limit] if limit else todo
    summary = {"addresses": len(by_key), "already_cached": len(by_key) - len(todo), "looked_up": 0,
               "errors": []}
    for start in range(0, len(todo), chunk):
        batch = [by_key[k] for k in todo[start:start + chunk]]
        log(f"geocoding {start + 1}-{start + len(batch)} of {len(todo)}…")
        try:
            results = geocoder.geocode(batch)
        except GeocodeError as e:
            # Nothing is recorded for this batch, so it's simply tried again next time.
            summary["errors"].append(str(e))
            log(f"  skipped: {e}")
            continue
        for a in batch:
            record(cache, a, results.get(a.key, Result(a.key, error="missing from answer")), geocoder.source, today)
        summary["looked_up"] += len(batch)
        save_cache(folder, cache)
        if pause and start + chunk < len(todo):
            time.sleep(pause)
    save_cache(folder, cache)
    return summary


def coverage(rows, folder: Path):
    """Placement counts for not-closed facilities (by facility, not address), using cache and overrides."""
    cache = load_cache(folder)
    overridden = {o["facility_number"] for o in load_overrides(folder) if o.get("facility_number")}
    counts = {"facilities": 0, "no_usable_address": 0, "exact": 0, "approximate": 0, "tie": 0, "none": 0,
              "not_yet_looked_up": 0, "manual": 0}
    for r in rows:
        if (r.get("Facility Status") or "").strip().upper() == "CLOSED":
            continue
        counts["facilities"] += 1
        a = from_row(r)
        if r["Facility Number"].strip() in overridden:
            counts["manual"] += 1
        elif not (a.key and a.zip5):
            counts["no_usable_address"] += 1
        elif a.key not in cache:
            counts["not_yet_looked_up"] += 1
        else:
            counts[cache[a.key].get("match_quality") or "none"] += 1
    return counts


def main(argv=None, paths=config.DEFAULT_PATHS):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", type=Path)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    snap = args.snapshot or (list_snapshots(paths.snapshots)[-1][1] if list_snapshots(paths.snapshots) else None)
    if not snap:
        print("No snapshot found.")
        return 1
    _, rows = read_csv(snap)
    today = date.today()
    if args.dry_run:
        by_key, todo = addresses_to_geocode(rows, load_cache(paths.geocache), today)
        print(f"{snap.name}: {len(by_key)} addresses, {len(todo)} would be looked up")
        return 0
    summary = run(rows, paths.geocache, CensusGeocoder(), today, limit=args.limit)
    print(summary)
    print(coverage(rows, paths.geocache))
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
