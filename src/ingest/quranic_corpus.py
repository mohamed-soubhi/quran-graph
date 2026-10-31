"""Downloader verification and morphology reader for Quranic Arabic Corpus (T1.4).

The Quranic Arabic Corpus morphology v0.4 file is distributed as a zip archive
containing `quranic-corpus-morphology-0.4.txt`. In accordance with Hard Rule 5
and project data management rules:
- The zip file in data/raw/ is read-only and is not unzipped on disk.
- Data is parsed directly from the zip archive using Python's `zipfile`.
- SHA-256 is recorded in data/raw/CHECKSUMS.txt.
"""

from pathlib import Path
import re
import sys
import zipfile
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingest.download import (
    append_checksum,
    calculate_sha256,
    read_checksums,
)
from src.log import get_logger

RAW_DIR = ROOT / "data" / "raw"
CORPUS_DIR = RAW_DIR / "quranic-corpus"
CORPUS_ZIP_PATH = CORPUS_DIR / "quranic-corpus-morphology-0.4.zip"
CORPUS_TXT_NAME = "quranic-corpus-morphology-0.4.txt"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"

CORPUS_URL = "https://corpus.quran.com/download/"
CORPUS_SHA256 = "fda26f87cc58b42fc992a3ad666a562805b636f34bcecb46326d048337ca7999"

# Verified exact baseline counts for morphology v0.4
EXPECTED_MORPHEMES = 128219
EXPECTED_WORDS = 77429
EXPECTED_AYAT = 6236
EXPECTED_ROOTS = 1642

logger = get_logger("quranic_corpus")

LOCATION_PATTERN = re.compile(r"^\((\d+):(\d+):(\d+):(\d+)\)$")
ROOT_PATTERN = re.compile(r"ROOT:([^|\s\r\n]+)")


def verify_and_record_checksum(
    zip_path: Path | str = CORPUS_ZIP_PATH,
    checksums_path: Path | str = CHECKSUMS_FILE,
    date_str: str = "2026-10-31",
) -> str:
    """Verify SHA-256 of the morphology zip and record it in CHECKSUMS.txt if not present."""
    path = Path(zip_path)
    if not path.exists():
        raise FileNotFoundError(f"Corpus zip not found at {path}")

    actual_sha256 = calculate_sha256(path)
    if actual_sha256 != CORPUS_SHA256:
        raise ValueError(
            f"Checksum mismatch for {path}: expected {CORPUS_SHA256}, got {actual_sha256}"
        )

    try:
        rel_path = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel_path = path.as_posix()

    target_checksums = Path(checksums_path)
    existing_entries = read_checksums(target_checksums)
    already_recorded = any(entry.get("path") == rel_path for entry in existing_entries)

    if not already_recorded:
        append_checksum(
            sha256_hex=actual_sha256,
            rel_path=rel_path,
            url=CORPUS_URL,
            date_str=date_str,
            checksums_path=target_checksums,
        )
        logger.info("Recorded checksum for %s in %s", rel_path, target_checksums)
    else:
        logger.info("Checksum for %s already recorded in %s", rel_path, target_checksums)

    return actual_sha256


def parse_morphology_stream(
    zip_path: Path | str = CORPUS_ZIP_PATH,
) -> Iterator[dict[str, Any]]:
    """Stream parsed morphology records directly from the zip archive without extracting to disk.

    Yields dicts with:
      - surah (int)
      - ayah (int)
      - word (int)
      - segment (int)
      - location (str)
      - form (str)
      - tag (str)
      - features (str)
      - root (str | None)
    """
    path = Path(zip_path)
    if not path.exists():
        raise FileNotFoundError(f"Corpus zip not found at {path}")

    with zipfile.ZipFile(path, "r") as zf:
        namelist = zf.namelist()
        if CORPUS_TXT_NAME not in namelist:
            raise ValueError(
                f"Zip file {path} does not contain expected file {CORPUS_TXT_NAME}. Members: {namelist}"
            )

        with zf.open(CORPUS_TXT_NAME, "r") as member_file:
            header_seen = False
            for raw_line in member_file:
                line = raw_line.decode("utf-8")
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue

                if not header_seen and stripped.startswith("LOCATION"):
                    header_seen = True
                    continue

                parts = stripped.split("\t")
                if len(parts) < 4:
                    continue

                loc_str, form, tag, features = parts[0], parts[1], parts[2], parts[3]
                loc_match = LOCATION_PATTERN.match(loc_str)
                if not loc_match:
                    continue

                s, a, w, seg = map(int, loc_match.groups())
                root_match = ROOT_PATTERN.search(features)
                root = root_match.group(1) if root_match else None

                yield {
                    "surah": s,
                    "ayah": a,
                    "word": w,
                    "segment": seg,
                    "location": loc_str,
                    "form": form,
                    "tag": tag,
                    "features": features,
                    "root": root,
                }


def compute_corpus_stats(
    zip_path: Path | str = CORPUS_ZIP_PATH,
) -> dict[str, Any]:
    """Compute exact verification statistics across the morphology corpus."""
    morpheme_count = 0
    words: set[tuple[int, int, int]] = set()
    ayat: set[tuple[int, int]] = set()
    roots: set[str] = set()

    for row in parse_morphology_stream(zip_path):
        morpheme_count += 1
        words.add((row["surah"], row["ayah"], row["word"]))
        ayat.add((row["surah"], row["ayah"]))
        if row["root"]:
            roots.add(row["root"])

    return {
        "morpheme_count": morpheme_count,
        "distinct_words": len(words),
        "distinct_ayat": len(ayat),
        "distinct_roots": len(roots),
        "ayat_set": ayat,
        "words_set": words,
        "roots_set": roots,
    }
