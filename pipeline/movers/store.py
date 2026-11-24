"""Where Weekly Movers reports live, and the only code that changes their review state.

Layout (inside the private data repository's movers/ folder; never in the public repository):

    drafts/<report_id>/report.json        the full report: review copy, with private street lines and notes
    drafts/<report_id>/preview/           draft Markdown, brief, scripts and charts for reviewing (not approved)
    approved/<source_date>/<report_id>/   written once, at approval: report.json (public artifact), report.md,
                                          news-brief.md, teleprompter-draft.md, social-drafts.md, charts.json,
                                          cards/*.svg. Never rewritten. A later correction adds superseded-by.json.
    approved/index.json                   archive of approved and superseded reports (public-safe)
    reviews.jsonl                         append-only log of every review action
    runs/<stamp>.json                     every weekly run, including failures (details for administrators)
    last-run.json                         the latest weekly run's outcome, for the weekly notice

Only approve() makes a report Approved, and it needs a named reviewer and an explicit acknowledgment. The
weekly job only ever calls create_draft().
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.movers import config as C
from pipeline.movers import outputs
from pipeline.movers.report import counts, public_artifact

ALLOWED = {C.DRAFT: {C.APPROVED, C.REJECTED, C.HELD}, C.HELD: {C.APPROVED, C.REJECTED, C.DRAFT},
           C.APPROVED: {C.SUPERSEDED}, C.REJECTED: set(), C.SUPERSEDED: set()}


class ReviewError(Exception):
    """A review action that isn't allowed (wrong state, no acknowledgment, no reviewer, unknown item)."""


def _now(now=None):
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def _write_json(path: Path, data, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    if exclusive and path.exists():
        raise ReviewError(f"{path.name} already exists and is never overwritten")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _write_text(path: Path, text, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise ReviewError(f"{path.name} already exists and is never overwritten")
    path.write_text(text, encoding="utf-8")


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)

    # ------------------------------------------------------------------ reading
    def draft_dir(self, rid):
        if not rid or "/" in rid or ".." in rid or not rid.startswith("wm-"):
            raise ReviewError("unknown report")
        return self.root / "drafts" / rid

    def load(self, rid):
        path = self.draft_dir(rid) / "report.json"
        if not path.exists():
            raise ReviewError("unknown report")
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self):
        out = []
        for p in sorted((self.root / "drafts").glob("wm-*/report.json")):
            r = json.loads(p.read_text(encoding="utf-8"))
            out.append({"report_id": r["report_id"], "state": r["state"], "comparison_period": r["comparison_period"],
                        "source_date": r["current"]["source_date"], "version": r["version"],
                        "supersedes": r.get("supersedes"), "superseded_by": r.get("superseded_by"),
                        "methodology_version": r["methodology_version"], "created_at": r["created_at"]})
        return sorted(out, key=lambda r: (r["source_date"], r["version"]), reverse=True)

    def reports_for(self, source_date):
        return [r for r in self.list() if r["source_date"] == source_date]

    def log(self):
        path = self.root / "reviews.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ------------------------------------------------------------------ writing
    def _save(self, report):
        _write_json(self.draft_dir(report["report_id"]) / "report.json", report)

    def _append_log(self, entry):
        path = self.root / "reviews.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def _log(self, report, actor, action, previous_state, now, acknowledged=False, note="", item=None):
        c = counts(report)
        self._append_log({
            "action": action, "user": actor, "at": _now(now), "report_id": report["report_id"],
            "current_snapshot_id": report["current"]["snapshot_id"],
            "previous_snapshot_id": (report.get("previous") or {}).get("snapshot_id"),
            "previous_state": previous_state, "new_state": report["state"],
            "included_findings": c["included_findings"], "excluded_or_held_findings": c["excluded_or_held_findings"],
            "acknowledged_reviewed": bool(acknowledged), "note": note or "", "item": item,
        })

    def write_preview(self, report):
        """Draft review copies of every output, clearly marked as not approved."""
        if report.get("statewide") is None:
            return
        art = public_artifact(report)
        d = self.draft_dir(report["report_id"]) / "preview"
        _write_text(d / "report.md", outputs.markdown(art))
        _write_text(d / "news-brief.md", outputs.news_brief(art))
        _write_text(d / "teleprompter-draft.md", outputs.teleprompter(art))
        _write_text(d / "social-drafts.md", outputs.social(art))
        ch = outputs.charts(art)
        _write_json(d / "charts.json", ch)
        for name, svg in outputs.svg_cards(ch).items():
            _write_text(d / "cards" / f"{name}.svg", svg)

    def create_draft(self, report, actor="weekly job", now=None):
        """Save a new Draft or Held report. Never replaces an existing report."""
        if report["state"] not in (C.DRAFT, C.HELD):
            raise ReviewError("a new report can only be a Draft or Held for data review")
        if (self.draft_dir(report["report_id"]) / "report.json").exists():
            raise ReviewError(f"{report['report_id']} already exists and is never overwritten")
        self._save(report)
        self.write_preview(report)
        self._log(report, actor, "created", None, now)
        return report

    def _editable(self, report):
        if report["state"] not in (C.DRAFT, C.HELD):
            raise ReviewError(f"a report that is {C.STATE_LABELS[report['state']]} can't be changed")

    def set_decision(self, rid, item_id, choice, actor, now=None):
        """Include or exclude one finding or area row in the public report. Source data is never deleted."""
        if choice not in ("include", "exclude", "default"):
            raise ReviewError("choice must be include, exclude or default")
        if not actor:
            raise ReviewError("a reviewer is required")
        report = self.load(rid)
        self._editable(report)
        known = {f["id"] for f in report["findings"]} | {r["id"] for r in report["cities"] + report["counties"]}
        if item_id not in known:
            raise ReviewError("unknown item")
        if choice == "default":
            report["decisions"].pop(item_id, None)
        else:
            report["decisions"][item_id] = choice
        self._save(report)
        self.write_preview(report)
        self._log(report, actor, f"{choice}_item", report["state"], now, item=item_id)
        return report

    def add_note(self, rid, text, actor, now=None):
        """A private review note. Never copied into any public file."""
        text = (text or "").strip()
        if not text or not actor:
            raise ReviewError("a note and a reviewer are required")
        report = self.load(rid)
        report["notes"].append({"at": _now(now), "user": actor, "text": text[:2000]})
        self._save(report)
        self._log(report, actor, "note", report["state"], now, note=text[:2000])
        return report

    def _transition(self, report, new_state, actor, now, acknowledged=False, note="", action=None):
        old = report["state"]
        if new_state not in ALLOWED[old]:
            raise ReviewError(f"can't move a report from {C.STATE_LABELS[old]} to {C.STATE_LABELS[new_state]}")
        report["state"] = new_state
        report.setdefault("state_history", []).append({"from": old, "to": new_state, "at": _now(now), "user": actor})
        self._save(report)
        self._log(report, actor, action or new_state, old, now, acknowledged, note)

    def hold(self, rid, actor, note="", now=None):
        if not actor:
            raise ReviewError("a reviewer is required")
        self._transition(self.load(rid), C.HELD, actor, now, note=note, action="held")

    def reject(self, rid, actor, note="", now=None):
        if not actor:
            raise ReviewError("a reviewer is required")
        self._transition(self.load(rid), C.REJECTED, actor, now, note=note, action="rejected")

    def approve(self, rid, actor, acknowledged, note="", now=None):
        """The only way a report becomes Approved. Writes the approved files once and never rewrites them."""
        if not actor:
            raise ReviewError("a reviewer is required")
        if acknowledged is not True:
            raise ReviewError("confirm that you reviewed the report before approving it")
        report = self.load(rid)
        if report.get("statewide") is None:
            raise ReviewError("this report has no comparison to approve; reject it instead")
        if report["state"] not in (C.DRAFT, C.HELD):
            raise ReviewError(f"a report that is {C.STATE_LABELS[report['state']]} can't be approved")
        when = _now(now)
        folder = self.root / "approved" / report["current"]["source_date"] / rid
        if folder.exists():
            raise ReviewError("approved files for this report already exist and are never overwritten")
        # Files first, state second: a failed write leaves the report unapproved.
        art = public_artifact(dict(report, state=C.APPROVED), approved_at=when)
        _write_json(folder / "report.json", art, exclusive=True)
        _write_text(folder / "report.md", outputs.markdown(art), exclusive=True)
        _write_text(folder / "news-brief.md", outputs.news_brief(art), exclusive=True)
        _write_text(folder / "teleprompter-draft.md", outputs.teleprompter(art), exclusive=True)
        _write_text(folder / "social-drafts.md", outputs.social(art), exclusive=True)
        ch = outputs.charts(art)
        _write_json(folder / "charts.json", ch, exclusive=True)
        for name, svg in outputs.svg_cards(ch).items():
            _write_text(folder / "cards" / f"{name}.svg", svg, exclusive=True)
        report["approved_at"] = when
        report["approved_by"] = actor
        self._transition(report, C.APPROVED, actor, now, acknowledged, note, action="approved")
        # A corrected version replaces the report it supersedes.
        if report.get("supersedes"):
            old = self.load(report["supersedes"])
            old["superseded_by"] = rid
            self._transition(old, C.SUPERSEDED, actor, now, True, f"Superseded by {rid}", action="superseded")
            old_folder = self.root / "approved" / old["current"]["source_date"] / old["report_id"]
            _write_json(old_folder / "superseded-by.json",
                        {"report_id": old["report_id"], "superseded_by": rid, "at": when}, exclusive=True)
        self.write_index()
        return report

    def create_correction(self, rid, rebuilt, actor, now=None):
        """A corrected version of an Approved report, as a new Draft that supersedes it once approved.
        `rebuilt` is a freshly built report for the same snapshots. The reviewer's earlier choices carry over."""
        old = self.load(rid)
        if old["state"] != C.APPROVED:
            raise ReviewError("only an Approved report can be corrected")
        if any(r["supersedes"] == rid and r["state"] in (C.DRAFT, C.HELD) for r in self.list()):
            raise ReviewError("a corrected version is already waiting for review")
        if rebuilt["current"]["snapshot_id"] != old["current"]["snapshot_id"]:
            raise ReviewError("a correction must cover the same snapshots")
        version = max(r["version"] for r in self.reports_for(old["current"]["source_date"])) + 1
        rebuilt["report_id"] = f"wm-{old['current']['source_date']}-r{version}"
        rebuilt["version"] = version
        rebuilt["supersedes"] = rid
        known = {f["id"] for f in rebuilt["findings"]} | {r["id"] for r in rebuilt["cities"] + rebuilt["counties"]}
        rebuilt["decisions"] = {k: v for k, v in old["decisions"].items() if k in known}
        return self.create_draft(rebuilt, actor, now)

    def write_index(self):
        """Archive of approved and superseded reports for members to browse later. Public-safe."""
        items = []
        for r in self.list():
            if r["state"] not in (C.APPROVED, C.SUPERSEDED):
                continue
            items.append({"report_id": r["report_id"], "status": r["state"], "source_date": r["source_date"],
                          "comparison_period": r["comparison_period"], "methodology_version": r["methodology_version"],
                          "supersedes": r["supersedes"], "superseded_by": r["superseded_by"],
                          "path": f"{r['source_date']}/{r['report_id']}/report.json"})
        current = next((i["report_id"] for i in items if i["status"] == C.APPROVED), None)
        _write_json(self.root / "approved" / "index.json",
                    {"schema": C.SCHEMA + "/index", "label": C.LABEL, "current_report_id": current,
                     "methodology_note": methodology_note([i["methodology_version"] for i in items]),
                     "reports": items})

    # ------------------------------------------------------------------ weekly runs
    def record_run(self, outcome, detail, now=None, report_id=None):
        entry = {"at": _now(now), "outcome": outcome, "report_id": report_id, "detail": detail}
        stamp = entry["at"].replace(":", "").replace("+0000", "Z")
        _write_json(self.root / "runs" / f"{stamp}.json", entry)
        _write_json(self.root / "last-run.json", entry)
        return entry


def methodology_note(versions):
    """A visible warning when reports made under different methodology versions are compared."""
    if len(set(versions)) > 1:
        return ("These reports were made with different methodology versions (" + ", ".join(sorted(set(versions)))
                + "). Compare them with care.")
    return None
