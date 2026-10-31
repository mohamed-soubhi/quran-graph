"""Unit tests for src.ingest.download framework (T1.1)."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingest.download import (
    append_checksum,
    calculate_sha256,
    fetch,
    read_checksums,
)

ROOT = Path(__file__).resolve().parent.parent
SCRATCH_DIR = ROOT / ".scratch"


@pytest.fixture
def temp_scratch(tmp_path):
    SCRATCH_DIR.mkdir(exist_ok=True)
    test_dir = SCRATCH_DIR / "test_download"
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    # Cleanup files inside test_dir
    for f in test_dir.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        test_dir.rmdir()
    except OSError:
        pass


def test_calculate_sha256(temp_scratch):
    sample_file = temp_scratch / "sample.txt"
    content = "بسم الله الرحمن الرحيم\n".encode("utf-8")
    sample_file.write_bytes(content)

    expected_sha = hashlib.sha256(content).hexdigest()
    assert calculate_sha256(sample_file) == expected_sha


def test_append_and_read_checksums(temp_scratch):
    checksums_file = temp_scratch / "test_checksums.txt"
    sha1 = "a" * 64
    path1 = "data/raw/test1.txt"
    url1 = "https://example.com/test1"
    date1 = "2026-10-31"

    append_checksum(sha1, path1, url1, date1, checksums_path=checksums_file)

    entries = read_checksums(checksums_file)
    assert len(entries) == 1
    assert entries[0]["sha256"] == sha1
    assert entries[0]["path"] == path1
    assert entries[0]["url"] == url1
    assert entries[0]["date"] == date1


def test_fetch_skips_existing_file(temp_scratch):
    dest = temp_scratch / "existing.txt"
    dest.write_text("already downloaded", encoding="utf-8")

    checksums_file = temp_scratch / "chk.txt"

    with patch("requests.get") as mock_get:
        res = fetch("https://example.com/not-called", dest, checksums_path=checksums_file)
        assert res == dest
        mock_get.assert_not_called()

    # CHECKSUMS.txt should not be written to when skipped
    assert not checksums_file.exists()


def test_fetch_downloads_and_records(temp_scratch):
    dest = temp_scratch / "new_download.txt"
    checksums_file = temp_scratch / "chk2.txt"
    content = b"download payload content"
    expected_sha = hashlib.sha256(content).hexdigest()

    mock_resp = MagicMock()
    mock_resp.iter_content.return_value = [content]
    mock_resp.raise_for_status.return_value = None
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("requests.get", return_value=mock_resp) as mock_get:
        res = fetch("https://example.com/file.txt", dest, checksums_path=checksums_file)
        assert res == dest
        mock_get.assert_called_once()

    assert dest.exists()
    assert dest.read_bytes() == content

    entries = read_checksums(checksums_file)
    assert len(entries) == 1
    assert entries[0]["sha256"] == expected_sha
    assert entries[0]["url"] == "https://example.com/file.txt"
