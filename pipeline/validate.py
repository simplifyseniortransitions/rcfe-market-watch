"""Step 1 validation. A run publishes nothing unless every check here passes."""
import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pipeline import config

DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
OVERFLOW_KEY = "_overflow"


class InputError(Exception):
    """The file could not be read as a CSV at all."""


def parse_date(value):
    """Return a date for 'M/D/YYYY' or 'MM/DD/YYYY', None for blank. Raise ValueError otherwise."""
    value = (value or "").strip()
    if not value:
        return None
    m = DATE_RE.fullmatch(value)
    if not m:
        raise ValueError(f"not M/D/YYYY: {value!r}")
    month, day, year = (int(g) for g in m.groups())
    return date(year, month, day)  # raises ValueError for impossible dates like 2/30


def read_csv(path: Path):
    """Return (header, rows). Rows are dicts; extra trailing fields land under OVERFLOW_KEY."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, restkey=OVERFLOW_KEY)
            header = [h.strip() for h in (reader.fieldnames or [])]
            reader.fieldnames = header
            rows = list(reader)
    except UnicodeDecodeError as e:
        raise InputError(f"file is not UTF-8 text: {e}") from e
    except csv.Error as e:
        raise InputError(f"file is not a readable CSV: {e}") from e
    if not header:
        raise InputError("file is empty")
    return header, rows


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    examples: list = field(default_factory=list)

    def as_dict(self):
        d = {"name": self.name, "passed": self.passed, "detail": self.detail}
        if self.examples:
            d["examples"] = self.examples
        return d


@dataclass
class ValidationResult:
    row_count: int
    checks: list
    warnings: list
    counts: dict

    @property
    def ok(self):
        return all(c.passed for c in self.checks)

    @property
    def errors(self):
        return [f"{c.name}: {c.detail}" for c in self.checks if not c.passed]


def check_columns(header):
    missing = [c for c in config.REQUIRED_COLUMNS if c not in header]
    if missing:
        return Check("required_columns", False, f"missing {len(missing)} required column(s): {', '.join(missing)}")
    return Check("required_columns", True, f"all {len(config.REQUIRED_COLUMNS)} required columns present")


def check_duplicates(rows):
    numbers = Counter((r.get("Facility Number") or "").strip() for r in rows)
    blank = numbers.pop("", 0)
    dupes = {k: v for k, v in numbers.items() if v > 1}
    problems = []
    if dupes:
        problems.append(f"{len(dupes)} Facility Number(s) appear more than once")
    if blank:
        problems.append(f"{blank} row(s) have a blank Facility Number")
    if problems:
        examples = [{"facility_number": k, "rows": v} for k, v in sorted(dupes.items())[: config.EXAMPLE_LIMIT]]
        return Check("unique_facility_number", False, "; ".join(problems), examples)
    return Check("unique_facility_number", True, f"{len(numbers)} unique Facility Numbers, none blank")


def check_dates(rows):
    bad = []
    checked = 0
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        for col in config.DATE_COLUMNS:
            value = r.get(col)
            if not (value or "").strip():
                continue
            checked += 1
            try:
                parse_date(value)
            except ValueError:
                bad.append({"line": i, "facility_number": (r.get("Facility Number") or "").strip(),
                            "column": col, "value": value})
    if bad:
        return Check("date_format", False,
                     f"{len(bad)} value(s) in {', '.join(config.DATE_COLUMNS)} are not a valid M/D/YYYY date",
                     bad[: config.EXAMPLE_LIMIT])
    return Check("date_format", True,
                 f"{checked} non-blank dates in {', '.join(config.DATE_COLUMNS)} are valid M/D/YYYY")


def check_row_count(row_count, prior_row_count, accept_row_drop=False):
    if prior_row_count is None:
        return Check("row_count", True, f"{row_count} rows; no prior snapshot to compare (first run)")
    change = (row_count - prior_row_count) / prior_row_count if prior_row_count else 0.0
    detail = f"{row_count} rows vs {prior_row_count} in prior snapshot ({change:+.2%})"
    if -change > config.MAX_ROW_DROP:
        if accept_row_drop:
            return Check("row_count", True, detail + f"; drop over {config.MAX_ROW_DROP:.0%} accepted by owner override")
        return Check("row_count", False, detail + f"; drop is over the {config.MAX_ROW_DROP:.0%} limit")
    return Check("row_count", True, detail)


def collect_warnings(header, rows):
    warnings = []
    blank_type = sum(1 for r in rows if not (r.get("Facility Type") or "").strip())
    if blank_type:
        warnings.append(f"{blank_type} row(s) have a blank Facility Type (pending applications; counted with regular RCFEs)")
    from pipeline.normalize import KNOWN_TYPES  # local import: normalize imports this module
    new_types = Counter(" ".join((r.get("Facility Type") or "").split()).upper() for r in rows)
    for t in sorted(set(new_types) - KNOWN_TYPES):
        warnings.append(f"{new_types[t]} row(s) have a new Facility Type {t!r}; they are counted as CCRCs "
                        "(the 'CCRCs only' group) until the rules are updated")
    bad_cap = sum(1 for r in rows if not (r.get("Facility Capacity") or "").strip().isdigit())
    if bad_cap:
        warnings.append(f"{bad_cap} row(s) have a blank or non-numeric Facility Capacity (counted as 0 beds)")
    overflow = sum(1 for r in rows if r.get(OVERFLOW_KEY))
    if overflow:
        warnings.append(f"{overflow} row(s) have extra trailing fields beyond the header "
                        "(complaint detail spill-over; not used)")
    for col in config.LIST_DATE_COLUMNS:
        if col not in header:
            continue
        stray = 0
        for r in rows:
            for token in (r.get(col) or "").split(","):
                token = token.strip()
                if not token:
                    continue
                try:
                    parse_date(token)
                except ValueError:
                    stray += 1
        if stray:
            warnings.append(f"{stray} non-date token(s) in the {col} list (ignored)")
    return warnings


def summarize(rows):
    return {
        "by_facility_type": dict(Counter((r.get("Facility Type") or "").strip() or "(blank)" for r in rows)),
        "by_facility_status": dict(Counter((r.get("Facility Status") or "").strip() or "(blank)" for r in rows)),
    }


def validate(header, rows, prior_row_count=None, accept_row_drop=False) -> ValidationResult:
    columns = check_columns(header)
    checks = [columns]
    if columns.passed:
        checks += [check_duplicates(rows), check_dates(rows)]
    checks.append(check_row_count(len(rows), prior_row_count, accept_row_drop))
    warnings = collect_warnings(header, rows) if columns.passed else []
    counts = summarize(rows) if columns.passed else {}
    return ValidationResult(len(rows), checks, warnings, counts)
