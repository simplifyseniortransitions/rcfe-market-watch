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
