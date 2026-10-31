"""Tests for raw Quranic Arabic Corpus morphology archive (T1.4)."""

from pathlib import Path
import pytest
import zipfile

from src.ingest.download import calculate_sha256, read_checksums
from src.ingest.quranic_corpus import (
    CORPUS_SHA256,
    CORPUS_TXT_NAME,
    CORPUS_ZIP_PATH,
    EXPECTED_AYAT,
    EXPECTED_MORPHEMES,
    EXPECTED_ROOTS,
    EXPECTED_WORDS,
    compute_corpus_stats,
)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"
TANZIL_SIMPLE_CLEAN = RAW_DIR / "tanzil" / "quran-simple-clean.txt"

EXPECTED_UNCOMPRESSED_SIZE = 6309503


def _check_zip_present() -> None:
    if not CORPUS_ZIP_PATH.exists():
        pytest.skip(f"Quranic Corpus zip absent at {CORPUS_ZIP_PATH}; skipping test.")


def test_corpus_zip_integrity_and_single_member():
    """Verify zip integrity, exactly one member, and uncompressed size."""
    _check_zip_present()

    with zipfile.ZipFile(CORPUS_ZIP_PATH, "r") as zf:
        # testzip() returns None if no bad CRC or corrupt file is found
        bad_file = zf.testzip()
        assert bad_file is None, f"Corrupted file found in zip: {bad_file}"

        namelist = zf.namelist()
        assert namelist == [CORPUS_TXT_NAME], f"Expected exactly [{CORPUS_TXT_NAME}], got {namelist}"

        info = zf.getinfo(CORPUS_TXT_NAME)
        assert info.file_size == EXPECTED_UNCOMPRESSED_SIZE, (
            f"Expected file size {EXPECTED_UNCOMPRESSED_SIZE}, got {info.file_size}"
        )


def test_corpus_checksum_recorded_and_matches():
    """Verify sha256 of the zip matches CHECKSUMS.txt and pinned baseline."""
    _check_zip_present()
    assert CHECKSUMS_FILE.exists(), f"CHECKSUMS.txt missing at {CHECKSUMS_FILE}"

    entries = read_checksums(CHECKSUMS_FILE)
    matching_entries = [
        entry
        for entry in entries
        if entry["path"].replace("\\", "/").endswith("quranic-corpus-morphology-0.4.zip")
    ]
    assert len(matching_entries) == 1, (
        f"Expected exactly 1 checksum entry for morphology zip, got {len(matching_entries)}"
    )

    recorded_sha = matching_entries[0]["sha256"]
    assert recorded_sha == CORPUS_SHA256, (
        f"Recorded sha256 {recorded_sha} does not match expected {CORPUS_SHA256}"
    )

    actual_sha = calculate_sha256(CORPUS_ZIP_PATH)
    assert actual_sha == CORPUS_SHA256, (
        f"Computed sha256 {actual_sha} does not match expected {CORPUS_SHA256}"
    )


def test_morphology_exact_counts_and_tanzil_ayat_alignment():
    """Verify exact counts: morphemes, words, roots, and 1:1 match with Tanzil ayat."""
    _check_zip_present()
    if not TANZIL_SIMPLE_CLEAN.exists():
        pytest.skip(f"Tanzil clean text absent at {TANZIL_SIMPLE_CLEAN}; cannot verify ayat set.")

    # Read Tanzil ayat set
    tanzil_ayat: set[tuple[int, int]] = set()
    with open(TANZIL_SIMPLE_CLEAN, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split("|")
            assert len(parts) >= 2, f"Invalid Tanzil line format: {line}"
            tanzil_ayat.add((int(parts[0]), int(parts[1])))

    assert len(tanzil_ayat) == EXPECTED_AYAT, (
        f"Expected {EXPECTED_AYAT} ayat in Tanzil, found {len(tanzil_ayat)}"
    )

    # Compute corpus statistics directly from zip stream
    stats = compute_corpus_stats(CORPUS_ZIP_PATH)

    assert stats["morpheme_count"] == EXPECTED_MORPHEMES, (
        f"Expected {EXPECTED_MORPHEMES} morphemes, got {stats['morpheme_count']}"
    )
    assert stats["distinct_words"] == EXPECTED_WORDS, (
        f"Expected {EXPECTED_WORDS} distinct words, got {stats['distinct_words']}"
    )
    assert stats["distinct_roots"] == EXPECTED_ROOTS, (
        f"Expected {EXPECTED_ROOTS} distinct roots, got {stats['distinct_roots']}"
    )
    assert stats["distinct_ayat"] == EXPECTED_AYAT, (
        f"Expected {EXPECTED_AYAT} distinct ayat, got {stats['distinct_ayat']}"
    )

    # Verify set equality between Corpus ayat and Tanzil ayat
    corpus_ayat: set[tuple[int, int]] = stats["ayat_set"]
    assert corpus_ayat == tanzil_ayat, (
        f"Mismatch between Corpus ayat and Tanzil ayat. "
        f"In Corpus not Tanzil: {corpus_ayat - tanzil_ayat}. "
        f"In Tanzil not Corpus: {tanzil_ayat - corpus_ayat}."
    )
