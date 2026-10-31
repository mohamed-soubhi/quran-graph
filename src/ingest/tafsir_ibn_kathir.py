"""Downloader and manifest manager for Ibn Kathir Arabic tafsir (T1.2).

Downloads all 6236 per-ayah JSON files from pinned spa5k/tafsir_api commit
eb82bb6294efe30ad5c135c03b1864afaa70e855.
Per-file checksums are saved in data/raw/tafsir/ibn-kathir/MANIFEST.txt.
Once all 6236 files exist, MANIFEST.txt checksum is recorded in data/raw/CHECKSUMS.txt.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.ingest.download import (
    append_checksum,
    calculate_sha256,
    fetch,
    read_checksums,
)
from src.log import get_logger

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = ROOT / "data" / "raw"
TANZIL_SIMPLE_CLEAN = RAW_DIR / "tanzil" / "quran-simple-clean.txt"
TAFSIR_DIR = RAW_DIR / "tafsir" / "ibn-kathir"
MANIFEST_FILE = TAFSIR_DIR / "MANIFEST.txt"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"

PINNED_COMMIT = "eb82bb6294efe30ad5c135c03b1864afaa70e855"
REPO_TREE_URL = f"https://github.com/spa5k/tafsir_api/tree/{PINNED_COMMIT}"
URL_TEMPLATE = (
    f"https://raw.githubusercontent.com/spa5k/tafsir_api/{PINNED_COMMIT}/"
    "tafsir/ar-tafsir-ibn-kathir/{surah}/{ayah}.json"
)

logger = get_logger("tafsir_ibn_kathir")


def load_surah_ayah_pairs(simple_clean_path: Path | str = TANZIL_SIMPLE_CLEAN) -> list[tuple[int, int]]:
    """Read all (surah, ayah) pairs from Tanzil simple-clean text.

    Returns a list of 6236 (surah, ayah) tuples.
    Raises ValueError or FileNotFoundError if file is missing or invalid.
    """
    path = Path(simple_clean_path)
    if not path.exists():
        raise FileNotFoundError(f"Tanzil simple-clean text not found at {path}")

    pairs: list[tuple[int, int]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split("|", 2)
            if len(parts) >= 2:
                pairs.append((int(parts[0]), int(parts[1])))

    if len(pairs) != 6236:
        raise ValueError(f"Expected 6236 ayat in Tanzil text, found {len(pairs)}")

    # Verify 114 surahs
    surahs = {s for s, _ in pairs}
    if len(surahs) != 114 or surahs != set(range(1, 115)):
        raise ValueError(f"Expected 114 continuous surahs (1..114), got {len(surahs)}")

    return pairs


def create_session(pool_size: int = 4) -> requests.Session:
    """Create a requests session with connection pooling and socket keep-alive."""
    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
        max_retries=0,  # Retries handled explicitly in fetch() with backoff
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def download_ibn_kathir(
    target_dir: Path | str = TAFSIR_DIR,
    manifest_path: Path | str = MANIFEST_FILE,
    tanzil_path: Path | str = TANZIL_SIMPLE_CLEAN,
    checksums_path: Path | str = CHECKSUMS_FILE,
    max_workers: int = 4,
    timeout: float = 30.0,
    retries: int = 3,
) -> dict[str, Any]:
    """Download all 6236 per-ayah JSON files for Ibn Kathir Arabic tafsir.

    - Resumable: skips files that already exist.
    - Checksums recorded per-file in manifest_path.
    - When all 6236 files exist, records manifest_path sha256 in checksums_path.
    - Returns summary dict with total, downloaded, missing, and missing_ayat.
    """
    target = Path(target_dir)
    manifest = Path(manifest_path)
    target.mkdir(parents=True, exist_ok=True)

    ayat = load_surah_ayah_pairs(tanzil_path)
    logger.info("Loaded %d ayah references from Tanzil source", len(ayat))

    # Read existing manifest entries
    existing_manifest_entries = read_checksums(manifest)
    manifest_map = {e["path"]: e["sha256"] for e in existing_manifest_entries}

    # Reconcile files already on disk that may not have been logged to manifest
    for surah, ayah in ayat:
        dest_file = target / str(surah) / f"{ayah}.json"
        try:
            rel_path = dest_file.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            rel_path = dest_file.as_posix()

        if dest_file.exists() and dest_file.stat().st_size > 0 and rel_path not in manifest_map:
            sha256_hex = calculate_sha256(dest_file)
            url = URL_TEMPLATE.format(surah=surah, ayah=ayah)
            append_checksum(
                sha256_hex=sha256_hex,
                rel_path=rel_path,
                url=url,
                checksums_path=manifest,
            )
            manifest_map[rel_path] = sha256_hex

    # Identify files that still need downloading
    to_download: list[tuple[int, int]] = []
    for surah, ayah in ayat:
        dest_file = target / str(surah) / f"{ayah}.json"
        if not (dest_file.exists() and dest_file.stat().st_size > 0):
            to_download.append((surah, ayah))

    logger.info(
        "Tafsir files status: %d already on disk, %d to download",
        len(ayat) - len(to_download),
        len(to_download),
    )

    failed_downloads: list[tuple[int, int, str]] = []
    session = create_session(pool_size=max_workers)

    if to_download:
        completed_count = 0
        total_to_download = len(to_download)
        counter_lock = threading.Lock()

        def _worker(item: tuple[int, int]) -> tuple[int, int, bool, str | None]:
            surah_num, ayah_num = item
            url = URL_TEMPLATE.format(surah=surah_num, ayah=ayah_num)
            dest_file = target / str(surah_num) / f"{ayah_num}.json"
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
                    if completed_count % 500 == 0 or completed_count == total_to_download:
                        logger.info("Download progress: %d / %d", completed_count, total_to_download)
                return (surah_num, ayah_num, True, None)
            except Exception as exc:
                logger.error("Failed to fetch %d:%d from %s: %s", surah_num, ayah_num, url, exc)
                return (surah_num, ayah_num, False, str(exc))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {executor.submit(_worker, item): item for item in to_download}
            for future in as_completed(future_to_item):
                surah_num, ayah_num, success, err = future.result()
                if not success:
                    failed_downloads.append((surah_num, ayah_num, err or "unknown error"))

    # Final tally
    missing_ayat: list[tuple[int, int]] = []
    for surah, ayah in ayat:
        dest_file = target / str(surah) / f"{ayah}.json"
        if not (dest_file.exists() and dest_file.stat().st_size > 0):
            missing_ayat.append((surah, ayah))

    missing_count = len(missing_ayat)
    logger.info("Run finished: %d missing files out of %d total", missing_count, len(ayat))

    if missing_count == 0:
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
        "total": len(ayat),
        "present": len(ayat) - missing_count,
        "missing": missing_count,
        "missing_ayat": missing_ayat,
        "failures": failed_downloads,
    }


if __name__ == "__main__":
    result = download_ibn_kathir()
    if result["missing"] > 0:
        print(f"FAILED: {result['missing']} files missing")
        sys.exit(1)
    else:
        print(f"SUCCESS: all {result['total']} files verified and manifest recorded")
        sys.exit(0)
