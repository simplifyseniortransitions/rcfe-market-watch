"""California RCFE Weekly Movers review screen: http://127.0.0.1:5083 (this Mac only; never published).

    .venv/bin/python movers_review.py                 reviews in private-data/movers (the private data repository)
    .venv/bin/python movers_review.py --store DIR     reviews somewhere else (e.g. a sample)
    .venv/bin/python movers_review.py --no-sync       don't pull or push the private repository
    .venv/bin/python movers_review.py --deploy        after publishing, also push the public files to GitHub Pages
                                                      (only once publication infrastructure is approved)

View a draft, its statewide totals, city and county movers and the facility changes behind them; include or
exclude findings, add private notes, approve, reject, hold, or create a corrected version of an approved
report; copy the News Production Brief; assign an approved RCFE Deal Room News episode; preview the public
Weekly Movers frame with a clearly labeled test copy of any report.

Approving a report publishes it: its sanitized public preview goes to site/data/weekly-movers/ (GitHub Pages
copy, pushed only with --deploy) and its free-community copy to the private store, and the current pointer
moves last. A failed publication leaves the previous published report in place.

Safety: listens on 127.0.0.1 only. Every change needs the page's one-time key and must come from this page
(Host and Origin are checked), so another website open in the browser can't act on it. The weekly job has no
way to approve or publish; only this screen calls Store.approve() and publish().
"""
import argparse
import getpass
import json
import re
import secrets
import subprocess
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pipeline import config as pipeline_config
from pipeline.movers import config as C
from pipeline.movers import publish as P
from pipeline.movers.report import build, counts
from pipeline.movers.store import ReviewError, Store

PORT = 5083
ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "preview" / "movers-review.html"
SITE = ROOT / "site"
DATA_REPO = "simplifyseniortransitions/rcfe-market-watch-data"
# Files the local test preview may serve, and nothing else (no directory listing).
PREVIEW_FILES = {"weekly-movers.html": "text/html; charset=utf-8",
                 "assets/weekly-movers.js": "text/javascript; charset=utf-8",
                 "assets/weekly-movers.css": "text/css; charset=utf-8",
                 "assets/guard.js": "text/javascript; charset=utf-8"}


def reviewer():
    return f"{getpass.getuser()} (review screen on this Mac)"


class App:
    def __init__(self, store: Store, paths=pipeline_config.DEFAULT_PATHS, sync=False, token=None,
                 public_dir=P.DEFAULT_PUBLIC_DIR, deploy=False):
        self.store, self.paths, self.sync = store, paths, sync
        self.public_dir, self.deploy = Path(public_dir), deploy
        self.token = token or secrets.token_urlsafe(24)
        self.actor = reviewer()

    def repo(self):
        return self.store.root.parent

    def pull(self):
        if self.sync:
            subprocess.run(["git", "-C", str(self.repo()), "pull", "-q", "--rebase"], check=False)

    def push(self, message):
        if not self.sync:
            return
        r = self.repo()
        subprocess.run(["git", "-C", str(r), "add", "movers"], check=False)
        if subprocess.run(["git", "-C", str(r), "diff", "--cached", "--quiet"]).returncode != 0:
            subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", message], check=False)
            subprocess.run(["git", "-C", str(r), "push", "-q"], check=False)

    def deploy_public(self, message):
        """Push site/data/weekly-movers to GitHub and republish GitHub Pages, the way the weekly job does.
        Only with --deploy. Commits nothing outside that folder."""
        if not self.deploy:
            return "Saved locally; not pushed to GitHub Pages (review screen started without --deploy)."
        g = ["git", "-C", str(ROOT)]
        rel = str(self.public_dir.relative_to(ROOT))
        steps = [g + ["add", "--", rel], g + ["commit", "-q", "-m", message, "--", rel],
                 g + ["pull", "-q", "--rebase", "origin", "main"], g + ["push", "-q", "origin", "HEAD:main"],
                 g + ["fetch", "-q", "origin", "gh-pages"]]
        for s in steps:
            if subprocess.run(s).returncode != 0 and "commit" not in s:
                return "Saved locally, but pushing to GitHub failed. The live page keeps the previous report."
        tree = subprocess.run(g + ["rev-parse", "HEAD:site"], capture_output=True, text=True).stdout.strip()
        commit = subprocess.run(g + ["commit-tree", tree, "-p", "origin/gh-pages", "-m", f"Publish site/ ({message})"],
                                capture_output=True, text=True).stdout.strip()
        if not commit or subprocess.run(g + ["push", "-q", "origin", f"{commit}:refs/heads/gh-pages"]).returncode:
            return "Pushed to main, but GitHub Pages wasn't republished. The live page keeps the previous report."
        subprocess.run(["gh", "api", "-X", "POST", "repos/simplifyseniortransitions/rcfe-market-watch/pages/builds"],
                       capture_output=True)
        return "Published to GitHub Pages. The Market Watch frame shows it within about 10 minutes."

    # ---------------------------------------------------------------- reads
    def report_view(self, rid):
        report = self.store.load(rid)
        view = {"report": report, "counts": counts(report), "state_label": C.STATE_LABELS[report["state"]],
                "flags": C.FLAGS, "labels": C.CHANGE_LABELS, "texts": {}, "cards": [],
                "log": [e for e in self.store.log() if e["report_id"] == rid],
                "publication": P.published_status(self.store, rid, self.public_dir),
                "news": json.loads(P.news_path(self.store, rid).read_text()) if P.news_path(self.store, rid).exists() else None,
                "deploy": self.deploy, "sample_store": P.is_sample(self.store)}
        if report.get("statewide") is not None:
            folder = self.store.root / "approved" / report["current"]["source_date"] / rid
            if report["state"] in (C.APPROVED, C.SUPERSEDED) and folder.exists():
                src = folder
            else:
                src = self.store.draft_dir(rid) / "preview"
            view["text_source"] = "approved" if src == folder else "draft preview"
            for key, name in (("report", "report.md"), ("brief", "news-brief.md"),
                              ("teleprompter", "teleprompter-draft.md"), ("social", "social-drafts.md")):
                p = src / name
                view["texts"][key] = p.read_text(encoding="utf-8") if p.exists() else ""
            view["cards"] = sorted(p.stem for p in (src / "cards").glob("*.svg"))
        return view

    def card(self, rid, name):
        report = self.store.load(rid)
        if not name.replace("-", "").isalnum():
            raise ReviewError("unknown card")
        folder = self.store.root / "approved" / report["current"]["source_date"] / rid / "cards"
        if not folder.exists():
            folder = self.store.draft_dir(rid) / "preview" / "cards"
        p = folder / f"{name}.svg"
        if not p.exists():
            raise ReviewError("unknown card")
        return p.read_bytes()

    def preview_file(self, scenario, rel):
        """Local test preview of the public frame. scenario: a report ID (labeled test copy), 'empty' or
        'unavailable'. Only whitelisted files; never a directory listing."""
        if rel in PREVIEW_FILES:
            return (SITE / rel).read_bytes(), PREVIEW_FILES[rel]
        m = re.fullmatch(r"data/weekly-movers/(current\.json|reports/(wm-[0-9-]+r\d+)\.json)", rel)
        if not m or scenario == "unavailable":
            raise ReviewError("not found")
        if scenario == "empty":
            if m.group(1) != "current.json":
                raise ReviewError("not found")
            body = {"schema": P.POINTER_SCHEMA, "label": C.LABEL, "status": "empty", "report_id": None,
                    "report_url": None, "message": P.EMPTY_MESSAGE, "updated_at": None, "test_preview": True,
                    "complete_report_url": None, "complete_report_label": "Complete report for free members — coming soon"}
            return json.dumps(body).encode(), "application/json"
        report = self.store.load(scenario)
        if report.get("statewide") is None:
            raise ReviewError("not found")
        pointer, payload = P.sample_preview(report)
        if m.group(1) == "current.json":
            return json.dumps(pointer).encode(), "application/json"
        if m.group(2) != scenario:
            raise ReviewError("not found")
        return json.dumps(payload).encode(), "application/json"

    # ---------------------------------------------------------------- actions
    def _publish(self, rid):
        try:
            P.publish(self.store, rid, self.public_dir, self.actor)
        except P.PublicationError as e:
            self.push(f"Weekly Movers: publication refused for {rid}")
            return {"published": False, "message": "Not published: " + "; ".join(e.problems)}
        self.push(f"Weekly Movers: published {rid}")
        return {"published": True, "message": self.deploy_public(f"Weekly Movers: {rid}")}

    def act(self, rid, action, body):
        s, who = self.store, self.actor
        if action == "decision":
            s.set_decision(rid, str(body.get("item", "")), str(body.get("choice", "")), who)
        elif action == "note":
            s.add_note(rid, str(body.get("text", "")), who)
        elif action == "approve":
            s.approve(rid, who, body.get("acknowledged") is True, str(body.get("note", "")))
            self.push(f"Weekly Movers: approved {rid}")
            if P.is_sample(s):
                return {"ok": True, "report_id": rid, "message": "Approved in the sample store; samples are never published."}
            return {"ok": True, "report_id": rid, **self._publish(rid)}
        elif action == "publish":
            return {"ok": True, "report_id": rid, **self._publish(rid)}
        elif action == "news":
            P.set_news(s, rid, body.get("title"), body.get("url"), body.get("youtube_url"), body.get("published_on"),
                       body.get("approved") is True, who)
            msg = "Episode saved."
            if P.published_status(s, rid, self.public_dir)["published"]:
                P.write_pointers(s, self.public_dir)
                msg = self.deploy_public(f"Weekly Movers news link: {rid}")
            self.push(f"Weekly Movers: news episode for {rid}")
            return {"ok": True, "report_id": rid, "message": msg}
        elif action == "news_clear":
            P.clear_news(s, rid, who)
            if P.published_status(s, rid, self.public_dir)["published"]:
                P.write_pointers(s, self.public_dir)
                self.deploy_public(f"Weekly Movers news link removed: {rid}")
        elif action == "reject":
            s.reject(rid, who, str(body.get("note", "")))
        elif action == "hold":
            s.hold(rid, who, str(body.get("note", "")))
        elif action == "correct":
            old = s.load(rid)
            qa = json.loads(self.paths.qa_report.read_text(encoding="utf-8")) if self.paths.qa_report.exists() else {}
            rebuilt = build(self.paths.snapshots, qa, as_of=date.fromisoformat(old["current"]["source_date"]))
            new = s.create_correction(rid, rebuilt, who)
            self.push(f"Weekly Movers: corrected version {new['report_id']}")
            return {"ok": True, "report_id": new["report_id"]}
        else:
            raise ReviewError("unknown action")
        self.push(f"Weekly Movers: {action} {rid}")
        return {"ok": True, "report_id": rid}


def make_handler(app: App, port=PORT):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def _host_ok(self):
            return self.headers.get("Host", "") in allowed_hosts or getattr(self.server, "testing", False)

        def do_GET(self):
            if not self._host_ok():
                return self.send_error(403)
            path = self.path.split("?")[0]
            try:
                if path in ("/", "/index.html"):
                    html = PAGE.read_text(encoding="utf-8").replace("__TOKEN__", app.token)
                    return self.send(html.encode(), "text/html; charset=utf-8")
                if path == "/api/reports":
                    app.pull()
                    return self.json({"reports": app.store.list(), "reviewer": app.actor, "sync": app.sync})
                parts = path.strip("/").split("/")
                if len(parts) >= 3 and parts[0] == "wm-preview":
                    body, ctype = app.preview_file(parts[1], "/".join(parts[2:]))
                    return self.send(body, ctype)
                if len(parts) == 3 and parts[:1] == ["api"] and parts[1] == "report":
                    return self.json(app.report_view(parts[2]))
                if len(parts) == 5 and parts[:2] == ["api", "report"] and parts[3] == "card":
                    return self.send(app.card(parts[2], parts[4].removesuffix(".svg")), "image/svg+xml")
            except ReviewError as e:
                return self.json({"ok": False, "error": str(e)}, 404)
            self.send_error(404)

        def do_POST(self):
            origin = self.headers.get("Origin", "")
            if not self._host_ok() or self.headers.get("X-Review-Key") != app.token or \
                    (origin and origin not in {f"http://{h}" for h in allowed_hosts}):
                return self.json({"ok": False, "error": "Not allowed."}, 403)
            parts = self.path.split("?")[0].strip("/").split("/")
            if len(parts) != 4 or parts[:2] != ["api", "report"]:
                return self.json({"ok": False, "error": "Not found."}, 404)
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 20000)
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self.json({"ok": False, "error": "Bad request."}, 400)
            try:
                return self.json(app.act(parts[2], parts[3], body))
            except ReviewError as e:
                return self.json({"ok": False, "error": str(e)}, 409)

        def json(self, data, status=200):
            self.send(json.dumps(data).encode(), "application/json", status)

        def send(self, body, ctype, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                             "img-src 'self'; frame-ancestors 'none'")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", type=Path, default=C.DEFAULT_STORE)
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)
    repo = args.store.parent
    if args.store == C.DEFAULT_STORE and not (repo / ".git").exists():
        print(f"The private data repository isn't on this Mac yet. Run once:\n"
              f"  gh repo clone {DATA_REPO} {repo}")
        return 1
    sync = not args.no_sync and (repo / ".git").exists()
    app = App(Store(args.store), sync=sync, deploy=args.deploy and not P.is_sample(Store(args.store)))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app, args.port))
    except OSError:
        print(f"The review screen is already running: http://127.0.0.1:{args.port}")
        return 0
    print(f"California RCFE Weekly Movers review: http://127.0.0.1:{args.port}  (this Mac only; Ctrl+C to stop)")
    print(f"Reports: {args.store}  ·  sync with private repository: {'on' if sync else 'off'}  ·  "
          f"push public files to GitHub Pages: {'on' if app.deploy else 'off'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
