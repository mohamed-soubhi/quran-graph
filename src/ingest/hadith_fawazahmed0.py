"""Downloader and manifest manager for fawazahmed0 hadith collections (T1.3).

Downloads editions.json and the 10 diacritized Arabic editions (ara-<collection>.json)
from pinned fawazahmed0/hadith-api commit df57907be35291c91ad6a6691180e22ca9920784.
Per-file checksums are recorded in data/raw/hadith/fawazahmed0/MANIFEST.txt.
Once all 11 files exist, MANIFEST.txt checksum is recorded in data/raw/CHECKSUMS.txt.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import threading
from typing import Any

import requests
from requests.adapters import HTTPAdapter

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingest.download import (
    append_checksum,
    calculate_sha256,
    fetch,
    read_checksums,
)
from src.log import get_logger

RAW_DIR = ROOT / "data" / "raw"
HADITH_DIR = RAW_DIR / "hadith" / "fawazahmed0"
MANIFEST_FILE = HADITH_DIR / "MANIFEST.txt"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"

PINNED_COMMIT = "df57907be35291c91ad6a6691180e22ca9920784"
REPO_TREE_URL = f"https://github.com/fawazahmed0/hadith-api/tree/{PINNED_COMMIT}"
BASE_RAW_URL = f"https://raw.githubusercontent.com/fawazahmed0/hadith-api/{PINNED_COMMIT}"
EDITIONS_URL = f"{BASE_RAW_URL}/editions.json"
EDITION_URL_TEMPLATE = f"{BASE_RAW_URL}/editions/{{edition_name}}.json"

logger = get_logger("hadith_fawazahmed0")


def extract_arabic_editions(editions_path: Path | str) -> list[str]:
    """Read diacritized Arabic edition names from editions.json.

    Finds all editions where language == 'Arabic' and edition name matches
    ara-<collection> (diacritized, not ending in '1'). Does not hard-code the list.
    """
    path = Path(editions_path)
    if not path.exists():
        raise FileNotFoundError(f"editions.json not found at {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Expected dict in editions.json, got {type(data).__name__}")

    editions: list[str] = []
    for col_key, col_info in data.items():
        if not isinstance(col_info, dict):
            continue
        for ed in col_info.get("collection", []):
            if not isinstance(ed, dict):
                continue
            if ed.get("language") == "Arabic" and ed.get("name") == f"ara-{col_key}":
                editions.append(ed["name"])

    return editions


def create_session(pool_size: int = 4) -> requests.Session:
    """Create a requests session with connection pooling."""
    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
        max_retries=0,  # Retries handled explicitly in fetch() with backoff
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def download_hadith(
    target_dir: Path | str = HADITH_DIR,
    manifest_path: Path | str = MANIFEST_FILE,
    checksums_path: Path | str = CHECKSUMS_FILE,
    timeout: float = 60.0,
    retries: int = 3,
    max_workers: int = 4,
) -> dict[str, Any]:
    """Download editions.json and the 10 Arabic hadith collection files.

    - Resumable: skips files that already exist on disk.
    - Checksums recorded per-file in manifest_path.
    - When all 11 files exist, records manifest_path sha256 in checksums_path.
    - Returns summary dict with file counts, missing files, and failures.
    """
    target = Path(target_dir)
    manifest = Path(manifest_path)
    target.mkdir(parents=True, exist_ok=True)

    session = create_session(pool_size=max_workers)

    # 1. Fetch editions.json
    editions_file = target / "editions.json"
    fetch(
        url=EDITIONS_URL,
        dest_path=editions_file,
        timeout=timeout,
        checksums_path=manifest,
        retries=retries,
        session=session,
    )

    # Existing manifest entries map
    existing_manifest_entries = read_checksums(manifest)
    manifest_map = {e["path"]: e["sha256"] for e in existing_manifest_entries}

    # Reconcile editions.json if it was already on disk before manifest recording
    try:
        rel_editions_path = editions_file.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel_editions_path = editions_file.as_posix()

    if rel_editions_path not in manifest_map:
        editions_sha = calculate_sha256(editions_file)
        append_checksum(
            sha256_hex=editions_sha,
            rel_path=rel_editions_path,
            url=EDITIONS_URL,
            checksums_path=manifest,
        )
        manifest_map[rel_editions_path] = editions_sha

    # 2. Extract Arabic editions dynamically from editions.json
    arabic_editions = extract_arabic_editions(editions_file)
    logger.info("Found %d Arabic editions from editions.json: %s", len(arabic_editions), arabic_editions)

    # Reconcile existing collection files already on disk
    for ed_name in arabic_editions:
        dest_file = target / f"{ed_name}.json"
        try:
            rel_path = dest_file.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            rel_path = dest_file.as_posix()

        if dest_file.exists() and dest_file.stat().st_size > 0 and rel_path not in manifest_map:
            sha256_hex = calculate_sha256(dest_file)
            url = EDITION_URL_TEMPLATE.format(edition_name=ed_name)
            append_checksum(
                sha256_hex=sha256_hex,
                rel_path=rel_path,
                url=url,
                checksums_path=manifest,
            )
            manifest_map[rel_path] = sha256_hex

    # 3. Identify files to download
    to_download: list[str] = []
    for ed_name in arabic_editions:
        dest_file = target / f"{ed_name}.json"
        if not (dest_file.exists() and dest_file.stat().st_size > 0):
            to_download.append(ed_name)

    logger.info(
        "Hadith files status: %d already on disk, %d to download",
        len(arabic_editions) - len(to_download),
        len(to_download),
    )

    failed_downloads: list[tuple[str, str]] = []

    if to_download:
        completed_count = 0
        total_to_download = len(to_download)
        counter_lock = threading.Lock()

        def _worker(ed_name: str) -> tuple[str, bool, str | None]:
            url = EDITION_URL_TEMPLATE.format(edition_name=ed_name)
            dest_file = target / f"{ed_name}.json"
            try:
                fetch(
                    url=url,
                    dest_path=dest_file,
                    timeout=timeout,
                    checksums_path=manifest,
                    retries=retries,
                    session=session,
                )
                with counter_lock:
                    nonlocal completed_count
                    completed_count += 1
                    logger.info("Download progress: %d / %d (%s)", completed_count, total_to_download, ed_name)
                return (ed_name, True, None)
            except Exception as exc:
                logger.error("Failed to fetch %s from %s: %s", ed_name, url, exc)
                return (ed_name, False, str(exc))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {executor.submit(_worker, ed_name): ed_name for ed_name in to_download}
            for future in as_completed(future_to_item):
                ed_name, success, err = future.result()
                if not success:
                    failed_downloads.append((ed_name, err or "unknown error"))

    # Final check of all 11 files (editions.json + 10 editions)
    all_expected_files = [editions_file] + [target / f"{ed}.json" for ed in arabic_editions]
    missing_files: list[str] = []
    for f in all_expected_files:
        if not (f.exists() and f.stat().st_size > 0):
            missing_files.append(f.name)

    missing_count = len(missing_files)
    logger.info("Hadith ingest finished: %d missing files out of %d total", missing_count, len(all_expected_files))

    if missing_count == 0 and len(all_expected_files) == 11:
        # Record manifest sha256 in data/raw/CHECKSUMS.txt if not already recorded
        manifest_sha = calculate_sha256(manifest)
        try:
            rel_manifest_path = manifest.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            rel_manifest_path = manifest.as_posix()

        existing_root_checksums = read_checksums(checksums_path)
        already_in_checksums = any(
            e["path"] == rel_manifest_path and e["sha256"] == manifest_sha
            for e in existing_root_checksums
        )
        if not already_in_checksums:
            append_checksum(
                sha256_hex=manifest_sha,
                rel_path=rel_manifest_path,
                url=REPO_TREE_URL,
                checksums_path=checksums_path,
            )
            logger.info("Recorded MANIFEST.txt checksum (%s) in %s", manifest_sha, checksums_path)
        else:
            logger.info("MANIFEST.txt checksum already present in %s", checksums_path)

    return {
        "total": len(all_expected_files),
        "present": len(all_expected_files) - missing_count,
        "missing": missing_count,
        "missing_files": missing_files,
        "arabic_editions": arabic_editions,
        "failures": failed_downloads,
    }


if __name__ == "__main__":
    result = download_hadith()
    if result["missing"] > 0:
        print(f"FAILED: {result['missing']} files missing: {result['missing_files']}")
        sys.exit(1)
    else:
        print(f"SUCCESS: all {result['total']} files verified and manifest recorded")
        sys.exit(0)
