"""Section 5a reference values from the spec (docs/RCFE_Pulse_Claude_Code_Spec.md), Oct 18, 2026 file, all types."""
import pytest

from pipeline import golden
from tests.test_golden import SNAPSHOT

pytestmark = pytest.mark.skipif(not SNAPSHOT.exists(), reason="Oct 18 snapshot not loaded")

# area: (licensed, new 12m, closures 12m, net, growth %, churn %, pending, probation, probation share %,
#        3+ licensee share %, beds, median beds)
SPEC_5A = {
    "California": (8607, 1054, 468, 586, 12.2, 5.4, 924, 24, 0.28, 9.1, 212076, 6),
    "LOS ANGELES": (1909, 321, 99, 222, 16.8, 5.2, 276, 1, 0.05, 5.0, 45435, 6),
    "ORANGE": (1127, 108, 40, 68, 9.6, 3.5, 77, 0, 0.00, 12.2, 25045, 6),
    "SACRAMENTO": (686, 107, 48, 59, 15.6, 7.0, 74, 10, 1.44, 7.0, 10452, 6),
    "SAN DIEGO": (615, 65, 31, 34, 10.6, 5.0, 42, 1, 0.16, 10.1, 22171, 6),
    "RIVERSIDE": (590, 84, 35, 49, 14.2, 5.9, 75, 1, 0.17, 7.8, 11035, 6),
}


@pytest.fixture(scope="module")
def headline():
    result = golden.golden_metrics()
    return result["scopes"][result["headline_scope"]]


@pytest.mark.parametrize("area,expected", SPEC_5A.items())
def test_spec_reference_values(headline, area, expected):
    t = headline["totals"] if area == "California" else next(c for c in headline["counties"] if c["county"] == area)
    pct = lambda x, places=1: round(100 * x, places)  # noqa: E731
    got = (t["licensed_facilities"], t["new_licenses_12m"], t["closures_12m"], t["net_change_12m"],
           pct(t["growth_rate_12m"]), pct(t["churn_rate_12m"]), t["pending"], t["on_probation"],
           pct(t["probation_share"], 2), pct(t["share_licensed_multi"]), t["licensed_beds"],
           t["median_licensed_capacity"])
    assert got == expected
