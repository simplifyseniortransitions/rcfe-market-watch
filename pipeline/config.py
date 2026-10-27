"""Fixed settings for the weekly pipeline. Every rule the validator applies lives here."""
from dataclasses import dataclass
from pathlib import Path

PRODUCT_NAME = "RCFE Deal Room Market Watch"

SOURCE = (
    "California Department of Social Services, Community Care Licensing Division: "
    "Residential Care Facilities for the Elderly licensing file (CC BY)"
)

REQUIRED_COLUMNS = [
    "Facility Type",
    "Facility Number",
    "Facility Name",
    "Licensee",
    "Facility Capacity",
    "Facility Status",
    "County Name",
    "Facility City",
    "License First Date",
    "Closed Date",
    "Last Visit Date",
    "Total Visits",
    "Complaint Visits",
    "Substantiated Allegations",
    "Citation Numbers",
]

# Single-date columns: every value must be a real M/D/YYYY date or blank, or the run fails.
DATE_COLUMNS = ["License First Date", "Closed Date", "Last Visit Date"]

# Comma-separated date lists. The state file has stray non-date tokens in these
# (2-digit years, regulation codes), so they are reported as warnings, not failures.
LIST_DATE_COLUMNS = ["POC Dates", "All Visit Dates", "Inspection Visit Dates", "Other Visit Dates"]

# A drop larger than this versus the last good snapshot fails the run.
MAX_ROW_DROP = 0.10

# Never written to any output file.
PRIVATE_COLUMNS = ["Facility Administrator", "Facility Telephone Number", "Facility Address"]

# Complaint signal: this many complaints or more dated in the last 12 months (Dale, 2026-10-21).
COMPLAINT_THRESHOLD = 3

# Trend charts appear once this many weekly files exist (spec: after 4 weeks).
HISTORY_MIN_SNAPSHOTS = 4

QA_HISTORY_LIMIT = 52
EXAMPLE_LIMIT = 20


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def inbox(self) -> Path:
        return self.root / "inbox"

    @property
    def processed(self) -> Path:
        return self.inbox / "processed"

    @property
    def snapshots(self) -> Path:
        return self.root / "snapshots"

    @property
    def rejected(self) -> Path:
        return self.snapshots / "rejected"

    @property
    def data(self) -> Path:
        return self.root / "site" / "data"

    @property
    def qa_report(self) -> Path:
        return self.data / "qa-report.json"


DEFAULT_PATHS = Paths(Path(__file__).resolve().parent.parent)
