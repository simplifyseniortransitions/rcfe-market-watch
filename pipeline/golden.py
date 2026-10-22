"""Golden check on the Oct 18, 2026 snapshot.  ./run.sh golden

The expected values are Dale's acceptance numbers. They are never edited to make a test pass.
"""
import sys
from datetime import date

from pipeline import config, metrics
from pipeline.normalize import normalize
from pipeline.validate import read_csv

GOLDEN_AS_OF = date(2026, 10, 18)
GOLDEN_PRIOR = date(2026, 10, 11)

GOLDEN_TOTALS = {
    "licensed_facilities": 8607,
    "licensed_beds": 212076,
    "median_licensed_capacity": 6,
    "pending": 924,
    "on_probation": 24,
    "new_licenses_90d": 309,
    # Dale's original value was 136. On 2026-10-22 he decided closures count only facilities with a
    # License First Date, which leaves out 34 applications that closed before a license was issued.
    "closures_closed_date_90d": 102,
    # Dale's original value was 198, which treats "BCRG  INC. " and "BCRG INC." as two names.
    # Dale approved 199 on 2026-10-21 with the spacing/case name merge (see licensees_3plus definition).
    "licensees_3plus": 199,
}
GOLDEN_COUNTIES = {
    "LOS ANGELES": 1909,
    "ORANGE": 1127,
    "SACRAMENTO": 686,
    "SAN DIEGO": 615,
    "RIVERSIDE": 590,
}


def load(day, paths=config.DEFAULT_PATHS):
    header, rows = read_csv(paths.snapshots / f"{day.isoformat()}.csv")
    return normalize(header, rows)


def golden_metrics(paths=config.DEFAULT_PATHS):
    prior_file = paths.snapshots / f"{GOLDEN_PRIOR.isoformat()}.csv"
    prior = load(GOLDEN_PRIOR, paths) if prior_file.exists() else None
    return metrics.compute(load(GOLDEN_AS_OF, paths), GOLDEN_AS_OF, prior, GOLDEN_PRIOR if prior else None)


def county_value(scope, county):
    return next((c["licensed_facilities"] for c in scope["counties"] if c["county"] == county), 0)


def rows(result):
    """[(label, expected, {scope: actual})] in display order."""
    out = []
    for key, expected in GOLDEN_TOTALS.items():
        out.append((metrics.DEFINITIONS[key][0], expected,
                    {s: v["totals"][key] for s, v in result["scopes"].items()}))
    for county, expected in GOLDEN_COUNTIES.items():
        out.append((f"{county.title()} licensed homes", expected,
                    {s: county_value(v, county) for s, v in result["scopes"].items()}))
    return out


def main():
    result = golden_metrics()
    head = result["headline_scope"]
    print(f"Golden check, snapshot {result['as_of']} (headline scope: {head})\n")
    print(f"{'Metric':42} {'Expected':>9} {'All':>9} {'Core':>9}  Result ({head})")
    failures = 0
    for label, expected, actual in rows(result):
        ok = actual[head] == expected
        failures += not ok
        print(f"{label:42} {expected:>9,} {actual['all']:>9,} {actual['core']:>9,}  "
              f"{'PASS' if ok else 'DIFF ' + format(actual[head] - expected, '+,')}")
    print(f"\n{failures} of {len(rows(result))} values differ on the headline scope.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
