"""A hand-built 50-row snapshot (Oct 18, 2026) and its prior week (Oct 11, 2026).

Every expected value in test_metrics.py can be worked out from the notes here.

Current week, 50 rows:
  n0-n29   core LICENSED. Capacity 6, except n20-n24 = 4 and n25-n29 = 15.
           County LOS ANGELES for n0-n9, ORANGE for n10-n14, SACRAMENTO for the rest.
           License First Date: n0 10/18/2026, n1 10/11/2026, n2 10/10/2026, n3 7/20/2026, n4 7/19/2026.
           Licensees: BIG CHAIN LLC owns n5, n6, n10, n11.
                      BCRG is spelled three ways (n12, n13, n14), which counts as one name.
                      SMALL LLC owns n15 and n16 (plus closed n41).
           n20 has 2 substantiated allegations (prior 0) and 2 complaint visits (prior 0).
           n21 has 3 substantiated allegations (prior 1); n22 has 1 (prior 3).
           POC dates: n25 10/18/2025 + 05/01/2024; n26 10/17/2025; n27 two dates in 2026 + one junk token.
  n30-n34  core PENDING. n30 License First Date 9/1/2026.
  n35-n36  core ON PROBATION.
  n37-n46  core CLOSED. Closed Date: n37 10/16/2026, n38 8/1/2026, n39 7/19/2026, n40 7/20/2026,
           the rest 3/1/2020, except two applications that closed before a license was issued
           (no License First Date, so never counted as closures): n45 10/14/2026, n46 10/17/2026.
  n47-n48  continuing care retirement communities: LICENSED, 100 beds, LOS ANGELES.
  n49      blank facility type (counted with regular RCFEs): LICENSED, blank capacity, SAN DIEGO.

Prior week: the same rows, except:
  n0 was PENDING with no License First Date.  n1 was not listed.  n99 was listed (LICENSED, SACRAMENTO).
  n37 was LICENSED with no Closed Date.        n17 licensee was OLD OWNER LLC (now NEW OWNER LLC).
  n18 licensee was "ACME  care inc" (now "ACME CARE INC": a spacing and case change only).
  n19 capacity was 4.   n20: 0 substantiated, 0 complaint visits.   n21: 1.   n22: 3.
  n45 was PENDING (no Closed Date).
"""
import copy
from datetime import date

from tests.conftest import write_csv

AS_OF = date(2026, 10, 18)
PRIOR_AS_OF = date(2026, 10, 11)


def base(n):
    return {
        "Facility Type": "RESIDENTIAL CARE ELDERLY",
        "Facility Number": f"{400000000 + n:09d}",
        "Facility Name": f"HOME {n}",
        "Licensee": f"SOLO OWNER {n}",
        "Facility Administrator": f"ADMIN PERSON {n}",
        "Facility Telephone Number": "(555) 555-0100",
        "Facility Address": f"{n} TEST ST",
        "Facility City": "SACRAMENTO",
        "Facility State": "CA",
        "County Name": "SACRAMENTO",
        "Facility Capacity": "6",
        "Facility Status": "LICENSED",
        "License First Date": "1/15/2015",
        "Closed Date": "",
        "Last Visit Date": "3/3/2026",
        "Total Visits": "2",
        "Complaint Visits": "0",
        "Substantiated Allegations": "0",
        "Citation Numbers": "",
        "POC Dates": "",
    }


def current_rows():
    rows = {n: base(n) for n in range(50)}
    for n in range(20, 25):
        rows[n]["Facility Capacity"] = "4"
    for n in range(25, 30):
        rows[n]["Facility Capacity"] = "15"
    for n in range(0, 10):
        rows[n]["County Name"] = "LOS ANGELES"
    for n in range(10, 15):
        rows[n]["County Name"] = "ORANGE"
    for n, d in {0: "10/18/2026", 1: "10/11/2026", 2: "10/10/2026", 3: "7/20/2026", 4: "7/19/2026",
                 30: "9/1/2026"}.items():
        rows[n]["License First Date"] = d
    for n in (5, 6, 10, 11):
        rows[n]["Licensee"] = "BIG CHAIN LLC"
    rows[12]["Licensee"] = "BCRG  INC. "
    rows[13]["Licensee"] = "BCRG INC."
    rows[14]["Licensee"] = "bcrg inc."
    for n in (15, 16, 41):
        rows[n]["Licensee"] = "SMALL LLC"
    rows[17]["Licensee"] = "NEW OWNER LLC"
    rows[18]["Licensee"] = "ACME CARE INC"
    rows[20].update({"Substantiated Allegations": "2", "Complaint Visits": "2"})
    rows[21]["Substantiated Allegations"] = "3"
    rows[22]["Substantiated Allegations"] = "1"
    rows[25].update({"Citation Numbers": "87303(a), 87411(a)", "POC Dates": "10/18/2025, 05/01/2024"})
    rows[26].update({"Citation Numbers": "87303(a)", "POC Dates": "10/17/2025"})
    rows[27].update({"Citation Numbers": "87303(a), 87465(c)(3)",
                     "POC Dates": "01/02/2026, 03/04/2026, 87303(a)"})
    for n in range(30, 35):
        rows[n]["Facility Status"] = "PENDING"
    for n in (35, 36):
        rows[n]["Facility Status"] = "ON PROBATION"
    for n in range(37, 47):
        rows[n].update({"Facility Status": "CLOSED", "Closed Date": "3/1/2020"})
    for n, d in {37: "10/16/2026", 38: "8/1/2026", 39: "7/19/2026", 40: "7/20/2026"}.items():
        rows[n]["Closed Date"] = d
    for n, d in {45: "10/14/2026", 46: "10/17/2026"}.items():
        rows[n].update({"Closed Date": d, "License First Date": ""})
    for n in (47, 48):
        rows[n].update({"Facility Type": "RCFE-CONTINUING CARE RETIREMENT COMMUNITY",
                        "Facility Capacity": "100", "County Name": "LOS ANGELES"})
    rows[49].update({"Facility Type": "", "Facility Capacity": "", "County Name": "SAN DIEGO"})
    return [rows[n] for n in range(50)]


def prior_rows():
    rows = {int(r["Facility Number"]) - 400000000: r for r in copy.deepcopy(current_rows())}
    rows[0].update({"Facility Status": "PENDING", "License First Date": ""})
    del rows[1]
    rows[99] = base(99)
    rows[37].update({"Facility Status": "LICENSED", "Closed Date": ""})
    rows[17]["Licensee"] = "OLD OWNER LLC"
    rows[18]["Licensee"] = "ACME  care inc"
    rows[19]["Facility Capacity"] = "4"
    rows[20].update({"Substantiated Allegations": "0", "Complaint Visits": "0"})
    rows[21]["Substantiated Allegations"] = "1"
    rows[22]["Substantiated Allegations"] = "3"
    rows[45].update({"Facility Status": "PENDING", "Closed Date": ""})
    return [rows[n] for n in sorted(rows)]


def write_pair(folder):
    """Write both weeks as CDSS-style file names and return their paths (prior, current)."""
    return (write_csv(folder / "ResidentialElderCareFacility10112026.csv", prior_rows()),
            write_csv(folder / "ResidentialElderCareFacility10182026.csv", current_rows()))
