"""California RCFE Weekly Movers publication layer: approved reports only.

    Approved report (private store)  ->  validate  ->  sanitized files  ->  pointer swapped last

Public (GitHub Pages, next to Market Watch; read by the Weekly Movers frame on rcfedealroom.com/market-watch):
    site/data/weekly-movers/reports/<report_id>.json   public preview of one approved report. Written once.
    site/data/weekly-movers/index.json                 every published report, with superseded labels
    site/data/weekly-movers/current.json               pointer to the current report (or a valid empty state)

Free-community (PRIVATE store, for later authenticated ingestion by the community app; never on GitHub Pages,
because a public static file can't be limited to members):
    movers/community/reports/<report_id>.json, movers/community/index.json, movers/community/current.json

Nothing here approves anything. publish() refuses any report that isn't Approved with a logged, acknowledged
approval, and refuses a store marked as a sample.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline.movers import config as C
from pipeline.movers.report import included

PUBLIC_SCHEMA = "weekly-movers-public/1"
COMMUNITY_SCHEMA = "weekly-movers-community/1"
POINTER_SCHEMA = "weekly-movers-pointer/1"
PREVIEW_TOP = 3
COMMUNITY_TOP = 20
RID = re.compile(r"^wm-\d{4}-\d{2}-\d{2}-r\d{1,3}$")
SAMPLE_MARKER = ".sample-only"
DEFAULT_PUBLIC_DIR = Path(__file__).resolve().parent.parent.parent / "site" / "data" / "weekly-movers"
EMPTY_MESSAGE = ("The first California RCFE Weekly Movers report is being prepared. Check back after the next "
                 "approved weekly update.")
METHODOLOGY = {
    "id": f"weekly-movers-methodology-{C.METHODOLOGY_VERSION}",
    "summary": [
        "Compares the two most recent weekly CDSS Residential Care Facilities for the Elderly files, about 7 days apart.",
        "Active records are those with Facility Status Licensed or On Probation.",
        "Recorded licensed capacity is the sum of Facility Capacity for active records: the license limit, not occupancy.",
        "Cities are CDSS mailing cities with known spelling errors corrected; counties are CDSS county labels.",
        "Percentages are shown only when the previous value is 10 or more.",
        "Every report is reviewed and approved by RCFE Deal Room before it appears here. Records that need "
        "verification are left out until checked.",
    ],
}
# Text that must never appear in a published file.
FORBIDDEN_TEXT = ("private-data", "reviews.jsonl", "/Users/", "drafts/", "\"notes\"", "\"private\"",
                  "decision_note", "SHARED_SECRET", "SHEET_SECRET", "token", "password", "api_key", "apikey",
                  "BEGIN PRIVATE KEY", "Facility Administrator", "Telephone")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"\(?\b\d{3}\)?[ .-]\d{3}-\d{4}\b")
NEWS_HOSTS = re.compile(r"^https://(www\.)?(rcfedealroom\.com|youtube\.com|youtu\.be|rcfe-deal-room\.marblism\.me)(/|$)")


class PublicationError(Exception):
    """Publication was refused or failed. The previously published files are untouched."""

    def __init__(self, problems):
        self.problems = problems if isinstance(problems, list) else [problems]
        super().__init__("; ".join(self.problems))


def _now(now=None):
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def _dump(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _atomic(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _write_once(path: Path, text: str):
    """Immutable report files: written once; a retry with identical content is fine, a different one is not."""
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise PublicationError(f"{path.name} is already published with different content; publish a correction")
        return
    _atomic(path, text)


def is_sample(store):
    return (store.root / SAMPLE_MARKER).exists()


# ---------------------------------------------------------------------------------------------- validation
def approved_artifact_path(store, report):
    return store.root / "approved" / report["current"]["source_date"] / report["report_id"] / "report.json"


def validate(store, rid):
    """(report, approved artifact). Raises PublicationError listing every problem."""
    problems = []
    if not isinstance(rid, str) or not RID.match(rid):
        raise PublicationError("not a report identifier")
    if is_sample(store):
        raise PublicationError("this is a sample store; sample reports are never published")
    report = store.load(rid)
    if report.get("state") != C.APPROVED:
        problems.append(f"report is {C.STATE_LABELS.get(report.get('state'), report.get('state'))}, not Approved")
    if not report.get("approved_by"):
        problems.append("no approval user")
    if not report.get("approved_at"):
        problems.append("no approval time")
    ack = [e for e in store.log() if e.get("report_id") == rid and e.get("action") == "approved"
           and e.get("acknowledged_reviewed") is True and e.get("user") == report.get("approved_by")]
    if not ack:
        problems.append("no acknowledged approval in the review log")
    cur, prev = report.get("current") or {}, report.get("previous") or {}
    for label, value in (("current snapshot", cur.get("snapshot_id")), ("previous snapshot", prev.get("snapshot_id")),
                         ("current source date", cur.get("source_date")), ("previous source date", prev.get("source_date")),
                         ("methodology version", report.get("methodology_version"))):
        if not value:
            problems.append(f"missing {label}")
    if problems:
        raise PublicationError(problems)

    path = approved_artifact_path(store, report)
    if not path.exists():
        raise PublicationError("the approved report file is missing")
    art = json.loads(path.read_text(encoding="utf-8"))
    if art.get("status") != C.APPROVED or art.get("report_id") != rid:
        problems.append("the approved report file does not match this approved report")

    # Held and excluded findings must not be in the approved file.
    shown = {f["id"] for items in art.get("facility_changes", {}).values() for f in items}
    for f in report["findings"]:
        if f["id"] in shown and not included(f, report["decisions"]):
            problems.append(f"held or excluded finding present: {f['id']}")
    areas = [r for k in ("city_movers", "county_movers") for rows in art.get(k, {}).values() for r in rows]
    by_id = {r["id"]: r for r in report["cities"] + report["counties"]}
    for a in areas:
        if a["id"] in by_id and not included(by_id[a["id"]], report["decisions"]):
            problems.append(f"held or excluded area present: {a['id']}")
        if a["count_change"] != a["current_count"] - a["previous_count"] or \
                a["capacity_change"] != a["current_capacity"] - a["previous_capacity"]:
            problems.append(f"area totals don't add up: {a['id']}")

    # Totals reconcile: with the review copy, with themselves, and with the findings.
    s, rs = art.get("statewide") or {}, report.get("statewide") or {}
    for k in ("previous_active", "current_active", "net_active_change", "newly_observed", "no_longer_active",
              "previous_capacity", "current_capacity", "net_capacity_change"):
        if s.get(k) != rs.get(k):
            problems.append(f"statewide {k} differs from the approved review copy")
    if s.get("net_active_change") != s.get("current_active", 0) - s.get("previous_active", 0):
        problems.append("net active change doesn't equal current minus previous")
    if s.get("net_active_change") != s.get("newly_observed", 0) - s.get("no_longer_active", 0):
        problems.append("net active change doesn't equal newly observed minus no longer active")
    if s.get("net_capacity_change") != s.get("current_capacity", 0) - s.get("previous_capacity", 0):
        problems.append("net capacity change doesn't equal current minus previous")
    for kind, total in (("newly_observed", s.get("newly_observed")), ("no_longer_active", s.get("no_longer_active"))):
        listed = len(art.get("facility_changes", {}).get(kind, []))
        everything = sum(1 for f in report["findings"] if f["change_type"] == kind)
        if everything != total or listed > total:
            problems.append(f"{kind} records don't reconcile with the total")
    if art.get("counts", {}).get("included_findings") != len(shown):
        problems.append("included-finding count doesn't match the listed findings")
    if art.get("disclaimer") != C.DISCLAIMER or art.get("spoken_disclaimer") != C.SPOKEN_DISCLAIMER:
        problems.append("required disclaimer missing or changed")
    blob = json.dumps(art)
    if "\"notes\"" in blob or "\"private\"" in blob:
        problems.append("private fields present")
    if problems:
        raise PublicationError(problems)
    return report, art


# ---------------------------------------------------------------------------------------------- payloads
def _area(r):
    return {"area": r["area"], "county": r["county"], "previous_count": r["previous_count"],
            "current_count": r["current_count"], "count_change": r["count_change"], "count_pct": r["count_pct"],
            "previous_capacity": r["previous_capacity"], "current_capacity": r["current_capacity"],
            "capacity_change": r["capacity_change"], "capacity_pct": r["capacity_pct"]}


def _dates(art):
    return {"report_id": art["report_id"], "version": art.get("version", 1),
            "reporting_period": {"previous_source_date": art["previous_source_date"],
                                 "current_source_date": art["current_source_date"],
                                 "days": art.get("comparison_days")},
            "current_source_date": art["current_source_date"], "previous_source_date": art["previous_source_date"],
            "processing_date": art.get("processing_date"), "approval_date": art.get("approval_date"),
            "methodology_version": art["methodology_version"], "methodology": METHODOLOGY,
            "supersedes": art.get("supersedes")}


def _summary(s):
    return {k: s[k] for k in ("previous_active", "current_active", "net_active_change", "newly_observed",
                              "no_longer_active", "previous_capacity", "current_capacity", "net_capacity_change")} | {
        "counties_affected": s["counties_with_count_change"], "cities_affected": s["cities_with_count_change"]}


def preview_payload(art):
    """The public Market Watch preview: totals and the top three movers only. No facility records."""
    cm, km = art["city_movers"], art["county_movers"]
    return {
        "schema": PUBLIC_SCHEMA, "label": C.LABEL, "status": "approved", **_dates(art),
        "statewide": _summary(art["statewide"]),
        "movers": {
            "city_count_increases": [_area(r) for r in cm.get("count_increases", [])[:PREVIEW_TOP]],
            "city_count_decreases": [_area(r) for r in cm.get("count_decreases", [])[:PREVIEW_TOP]],
            "county_capacity_increases": [_area(r) for r in km.get("capacity_increases", [])[:PREVIEW_TOP]],
            "county_capacity_decreases": [_area(r) for r in km.get("capacity_decreases", [])[:PREVIEW_TOP]],
        },
        "city_note": C.CITY_NOTE, "disclaimer": C.SPOKEN_DISCLAIMER, "full_disclaimer": C.DISCLAIMER,
        "source_name": C.SOURCE_NAME,
    }


COMMUNITY_FINDING_KEYS = ("change_type", "change_label", "facility_number", "facility_name", "city", "county",
                          "previous", "current", "change", "capacity", "status_origin", "license_first_date",
                          "closed_date", "first_observed", "first_observed_is_earliest_file", "last_observed",
                          "last_observed_active")


def community_payload(art):
    """The complete approved statewide report for free members. Private store only."""
    def finding(f):
        out = {k: f[k] for k in COMMUNITY_FINDING_KEYS if k in f}
        out["verification"] = "Requires verification" if f.get("verification") == "requires_verification" else "Routine"
        return out

    movers = {}
    for kind in ("city_movers", "county_movers"):
        movers[kind] = {k: [_area(r) | {"record_count": r["record_count"]} for r in rows[:COMMUNITY_TOP]]
                        for k, rows in art[kind].items()}
    changes = {k: [finding(f) for f in items] for k, items in art["facility_changes"].items()}
    return {
        "schema": COMMUNITY_SCHEMA, "label": C.LABEL, "status": "approved", "audience": "free members",
        **_dates(art), "statewide": _summary(art["statewide"]), **movers, "facility_changes": changes,
        "counts": {"records_shown": sum(len(v) for v in changes.values()),
                   "records_held_or_excluded": art["counts"]["held_or_excluded_findings"]},
        "terminology": art["terminology"], "city_note": C.CITY_NOTE, "limitations": art["limitations"],
        "disclaimer": C.DISCLAIMER, "spoken_disclaimer": C.SPOKEN_DISCLAIMER, "source_name": C.SOURCE_NAME,
    }


def scan(text, report):
    """Problems found in text that is about to be published."""
    found = [t for t in FORBIDDEN_TEXT if t.lower() in text.lower()]
    if EMAIL.search(text):
        found.append("email address")
    if PHONE.search(text):
        found.append("phone number")
    streets = {(f.get("private") or {}).get(k) for f in report["findings"] for k in ("street", "previous", "current")}
    for s in streets - {None, ""}:
        if len(s) > 6 and s in text:
            found.append("street address")
            break
    return found


# ---------------------------------------------------------------------------------------------- news episode
def news_path(store, rid):
    return store.root / "news" / f"{rid}.json"


def load_news(store, rid):
    p = news_path(store, rid)
    if not p.exists():
        return None
    n = json.loads(p.read_text(encoding="utf-8"))
    return n if n.get("approved") is True else None


def set_news(store, rid, title, url, youtube_url, published_on, approved, actor, now=None):
    """Manually assign an RCFE Deal Room News episode to an approved report. Nothing is inferred or scraped.
    The link is published only when `approved` is True."""
    from pipeline.movers.store import ReviewError
    if not actor:
        raise ReviewError("a reviewer is required")
    report = store.load(rid)
    if report["state"] != C.APPROVED:
        raise ReviewError("an episode can only be assigned to an Approved report")
    title, url, youtube_url = (title or "").strip()[:160], (url or "").strip(), (youtube_url or "").strip()
    if not title or not NEWS_HOSTS.match(url):
        raise ReviewError("enter a title and an https link on rcfedealroom.com or YouTube")
    if youtube_url and not re.match(r"^https://(www\.)?(youtube\.com|youtu\.be)/", youtube_url):
        raise ReviewError("the YouTube link must start with https://www.youtube.com/ or https://youtu.be/")
    if published_on and not re.match(r"^\d{4}-\d{2}-\d{2}$", published_on):
        raise ReviewError("publication date must be YYYY-MM-DD")
    entry = {"report_id": rid, "title": title, "url": url, "youtube_url": youtube_url or None,
             "published_on": published_on or None, "approved": approved is True, "saved_by": actor,
             "saved_at": _now(now)}
    _atomic(news_path(store, rid), _dump(entry))
    store._append_log({"action": "news_episode_saved" if approved is True else "news_episode_draft", "user": actor,
                       "at": entry["saved_at"], "report_id": rid, "current_snapshot_id": report["current"]["snapshot_id"],
                       "previous_snapshot_id": report["previous"]["snapshot_id"], "previous_state": report["state"],
                       "new_state": report["state"], "included_findings": None, "excluded_or_held_findings": None,
                       "acknowledged_reviewed": approved is True, "note": "", "item": url})
    return entry


def clear_news(store, rid, actor, now=None):
    p = news_path(store, rid)
    if p.exists():
        p.unlink()
    store._append_log({"action": "news_episode_removed", "user": actor, "at": _now(now), "report_id": rid,
                       "acknowledged_reviewed": False, "note": "", "item": None})


def _public_news(n):
    if not n:
        return None
    return {"title": n["title"], "url": n["url"], "youtube_url": n.get("youtube_url"), "published_on": n.get("published_on")}


# ---------------------------------------------------------------------------------------------- pointers
def _published(store, public_dir):
    """Reports with both public and community files, newest first, with their current review state."""
    out = []
    for r in store.list():
        if (public_dir / "reports" / f"{r['report_id']}.json").exists() and \
                (store.root / "community" / "reports" / f"{r['report_id']}.json").exists():
            out.append(r)
    return out


def _index(store, published, url_prefix):
    items = []
    for r in published:
        items.append({"report_id": r["report_id"], "status": r["state"], "version": r["version"],
                      "current_source_date": r["source_date"], "comparison_period": r["comparison_period"],
                      "methodology_version": r["methodology_version"], "supersedes": r["supersedes"],
                      "superseded_by": r["superseded_by"],
                      "label": "Corrected version" if r["supersedes"] else
                      ("Superseded by a corrected version" if r["state"] == C.SUPERSEDED else None),
                      "report_url": f"{url_prefix}{r['report_id']}.json"})
    versions = sorted({i["methodology_version"] for i in items})
    return {"schema": POINTER_SCHEMA + "/index", "label": C.LABEL, "reports": items,
            "methodology_note": ("Reports here were made with different methodology versions (" + ", ".join(versions)
                                 + "). Compare them with care.") if len(versions) > 1 else None}


def _current(store, published, url_prefix, now, extra):
    live = [r for r in published if r["state"] == C.APPROVED]
    if not live:
        return {"schema": POINTER_SCHEMA, "label": C.LABEL, "status": "empty", "report_id": None,
                "report_url": None, "message": EMPTY_MESSAGE, "updated_at": _now(now), **extra}
    r = live[0]
    return {"schema": POINTER_SCHEMA, "label": C.LABEL, "status": "published", "report_id": r["report_id"],
            "report_url": f"{url_prefix}{r['report_id']}.json", "current_source_date": r["source_date"],
            "comparison_period": r["comparison_period"], "corrected": bool(r["supersedes"]),
            "news": _public_news(load_news(store, r["report_id"])), "updated_at": _now(now), **extra}


def write_pointers(store, public_dir=DEFAULT_PUBLIC_DIR, now=None):
    """Rebuild index.json and current.json (public and community), each swapped in atomically, current last."""
    published = _published(store, Path(public_dir))
    cta = {"complete_report_url": C.COMMUNITY_URL, "complete_report_label":
           "View the complete Weekly Movers report" if C.COMMUNITY_URL else
           "Complete report for free members — coming soon"}
    community = store.root / "community"
    _atomic(Path(public_dir) / "index.json", _dump(_index(store, published, "reports/")))
    _atomic(community / "index.json", _dump(_index(store, published, "reports/")))
    _atomic(community / "current.json", _dump(_current(store, published, "reports/", now, {})))
    current = _current(store, published, "reports/", now, cta)
    _atomic(Path(public_dir) / "current.json", _dump(current))
    return current


# ---------------------------------------------------------------------------------------------- publish
def _record(store, entry):
    path = store.root / "publications.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def publish(store, rid, public_dir=DEFAULT_PUBLIC_DIR, actor="", now=None):
    """Validate an approved report, write its sanitized files, then move the current pointer.
    On any problem nothing already published changes, and the failure is recorded privately."""
    public_dir = Path(public_dir)
    try:
        report, art = validate(store, rid)
        preview, community = _dump(preview_payload(art)), _dump(community_payload(art))
        for text in (preview, community):
            problems = scan(text, report)
            if problems:
                raise PublicationError([f"content check failed: {p}" for p in problems])
        if any(k in preview for k in ('"facility_changes"', '"facility_number"', '"facility_name"')):
            raise PublicationError("facility records found in the public preview")
        _write_once(public_dir / "reports" / f"{rid}.json", preview)
        _write_once(store.root / "community" / "reports" / f"{rid}.json", community)
        # Read back before moving the pointer.
        for path, text in ((public_dir / "reports" / f"{rid}.json", preview),
                           (store.root / "community" / "reports" / f"{rid}.json", community)):
            if path.read_text(encoding="utf-8") != text:
                raise PublicationError(f"{path.name} did not save correctly")
        current = write_pointers(store, public_dir, now)
    except PublicationError as e:
        _record(store, {"at": _now(now), "report_id": rid, "outcome": "refused", "user": actor, "problems": e.problems})
        raise
    except Exception as e:  # noqa: BLE001 — record privately, keep the last good public files
        _record(store, {"at": _now(now), "report_id": rid, "outcome": "failed", "user": actor,
                        "problems": [f"{type(e).__name__}: {e}"]})
        raise PublicationError(f"publication failed: {type(e).__name__}") from e
    _record(store, {"at": _now(now), "report_id": rid, "outcome": "published", "user": actor,
                    "current": current["report_id"]})
    return current


def published_status(store, rid, public_dir=DEFAULT_PUBLIC_DIR):
    path = store.root / "publications.jsonl"
    last = None
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            if e.get("report_id") == rid:
                last = e
    return {"published": (Path(public_dir) / "reports" / f"{rid}.json").exists(), "last_attempt": last}


# ---------------------------------------------------------------------------------------------- test preview
def sample_preview(report):
    """A clearly labeled, never-published preview of any report (e.g. the Nov 22 sample), for this Mac only.
    It is built in memory and served only by the local review screen."""
    from pipeline.movers.report import public_artifact
    art = public_artifact(report)
    p = preview_payload(art)
    p["status"] = "test_preview"
    p["test_preview"] = True
    p["test_label"] = "TEST PREVIEW — NOT A PUBLISHED REPORT"
    p["approval_date"] = None
    pointer = {"schema": POINTER_SCHEMA, "label": C.LABEL, "status": "test_preview", "test_preview": True,
               "report_id": report["report_id"], "report_url": f"reports/{report['report_id']}.json",
               "current_source_date": report["current"]["source_date"], "comparison_period": report["comparison_period"],
               "corrected": False, "news": None, "updated_at": report["created_at"],
               "complete_report_url": None, "complete_report_label": "Complete report for free members — coming soon"}
    return pointer, p
