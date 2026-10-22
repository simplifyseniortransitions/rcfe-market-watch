from datetime import date

import pytest

from pipeline import config
from pipeline.validate import parse_date, validate
from tests.conftest import HEADER, make_row, make_rows


def check(result, name):
    return next(c for c in result.checks if c.name == name)


def test_clean_50_rows_pass():
    result = validate(HEADER, make_rows(50))
    assert result.ok, result.errors
    assert result.row_count == 50


@pytest.mark.parametrize("column", config.REQUIRED_COLUMNS)
def test_missing_required_column_fails(column):
    header = [h for h in HEADER if h != column]
    rows = [{k: v for k, v in r.items() if k != column} for r in make_rows(5)]
    result = validate(header, rows)
    assert not result.ok
    assert column in check(result, "required_columns").detail


def test_duplicate_facility_number_fails():
    rows = make_rows(50)
    rows[10]["Facility Number"] = rows[3]["Facility Number"]
    result = validate(HEADER, rows)
    c = check(result, "unique_facility_number")
    assert not c.passed
    assert c.examples == [{"facility_number": rows[3]["Facility Number"], "rows": 2}]


def test_blank_facility_number_fails():
    rows = make_rows(5)
    rows[2]["Facility Number"] = " "
    assert not check(validate(HEADER, rows), "unique_facility_number").passed


@pytest.mark.parametrize("value", ["2026-10-18", "13/01/2026", "2/30/2026", "5/6/26", "Jan 5 2026", "05/06/2026x"])
@pytest.mark.parametrize("column", config.DATE_COLUMNS)
def test_bad_date_fails(column, value):
    rows = make_rows(10)
    rows[4][column] = value
    c = check(validate(HEADER, rows), "date_format")
    assert not c.passed
    assert c.examples[0]["column"] == column
    assert c.examples[0]["value"] == value
    assert c.examples[0]["line"] == 6  # header is line 1


@pytest.mark.parametrize("value", ["5/6/2026", "05/06/2026", "12/31/1999", "", "  "])
def test_good_or_blank_dates_pass(value):
    rows = make_rows(5)
    rows[0]["Closed Date"] = value
    assert check(validate(HEADER, rows), "date_format").passed


def test_parse_date():
    assert parse_date("5/6/2026") == date(2026, 5, 6)
    assert parse_date("05/06/2026") == date(2026, 5, 6)
    assert parse_date("") is None
    with pytest.raises(ValueError):
        parse_date("2/29/2025")


def test_row_drop_over_10_percent_fails():
    result = validate(HEADER, make_rows(89), prior_row_count=100)
    c = check(result, "row_count")
    assert not result.ok and not c.passed
    assert "-11.00%" in c.detail


def test_row_drop_of_exactly_10_percent_passes():
    assert check(validate(HEADER, make_rows(90), prior_row_count=100), "row_count").passed


def test_row_increase_passes():
    assert check(validate(HEADER, make_rows(50), prior_row_count=20), "row_count").passed


def test_row_drop_owner_override_passes_and_is_labelled():
    c = check(validate(HEADER, make_rows(50), prior_row_count=100, accept_row_drop=True), "row_count")
    assert c.passed and "override" in c.detail


def test_list_date_junk_is_a_warning_not_a_failure():
    rows = make_rows(5)
    rows[1]["POC Dates"] = "05/01/87, 87465(c)(3)"
    result = validate(HEADER, rows)
    assert result.ok
    assert any("POC Dates" in w and "2 non-date" in w for w in result.warnings)


def test_blank_type_and_capacity_are_warnings():
    rows = make_rows(5) + [make_row(99, **{"Facility Type": "", "Facility Capacity": ""})]
    result = validate(HEADER, rows)
    assert result.ok
    assert result.counts["by_facility_type"]["(blank)"] == 1
    assert len(result.warnings) == 2


def test_new_facility_type_is_a_warning():
    rows = make_rows(5) + [make_row(98, **{"Facility Type": "RCFE-SOMETHING NEW"})]
    result = validate(HEADER, rows)
    assert result.ok
    assert any("RCFE-SOMETHING NEW" in w for w in result.warnings)
