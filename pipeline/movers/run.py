"""Weekly job entry point for California RCFE Weekly Movers. It only ever creates a Draft or Held report.

    python -m pipeline.movers.run draft [--store DIR] [--as-of YYYY-MM-DD]
    python -m pipeline.movers.run notice [--store DIR]     the one line for the weekly notice

It runs after Market Watch, the members' map and the map preview are published, reads only the saved
snapshots and the QA report, and writes only inside the store folder (the private data repository). Any error
is caught and recorded: it never changes site/, the map files or anything already published.
"""
import argparse
import json
import sys
import traceback
from datetime import date
from pathlib import Path

from pipeline import config as pipeline_config
from pipeline.movers import config as C
from pipeline.movers.report import build
from pipeline.movers.store import Store

LINES = {
    "draft": "Weekly Movers: draft created",
    "held": "Weekly Movers: held for review",
    "exists": "Weekly Movers: draft created",
    "failed": "Weekly Movers: did not generate",
}


def make_draft(store: Store, paths=pipeline_config.DEFAULT_PATHS, as_of=None, now=None):
    """Create this week's draft. Returns the run record; never raises."""
    try:
        qa = json.loads(paths.qa_report.read_text(encoding="utf-8")) if paths.qa_report.exists() else {}
        report = build(paths.snapshots, qa, as_of=as_of, now=now)
        existing = store.reports_for(report["current"]["source_date"])
        if existing:
            # A retry, or a week already drafted: never replace a report.
            return store.record_run("exists", f"A report already exists for {report['current']['source_date']}.",
                                    now, existing[0]["report_id"])
        store.create_draft(report, now=now)
        detail = "; ".join(report["held_reasons"]) or "Ready for review."
        return store.record_run(report["state"], detail, now, report["report_id"])
    except Exception as e:  # noqa: BLE001 — isolation: report it, never break the weekly job
        detail = f"{type(e).__name__}: {e}"
        print(traceback.format_exc(), file=sys.stderr)
        try:
            return store.record_run("failed", detail, now)
        except Exception:  # noqa: BLE001
            return {"outcome": "failed", "detail": detail}


def notice_line(store: Store, step_outcome=""):
    """The line for the weekly notice. Technical details stay in the private run record."""
    if step_outcome == "failure":
        return LINES["failed"]
    path = store.root / "last-run.json"
    if not path.exists():
        return LINES["failed"] if step_outcome == "success" else ""
    return LINES.get(json.loads(path.read_text(encoding="utf-8")).get("outcome"), LINES["failed"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["draft", "notice"])
    ap.add_argument("--store", type=Path, default=C.DEFAULT_STORE)
    ap.add_argument("--as-of", type=date.fromisoformat)
    args = ap.parse_args(argv)
    store = Store(args.store)
    if args.command == "draft":
        run = make_draft(store, as_of=args.as_of)
        print(f"{LINES.get(run['outcome'], LINES['failed'])} ({run.get('report_id') or 'no report'}): {run['detail']}")
        return 0 if run["outcome"] != "failed" else 1
    print(notice_line(store))
    return 0


if __name__ == "__main__":
    sys.exit(main())
