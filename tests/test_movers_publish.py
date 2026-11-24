"""Weekly Movers publication layer. Numbers in brackets are the spec's test items (1-32)."""
import json
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from pipeline.movers import config as C
from pipeline.movers import publish as P
from pipeline.movers.run import make_draft
from pipeline.movers.store import ReviewError, Store
from tests.test_movers import D1, D2, D3, NOW, call, qa, save, week

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
JS = (SITE / "assets" / "weekly-movers.js").read_text()
HTML = (SITE / "weekly-movers.html").read_text()
RID = "wm-2026-11-15-r1"


@pytest.fixture
def env(paths):
    """A real-looking store with one Nov 8 -> Nov 15 draft, and an empty public folder."""
    save(paths, D1, week(34, {30: {"Facility Status": "PENDING"}, 31: {"Facility Status": "PENDING"},
                              32: {"Facility Status": "CLOSED"}, 33: {"Facility Status": "CLOSED"}}))
    save(paths, D2, week(34, {30: {"License First Date": "11/12/2026"}, 31: {"License First Date": "11/13/2026"},
                              32: {"Facility Status": "CLOSED"}, 33: {"Facility Status": "CLOSED"},
                              5: {"Facility Status": "CLOSED", "Closed Date": "11/12/2026"},
                              7: {"Facility Capacity": "8"}, 8: {"Facility Capacity": "4"},
                              # Held: a large capacity change; and a review-only address change.
                              12: {"Facility Capacity": "90"}, 13: {"Facility Address": "77 HIDDEN LANE"}}))
    qa(paths, D1, D2)
    store = Store(paths.root / "movers")
    make_draft(store, paths, now=NOW)
    return store, paths.root / "public"


def approve(store, rid=RID, note=""):
    store.approve(rid, "Reviewer", True, note, now=NOW)


def published(public):
    return json.loads((public / "current.json").read_text())


def files(folder):
    return {str(p.relative_to(folder)): p.read_text() for p in sorted(folder.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------------------------- refusals
@pytest.mark.parametrize("state", ["draft", "held", "rejected"])
def test_unapproved_reports_cannot_publish(env, state):  # [1] [2] [3]
    store, public = env
    if state == "held":
        store.hold(RID, "Reviewer", now=NOW)
    if state == "rejected":
        store.reject(RID, "Reviewer", now=NOW)
    with pytest.raises(P.PublicationError):
        P.publish(store, RID, public, now=NOW)
    assert not (public / "reports").exists() and not (public / "current.json").exists()
    entry = json.loads((store.root / "publications.jsonl").read_text().splitlines()[-1])
    assert entry["outcome"] == "refused"                      # recorded privately


def test_approved_report_publishes_sanitized_files(env):  # [4]
    store, public = env
    approve(store)
    current = P.publish(store, RID, public, now=NOW)
    assert current["status"] == "published" and current["report_id"] == RID
    assert set(files(public)) == {"current.json", "index.json", f"reports/{RID}.json"}
    preview = json.loads((public / "reports" / f"{RID}.json").read_text())
    assert preview["schema"] == P.PUBLIC_SCHEMA and preview["status"] == "approved"
    for key in ("report_id", "reporting_period", "current_source_date", "previous_source_date", "processing_date",
                "approval_date", "methodology_version", "methodology", "disclaimer"):
        assert preview[key]
    assert set(preview["statewide"]) == {"previous_active", "current_active", "net_active_change", "newly_observed",
                                         "no_longer_active", "previous_capacity", "current_capacity",
                                         "net_capacity_change", "counties_affected", "cities_affected"}
    assert set(preview["movers"]) == {"city_count_increases", "city_count_decreases", "county_capacity_increases",
                                      "county_capacity_decreases"}
    assert all(len(v) <= 3 for v in preview["movers"].values())
    assert (store.root / "community" / "reports" / f"{RID}.json").exists()


def test_acknowledgment_is_required(env):  # [5]
    store, public = env
    approve(store)
    log = store.root / "reviews.jsonl"
    lines = [json.loads(x) for x in log.read_text().splitlines()]
    for e in lines:
        if e["action"] == "approved":
            e["acknowledged_reviewed"] = False
    log.write_text("".join(json.dumps(e) + "\n" for e in lines))
    with pytest.raises(P.PublicationError, match="acknowledged"):
        P.publish(store, RID, public, now=NOW)
    with pytest.raises(ReviewError):
        store.approve("wm-2026-11-15-r1", "Reviewer", False)


def test_missing_source_metadata_prevents_publication(env):  # [6]
    store, public = env
    approve(store)
    path = store.draft_dir(RID) / "report.json"
    r = json.loads(path.read_text())
    r["previous"]["source_date"] = None
    path.write_text(json.dumps(r))
    with pytest.raises(P.PublicationError, match="previous source date"):
        P.publish(store, RID, public, now=NOW)
    assert not public.exists() or not (public / "current.json").exists()


# ---------------------------------------------------------------------------------------------- content
def test_held_and_excluded_findings_are_left_out(env):  # [7] [8]
    store, public = env
    r = store.load(RID)
    held = next(f for f in r["findings"] if f["held"])
    excluded = next(f for f in r["findings"] if f["change_type"] == "capacity_decrease")
    store.set_decision(RID, excluded["id"], "exclude", "Reviewer")
    approve(store)
    P.publish(store, RID, public, now=NOW)
    community = (store.root / "community" / "reports" / f"{RID}.json").read_text()
    everything = community + "".join(files(public).values())
    for f in (held, excluded):
        assert f"#{f['facility_number']}" not in everything and f["facility_name"] not in everything
    # Tampering with the approved file is caught before anything is written.
    approved = store.root / "approved" / "2026-11-15" / RID / "report.json"
    art = json.loads(approved.read_text())
    art["facility_changes"].setdefault("capacity_increase", []).append({**held, "flags": []})
    approved.write_text(json.dumps(art))
    with pytest.raises(P.PublicationError, match="held or excluded"):
        P.validate(store, RID)


def test_private_notes_and_review_log_are_left_out(env):  # [9] [10]
    store, public = env
    store.add_note(RID, "PRIVATE-NOTE-XYZ", "Reviewer", now=NOW)
    approve(store, note="DECISION-NOTE-XYZ")
    P.publish(store, RID, public, now=NOW)
    blob = "".join(files(public).values()) + "".join(files(store.root / "community").values())
    for text in ("PRIVATE-NOTE-XYZ", "DECISION-NOTE-XYZ", "Reviewer", "reviews.jsonl", "acknowledged", "approved_by"):
        assert text not in blob


def test_street_addresses_stay_out(env):  # [11]
    store, public = env
    approve(store)
    P.publish(store, RID, public, now=NOW)
    blob = "".join(files(public).values()) + "".join(files(store.root / "community").values())
    assert "HIDDEN" not in blob and "OAK ST" not in blob and "OAK STREET" not in blob
    preview = (public / "reports" / f"{RID}.json").read_text()
    assert "facility_name" not in preview and "facility_number" not in preview
    assert P.scan("123 OAK ST something", {"findings": [{"private": {"street": "123 OAK ST"}}]}) == ["street address"]
    assert "email address" in P.scan("a@b.co", {"findings": []}) and "phone number" in P.scan("(555) 555-0100", {"findings": []})


def test_public_values_reconcile_with_the_approved_report(env):  # [12]
    store, public = env
    approve(store)
    P.publish(store, RID, public, now=NOW)
    art = json.loads((store.root / "approved" / "2026-11-15" / RID / "report.json").read_text())
    preview = json.loads((public / "reports" / f"{RID}.json").read_text())
    for k, v in preview["statewide"].items():
        source = {"counties_affected": "counties_with_count_change", "cities_affected": "cities_with_count_change"}.get(k, k)
        assert v == art["statewide"][source]
    top = preview["movers"]["city_count_increases"]
    assert [r["area"] for r in top] == [r["area"] for r in art["city_movers"]["count_increases"][:3]]
    s = preview["statewide"]
    assert s["net_active_change"] == s["current_active"] - s["previous_active"] == s["newly_observed"] - s["no_longer_active"]


# ---------------------------------------------------------------------------------------------- pointer
def test_pointer_moves_last_and_atomically(env, monkeypatch):  # [13]
    store, public = env
    approve(store)
    order = []
    real = P._atomic

    def spy(path, text):
        order.append(path.name)
        real(path, text)
    monkeypatch.setattr(P, "_atomic", spy)
    P.publish(store, RID, public, now=NOW)
    assert order[-1] == "current.json" and order.index(f"{RID}.json") < order.index("index.json")
    assert not list(public.rglob(".*.tmp"))


def test_failed_publication_keeps_the_previous_report(env, paths, monkeypatch):  # [14]
    store, public = env
    approve(store)
    P.publish(store, RID, public, now=NOW)
    before = files(public)
    # Next week: approved, but writing its file fails.
    save(paths, D3, week(34, {30: {"License First Date": "11/12/2026"}, 31: {"License First Date": "11/13/2026"},
                              32: {"Facility Status": "CLOSED"}, 33: {"Facility Status": "CLOSED"},
                              5: {"Facility Status": "CLOSED"}}))
    qa(paths, D1, D2, D3)
    make_draft(store, paths, now=NOW)
    store.approve("wm-2026-11-22-r1", "Reviewer", True, now=NOW)

    def boom(path, text):
        raise OSError("disk full")
    monkeypatch.setattr(P, "_write_once", boom)
    with pytest.raises(P.PublicationError):
        P.publish(store, "wm-2026-11-22-r1", public, now=NOW)
    assert files(public) == before and published(public)["report_id"] == RID
    last = json.loads((store.root / "publications.jsonl").read_text().splitlines()[-1])
    assert last["outcome"] == "failed" and "disk full" in last["problems"][0]


def test_published_reports_are_immutable(env):  # [15]
    store, public = env
    approve(store)
    P.publish(store, RID, public, now=NOW)
    path = public / "reports" / f"{RID}.json"
    P.publish(store, RID, public, now=NOW)                      # same content again is fine
    path.write_text(path.read_text().replace('"approved"', '"tampered"', 1))
    with pytest.raises(P.PublicationError, match="different content"):
        P.publish(store, RID, public, now=NOW)


def test_corrections_supersede_without_overwriting(env, paths):  # [16]
    store, public = env
    approve(store)
    P.publish(store, RID, public, now=NOW)
    first = (public / "reports" / f"{RID}.json").read_text()
    from pipeline.movers.report import build
    rebuilt = build(paths.snapshots, json.loads(paths.qa_report.read_text()), now=NOW)
    new = store.create_correction(RID, rebuilt, "Reviewer", now=NOW)
    assert published(public)["report_id"] == RID                # a draft correction changes nothing
    store.approve(new["report_id"], "Reviewer", True, now=NOW)
    P.publish(store, new["report_id"], public, now=NOW)
    cur = published(public)
    assert cur["report_id"] == "wm-2026-11-15-r2" and cur["corrected"] is True
    index = json.loads((public / "index.json").read_text())
    by = {i["report_id"]: i for i in index["reports"]}
    assert by[RID]["status"] == "superseded" and by[RID]["superseded_by"] == "wm-2026-11-15-r2"
    assert by["wm-2026-11-15-r2"]["label"] == "Corrected version"
    assert (public / "reports" / f"{RID}.json").read_text() == first


def test_empty_state(env):  # [17]
    store, public = env
    cur = P.write_pointers(store, public, now=NOW)
    assert cur["status"] == "empty" and cur["report_id"] is None and cur["message"] == P.EMPTY_MESSAGE
    assert "being prepared" in JS and "Check back after the next approved weekly update" in JS
    assert json.loads((public / "index.json").read_text())["reports"] == []


def test_site_ships_with_a_valid_empty_or_published_pointer():  # [17]
    cur = json.loads((SITE / "data" / "weekly-movers" / "current.json").read_text())
    assert cur["schema"] == P.POINTER_SCHEMA and cur["status"] in ("empty", "published")
    assert "test_preview" not in cur


# ---------------------------------------------------------------------------------------------- component
def test_failure_state_and_independence():  # [18]
    assert "Weekly Movers is temporarily unavailable. The rest of RCFE Deal Room Market Watch remains available." in JS
    assert JS.count("showMessage(FAILED)") >= 2 and "catch {" in JS
    assert "common.js" not in HTML and "map-preview" not in HTML and "assets/guard.js" in HTML
    assert 'content="noindex, nofollow"' in HTML


def test_component_reads_values_without_calculating():  # [19]
    body = JS[JS.index("export function renderReport"):JS.index("export function renderCtas")]
    # No arithmetic on report numbers: values come straight from the artifact.
    assert not re.search(r"\b(s|r|report|m)(\.\w+|\[\w+\])\s*[-+*/]\s*\w", body)
    assert "statewide" in body and "net_active_change" in body and "previous_active" in body
    assert "data/weekly-movers/" in JS and "current.json" in JS


def test_messages_are_namespaced():  # [20] [21] [22]
    assert 'HEIGHT_MESSAGE = "rcfe-weekly-movers-height"' in JS and 'ANALYTICS_EVENT = "rcfe_weekly_movers"' in JS
    for other in ('"rcfe-height"', '"rcfe-map-height"', '"rcfe-map-ready"', '"rcfe-map-context"', "rcfe_map_preview",
                  "setupEarlyAccess", "early_access_form", "postMessage({ type: \"rcfe-height\""):
        assert other not in JS
    assert ", origin)" in JS and '"*"' not in JS
    # The existing frames still send their own messages, unchanged.
    assert '{ type: "rcfe-height", height }' in (SITE / "assets" / "common.js").read_text()
    mp = (SITE / "assets" / "map-preview.js").read_text()
    assert '{ type: "rcfe-map-height", height }' in mp and 'event: "rcfe_map_preview"' in mp
    assert "weekly-movers" not in mp and "rcfe_weekly" not in mp and "weekly-movers" not in (SITE / "map.html").read_text()


def test_community_contract_has_only_approved_fields(env):  # [23]
    store, public = env
    approve(store)
    P.publish(store, RID, public, now=NOW)
    c = json.loads((store.root / "community" / "reports" / f"{RID}.json").read_text())
    assert c["schema"] == P.COMMUNITY_SCHEMA and c["audience"] == "free members"
    allowed = set(P.COMMUNITY_FINDING_KEYS) | {"verification"}
    for items in c["facility_changes"].values():
        for f in items:
            assert set(f) <= allowed and f["verification"] in ("Routine", "Requires verification")
    assert "address_change" not in c["facility_changes"]
    for kind in ("city_movers", "county_movers"):
        assert all(len(v) <= P.COMMUNITY_TOP for v in c[kind].values())
    assert C.TOP_N >= P.COMMUNITY_TOP
    # Member detail never goes to the public GitHub Pages folder.
    assert not (public / "community").exists() and "facility_changes" not in "".join(files(public).values())
    assert json.loads((store.root / "community" / "current.json").read_text())["report_id"] == RID


# ---------------------------------------------------------------------------------------------- security
@pytest.fixture
def server(env):
    import movers_review
    store, public = env
    app = movers_review.App(store, token="k" * 30, public_dir=public)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), movers_review.make_handler(app))
    httpd.testing = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", app, store, public
    httpd.shutdown()


def test_no_directory_listing_and_no_private_paths(server):  # [24] [25]
    base, app, store, public = server
    for path in ("/wm-preview/empty/data/weekly-movers/", "/wm-preview/empty/assets/", "/wm-preview/empty/",
                 "/wm-preview/empty/data/weekly-movers/index.json", "/wm-preview/empty/../movers/reviews.jsonl",
                 f"/wm-preview/{RID}/data/weekly-movers/reports/wm-2026-11-08-r1.json",
                 "/wm-preview/unavailable/data/weekly-movers/current.json"):
        assert call(base + path)[0] == 404, path
    status, body = call(f"{base}/wm-preview/{RID}/data/weekly-movers/current.json")
    assert status == 200 and json.loads(body)["test_preview"] is True
    approve(store)
    P.publish(store, RID, public, now=NOW)
    blob = "".join(files(public).values())
    for text in ("private-data", "/Users/", "movers/", "drafts", str(store.root)):
        assert text not in blob
    assert not (public / "index.html").exists()
    assert P.RID.match(RID) and not P.RID.match("../x") and not P.RID.match("wm-2026-11-15-r1/../../x")


def test_no_secrets_in_generated_artifacts(env):  # [26]
    store, public = env
    approve(store)
    P.publish(store, RID, public, now=NOW)
    blob = "".join(files(public).values()) + "".join(files(store.root / "community").values())
    assert not re.search(r"(sk-[A-Za-z0-9]{20}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30}|PRIVATE KEY|script\.google|secret)", blob, re.I)
    assert P.scan(blob, store.load(RID)) == []


def test_analytics_events_are_non_personal():  # [27]
    actions = set(re.findall(r'track\("(\w+)"', JS))
    assert actions == {"weekly_movers_public_view", "weekly_movers_methodology_click", "weekly_movers_complete_report_click",
                       "weekly_movers_news_click", "weekly_movers_period_view"}
    labels = re.findall(r'track\("\w+",\s*([^)]+)\)', JS)
    assert labels == ["report.current_source_date"]                     # a date, nothing personal


def test_news_link_is_manual_and_approved_only(env):  # [28] [29]
    store, public = env
    with pytest.raises(ReviewError):
        P.set_news(store, RID, "Ep 1", "https://www.youtube.com/watch?v=x", None, "2026-11-25", True, "Reviewer")
    approve(store)
    P.publish(store, RID, public, now=NOW)
    assert published(public)["news"] is None                             # no link until one is saved
    with pytest.raises(ReviewError):
        P.set_news(store, RID, "Ep 1", "https://evil.example/x", None, None, True, "Reviewer")
    P.set_news(store, RID, "Ep 1", "https://www.youtube.com/watch?v=abc", None, "2026-11-25", False, "Reviewer")
    P.write_pointers(store, public, now=NOW)
    assert published(public)["news"] is None                             # saved but not approved
    P.set_news(store, RID, "Ep 1", "https://www.youtube.com/watch?v=abc", None, "2026-11-25", True, "Reviewer")
    P.write_pointers(store, public, now=NOW)
    assert published(public)["news"]["url"] == "https://www.youtube.com/watch?v=abc"
    assert "news" not in (public / "reports" / f"{RID}.json").read_text()  # never baked into the immutable file
    P.clear_news(store, RID, "Reviewer")
    P.write_pointers(store, public, now=NOW)
    assert published(public)["news"] is None
    assert "const news = pointer && pointer.news && SAFE_LINK.test" in JS and "if (news)" in JS


def test_cache_behavior():  # [30]
    assert 'fetch(`${base}current.json`, { cache: "no-cache"' in JS          # always revalidated
    assert "fetch(base + pointer.report_url, { credentials" in JS           # immutable, cacheable by ID
    assert "REPORT_PATH.test(pointer.report_url" in JS
    import movers_review
    assert "no-store" in Path(movers_review.__file__).read_text()


def test_sample_cannot_become_the_current_report(env, tmp_path):  # [31]
    store, public = env
    approve(store)
    (store.root / P.SAMPLE_MARKER).write_text("sample")
    with pytest.raises(P.PublicationError, match="sample"):
        P.publish(store, RID, public, now=NOW)
    assert not (public / "current.json").exists()
    pointer, payload = P.sample_preview(store.load(RID))
    assert pointer["test_preview"] and payload["test_label"] == "TEST PREVIEW — NOT A PUBLISHED REPORT"
    assert payload["status"] == "test_preview" and payload["approval_date"] is None
    sample = ROOT / "movers-sample"
    if sample.exists():
        assert (sample / P.SAMPLE_MARKER).exists()
    assert "status !== \"approved\" && !(pointer.test_preview && report.test_preview)" in JS


def test_publication_stays_out_of_the_weekly_job():  # [32]
    wf = (ROOT / ".github" / "workflows" / "weekly.yml").read_text()
    assert "movers.publish" not in wf and "weekly-movers" not in wf
    step = wf[wf.index("- name: Weekly Movers draft"):]
    step = step[:step.index("\n      - name:", 1)]
    assert "continue-on-error: true" in step
    run = (ROOT / "pipeline" / "movers" / "run.py").read_text()
    assert "publish" not in run.replace("published", "")


def test_review_screen_publish_requires_key(server):
    base, app, store, public = server
    assert call(f"{base}/api/report/{RID}/publish", {}, key="wrong")[0] == 403
    assert call(f"{base}/api/report/{RID}/approve", {"acknowledged": True}, key=app.token, origin="https://evil.example")[0] == 403
    status, body = call(f"{base}/api/report/{RID}/approve", {"acknowledged": True}, key=app.token)
    out = json.loads(body)
    assert status == 200 and out["published"] is True and published(public)["report_id"] == RID
