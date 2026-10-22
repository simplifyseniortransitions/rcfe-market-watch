"""Static checks on the phase-1 pages in site/."""
import re
from html.parser import HTMLParser

import pytest

from pipeline import config

SITE = config.DEFAULT_PATHS.root / "site"
PAGES = ["index.html", "market.html", "facilities.html", "facility.html", "methodology.html"]
NAV = [("index.html", "Pulse"), ("market.html", "Market"), ("facilities.html", "Facilities"),
       ("methodology.html", "Methodology")]
DISCLAIMER = "General educational information only. Not legal, tax, licensing, valuation, or financial advice."
# Code-level markers of common trackers and ad tags (plain words like "analytics" may appear in page prose).
TRACKERS = ["gtag(", "googletagmanager", "google-analytics", "fbq(", "connect.facebook", "hotjar", "segment.io",
            "plausible.io", "doubleclick", "adsbygoogle", "navigator.sendbeacon", "document.cookie"]


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts, self.styles, self.nav, self.text = [], [], [], []
        self._in_nav = self._in_link = False
        self._link = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script":
            self.scripts.append(a.get("src"))
        if tag == "link" and a.get("rel") == "stylesheet":
            self.styles.append(a.get("href"))
        if tag == "nav":
            self._in_nav = True
        if tag == "a" and self._in_nav:
            self._link = [a.get("href"), "", "aria-current" in a]

    def handle_endtag(self, tag):
        if tag == "nav":
            self._in_nav = False
        if tag == "a" and self._link:
            self.nav.append(tuple(self._link))
            self._link = None

    def handle_data(self, data):
        self.text.append(data)
        if self._link:
            self._link[1] += data.strip()


def parse(name):
    page = Page()
    page.feed((SITE / name).read_text(encoding="utf-8"))
    return page


@pytest.mark.parametrize("name", PAGES)
def test_footer_disclaimer_on_every_page(name):
    assert DISCLAIMER in " ".join(" ".join(parse(name).text).split())


@pytest.mark.parametrize("name", PAGES)
def test_navigation_is_phase_1_only(name):
    nav = parse(name).nav
    assert [(href, label) for href, label, _ in nav] == NAV
    assert sum(current for *_, current in nav) == 1


EMBED_SNIPPET = ('<script>if (window.self !== window.top || /[?&]embed=1\\b/.test(location.search)) '
                 'document.documentElement.classList.add("embedded");</script>')


@pytest.mark.parametrize("name", PAGES)
def test_only_local_scripts_and_styles(name):
    page = parse(name)
    assert page.scripts and page.styles
    files = [ref for ref in page.scripts if ref is not None] + page.styles
    for ref in files:
        assert "//" not in ref and (SITE / ref).exists(), ref
    # The only inline script is the one-line embed check.
    html = (SITE / name).read_text()
    assert page.scripts.count(None) == 1 and html.count(EMBED_SNIPPET) == 1


@pytest.mark.parametrize("name", PAGES)
def test_light_only_with_title_band(name):
    html = (SITE / name).read_text()
    assert '<meta name="color-scheme" content="light">' in html
    assert '<section class="hero">' in html and '<p class="eyebrow">' in html


def test_stylesheet_is_light_only_and_uses_system_fonts():
    css = (SITE / "assets" / "style.css").read_text()
    assert "prefers-color-scheme" not in css
    assert "@import" not in css and "@font-face" not in css and "url(" not in css
    assert "Georgia" in css and "Arial" in css


def test_embed_mode_hides_only_the_brand():
    css = (SITE / "assets" / "style.css").read_text()
    assert "html.embedded .brand { display: none; }" in css
    assert "html.embedded .site-nav" in css and "html.embedded .site-footer" not in css  # disclaimer stays
    js = (SITE / "assets" / "common.js").read_text()
    assert '{ type: "rcfe-height", height }' in js


def all_source():
    files = [SITE / n for n in PAGES] + sorted((SITE / "assets").glob("*"))
    return {f.name: f.read_text(encoding="utf-8") for f in files}


def test_no_tracking_ads_or_third_party_code():
    for name, text in all_source().items():
        low = text.lower()
        for word in TRACKERS:
            assert word not in low, f"{word} in {name}"
        assert not re.search(r"""(src|href)=["']https?://""", text), name
        assert "import(" not in text and "http://" not in low and "https://" not in low, name


def test_scripts_never_insert_raw_html():
    for name, text in all_source().items():
        if name.endswith(".js"):
            assert not re.search(r"\.(innerHTML|outerHTML)\s*=|insertAdjacentHTML\(|document\.write\(", text), name


def test_scripts_do_not_reference_private_columns():
    for name, text in all_source().items():
        for col in config.PRIVATE_COLUMNS:
            assert col not in text, f"{col} in {name}"


def test_email_signup_is_a_disabled_stub():
    html = (SITE / "index.html").read_text()
    form = html[html.index("<form"):html.index("</form>")]
    assert "action=" not in form
    assert form.count("disabled") >= 3


def test_page_scripts_import_existing_modules():
    for name, text in all_source().items():
        for mod in re.findall(r'from "\./([^"]+)"', text):
            assert (SITE / "assets" / mod).exists(), f"{name} imports missing {mod}"



def test_no_corrections_page_or_links():
    # Dale, 2026-10-22: no Corrections tab; record errors go to CDSS.
    assert not (SITE / "corrections.html").exists()
    for name, text in all_source().items():
        assert "corrections.html" not in text, name


def test_market_page_has_no_opportunity_wording():
    for name in ("market.html", "assets/market.js"):
        assert "opportunit" not in (SITE / name).read_text().lower(), name


def test_deal_room_box_uses_interim_wording_and_disclaimer():
    html = (SITE / "market.html").read_text()
    box = " ".join(html[html.index('aria-labelledby="angle-h"'):html.index("</aside>")].split())
    assert "Deal Room angle" in box and DISCLAIMER in box
    assert "a new owner generally applies for their own RCFE license" in box  # until counsel confirms
    assert "does not move to a new owner" not in box
    assert "$" not in box and "price range" not in box.lower()


def test_market_table_groups_activity_and_supply():
    js = (SITE / "assets" / "market.js").read_text()
    assert "Activity, " in js and "Available supply, " in js
    for key in ("new_licenses_12m", "closures_12m", "net_change_12m", "growth_rate_12m", "churn_rate_12m",
                "pending", "on_probation", "probation_share", "share_licensed_multi", "licensed_beds",
                "median_licensed_capacity"):
        assert f'key: "{key}"' in js, key
