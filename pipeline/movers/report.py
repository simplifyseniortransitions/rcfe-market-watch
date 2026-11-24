"""Builds a California RCFE Weekly Movers report (always a Draft, or Held for data review) and the public
artifact made from an approved one.

The report holds everything the reviewer needs, including private street lines under "private" keys. The
public artifact (`public_artifact`) is the only thing any other destination may read: it drops private keys,
review notes and every finding or area row that is held or excluded.
"""
from datetime import datetime, timezone
from pathlib import Path

from pipeline.movers import compare as cmp
from pipeline.movers import config as C
from pipeline.snapshot import list_snapshots


def report_id(source_date, version=1):
    return f"wm-{source_date}-r{version}"


def _snap_meta(snap, processing):
    if snap is None:
        return None
    return {"snapshot_id": snap.snapshot_id, "source_date": snap.snapshot_id,
            "processing_date": processing.get(snap.snapshot_id),
            "retrieval_note": "Retrieved by the weekly job shortly before processing; not recorded separately.",
            "rows": snap.row_count, "file_sha256": snap.sha256}


def build(snapshot_dir: Path, qa_report=None, as_of=None, now=None, version=1, supersedes=None,
          history_weeks=C.BASELINE_WEEKS):
    """One draft report for the newest snapshot (or `as_of`) against the immediately preceding one."""
    now = now or datetime.now(timezone.utc)
    processing = cmp.processing_dates(qa_report)
    cur_entry, prev_entry, problems = cmp.select(snapshot_dir, as_of)
    if cur_entry is None:
        raise ValueError(problems[0] if problems else "No snapshot to report on.")

    every = [s for s in list_snapshots(snapshot_dir) if s[0] <= cur_entry[0]]
    presence = {}
    for d, p in every:
        for n in cmp.numbers_in(p):
            presence.setdefault(n, []).append(d.isoformat())
    presence["__earliest__"] = every[0][0].isoformat()

    cur = cmp.load(*cur_entry)
    prev = cmp.load(*prev_entry) if prev_entry else None

    # Recent history (earlier weekly pairs only) for the thresholds' baselines.
    history = []
    earlier = every[:-1][-(history_weeks + 1):]
    if not problems and len(earlier) > 1:
        loaded = [cmp.load(*s) for s in earlier]
        for a, b in zip(loaded, loaded[1:]):
            if C.GAP_DAYS[0] <= (b.as_of - a.as_of).days <= C.GAP_DAYS[1]:
                f, _ = cmp.compare(a, b)
                cr, co = cmp.areas(a, b, f, "city"), cmp.areas(a, b, f, "county")
                history.append(cmp.week_stats(cmp.statewide(a, b, f, cr, co), cr, co))

    rid = report_id(cur.snapshot_id, version)
    report = {
        "report_id": rid, "label": C.LABEL, "schema": C.SCHEMA, "methodology_version": C.METHODOLOGY_VERSION,
        "version": version, "supersedes": supersedes, "superseded_by": None,
        "created_at": now.isoformat(timespec="seconds"), "source_name": C.SOURCE_NAME,
        "current": _snap_meta(cur, processing), "previous": _snap_meta(prev, processing),
        "comparison_days": (cur.as_of - prev.as_of).days if prev else None,
        "comparison_period": f"{prev.snapshot_id} to {cur.snapshot_id}" if prev else None,
        "statewide": None, "cities": [], "counties": [], "movers": {}, "findings": [], "checks": [],
        "baseline_weeks": len(history), "decisions": {}, "notes": [], "limitations": C.LIMITATIONS,
        "city_note": C.CITY_NOTE, "disclaimer": C.DISCLAIMER,
    }
    if prev is not None:
        findings, _ = cmp.compare(prev, cur, presence)
        city_rows, county_rows = cmp.areas(prev, cur, findings, "city"), cmp.areas(prev, cur, findings, "county")
        sw = cmp.statewide(prev, cur, findings, city_rows, county_rows)
        report["checks"] = cmp.checks(prev, cur, sw, findings, city_rows, county_rows, history, problems)
        sw["areas_held_for_review"] = sum(1 for r in city_rows + county_rows if r["held"])
        report.update(statewide=sw, findings=findings, cities=city_rows, counties=county_rows,
                      movers={"city": cmp.movers(city_rows), "county": cmp.movers(county_rows)})
    else:
        report["checks"] = cmp.checks(None, cur, None, [], [], [], [], problems)
    report["held_reasons"] = [c["detail"] for c in report["checks"] if not c["passed"] and c["scope"] == "report"]
    report["state"] = C.HELD if report["held_reasons"] else C.DRAFT
    return report


# ---------------------------------------------------------------------------------------------- inclusion
def included(item, decisions):
    """A finding or area row is shown publicly when it is public, and either not held or included by the
    reviewer, and not excluded by the reviewer."""
    choice = (decisions or {}).get(item["id"])
    if not item.get("public", True):
        return False
    if choice == "exclude":
        return False
    if choice == "include":
        return True
    return not item.get("held")


def counts(report):
    items = report["findings"]
    shown = [f for f in items if included(f, report["decisions"])]
    return {"included_findings": len(shown), "excluded_or_held_findings": len(items) - len(shown),
            "excluded_by_reviewer": sum(1 for f in items if report["decisions"].get(f["id"]) == "exclude"),
            "held_not_included": sum(1 for f in items if f.get("held") and report["decisions"].get(f["id"]) != "include"),
            "review_only": sum(1 for f in items if not f.get("public", True))}


PUBLIC_FINDING_KEYS = ("id", "change_type", "change_label", "facility_number", "facility_name", "city", "county",
                       "previous", "current", "change", "capacity", "status_origin", "license_first_date",
                       "closed_date", "first_observed", "first_observed_is_earliest_file", "last_observed", "last_observed_active",
                       "match_confidence", "match_basis", "verification", "flags")
PUBLIC_AREA_KEYS = ("id", "area", "kind", "county", "previous_count", "current_count", "count_change", "count_pct",
                    "previous_capacity", "current_capacity", "capacity_change", "capacity_pct", "record_count",
                    "finding_ids", "flags")


def public_artifact(report, approved_at=None, approved_by_role="RCFE Deal Room editor"):
    """The approved, machine-readable report every destination reads. No private keys, no notes, no street
    addresses, nothing held or excluded."""
    decisions = report["decisions"]
    findings = [{k: f[k] for k in PUBLIC_FINDING_KEYS if k in f}
                for f in report["findings"] if included(f, decisions)]
    shown_ids = {f["id"] for f in findings}
    areas = {}
    for row in report["cities"] + report["counties"]:
        if included(row, decisions):
            r = {k: row[k] for k in PUBLIC_AREA_KEYS}
            r["finding_ids"] = [i for i in row["finding_ids"] if i in shown_ids]
            r["flags"] = [C.FLAGS[f] for f in row["flags"]]
            areas[row["id"]] = r
    for f in findings:
        f["flags"] = [C.FLAGS[x].format(days=C.OLDER_LICENSE_DAYS if x == "older_license" else C.LATE_CLOSURE_DAYS)
                      for x in f["flags"]]
        f["source_dates"] = {"previous": report["previous"]["source_date"], "current": report["current"]["source_date"]}

    def pick(kind):
        return {k: [areas[i] for i in ids if i in areas] for k, ids in report["movers"].get(kind, {}).items()}

    by_type = {}
    for f in findings:
        by_type.setdefault(f["change_type"], []).append(f)
    c = counts(report)
    meta = lambda m: {k: m[k] for k in ("snapshot_id", "source_date", "processing_date", "rows")}  # noqa: E731
    return {
        "schema": C.SCHEMA, "report_id": report["report_id"], "label": C.LABEL,
        "status": report["state"], "version": report["version"],
        "supersedes": report.get("supersedes"), "superseded_by": report.get("superseded_by"),
        "methodology_version": report["methodology_version"], "source_name": C.SOURCE_NAME,
        "current_source_date": report["current"]["source_date"],
        "previous_source_date": report["previous"]["source_date"],
        "processing_date": report["current"]["processing_date"],
        "comparison_period": report["comparison_period"], "comparison_days": report["comparison_days"],
        "approval_date": approved_at, "approved_by": approved_by_role,
        "current": meta(report["current"]), "previous": meta(report["previous"]),
        "statewide": {k: v for k, v in report["statewide"].items() if k not in ("previous_rows", "current_rows")},
        "city_movers": pick("city"), "county_movers": pick("county"),
        "facility_changes": by_type,
        "counts": {"included_findings": c["included_findings"],
                   "held_or_excluded_findings": c["excluded_or_held_findings"],
                   "areas_held_or_excluded": sum(1 for r in report["cities"] + report["counties"]
                                                 if not included(r, decisions))},
        "terminology": C.CHANGE_LABELS, "city_note": C.CITY_NOTE, "limitations": C.LIMITATIONS,
        "disclaimer": C.DISCLAIMER, "spoken_disclaimer": C.SPOKEN_DISCLAIMER,
        "links": {"market_watch": C.MARKET_WATCH_URL, "community": C.COMMUNITY_URL},
        "last_updated": approved_at or report["created_at"],
    }
