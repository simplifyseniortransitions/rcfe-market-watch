"""Golden test on the real Oct 18, 2026 snapshot, headline (core) scope.

Expected values live in pipeline/golden.py and are Dale's acceptance numbers.
A failure here is reported to Dale; the numbers are never edited to make it pass.
"""
import pytest

from pipeline import config, golden

SNAPSHOT = config.DEFAULT_PATHS.snapshots / f"{golden.GOLDEN_AS_OF.isoformat()}.csv"
pytestmark = pytest.mark.skipif(not SNAPSHOT.exists(), reason="Oct 18 snapshot not loaded")


@pytest.fixture(scope="module")
def headline():
    result = golden.golden_metrics()
    return result["scopes"][result["headline_scope"]]


@pytest.mark.parametrize("key,expected", golden.GOLDEN_TOTALS.items())
def test_golden_total(headline, key, expected):
    assert headline["totals"][key] == expected


@pytest.mark.parametrize("county,expected", golden.GOLDEN_COUNTIES.items())
def test_golden_county(headline, county, expected):
    assert golden.county_value(headline, county) == expected
