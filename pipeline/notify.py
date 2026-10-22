"""Plain-language text for the weekly job's GitHub issue and run summary, from qa-report.json.

    python -m pipeline.notify failure "<download error, if any>"   issue body for a failed run
    python -m pipeline.notify summary                             short summary of the latest run
"""
import json
import sys

from pipeline import config


def load_latest(paths=config.DEFAULT_PATHS):
    try:
        return json.loads(paths.qa_report.read_text(encoding="utf-8")).get("latest_run") or {}
    except (OSError, ValueError):
        return {}


def failure_body(run, download_error="", run_url=""):
    lines = ["The weekly RCFE Market Watch update did not publish. **The site still shows the last good week.**", ""]
    if download_error:
        lines += ["**The CDSS file could not be downloaded.**", "", f"> {download_error}", ""]
    elif run:
        lines += [f"File: `{run.get('input_file', 'unknown')}` (as of {run.get('as_of') or 'unknown'}), "
                  f"{run.get('row_count', 'unknown')} rows.", "", "**What failed:**", ""]
        lines += [f"- {e}" for e in run.get("errors", [])] or ["- (no detail recorded)"]
        lines.append("")
        failed = [c for c in run.get("checks", []) if not c.get("passed")]
        for c in failed:
            for ex in c.get("examples", [])[:5]:
                lines.append(f"  - example: `{json.dumps(ex)}`")
        if run.get("rejected_copy"):
            lines += ["", "The file was kept for review in the private data repository under `snapshots/rejected/`."]
    else:
        lines += ["The job stopped before the checks ran. See the run log for the step that failed."]
    lines += ["", "**What to do:** if CDSS changed the file on purpose (for example a real drop in facilities), "
              "re-run the job from the Actions tab after checking it. Otherwise wait for next week's file, "
              "or download it by hand from the CDSS Download Data page."]
    if run_url:
        lines += ["", f"Run log: {run_url}"]
    return "\n".join(lines) + "\n"


def summary(run):
    if not run:
        return "No run recorded.\n"
    status = "published" if run.get("status") == "pass" else "NOT published"
    lines = [f"**{status}**: `{run.get('input_file')}` as of {run.get('as_of')}, {run.get('row_count')} rows", ""]
    lines += [f"- {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['detail']}" for c in run.get("checks", [])]
    lines += [f"- warning: {w}" for w in run.get("warnings", [])]
    return "\n".join(lines) + "\n"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    run = load_latest()
    if argv and argv[0] == "failure":
        download_error = argv[1] if len(argv) > 1 else ""
        run_url = argv[2] if len(argv) > 2 else ""
        sys.stdout.write(failure_body(run, download_error, run_url))
    else:
        sys.stdout.write(summary(run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
