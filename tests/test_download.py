import io

import pytest

from pipeline import download
from tests.conftest import make_rows, write_csv

NAME = "ResidentialElderCareFacility10252026.csv"


class FakeResponse(io.BytesIO):
    def __init__(self, body, disposition=f"attachment; filename={NAME}", status=200):
        super().__init__(body)
        self.status = status
        self.headers = {"Content-Disposition": disposition}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(body, **kw):
    seen = []

    def opener(request, timeout):
        seen.append(request)
        return FakeResponse(body, **kw)
    opener.seen = seen
    return opener


BIG = b'"Facility Type"\n' + b"x" * download.MIN_BYTES


@pytest.mark.parametrize("header,name", [
    (f"attachment; filename={NAME}", NAME),
    (f'attachment; filename="{NAME}"', NAME),
])
def test_filename_from_header(header, name):
    assert download.filename_from(header) == name


@pytest.mark.parametrize("header", [None, "attachment", "attachment; filename=../../etc/passwd",
                                    "attachment; filename=report.csv", "attachment; filename=Residential.csv"])
def test_unexpected_names_are_refused(header):
    with pytest.raises(download.DownloadError):
        download.filename_from(header)


def test_download_saves_cdss_name_and_uses_random_guid(paths, monkeypatch):
    opener = fake_urlopen(BIG)
    monkeypatch.setattr(download.urllib.request, "urlopen", opener)
    path = download.download(paths.inbox, attempts=1)
    assert path.name == NAME and path.read_bytes() == BIG
    assert not list(paths.inbox.glob("*.partial"))
    url = opener.seen[0].full_url
    assert url.startswith("https://www.ccld.dss.ca.gov/transparencyapi/api/DownloadStateData?id=ResidentialElderCareFacility&GUID=")
    assert len(url.split("GUID=")[1]) == 36


def test_tiny_response_is_an_error(paths, monkeypatch):
    monkeypatch.setattr(download.urllib.request, "urlopen", fake_urlopen(b"<html>maintenance</html>"))
    with pytest.raises(download.DownloadError, match="only"):
        download.download(paths.inbox, attempts=2, wait=0)
    assert not list(paths.inbox.iterdir())


def test_unchanged_file_is_reported_and_removed(paths, monkeypatch, tmp_path):
    rows = make_rows(5)
    paths.snapshots.mkdir(parents=True)
    write_csv(paths.snapshots / "2026-10-18.csv", rows)
    body = (paths.snapshots / "2026-10-18.csv").read_bytes()
    monkeypatch.setattr(download, "MIN_BYTES", 1)
    monkeypatch.setattr(download.urllib.request, "urlopen", fake_urlopen(body))
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert download.main(paths) == 0
    assert "status=unchanged" in out.read_text()
    assert not list(paths.inbox.glob("*.csv"))


def test_new_file_is_kept(paths, monkeypatch, tmp_path):
    monkeypatch.setattr(download.urllib.request, "urlopen", fake_urlopen(BIG))
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert download.main(paths) == 0
    assert f"status=new\nfile={NAME}" in out.read_text()
    assert (paths.inbox / NAME).exists()


def test_failed_download_sets_failed_status(paths, monkeypatch, tmp_path):
    def broken(request, timeout):
        raise OSError("connection reset")
    monkeypatch.setattr(download.urllib.request, "urlopen", broken)
    monkeypatch.setattr(download, "RETRY_SECONDS", 0)
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert download.main(paths) == 1
    assert "status=failed" in out.read_text()
