"""Public Market Map preview (Phase 4): county and city totals only, kept apart from the private map."""
import json
import re
from pathlib import Path

import pytest

from pipeline import cities, preview
from pipeline.counties import CA_COUNTIES

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PAGE = (SITE / "map.html").read_text()
SCRIPT = (SITE / "assets" / "map-preview.js").read_text()
STYLE = (SITE / "assets" / "map-preview.css").read_text()
LA, SAC = "44000", "64000"


@pytest.fixture
def fake_tables(monkeypatch):
    monkeypatch.setattr(cities, "block_places", lambda: {"B-LA": LA, "B-SAC": SAC})
    monkeypatch.setattr(cities, "places", lambda: {LA: ("Los Angeles", "city"), SAC: ("Sacramento", "city")})


def home(i, status="LICENSED", capacity=6, county="SACRAMENTO", block="B-SAC", city="SACRAMENTO"):
    return {"id": f"{i:09d}", "name": f"SAMPLE HOME {i}", "licensee": "SAMPLE LLC", "street": f"{i} SECRET LANE",
            "city": city, "zip": "95814", "county": county, "county_cdss": county, "status": status, "capacity": capacity,
            "size": "small", "type": "RCFE", "lat": 38.5 + i / 1000, "lon": -121.4, "quality": "exact", "block": block}


@pytest.fixture
def data(fake_tables):
    recs = [home(1), home(2, capacity=None), home(3, status="ON PROBATION", capacity=20), home(4, status="PENDING", capacity=60),
            home(5, status="CLOSED"), home(6, county="LOS ANGELES", block="B-LA", city="VAN NUYS", capacity=100)]
    recs += [home(10 + i, county="LOS ANGELES", block="B-LA", city="LOS ANGELES") for i in range(3)]
    recs = cities.assign(recs)
    for r in recs:
        del r["block"]
    return {"as_of": "2026-11-22", "processed_at": "2026-11-24T01:00:00+00:00", "source": "CDSS (CC BY)", "facilities": recs}


# ---- public aggregation ----

def test_county_totals_count_active_licenses_only(data):
    out = preview.build(data)
    by = {c["county"]: c for c in out["counties"]}
    assert len(out["counties"]) == 58 and set(by) == set(CA_COUNTIES.values())
    assert by["SACRAMENTO"] == {"county": "SACRAMENTO", "facilities": 3, "licensed_capacity": 26, "capacity_not_listed": 1}
    assert by["LOS ANGELES"]["facilities"] == 4 and by["NAPA"]["facilities"] == 0


def test_licensed_capacity_totals_add_up(data):
    out = preview.build(data)
    active = [f for f in data["facilities"] if f["status"] in ("LICENSED", "ON PROBATION")]
    assert out["statewide"] == {"facilities": len(active), "licensed_capacity": sum(f["capacity"] or 0 for f in active),
                                "counties_with_facilities": 2}
    assert sum(c["licensed_capacity"] for c in out["counties"]) == out["statewide"]["licensed_capacity"]


def test_top_five_in_both_views(data):
    top = preview.build(data)["top"]
    assert [m["id"] for m in top["metrics"]] == ["facilities", "licensed_capacity"]
    fac, cap = top["lists"]["facilities"], top["lists"]["licensed_capacity"]
    assert [r["city"] for r in fac] == ["Los Angeles", "Sacramento"] and fac[0]["facilities"] == 4
    assert [r["city"] for r in cap] == ["Los Angeles", "Sacramento"] and cap[0]["licensed_capacity"] == 118
    for rows in (fac, cap):
        assert len(rows) <= 5 and set(rows[0]) == {"rank", "tied", "city", "county", "facilities", "licensed_capacity"}
    assert top["explanation"] == cities.EXPLANATION


def test_data_dates_and_currency(data):
    out = preview.build(data)
    assert (out["as_of"], out["processed_at"]) == ("2026-11-22", "2026-11-24T01:00:00+00:00")
    assert "weekly" in out["refresh"].lower() and "California Department of Social Services" in out["verify"]
    for text in ("CDSS source file", "Processed by Market Watch", "data.refresh"):
        assert text in SCRIPT


# ---- nothing private reaches the public page ----

PRIVATE_KEYS = ("street", "lat", "lon", "licensee", "zip", "block", "market_city_id", "quality")


def test_no_addresses_or_locations_in_the_public_file(data):
    text = json.dumps(preview.build(data))
    assert "SECRET LANE" not in text and "SAMPLE HOME" not in text and "SAMPLE LLC" not in text and "000000001" not in text
    for key in PRIVATE_KEYS:
        assert f'"{key}"' not in text


def test_published_files_hold_only_totals():
    for name in ("map-preview.json", "map-cta.json"):
        path = SITE / "data" / name
        if not path.exists():
            continue
        text = path.read_text()
        for key in PRIVATE_KEYS:
            assert f'"{key}"' not in text, (name, key)
        assert "workers.dev" not in text and "r2.cloudflarestorage" not in text


def test_page_never_asks_for_private_data_or_the_test_site():
    for text in (PAGE, SCRIPT):
        assert "map/v/" not in text and "current.json" not in text and "/map/data" not in text
        assert "workers.dev" not in text and "r2." not in text and "MAP_R2_TOKEN" not in text
    assert "data/map-preview.json" in SCRIPT and "facilities.json" not in SCRIPT


def test_member_preview_uses_sample_details_only():
    assert "Sample Care Home" in PAGE and "Example Street" in PAGE and "Sample data shown" in PAGE
    assert "Member Preview" in PAGE
    # The sample ranking rows are bars, not real numbers.
    rows = re.findall(r'class="mp-fake-row">(.*?)</div>', PAGE)
    assert rows and not any(re.search(r"<(u|em)[^>]*>\d", r) for r in rows)


# ---- early-access button ----

@pytest.mark.parametrize("url,ok", [
    ("https://community.rcfedealroom.com/join", True),
    ("https://rcfedealroom.com/early-access", True),
    ("https://mailchi.mp/simplifyseniortransitions/w69iux4ks6", True),
    ("https://simplifyseniortransitions.us1.list-manage.com/subscribe?u=1", True),
    ("https://rcfe-community.dale-35c.workers.dev/join", False),
    ("http://community.rcfedealroom.com/join", False),
    ("javascript:alert(1)", False),
    ("https://evil.example.com/", False),
    ("https://rcfedealroom.com.evil.com/", False),
    ("", False),
    (None, False),
])
def test_cta_destination_is_configurable_but_only_approved(url, ok):
    assert preview.cta_config(url)["url"] == (url if ok else None)


def test_cta_writes_the_setting_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MAP_CTA_URL", "https://community.rcfedealroom.com/join")
    assert preview.main(["cta", str(tmp_path)]) == 0
    assert json.loads((tmp_path / "map-cta.json").read_text()) == {"url": "https://community.rcfedealroom.com/join"}
    monkeypatch.delenv("MAP_CTA_URL")
    preview.main(["cta", str(tmp_path)])
    assert json.loads((tmp_path / "map-cta.json").read_text()) == {"url": None}


def test_cta_copy_and_tracking():
    for text in ("Be notified when the full map opens", "Join the Early-Access List", "No credit card required.",
                 "Free member access will include individual facility locations, searches, filters, local-market totals and the complete Top 20 city rankings."):
        assert text in PAGE
    for action in ("preview_view", "county_select", "county_hover", "ranking_view", "member_preview_view", "member_preview_click",
                   "cta_click", "open_market_tab"):
        assert f'"{action}"' in SCRIPT, action
    # Events go only to RCFE Deal Room's own page, never to any site that frames it.
    assert 'postMessage(' in SCRIPT and ', "*")' not in SCRIPT
    assert "rcfedealroom" in SCRIPT and "gtag(" not in SCRIPT and "googletagmanager" not in SCRIPT


# ---- layout ----

def test_mobile_layout():
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in PAGE
    # Rankings drop below the map on narrow screens; the member demo and stats stack too.
    assert re.search(r"@media \(max-width: 900px\) \{ \.mp-grid \{ grid-template-columns: 1fr; \} \}", STYLE)
    assert re.search(r"@media \(max-width: 760px\) \{ \.mp-demo \{ grid-template-columns: 1fr;", STYLE)
    assert re.search(r"@media \(max-width: 560px\) \{ \.mp-stats \{ grid-template-columns: 1fr;", STYLE)
    assert PAGE.index('class="mp-card mp-mapcard"') < PAGE.index('class="mp-card mp-rankcard"')


# ---- failure isolation ----

def test_preview_cannot_disturb_market_watch_or_the_members_map():
    wf = (ROOT / ".github" / "workflows" / "weekly.yml").read_text()
    step = wf[wf.index("- name: Public map preview"):]
    step = step[:step.index("\n      - name:", 1)]
    assert wf.index("- name: Publish the site") < wf.index("- name: Members' map file") < wf.index("- name: Public map preview")
    assert "continue-on-error: true" in step and "steps.map.outcome == 'success'" in step
    assert "mapbuild/public/map-preview.json" in step and "mapbuild/map/" not in step
    # Its own frame and its own height message, so the host page never resizes the Market Watch frame by mistake.
    assert "common.js" not in PAGE and '"rcfe-map-height"' in SCRIPT and '"rcfe-height"' not in SCRIPT
    assert "assets/guard.js" in PAGE and 'content="noindex, nofollow"' in PAGE
    # A failed load shows a calm note; the member preview and button still appear.
    assert "catch {" in SCRIPT and "being refreshed" in SCRIPT


# ---- wording ----

def test_wording_rules():
    assert cities.EXPLANATION in PAGE
    for text in (PAGE, SCRIPT, (ROOT / "pipeline" / "preview.py").read_text()):
        body = text.replace(cities.EXPLANATION, "")
        assert not re.search(r"\bsaturated\b|undersupplied|oversupplied|\brecommended\b|\bprofitable\b|\b(good|bad) (market|city|county|area)\b", body, re.I)
    assert not re.search(r"\bbeds?\b", PAGE + SCRIPT, re.I)
    assert "Department of Social Services" in PAGE and "Verify a facility's current license directly" in PAGE
