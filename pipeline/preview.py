"""Public Market Map preview data (Market Map, Phase 4).

Built from the members' map data in the weekly map step, then published as site/data/map-preview.json.
It holds totals only: per county, statewide, and the top five cities. Never a street address, a location,
a facility name or a facility number. A test checks that.

Facility concentration is one market factor. Nothing here labels an area or recommends a location.
"""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from pipeline import cities
from pipeline.counties import CA_COUNTIES

ACTIVE = cities.SCOPES[cities.DEFAULT_SCOPE][1]          # Licensed and On probation
SITE_FILE = "map-preview.json"
CTA_FILE = "map-cta.json"
REFRESH = "Refreshed weekly when CDSS posts its updated facility file."
VERIFY = "Verify a facility's current license directly with the California Department of Social Services."

# Where the early-access button may point. Set by the repository variable MAP_CTA_URL; anything else
# (including the Community test site) is refused and the button shows "opening soon" instead.
CTA_HOSTS = {"rcfedealroom.com", "www.rcfedealroom.com", "community.rcfedealroom.com", "mailchi.mp", "eepurl.com"}
CTA_HOST_SUFFIXES = (".list-manage.com",)


def county_totals(records):
    """Active facilities and licensed capacity per county (where the home is located), all 58 counties."""
    out = {name: {"county": name, "facilities": 0, "licensed_capacity": 0, "capacity_not_listed": 0}
           for name in sorted(CA_COUNTIES.values())}
    for f in records:
        if f["status"] not in ACTIVE or f["county"] not in out:
            continue
        c = out[f["county"]]
        c["facilities"] += 1
        if f["capacity"] is None:
            c["capacity_not_listed"] += 1
        else:
            c["licensed_capacity"] += f["capacity"]
    return list(out.values())


def build(data):
    records = data["facilities"]
    counties = county_totals(records)
    top = cities.public_top(records, data["as_of"], data["source"])
    return {
        "title": "California RCFE Market Map",
        "as_of": data["as_of"],
        "processed_at": data["processed_at"],
        "refresh": REFRESH,
        "source": data["source"],
        "verify": VERIFY,
        "scope": "Active licenses (Licensed and On probation), all RCFE types including CCRCs",
        "county_rule": "County is where the home is located. The Market tab uses the county label in the CDSS file, "
                       "so a few county counts differ slightly.",
        "statewide": {"facilities": sum(c["facilities"] for c in counties),
                      "licensed_capacity": sum(c["licensed_capacity"] for c in counties),
                      "counties_with_facilities": sum(1 for c in counties if c["facilities"])},
        "counties": counties,
        "top": {"title": top["title"], "explanation": top["explanation"], "metrics": top["metrics"], "lists": top["lists"]},
    }


def cta_config(url):
    """The early-access button's destination, or none (shown as "opening soon")."""
    url = (url or "").strip()
    try:
        u = urlparse(url)
    except ValueError:
        return {"url": None}
    host = (u.hostname or "").lower()
    ok = u.scheme == "https" and (host in CTA_HOSTS or host.endswith(CTA_HOST_SUFFIXES)) and not re.search(r"[\s<>\"']", url)
    return {"url": url if ok else None}


def write(data, out_dir: Path):
    path = out_dir / "public" / SITE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(data), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv=None):
    """`python -m pipeline.preview cta <site_data_dir>`: writes map-cta.json from MAP_CTA_URL."""
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) == 2 and argv[0] == "cta":
        out = Path(argv[1]) / CTA_FILE
        out.write_text(json.dumps(cta_config(os.environ.get("MAP_CTA_URL")), indent=1) + "\n", encoding="utf-8")
        print(out.read_text().strip())
        return 0
    print(main.__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
