"""Members' map file (private; never written to site/).

Built from the newest snapshot and the geocode cache. Holds street addresses and coordinates, so it goes
only to the members' storage bucket, never to the public site.

    python -m pipeline.mapdata                  geocode new addresses, then build the map file
    python -m pipeline.mapdata --no-geocode     build from the cache as it is (no network)

Writes mapbuild/map/v/<as-of>.json (one version per week, kept for rollback) and mapbuild/map/current.json
(a small pointer to it).
"""
import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from pipeline import cities, config, geocode, metrics, preview
from pipeline.address import from_row
from pipeline.counties import county_name
from pipeline.normalize import CLOSED, administrator_keys, normalize, withhold
from pipeline.snapshot import list_snapshots
from pipeline.validate import read_csv

GEOCODER = "U.S. Census Bureau Geocoder"
# The only facility fields the map file carries. No administrator, phone or raw state columns.
FACILITY_FIELDS = ["id", "name", "licensee", "street", "city", "zip", "county", "county_cdss", "status",
                   "capacity", "size", "type", "lat", "lon", "quality", "market_city_id", "market_city",
                   "market_city_kind"]


def build(paths: config.Paths, processed_at=None):
    """The map file as a dict, for not-closed facilities in the newest snapshot."""
    snaps = list_snapshots(paths.snapshots)
    if not snaps:
        raise ValueError("no snapshot found")
    admin_keys = set()
    for _, path in snaps[:-1]:
        admin_keys |= administrator_keys(read_csv(path)[1])
    as_of, newest = snaps[-1]
    header, rows = read_csv(newest)
    admin_keys |= administrator_keys(rows)
    facilities = withhold(normalize(header, rows), admin_keys)
    raw = {r["Facility Number"].strip(): r for r in rows}

    cache = geocode.load_cache(paths.geocache)
    overrides = {o["facility_number"].strip(): o for o in geocode.load_overrides(paths.geocache)
                 if o.get("facility_number") and o.get("lat") and o.get("lon")}
    counts = {"facilities": 0, "placed": 0, "pending_location": 0, "exact": 0, "approximate": 0, "manual": 0,
              "county_differs": 0}
    out = []
    for f in facilities:
        if f.status == CLOSED:
            continue
        a = from_row(raw[f.number])
        entry = cache.get(a.key) if a.key and a.zip5 else None
        lat = lon = None
        quality = "pending"
        county = block = ""
        if f.number in overrides:
            o = overrides[f.number]
            lat, lon, quality = float(o["lat"]), float(o["lon"]), "manual"
        elif entry and entry.get("lat") and entry.get("lon"):
            lat, lon, quality = float(entry["lat"]), float(entry["lon"]), entry["match_quality"]
            county = county_name(entry.get("county_fips"))
            block = entry.get("block_geoid") or ""
        # The county the location falls in (Dale, 2026-11-23); the state's label when there is none.
        county = county or f.county
        counts["facilities"] += 1
        if lat is None:
            counts["pending_location"] += 1
        else:
            counts["placed"] += 1
            counts[quality] += 1
        if county != f.county:
            counts["county_differs"] += 1
        out.append({
            "id": f.number, "name": f.public_name, "licensee": f.public_licensee,
            "street": " ".join(p for p in (a.street, a.unit) if p), "city": a.city, "zip": a.zip5,
            "county": county, "county_cdss": f.county, "status": f.status, "capacity": f.capacity,
            "size": metrics.size_group(f), "type": f.facility_type, "lat": lat, "lon": lon, "quality": quality,
            "block": block,
        })
    cities.assign(out)
    for r in out:
        del r["block"]   # used only to find the city; not carried into the file
    out.sort(key=lambda r: r["id"])
    return {
        "as_of": as_of.isoformat(),
        "processed_at": processed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": config.SOURCE,
        "geocoder": GEOCODER,
        "counts": counts,
        "rankings": cities.rankings(out),
        "facilities": out,
    }


def write_public_top(data, out_dir: Path):
    """The public top-five file (no addresses or locations). Kept in mapbuild/ until the public preview phase."""
    top = cities.public_top(data["facilities"], data["as_of"], data["source"])
    path = out_dir / "public" / "top-cities.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(top, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write(data, out_dir: Path):
    """Write the weekly version and the pointer. Returns (version key, version path)."""
    key = f"map/v/{data['as_of']}.json"
    version = out_dir / key
    version.parent.mkdir(parents=True, exist_ok=True)
    tmp = version.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    tmp.replace(version)
    pointer = {"key": key, "as_of": data["as_of"], "processed_at": data["processed_at"], "counts": data["counts"]}
    (out_dir / "map" / "current.json").write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    return key, version


def main(argv=None, paths=config.DEFAULT_PATHS):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-geocode", action="store_true")
    args = ap.parse_args(argv)
    summary = {}
    if not args.no_geocode:
        snaps = list_snapshots(paths.snapshots)
        if snaps:
            _, rows = read_csv(snaps[-1][1])
            summary = geocode.run(rows, paths.geocache, geocode.CensusGeocoder(), date.today())
    data = build(paths)
    key, _ = write(data, paths.mapbuild)
    write_public_top(data, paths.mapbuild)
    preview.write(data, paths.mapbuild)
    # Geocoder outages don't stop the build: new addresses show as "location pending" until next week.
    print(json.dumps({"map_file": key, "counts": data["counts"], "geocode": summary}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
