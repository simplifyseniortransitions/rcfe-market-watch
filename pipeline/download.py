"""Download this week's CDSS RCFE file into inbox/.

Source (confirmed by Dale, 2026-10-22): the "Residential Care Facilities for the Elderly" link on
https://www.ccld.dss.ca.gov/carefacilitysearch/DownloadData, which calls the address below. The GUID is a
random ID the page makes up on every visit. CDSS names the file with its data date, for example
ResidentialElderCareFacility10182026.csv.

    python -m pipeline.download        prints "new" or "unchanged" and, in GitHub Actions, sets the step output
"""
import os
import re
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from pipeline import config
from pipeline.snapshot import list_snapshots, sha256

URL = ("https://www.ccld.dss.ca.gov/transparencyapi/api/DownloadStateData"
       "?id=ResidentialElderCareFacility&GUID={guid}")
USER_AGENT = ("RCFE-Market-Watch/1.0 (weekly public-data update; "
              "github.com/simplifyseniortransitions/rcfe-market-watch)")
FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)
EXPECTED_NAME = re.compile(r"ResidentialElderCareFacility\d{8}\.csv")
MIN_BYTES = 1_000_000  # the real file is about 8.6 MB; anything tiny is an error page
ATTEMPTS = 3
RETRY_SECONDS = 60


class DownloadError(Exception):
    pass


def filename_from(content_disposition):
    """The CDSS file name, checked so a strange header can never write outside inbox/."""
    m = FILENAME_RE.search(content_disposition or "")
    if not m:
        raise DownloadError(f"no file name in the download response ({content_disposition!r})")
    name = m.group(1).strip()
    if not EXPECTED_NAME.fullmatch(name):
        raise DownloadError(f"unexpected file name from CDSS: {name!r}")
    return name


def fetch(dest_dir: Path) -> Path:
    """One download attempt. Returns the saved file."""
    request = urllib.request.Request(URL.format(guid=uuid.uuid4()), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:
        if response.status != 200:
            raise DownloadError(f"CDSS answered HTTP {response.status}")
        name = filename_from(response.headers.get("Content-Disposition"))
        dest_dir.mkdir(parents=True, exist_ok=True)
        partial = dest_dir / (name + ".partial")
        with open(partial, "wb") as f:
            while chunk := response.read(1 << 20):
                f.write(chunk)
    if partial.stat().st_size < MIN_BYTES:
        size = partial.stat().st_size
        partial.unlink()
        raise DownloadError(f"download was only {size} bytes; expected the full file")
    dest = dest_dir / name
    partial.replace(dest)
    return dest


def download(dest_dir: Path, attempts=ATTEMPTS, wait=None) -> Path:
    wait = RETRY_SECONDS if wait is None else wait
    last = None
    for attempt in range(1, attempts + 1):
        try:
            return fetch(dest_dir)
        except (OSError, DownloadError) as e:  # URLError and timeouts are OSErrors
            last = e
            print(f"download attempt {attempt} of {attempts} failed: {e}", file=sys.stderr)
            if attempt < attempts:
                time.sleep(wait)
    raise DownloadError(f"could not download the CDSS file after {attempts} attempts: {last}")


def is_unchanged(path: Path, snapshot_dir: Path):
    """True when the download is byte-for-byte the newest saved snapshot (CDSS has not posted a new file)."""
    snapshots = list_snapshots(snapshot_dir)
    return bool(snapshots) and sha256(path) == sha256(snapshots[-1][1])


def set_output(**values):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")


def main(paths=config.DEFAULT_PATHS):
    try:
        path = download(paths.inbox)
    except DownloadError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        set_output(status="failed", error=str(e).replace("\n", " "))
        return 1
    if is_unchanged(path, paths.snapshots):
        path.unlink()
        print(f"unchanged: {path.name} is the same as the newest saved week; nothing to publish")
        set_output(status="unchanged", file=path.name)
        return 0
    print(f"new: {path}")
    set_output(status="new", file=path.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
