"""Address standardizing for the members' map (pipeline/address.py). Addresses here are made up."""
import pytest

from pipeline.address import standardize, standardize_street


@pytest.mark.parametrize("a,b", [
    # The kinds of rewording CDSS makes between weekly files: each pair must give one key.
    ("123 Main Street", "123 MAIN ST"),
    ("123  main   st.", "123 MAIN ST"),
    ("45 North Oak Avenue", "45 N OAK AVE"),
    ("45 Oak Avenue North", "45 OAK AVE N"),
    ("9 Mount Sample Circle", "9 MT SAMPLE CIR"),
    ("9 Saint Example Drive", "9 ST EXAMPLE DR"),
    ("One Sample Way", "1 SAMPLE WAY"),
    ("700 Sample Boulevard, Suite 4", "700 SAMPLE BLVD STE 4"),
    ("12 Example Key", "12 EXAMPLE KY"),
])
def test_rewordings_share_one_key(a, b):
    assert standardize(a, "Sample City", "95000").key == standardize(b, "SAMPLE CITY", "95000-1234").key


def test_unit_is_kept_apart_from_the_street():
    street, unit = standardize_street("700 Sample Boulevard Suite 4")
    assert (street, unit) == ("700 SAMPLE BLVD", "STE 4")
    assert standardize_street("12 Example Ln #B") == ("12 EXAMPLE LN", "#B")
    assert standardize_street("12 Example Ln Apartment 3") == ("12 EXAMPLE LN", "APT 3")


def test_a_street_named_for_a_direction_keeps_its_name():
    assert standardize_street("10 North Street")[0] == "10 NORTH ST"
    assert standardize_street("10 West Way")[0] == "10 WEST WAY"


def test_suffix_words_inside_a_name_are_left_alone():
    assert standardize_street("88 Park Avenue")[0] == "88 PARK AVE"
    assert standardize_street("88 Court Street")[0] == "88 COURT ST"


def test_zip_and_city_are_cleaned():
    a = standardize("1 Sample Rd", "  san   sample ", "95000-1234")
    assert (a.city, a.zip5) == ("SAN SAMPLE", "95000")
    assert a.key == "1 SAMPLE RD|SAN SAMPLE|95000"
    assert a.one_line == "1 SAMPLE RD, SAN SAMPLE, CA 95000"


def test_missing_parts_give_no_key():
    assert standardize("", "Sample City", "95000").key == ""
    assert standardize("1 Sample Rd", "", "").key == ""
    assert standardize("1 Sample Rd", "Sample City", "").key == "1 SAMPLE RD|SAMPLE CITY|"


def test_real_moves_get_a_new_key():
    assert standardize("1 Sample Rd", "Sample City", "95000").key != standardize("2 Sample Rd", "Sample City", "95000").key
