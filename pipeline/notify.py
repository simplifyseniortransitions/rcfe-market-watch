"""Plain-language text for the weekly job's GitHub issue and run summary, from qa-report.json.

    python -m pipeline.notify failure "<download error, if any>"   issue body for a failed run
    python -m pipeline.notify summary                             short summary of the latest run
    python -m pipeline.notify weekly                              the weekly notice (settings come from env vars)
"""
import json
import os
import sys
from datetime import date

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


# The @mention is what makes GitHub email the owner: on 2026-10-26 issues opened by the job alone sent no email.
OWNER = "@simplifyseniortransitions"
SITE_URL = "https://rcfedealroom.com/market-watch"
NEXT_TRY = {"main": "It will try again at 6 PM today and at 1 PM Tuesday (Pacific).",
            "final": "That was the last automatic try this week.",
            "manual": "This was a manual run."}


def nice_date(iso):
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def signed(n):
    return "no earlier week" if n is None else "no change" if n == 0 else f"{n:+,}".replace("-", "−")


def weekly_notice(status, published, slot, pulse, error="", run_url=""):
    """The weekly email text, or "" when this run should stay silent (a retry with nothing to report)."""
    if published:
        seg = pulse["segments"][pulse["headline_scope"]]["all_sizes"]
        t, w, a = seg["totals"], seg["week_over_week"], seg["activity"] or {}
        prior = f" Compared with {nice_date(pulse['prior_snapshot_id'])}." if pulse.get("prior_snapshot_id") else ""
        rows = [("Licensed facilities", "licensed_facilities"), ("Licensed beds", "licensed_beds"),
                ("Pending", "pending"), ("On probation", "on_probation")]
        lines = [f"{OWNER} **Market Watch updated: week of {nice_date(pulse['as_of'])}.**{prior}", ""]
        lines += [f"- {label}: {t[key]:,} ({signed(w[key])})" for label, key in rows]
        lines += [f"- New facility numbers: {a.get('new_facility_numbers', 0):,}",
                  f"- Closures (status changed to CLOSED): {a.get('closures_status_changed', 0):,}",
                  f"- Ownership changes: {a.get('ownership_changes', 0):,}",
                  f"- New substantiated allegations: {a.get('new_substantiated_allegations', 0):,}",
                  "", f"Site: {SITE_URL}"]
        return "\n".join(lines) + "\n"
    if slot == "evening":
        return ""
    week = nice_date(pulse["as_of"])
    if status == "unchanged":
        head = f"**No new CDSS file yet.** Nothing changed; the site still shows the week of {week}."
    else:
        head = f"**This week's update did not publish.** The site still shows the week of {week}."
        if error:
            head += f"\n\nReason: {error}"
    lines = [f"{OWNER} {head}", "", NEXT_TRY.get(slot, "")]
    if run_url and status != "unchanged":
        lines += ["", f"Run log: {run_url}"]
    return "\n".join(lines).rstrip() + "\n"


def load_pulse(paths=config.DEFAULT_PATHS):
    return json.loads((paths.data / "pulse.json").read_text(encoding="utf-8"))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    run = load_latest()
    if argv and argv[0] == "weekly":
        env = os.environ.get
        sys.stdout.write(weekly_notice(env("DOWNLOAD_STATUS", ""), env("PUBLISH_OUTCOME") == "success", env("SLOT", "manual"),
                                       load_pulse(), env("DOWNLOAD_ERROR", ""), env("RUN_URL", "")))
    elif argv and argv[0] == "failure":
        download_error = argv[1] if len(argv) > 1 else ""
        run_url = argv[2] if len(argv) > 2 else ""
        sys.stdout.write(failure_body(run, download_error, run_url))
    else:
        sys.stdout.write(summary(run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
