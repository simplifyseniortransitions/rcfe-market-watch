"""Step 4: write site/data/*.json from the snapshots. Everything is rebuilt from snapshot files each run.

Files are written to a staging folder first and only moved into site/data once all of them built,
so a failure leaves the last good set in place.
"""
import json
import shutil
from collections import Counter, defaultdict

from pipeline import config, feed, metrics, signals
from pipeline.snapshot import list_snapshots
from pipeline.normalize import administrator_keys, normalize, withhold
from pipeline.validate import read_csv

OUTPUT_FILES = ["pulse.json", "feed.json", "signals.json", "owners.json", "market.json",
                "facilities.json", "history.json"]
# Large lists are written without indentation to keep downloads small.
COMPACT = {"facilities.json", "feed.json", "signals.json", "market.json"}
RECENT_EVENTS = 10
SIZE_KEYS = ["all_sizes", *metrics.SIZES]


def load_snapshots(paths):
    """[(as_of, facilities)] for every snapshot, oldest first.

    A licensee name that is an administrator name in any loaded snapshot is withheld in all of them.
    """
    out, admin_keys = [], set()
    for as_of, path in list_snapshots(paths.snapshots):
        header, rows = read_csv(path)
        admin_keys |= administrator_keys(rows)
        out.append((as_of, normalize(header, rows)))
    return [(as_of, withhold(fs, admin_keys)) for as_of, fs in out]


def meta(as_of, generated_at):
    return {
        "as_of": as_of.isoformat(),
        "source": config.SOURCE,
        "generated_at": generated_at,
        "snapshot_id": as_of.isoformat(),
        "product": config.PRODUCT_NAME,
    }


def sized(seg, drop=("counties",)):
    """{all_sizes, small, large} views of a scope segment, without the listed keys."""
    views = {"all_sizes": seg, **seg["by_size"]}
    return {k: {f: v for f, v in views[k].items() if f not in drop + ("by_size", "bands")} for k in SIZE_KEYS}


def filters():
    return {
        "headline_scope": metrics.HEADLINE_SCOPE,
        "scopes": {k: label for k, (label, _) in metrics.SCOPES.items()},
        "sizes": {"all_sizes": "All sizes", **{k: label for k, (label, _) in metrics.SIZES.items()}},
    }


def signal_counts(facilities, flags):
    counts = {}
    for size in SIZE_KEYS:
        keep = (lambda f: True) if size == "all_sizes" else metrics.SIZES[size][1]
        c = {key: 0 for key, *_ in signals.RULES}
        for f in facilities:
            if keep(f):
                for flag in flags.get(f.number, []):
                    c[flag["rule"]] += 1
        counts[size] = c
    return counts


def add_county_signals(counties, current, flags):
    """Add {rule: facilities flagged} to every county row, matching that row's scope and size."""
    tally = defaultdict(Counter)
    for f in current:
        for flag in flags.get(f.number, []):
            for scope, (_, in_scope) in metrics.SCOPES.items():
                if not in_scope(f):
                    continue
                for size in SIZE_KEYS:
                    if size == "all_sizes" or metrics.SIZES[size][1](f):
                        tally[(scope, size, f.county or "(BLANK)")][flag["rule"]] += 1
    for scope, sizes in counties.items():
        for size, rows in sizes.items():
            for row in rows:
                c = tally[(scope, size, row["county"])]
                row["signals"] = {key: c[key] for key, *_ in signals.RULES}
    return counties


def facility_record(f, as_of, flags):
    year_ago = metrics.one_year_before(as_of)
    return {
        "facility_number": f.number,
        "facility_name": f.public_name,
        "licensee": f.public_licensee,
        "licensee_withheld": f.licensee_withheld,
        "facility_type": f.facility_type,
        "status": f.status,
        "city": f.city,
        "county": f.county,
        "capacity": f.capacity,
        "size_group": metrics.size_group(f),
        "band": metrics.band(f),
        "license_first_date": f.license_first_date.isoformat() if f.license_first_date else None,
        "closed_date": f.closed_date.isoformat() if f.closed_date else None,
        "last_visit_date": f.last_visit_date.isoformat() if f.last_visit_date else None,
        "total_visits": f.total_visits,
        "complaint_visits": f.complaint_visits,
        "substantiated_allegations": f.substantiated_allegations,
        "citations_12m": sum(1 for d in f.poc_dates if year_ago <= d <= as_of),
        "signals": [flag["rule"] for flag in flags.get(f.number, [])],
    }


def history(snapshots):
    weeks = []
    for as_of, fs in snapshots:
        multi = metrics.multi_home_numbers(fs)
        weeks.append({
            "snapshot_id": as_of.isoformat(),
            "totals": {
                "all": metrics.totals(fs, as_of, multi),
                "core": metrics.totals([f for f in fs if f.is_core], as_of, multi),
                **{size: metrics.totals([f for f in fs if keep(f)], as_of, multi)
                   for size, (_, keep) in metrics.SIZES.items()},
            },
        })
    return weeks


def build(snapshots, generated_at):
    """{file name: payload} for the latest snapshot. Needs at least one snapshot."""
    as_of, current = snapshots[-1]
    prior_as_of, prior = snapshots[-2] if len(snapshots) > 1 else (None, None)
    m = meta(as_of, generated_at)
    result = metrics.compute(current, as_of, prior, prior_as_of)
    events = feed.all_events(snapshots)
    flags = signals.compute(current, as_of, feed.recent(events, as_of, 90))
    feed_events = feed.feed_window(events, as_of)
    headline = metrics.HEADLINE_SCOPE

    outputs = {
        "pulse.json": {
            **m, **filters(),
            "prior_snapshot_id": result["prior_as_of"],
            "segments": {scope: sized(seg) for scope, seg in result["scopes"].items()},
            "recent_events": feed_events[:RECENT_EVENTS],
            "signal_counts": signal_counts(current, flags),
            "signal_rules": [{"key": k, "label": label, "rule": rule} for k, label, rule in signals.RULES],
            "signal_disclaimer": signals.DISCLAIMER,
            "event_types": [{"key": k, "label": label} for k, label, _ in feed.EVENT_TYPES],
            "definitions": {k: {"label": label, "rule": rule} for k, (label, rule) in metrics.DEFINITIONS.items()},
        },
        "feed.json": {
            **m,
            "weeks": feed.FEED_WEEKS,
            "event_types": [{"key": k, "label": label, "rule": rule} for k, label, rule in feed.EVENT_TYPES],
            "events": feed_events,
        },
        "signals.json": {
            **m,
            "complaint_threshold": config.COMPLAINT_THRESHOLD,
            "rules": [{"key": k, "label": label, "rule": rule} for k, label, rule in signals.RULES],
            "disclaimer": signals.DISCLAIMER,
            "facilities_without_complaint_detail": sum(f.complaints is None for f in current),
            "counts": signal_counts(current, flags),
            "facilities": sorted(
                ({**{k: v for k, v in facility_record(f, as_of, flags).items() if k != "signals"},
                  "flags": flags[f.number]} for f in current if f.number in flags),
                key=lambda r: (r["county"], r["facility_name"], r["facility_number"])),
        },
        "owners.json": {
            **m,
            "rule": metrics.DEFINITIONS["licensees_3plus"][1],
            "scope": headline,
            "owners": metrics.owners(current),
        },
        "market.json": {
            **m, **filters(),
            "small_base": metrics.SMALL_BASE,
            "window_12m_start": metrics.one_year_before(as_of).isoformat(),
            "bands": [{"key": k, "label": label} for k, label, *_ in metrics.BANDS],
            "band_totals": {scope: seg["bands"] for scope, seg in result["scopes"].items()},
            "counties": add_county_signals(
                {scope: {size: view["counties"] for size, view in {"all_sizes": seg, **seg["by_size"]}.items()}
                 for scope, seg in result["scopes"].items()}, current, flags),
        },
        "facilities.json": {
            **m,
            "facilities": sorted((facility_record(f, as_of, flags) for f in current),
                                 key=lambda r: (r["facility_name"], r["facility_number"])),
        },
    }
    if len(snapshots) >= config.HISTORY_MIN_SNAPSHOTS:
        outputs["history.json"] = {**m, "weeks": history(snapshots)}
    return outputs


def write_outputs(outputs, data_dir):
    staging = data_dir / ".staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for name, payload in outputs.items():
        indent = None if name in COMPACT else 2
        text = json.dumps(payload, indent=indent, ensure_ascii=False, separators=None if indent else (",", ":"))
        (staging / name).write_text(text + "\n", encoding="utf-8")
    for name in outputs:
        (staging / name).replace(data_dir / name)
    staging.rmdir()


def publish(paths, generated_at):
    """Rebuild and publish every output from the snapshots. Returns the file names written."""
    snapshots = load_snapshots(paths)
    if not snapshots:
        raise RuntimeError("no snapshots to publish")
    outputs = build(snapshots, generated_at)
    write_outputs(outputs, paths.data)
    return sorted(outputs)
