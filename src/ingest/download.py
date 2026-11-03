"""Reusable downloader and checksum recorder for raw data sources (T1.1)."""

import hashlib
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from src.log import get_logger

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "data" / "raw"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"

_checksum_lock = threading.Lock()

TANZIL_URLS = {
    "uthmani": "https://tanzil.net/pub/download/index.php?quranType=uthmani&outType=txt-2&agree=true",
    "simple-clean": "https://tanzil.net/pub/download/index.php?quranType=simple-clean&outType=txt-2&agree=true",
}
TANZIL_METADATA_URL = "https://tanzil.net/res/text/metadata/quran-data.xml"

logger = get_logger("download")


def calculate_sha256(file_path: Path | str, chunk_size: int = 65536) -> str:
    """Calculate the SHA-256 hex digest of a file on disk."""
    path = Path(file_path)
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def append_checksum(
    sha256_hex: str,
    rel_path: str,
    url: str,
    date_str: str | None = None,
    checksums_path: Path | str = CHECKSUMS_FILE,
) -> None:
    """Append a checksum record to CHECKSUMS.txt (or custom manifest)."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    target_path = Path(checksums_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    entry = f"{sha256_hex}  {rel_path}  {url}  {date_str}\n"
    with _checksum_lock:
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(entry)


def read_checksums(checksums_path: Path | str = CHECKSUMS_FILE) -> list[dict[str, str]]:
    """Read entries from CHECKSUMS.txt as a list of dicts."""
    target_path = Path(checksums_path)
    if not target_path.exists():
        return []

    entries: list[dict[str, str]] = []
    with open(target_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 4:
                entries.append(
                    {
                        "sha256": parts[0],
                        "path": parts[1],
                        "url": parts[2],
                        "date": parts[3],
                    }
                )
    return entries


def fetch(
    url: str,
    dest_path: Path | str,
    timeout: float = 60.0,
    chunk_size: int = 65536,
    checksums_path: Path | str = CHECKSUMS_FILE,
    retries: int = 0,
    backoff_factor: float = 0.5,
    session: requests.Session | None = None,
) -> Path:
    """Download a file from url to dest_path if not already present.

    - If dest_path exists, skips download (data/raw is read-only once written).
    - Streams download in binary mode without alteration.
    - Retries up to retries times with exponential backoff on failure.
    - Appends sha256, relative_path, url, and date to CHECKSUMS.txt or manifest.
    """
    dest = Path(dest_path)
    if not dest.is_absolute():
        dest = ROOT / dest

    if dest.exists() and dest.stat().st_size > 0:
        logger.info("File already exists, skipping download: %s", dest)
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_file = dest.with_suffix(dest.suffix + f".tmp.{os.getpid()}.{threading.get_ident()}")
    hasher = hashlib.sha256()

    getter = session.get if session is not None else requests.get

    logger.info("Fetching %s -> %s", url, dest)
    last_exc = None
    for attempt in range(retries + 1):
        try:
            with getter(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                with open(temp_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            hasher.update(chunk)
                            f.write(chunk)
            temp_file.replace(dest)
            break
        except Exception as exc:
            last_exc = exc
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            hasher = hashlib.sha256()
            if attempt < retries:
                sleep_s = backoff_factor * (2 ** attempt)
                logger.warning(
                    "Attempt %d failed for %s (%s). Retrying in %.1fs...",
                    attempt + 1,
                    url,
                    exc,
                    sleep_s,
                )
                time.sleep(sleep_s)
            else:
                logger.error("Download failed from %s after %d retries: %s", url, retries, exc)
                raise last_exc

    sha256_hex = hasher.hexdigest()
    try:
        rel_path = dest.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel_path = dest.as_posix()

    append_checksum(
        sha256_hex=sha256_hex,
        rel_path=rel_path,
        url=url,
        checksums_path=checksums_path,
    )
    logger.info("Saved %s (sha256: %s)", rel_path, sha256_hex)
    return dest


def download_tanzil(
    dest_dir: Path | str | None = None,
    timeout: float = 60.0,
    checksums_path: Path | str = CHECKSUMS_FILE,
) -> dict[str, Path]:
    """Download Tanzil uthmani and simple-clean raw Quran text files."""
    base_dir = Path(dest_dir) if dest_dir else (RAW_DIR / "tanzil")
    results = {}
    for quran_type, url in TANZIL_URLS.items():
        filename = f"quran-{quran_type}.txt"
        dest_path = base_dir / filename
        results[quran_type] = fetch(
            url=url,
            dest_path=dest_path,
            timeout=timeout,
            checksums_path=checksums_path,
        )
    return results


def download_tanzil_metadata(
    dest_path: Path | str | None = None,
    timeout: float = 60.0,
    checksums_path: Path | str = CHECKSUMS_FILE,
) -> Path:
    """Download Tanzil Quran metadata XML (quran-data.xml)."""
    dest = Path(dest_path) if dest_path else (RAW_DIR / "tanzil" / "quran-data.xml")
    return fetch(
        url=TANZIL_METADATA_URL,
        dest_path=dest,
        timeout=timeout,
        checksums_path=checksums_path,
    )


if __name__ == "__main__":
    download_tanzil()
