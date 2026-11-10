from pipeline import config, notify
from pipeline.run import process_file
from tests.conftest import make_rows, write_csv
from tests.test_publish import load


def test_failure_body_lists_failed_checks_without_private_data(paths):
    rows = make_rows(20)
    rows[3]["Facility Number"] = rows[2]["Facility Number"]
    process_file(write_csv(paths.inbox / "ResidentialElderCareFacility10252026.csv", rows), paths)
    body = notify.failure_body(notify.load_latest(paths), run_url="https://example.invalid/run/1")
    assert "still shows the last good week" in body
    assert "unique_facility_number" in body and "snapshots/rejected/" in body
    assert "https://example.invalid/run/1" in body
    for col in config.PRIVATE_COLUMNS:
        assert col not in body
    assert "ADMIN PERSON" not in body and "555-0100" not in body


def test_failure_body_for_download_error():
    body = notify.failure_body({}, download_error="CDSS answered HTTP 503")
    assert "could not be downloaded" in body and "HTTP 503" in body


def test_summary_of_a_published_run(paths):
    process_file(write_csv(paths.inbox / "ResidentialElderCareFacility10252026.csv", make_rows(20)), paths)
    assert load(paths, "qa-report.json")["status"] == "pass"
    text = notify.summary(notify.load_latest(paths))
    assert text.startswith("**published**") and "PASS required_columns" in text


def pulse_data(prior="2026-11-01"):
    seg = {"totals": {"licensed_facilities": 8610, "licensed_beds": 211943, "pending": 924, "on_probation": 25},
           "week_over_week": {"licensed_facilities": 12, "licensed_beds": -166, "pending": 0, "on_probation": None},
           "activity": {"new_facility_numbers": 20, "closures_status_changed": 13, "ownership_changes": 8,
                        "new_substantiated_allegations": 142}}
    return {"as_of": "2026-11-08", "prior_snapshot_id": prior, "headline_scope": "all",
            "segments": {"all": {"all_sizes": seg}}}


def test_published_notice_has_the_week_and_numbers():
    text = notify.weekly_notice("new", True, "main", pulse_data())
    assert text.startswith("@simplifyseniortransitions **Market Watch updated: week of Nov 8, 2026.**")
    assert "Compared with Nov 1, 2026." in text
    assert "Licensed facilities: 8,610 (+12)" in text and "Licensed beds: 211,943 (−166)" in text
    assert "Pending: 924 (no change)" in text and "On probation: 25 (no earlier week)" in text
    assert "New substantiated allegations: 142" in text and notify.SITE_URL in text


def test_a_retry_that_publishes_still_sends_a_notice():
    assert "Market Watch updated" in notify.weekly_notice("new", True, "evening", pulse_data())


def test_no_new_file_and_failure_notices_say_what_happens_next():
    none = notify.weekly_notice("unchanged", False, "main", pulse_data())
    assert "No new CDSS file yet" in none and "week of Nov 8, 2026" in none and "6 PM today" in none
    failed = notify.weekly_notice("failed", False, "final", pulse_data(), "HTTP Error 503", "https://example.invalid/r")
    assert "did not publish" in failed and "HTTP Error 503" in failed
    assert "last automatic try" in failed and "https://example.invalid/r" in failed


def test_the_evening_retry_stays_silent_unless_it_publishes():
    assert notify.weekly_notice("unchanged", False, "evening", pulse_data()) == ""
    assert notify.weekly_notice("failed", False, "evening", pulse_data(), "HTTP Error 503") == ""
