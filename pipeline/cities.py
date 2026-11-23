"""Market city for each facility, and the "Top California RCFE Markets" rankings.

A facility's market city is the official Census place its location falls in: an incorporated city, or a
community the Census names (Dale, 2026-11-23). Neighborhood mailing names such as Van Nuys count toward the city
they are in (Los Angeles). Facilities without a location use the place most homes with the same mailing city sit
in. Locations outside any place are grouped as "<mailing city> (unincorporated)".

Reference tables (Census 2020, public domain) live in pipeline/data/:
  ca_places.csv            place code, name, kind (city / community), counties
  ca_block_place.txt.gz    15-digit block -> place code, for blocks inside a place
  city_aliases.csv         reviewed mailing-city misspellings (from,to,note); nothing is merged automatically
"""
import csv
import gzip
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

# Shown wherever rankings appear (Dale, 2026-11-23). Never label a city by its totals.
EXPLANATION = (
    "A high facility count does not necessarily indicate market saturation. It may reflect population, demand, "
    "established referral networks or other local conditions. Facility concentration should be evaluated "
    "alongside demographics, occupancy, pricing, staffing, real estate costs and local referral patterns."
)
TITLE = "Top California RCFE Markets"
TOP_MEMBERS = 20
TOP_PUBLIC = 5

# Active licenses rank by default; Pending only when the member switches it on (Dale, 2026-11-23).
# Closed facilities are never ranked, and any status not listed here is left out.
SCOPES = {
    "active": ("Active licenses", ("LICENSED", "ON PROBATION")),
    "with_pending": ("Active licenses and pending applications", ("LICENSED", "ON PROBATION", "PENDING")),
}
DEFAULT_SCOPE = "active"
BANDS = [("1_6", "1–6", 1, 6), ("7_15", "7–15", 7, 15), ("16_49", "16–49", 16, 49), ("50_plus", "50+", 50, None)]

# Ranking measures. A later measure is one more entry here plus its values; "hidden" ones are never shown.
METRICS = [
    {"id": "facilities", "label": "Most facilities", "unit": "facilities", "tier": "free"},
    {"id": "licensed_capacity", "label": "Most licensed capacity", "unit": "licensed capacity", "tier": "free"},
    {"id": "facilities_per_10k_65plus", "label": "Facilities per 10,000 residents age 65+", "tier": "hidden"},
    {"id": "licensed_capacity_per_10k_65plus", "label": "Licensed capacity per 10,000 residents age 65+",
     "tier": "hidden"},
    {"id": "facilities_change_1w", "label": "Facility change, past week", "tier": "hidden"},
    {"id": "facilities_change_12m", "label": "Facility change, past 12 months", "tier": "hidden"},
    {"id": "licensed_capacity_change_12m", "label": "Licensed capacity change, past 12 months", "tier": "hidden"},
]
RANKED = ["facilities", "licensed_capacity"]


@lru_cache(maxsize=1)
def places():
    with open(DATA / "ca_places.csv", newline="", encoding="utf-8") as f:
        return {r["placefp"]: (r["name"], r["kind"]) for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def block_places():
    with gzip.open(DATA / "ca_block_place.txt.gz", "rt", encoding="utf-8") as f:
        return dict(line.rstrip("\n").split("|") for line in f)


@lru_cache(maxsize=1)
def aliases():
    with open(DATA / "city_aliases.csv", newline="", encoding="utf-8") as f:
        return {r["from"].strip(): r["to"].strip() for r in csv.DictReader(f)}


def mailing_city(city):
    """The standardized mailing city with reviewed misspellings corrected."""
    return aliases().get(city, city)


def place_of_block(block):
    return block_places().get(block or "", "")


def title(name):
    return " ".join(w[:1].upper() + w[1:].lower() if w.isupper() else w for w in name.split())


def assign(records):
    """Add market_city_id, market_city and market_city_kind to each map record (in place).

    Each record needs: city (standardized mailing city), county, county_cdss, lat, block (Census block or "").
    """
    usual = defaultdict(Counter)   # (mailing city, CDSS county) -> place codes of located homes
    for r in records:
        fp = place_of_block(r.get("block"))
        if fp:
            usual[(mailing_city(r["city"]), r["county_cdss"])][fp] += 1
    for r in records:
        mail = mailing_city(r["city"])
        fp = place_of_block(r.get("block"))
        if not fp and r["lat"] is None and usual.get((mail, r["county_cdss"])):
            fp = usual[(mail, r["county_cdss"])].most_common(1)[0][0]
        if fp and fp in places():
            name, kind = places()[fp]
            r.update(market_city_id=f"place-{fp}", market_city=name, market_city_kind=kind)
        elif mail:
            r.update(market_city_id=f"area-{r['county']}-{mail}".replace(" ", "_"),
                     market_city=f"{title(mail)} (unincorporated)", market_city_kind="unincorporated")
        else:
            r.update(market_city_id="", market_city="", market_city_kind="")
    return records


def band(capacity):
    if capacity is None:
        return None
    return next((k for k, _, lo, hi in BANDS if capacity >= lo and (hi is None or capacity <= hi)), None)


def aggregate(records, statuses):
    """City totals for facilities with one of the given statuses."""
    rows = [r for r in records if r["status"] in statuses and r["market_city_id"]]
    county_totals = defaultdict(lambda: [0, 0])
    for r in rows:
        county_totals[r["county"]][0] += 1
        county_totals[r["county"]][1] += r["capacity"] or 0
    cities = {}
    counties = defaultdict(Counter)
    for r in rows:
        c = cities.setdefault(r["market_city_id"], {
            "city_id": r["market_city_id"], "name": r["market_city"], "kind": r["market_city_kind"],
            "facilities": 0, "licensed_capacity": 0, "capacity_not_listed": 0,
            "by_capacity_band": {k: 0 for k, *_ in BANDS},
        })
        c["facilities"] += 1
        if r["capacity"] is None:
            c["capacity_not_listed"] += 1
        else:
            c["licensed_capacity"] += r["capacity"]
            b = band(r["capacity"])
            if b:
                c["by_capacity_band"][b] += 1
        counties[r["market_city_id"]][r["county"]] += 1
    for cid, c in cities.items():
        # The county most of the city's homes are located in; ties go to the name that sorts first.
        county = sorted(counties[cid].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        cf, cc = county_totals[county]
        c["county"] = county
        c["county_share"] = {
            "facilities": round(c["facilities"] / cf, 4) if cf else None,
            "licensed_capacity": round(c["licensed_capacity"] / cc, 4) if cc else None,
        }
    return cities


def rank(cities, metric, top):
    """Rows for the top cities by one measure. Tied cities share a rank; every city tied at the cutoff is kept.

    Order: the measure, then the other measure, then the name, so the list is the same every run.
    """
    other = "licensed_capacity" if metric == "facilities" else "facilities"
    ordered = sorted(cities.values(), key=lambda c: (-c[metric], -c[other], c["name"], c["city_id"]))
    rows, last_value, last_rank = [], None, 0
    for i, c in enumerate(ordered, start=1):
        r = last_rank if c[metric] == last_value else i
        if r > top:
            break
        rows.append({"rank": r, "city_id": c["city_id"]})
        last_value, last_rank = c[metric], r
    counts = Counter(row["rank"] for row in rows)
    for row in rows:
        row["tied"] = counts[row["rank"]] > 1
    return rows


def rankings(records, top=TOP_MEMBERS):
    """Rankings for the members' map file: both scopes, both measures, plus each ranked city's totals."""
    out = {"title": TITLE, "explanation": EXPLANATION, "metrics": [m for m in METRICS if m["tier"] != "hidden"],
           "default_scope": DEFAULT_SCOPE, "bands": [{"id": k, "label": label} for k, label, *_ in BANDS],
           "scopes": {}}
    for sid, (label, statuses) in SCOPES.items():
        cities = aggregate(records, statuses)
        lists = {m: rank(cities, m, top) for m in RANKED}
        shown = {row["city_id"] for rows in lists.values() for row in rows}
        out["scopes"][sid] = {"label": label, "statuses": list(statuses), "lists": lists,
                              "cities": {cid: cities[cid] for cid in sorted(shown)}}
    return out


def public_top(records, as_of, source, top=TOP_PUBLIC):
    """Top five per measure for the public preview: city, county and totals only."""
    cities = aggregate(records, SCOPES[DEFAULT_SCOPE][1])
    lists = {}
    for m in RANKED:
        lists[m] = [{"rank": row["rank"], "tied": row["tied"], "city": cities[row["city_id"]]["name"],
                     "county": cities[row["city_id"]]["county"],
                     "facilities": cities[row["city_id"]]["facilities"],
                     "licensed_capacity": cities[row["city_id"]]["licensed_capacity"]}
                    for row in rank(cities, m, top)]
    return {"title": TITLE, "explanation": EXPLANATION, "as_of": as_of, "source": source,
            "scope": SCOPES[DEFAULT_SCOPE][0], "metrics": [m for m in METRICS if m["tier"] != "hidden"],
            "lists": lists}
