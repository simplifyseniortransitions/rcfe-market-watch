import json
from datetime import date
from pathlib import Path

import pytest

from pipeline import config
from pipeline.run import main, process_file, process_inbox
from pipeline.snapshot import detect_as_of, prior_snapshot
from tests.conftest import make_rows, write_csv

REQUIRED_KEYS = {"as_of", "source", "generated_at", "snapshot_id"}


def report(paths):
    return json.loads(paths.qa_report.read_text())


def test_detect_as_of_from_file_names():
    assert detect_as_of(Path("ResidentialElderCareFacility10182026.csv")) == date(2026, 10, 18)
    assert detect_as_of(Path("2026-10-11.csv")) == date(2026, 10, 11)
    assert detect_as_of(Path("rcfe.csv")) is None


def test_pass_writes_snapshot_and_report(paths):
    src = write_csv(paths.inbox / "ResidentialElderCareFacility10112026.csv", make_rows(50))
    run = process_file(src, paths)
    assert run["status"] == "pass"
    snap = paths.snapshots / "2026-10-11.csv"
    assert snap.read_bytes() == src.read_bytes()
    r = report(paths)
    assert REQUIRED_KEYS <= r.keys()
    assert r["snapshot_id"] == "2026-10-11" and r["last_good_snapshot_id"] == "2026-10-11"


def test_failure_writes_no_snapshot_and_keeps_rejected_copy(paths):
    rows = make_rows(50)
    rows[1]["Facility Number"] = rows[0]["Facility Number"]
    src = write_csv(paths.inbox / "ResidentialElderCareFacility10112026.csv", rows)
    run = process_file(src, paths)
    assert run["status"] == "fail"
    assert not (paths.snapshots / "2026-10-11.csv").exists()
    assert list(paths.rejected.glob("2026-10-11_*.csv"))
    r = report(paths)
    assert REQUIRED_KEYS <= r.keys()
    assert r["status"] == "fail" and r["snapshot_id"] is None
    assert any("unique_facility_number" in e for e in r["latest_run"]["errors"])


def test_snapshot_never_overwritten(paths):
    first = write_csv(paths.inbox / "a_10112026.csv", make_rows(50))
    assert process_file(first, paths)["status"] == "pass"
    original = (paths.snapshots / "2026-10-11.csv").read_bytes()

    # Identical re-run is fine and leaves the file alone.
    again = process_file(first, paths)
    assert again["status"] == "pass" and again["snapshot_created"] is False

    # Different contents for the same date fail.
    changed = write_csv(paths.inbox / "b_10112026.csv", make_rows(51))
    run = process_file(changed, paths)
    assert run["status"] == "fail"
    assert "never overwritten" in run["errors"][0]
    assert (paths.snapshots / "2026-10-11.csv").read_bytes() == original


def test_row_drop_compares_against_prior_snapshot(paths):
    write_csv(paths.inbox / "x_10112026.csv", make_rows(100))
    write_csv(paths.inbox / "x_10182026.csv", make_rows(80))
    runs = process_inbox(paths)
    assert [r["status"] for r in runs] == ["pass", "fail"]
    assert runs[1]["prior_snapshot_id"] == "2026-10-11" and runs[1]["prior_row_count"] == 100
    assert not (paths.snapshots / "2026-10-18.csv").exists()
    # The failed file stays in the inbox; the good one moved to processed/.
    assert (paths.inbox / "x_10182026.csv").exists()
    assert (paths.processed / "x_10112026.csv").exists()


def test_failed_snapshot_is_never_a_baseline(paths):
    bad = make_rows(10)
    bad[0]["Closed Date"] = "2026-01-01"
    process_file(write_csv(paths.inbox / "x_10112026.csv", bad), paths)
    assert prior_snapshot(paths.snapshots, date(2026, 10, 18)) is None


def test_inbox_processes_oldest_first(paths):
    write_csv(paths.inbox / "x_10182026.csv", make_rows(50))
    write_csv(paths.inbox / "x_10112026.csv", make_rows(48))
    runs = process_inbox(paths)
    assert [r["as_of"] for r in runs] == ["2026-10-11", "2026-10-18"]
    assert len(report(paths)["runs"]) == 2


def test_missing_as_of_fails(paths):
    run = process_file(write_csv(paths.inbox / "rcfe.csv", make_rows(5)), paths)
    assert run["status"] == "fail" and "--as-of" in run["errors"][0]


def test_cli_exit_codes(paths):
    write_csv(paths.inbox / "x_10112026.csv", make_rows(5))
    assert main([], paths=paths) == 0
    bad = make_rows(5)
    bad[0]["Last Visit Date"] = "13/13/2026"
    write_csv(paths.inbox / "x_10182026.csv", bad)
    assert main([], paths=paths) == 1


def all_json_text(data_dir):
    return {p.name: p.read_text(encoding="utf-8") for p in data_dir.glob("*.json")}


def test_privacy_columns_never_in_json_outputs(paths):
    rows = make_rows(50)
    rows[0]["Facility Number"] = rows[1]["Facility Number"]
    process_file(write_csv(paths.inbox / "x_10042026.csv", rows), paths)  # a failure report
    process_file(write_csv(paths.inbox / "x_10112026.csv", make_rows(50)), paths)  # a pass report
    outputs = all_json_text(paths.data)
    assert outputs
    for name, text in outputs.items():
        for col in config.PRIVATE_COLUMNS:
            assert col not in text, f"{col} found in {name}"
        assert "ADMIN PERSON" not in text and "555-0100" not in text and "TEST ST" not in text, name


def test_privacy_in_published_site_data():
    for name, text in all_json_text(config.DEFAULT_PATHS.data).items():
        for col in config.PRIVATE_COLUMNS:
            assert col not in text, f"{col} found in site/data/{name}"


REAL_OCT_18 = config.DEFAULT_PATHS.snapshots / "2026-10-18.csv"


@pytest.mark.skipif(not REAL_OCT_18.exists(), reason="Oct 18 snapshot not loaded yet")
def test_real_oct_18_snapshot_validates():
    from pipeline.validate import read_csv, validate
    header, rows = read_csv(REAL_OCT_18)
    result = validate(header, rows)
    assert result.ok, result.errors
    assert result.row_count == 13313
