"""qa-report.json: the latest run plus a rolling log of past runs."""
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline import config


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def load_runs(path: Path):
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("runs", [])
    except (json.JSONDecodeError, AttributeError):
        return []


def write_report(path: Path, run: dict):
    runs = (load_runs(path) + [run])[-config.QA_HISTORY_LIMIT:]
    last_good = next((r["snapshot_id"] for r in reversed(runs) if r["status"] == "pass"), None)
    report = {
        "as_of": run["as_of"],
        "source": config.SOURCE,
        "generated_at": run["generated_at"],
        "snapshot_id": run["snapshot_id"],
        "status": run["status"],
        "last_good_snapshot_id": last_good,
        "latest_run": run,
        "runs": runs,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return report
