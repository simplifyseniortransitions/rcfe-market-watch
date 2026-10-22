import csv

import pytest

from pipeline import config

# Same column layout as the CDSS file, including the private columns, so the
# privacy test proves they are dropped rather than simply absent.
HEADER = [
    "Facility Type", "Facility Number", "Facility Name", "Licensee", "Facility Administrator",
    "Facility Telephone Number", "Facility Address", "Facility City", "Facility State", "Facility Zip",
    "County Name", "Regional Office", "Facility Capacity", "Facility Status", "License First Date",
    "Closed Date", "Last Visit Date", "Inspection Visits", "Complaint Visits", "Other Visits",
    "Total Visits", "Citation Numbers", "POC Dates", "All Visit Dates", "Inspection Visit Dates",
    "Substantiated Allegations",
]


def make_row(i, **overrides):
    row = {h: "" for h in HEADER}
    row.update({
        "Facility Type": "RESIDENTIAL CARE ELDERLY",
        "Facility Number": f"{300000000 + i:09d}",
        "Facility Name": f"TEST HOME {i}",
        "Licensee": f"TEST LICENSEE {i % 7}",
        "Facility Administrator": f"ADMIN PERSON {i}",
        "Facility Telephone Number": "(555) 555-0100",
        "Facility Address": f"{i} TEST ST",
        "Facility City": "SACRAMENTO",
        "Facility State": "CA",
        "County Name": "SACRAMENTO",
        "Facility Capacity": "6",
        "Facility Status": "LICENSED",
        "License First Date": f"{i % 12 + 1}/{i % 28 + 1}/2015",
        "Last Visit Date": "05/06/2026",
        "Total Visits": "3",
        "Complaint Visits": "1",
        "Substantiated Allegations": "0",
        "POC Dates": "04/14/2023, 5/15/2026",
    })
    row.update(overrides)
    return row


def make_rows(n=50):
    return [make_row(i) for i in range(n)]


def write_csv(path, rows, header=HEADER):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, quoting=csv.QUOTE_ALL, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return path


@pytest.fixture
def paths(tmp_path):
    p = config.Paths(tmp_path)
    p.inbox.mkdir(parents=True)
    return p
