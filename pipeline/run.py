"""Weekly pipeline entry point (Step 1: validate and snapshot).

    python -m pipeline.run                     every CSV in inbox/, oldest as-of date first
    python -m pipeline.run --file X.csv        one file
        --as-of YYYY-MM-DD                     when the date is not in the file name
        --accept-row-drop                      owner override for a confirmed real drop
"""
import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

from pipeline import config, publish, qa
from pipeline.snapshot import (SnapshotConflict, detect_as_of, prior_snapshot, save_rejected,
                               save_snapshot, sha256)
from pipeline.validate import InputError, read_csv, validate


def process_file(src: Path, paths: config.Paths, as_of=None, accept_row_drop=False) -> dict:
    """Validate one input, snapshot it on success, and log the run. Returns the run record."""
    started = qa.now_utc()
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    as_of = as_of or detect_as_of(src)
    run = {
        "generated_at": started.isoformat(),
        "input_file": src.name,
        "input_sha256": sha256(src),
        "as_of": as_of.isoformat() if as_of else None,
        "snapshot_id": None,
        "status": "fail",
        "errors": [],
        "warnings": [],
        "checks": [],
    }

    def fail(message):
        run["errors"].append(message)
        run["rejected_copy"] = str(save_rejected(src, paths.rejected, as_of, stamp).relative_to(paths.root))
        qa.write_report(paths.qa_report, run)
        return run

    if as_of is None:
        return fail("as-of date not found in the file name; rerun with --as-of YYYY-MM-DD")

    prior = prior_snapshot(paths.snapshots, as_of)
    prior_count = None
    if prior:
        _, prior_rows = read_csv(prior[1])
        prior_count = len(prior_rows)
        run["prior_snapshot_id"] = prior[0].isoformat()
        run["prior_row_count"] = prior_count

    try:
        header, rows = read_csv(src)
    except InputError as e:
        return fail(str(e))

    result = validate(header, rows, prior_count, accept_row_drop)
    run.update(row_count=result.row_count, checks=[c.as_dict() for c in result.checks],
               warnings=result.warnings, counts=result.counts)
    if accept_row_drop:
        run["owner_override"] = "accept_row_drop"
    if not result.ok:
        run["errors"] = result.errors
        return fail("validation failed; nothing published")

    try:
        dest, created = save_snapshot(src, paths.snapshots, as_of)
    except SnapshotConflict as e:
        return fail(str(e))

    run.update(snapshot_file=str(dest.relative_to(paths.root)), snapshot_created=created)
    try:
        run["published"] = publish.publish(paths, run["generated_at"])
    except Exception as e:  # keep the last good site; the valid snapshot stays saved
        run["errors"].append(f"publish failed, last good site kept: {type(e).__name__}: {e}")
        qa.write_report(paths.qa_report, run)
        return run
    run.update(status="pass", snapshot_id=as_of.isoformat())
    qa.write_report(paths.qa_report, run)
    return run


def unique_dest(folder: Path, name: str) -> Path:
    dest = folder / name
    n = 1
    while dest.exists():
        dest = folder / f"{Path(name).stem}_{n}{Path(name).suffix}"
        n += 1
    return dest


def process_inbox(paths: config.Paths, accept_row_drop=False):
    """Process inbox CSVs oldest first; stop at the first failure so later files keep a good baseline."""
    files = sorted(paths.inbox.glob("*.csv"), key=lambda p: (detect_as_of(p) or date.max, p.name))
    runs = []
    for src in files:
        run = process_file(src, paths, accept_row_drop=accept_row_drop)
        runs.append(run)
        if run["status"] != "pass":
            break
        paths.processed.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), unique_dest(paths.processed, src.name))
    return runs


def print_run(run):
    print(f"\n=== {run['input_file']}  (as of {run['as_of'] or 'unknown'}) — {run['status'].upper()} ===")
    if "row_count" in run:
        print(f"rows: {run['row_count']}")
    for c in run["checks"]:
        print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['name']}: {c['detail']}")
        for ex in c.get("examples", [])[:5]:
            print(f"         e.g. {ex}")
    for w in run["warnings"]:
        print(f"  [WARN] {w}")
    for e in run["errors"]:
        print(f"  [ERROR] {e}")
    if run.get("snapshot_file"):
        verb = "saved" if run["snapshot_created"] else "already saved (identical file)"
        print(f"snapshot {verb}: {run['snapshot_file']}")
    if run.get("published"):
        print(f"published: {', '.join(run['published'])}")
    elif run.get("rejected_copy"):
        print(f"input kept for review at {run['rejected_copy']}; no snapshot written")


def main(argv=None, paths=config.DEFAULT_PATHS):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path)
    ap.add_argument("--as-of", type=date.fromisoformat)
    ap.add_argument("--accept-row-drop", action="store_true")
    args = ap.parse_args(argv)

    if args.file:
        runs = [process_file(args.file, paths, args.as_of, args.accept_row_drop)]
    else:
        runs = process_inbox(paths, args.accept_row_drop)
        if not runs:
            print(f"No CSV files in {paths.inbox}")
    for run in runs:
        print_run(run)
    print(f"\nqa report: {paths.qa_report}")
    return 0 if all(r["status"] == "pass" for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
