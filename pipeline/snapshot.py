"""Immutable dated snapshots. A snapshot file is never overwritten."""
import hashlib
import re
import shutil
from datetime import date
from pathlib import Path

SNAPSHOT_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\.csv")
# CDSS download names end in MMDDYYYY, e.g. ResidentialElderCareFacility10182026.csv
CDSS_NAME_RE = re.compile(r"(\d{2})(\d{2})(\d{4})(?!\d)")
ISO_NAME_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


class SnapshotConflict(Exception):
    """A different file already exists for this snapshot date."""


def detect_as_of(path: Path):
    """Read the as-of date from the file name, or return None."""
    name = path.stem
    m = ISO_NAME_RE.search(name)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        return date(y, mo, d)
    m = CDSS_NAME_RE.search(name)
    if m:
        mo, d, y = (int(g) for g in m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_snapshots(snapshot_dir: Path):
    """Return [(date, path)] for every snapshot, oldest first."""
    found = []
    if snapshot_dir.exists():
        for p in snapshot_dir.iterdir():
            m = SNAPSHOT_RE.fullmatch(p.name)
            if m and p.is_file():
                found.append((date(*(int(g) for g in m.groups())), p))
    return sorted(found)


def prior_snapshot(snapshot_dir: Path, as_of: date):
    """The latest snapshot strictly before as_of, or None."""
    earlier = [s for s in list_snapshots(snapshot_dir) if s[0] < as_of]
    return earlier[-1] if earlier else None


def save_snapshot(src: Path, snapshot_dir: Path, as_of: date):
    """Copy src to snapshots/YYYY-MM-DD.csv. Returns (path, created)."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    dest = snapshot_dir / f"{as_of.isoformat()}.csv"
    if dest.exists():
        if sha256(dest) == sha256(src):
            return dest, False
        raise SnapshotConflict(f"{dest.name} already exists with different contents; it is never overwritten")
    shutil.copy2(src, dest)
    return dest, True


def save_rejected(src: Path, rejected_dir: Path, as_of, stamp: str) -> Path:
    """Keep a failed input under snapshots/rejected/ so it never becomes a baseline."""
    rejected_dir.mkdir(parents=True, exist_ok=True)
    label = as_of.isoformat() if as_of else "undated"
    dest = rejected_dir / f"{label}_{stamp}.csv"
    shutil.copy2(src, dest)
    return dest
