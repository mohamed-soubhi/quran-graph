"""Tests for raw fawazahmed0 hadith collection files (T1.3)."""

import json
from pathlib import Path
import unicodedata
import pytest

from src.ingest.download import calculate_sha256, read_checksums
from src.ingest.hadith_fawazahmed0 import extract_arabic_editions

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
HADITH_DIR = RAW_DIR / "hadith" / "fawazahmed0"
MANIFEST_FILE = HADITH_DIR / "MANIFEST.txt"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"
EDITIONS_FILE = HADITH_DIR / "editions.json"

EXPECTED_COLLECTIONS = {
    "abudawud",
    "bukhari",
    "dehlawi",
    "ibnmajah",
    "malik",
    "muslim",
    "nasai",
    "nawawi",
    "qudsi",
    "tirmidhi",
}


def _check_files_present():
    if not HADITH_DIR.exists() or not MANIFEST_FILE.exists() or not EDITIONS_FILE.exists():
        pytest.skip("Hadith raw files or manifest absent; skipping hadith tests.")
    sample = HADITH_DIR / "ara-bukhari.json"
    if not sample.exists():
        pytest.skip("Hadith raw files absent; skipping hadith tests.")


def test_extract_arabic_editions():
    """Verify editions.json parses and extracts the 10 Arabic editions dynamically."""
    _check_files_present()
    editions = extract_arabic_editions(EDITIONS_FILE)
    assert len(editions) == 10, f"Expected 10 editions, got {len(editions)}: {editions}"

    extracted_collections = set()
    for ed in editions:
        assert ed.startswith("ara-"), f"Edition name does not start with ara-: {ed}"
        assert not ed.endswith("1"), f"Undiacritized edition detected: {ed}"
        col_name = ed[4:]
        extracted_collections.add(col_name)

    assert extracted_collections == EXPECTED_COLLECTIONS, (
        f"Collections mismatch: {extracted_collections} != {EXPECTED_COLLECTIONS}"
    )


def test_hadith_raw_json_and_fields():
    """Verify each collection file parses as JSON and hadiths have hadithnumber and valid text."""
    _check_files_present()
    editions = extract_arabic_editions(EDITIONS_FILE)

    total_hadiths = 0
    non_empty_texts = 0

    for ed_name in editions:
        file_path = HADITH_DIR / f"{ed_name}.json"
        assert file_path.exists(), f"Missing hadith file: {file_path}"
        assert file_path.stat().st_size > 0, f"Empty file: {file_path}"

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "metadata" in data, f"Missing 'metadata' in {file_path}"
        assert "hadiths" in data, f"Missing 'hadiths' in {file_path}"

        hadiths = data["hadiths"]
        assert len(hadiths) > 0, f"No hadiths found in {file_path}"

        for h in hadiths:
            total_hadiths += 1
            # Every hadith has hadithnumber
            assert "hadithnumber" in h, f"Missing 'hadithnumber' in {file_path} item {h}"
            assert h["hadithnumber"] is not None, f"hadithnumber is None in {file_path}"
            assert isinstance(h["hadithnumber"], (int, float)), (
                f"Invalid hadithnumber type in {file_path}: {type(h['hadithnumber'])}"
            )

            # Every hadith has text field as str
            assert "text" in h, f"Missing 'text' key in {file_path} hadith {h.get('hadithnumber')}"
            assert isinstance(h["text"], str), f"text is not a string in {file_path}"

            if h["text"].strip():
                non_empty_texts += 1

        # Small collections must have 100% non-empty texts
        if ed_name in ("ara-dehlawi", "ara-nawawi", "ara-qudsi"):
            empty_in_small = sum(1 for h in hadiths if not h["text"].strip())
            assert empty_in_small == 0, f"Unexpected empty hadiths in {ed_name}: {empty_in_small}"

    # Across all collections, over 98% of hadith entries have non-empty text
    # (the remaining ~1.1% are upstream Book 0 / Introduction structural placeholders)
    non_empty_ratio = non_empty_texts / total_hadiths
    assert non_empty_ratio > 0.98, (
        f"Non-empty text ratio unexpectedly low: {non_empty_ratio:.2%} ({non_empty_texts}/{total_hadiths})"
    )


def test_hadith_bukhari_diacritics():
    """Verify ara-bukhari #1 has diacritics (expected 249 marks)."""
    _check_files_present()
    bukhari_file = HADITH_DIR / "ara-bukhari.json"
    with open(bukhari_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    h1 = data["hadiths"][0]
    assert h1["hadithnumber"] == 1
    marks = sum(1 for c in h1["text"] if unicodedata.category(c) == "Mn")
    assert marks == 249, f"Expected 249 diacritic marks in Bukhari #1, got {marks}"


def test_hadith_manifest_and_checksums():
    """Verify every file's sha256 matches MANIFEST.txt and MANIFEST.txt is in CHECKSUMS.txt."""
    _check_files_present()
    assert MANIFEST_FILE.exists(), f"MANIFEST.txt missing at {MANIFEST_FILE}"

    entries = read_checksums(MANIFEST_FILE)
    assert len(entries) == 11, f"Expected 11 entries in MANIFEST.txt, got {len(entries)}"

    manifest_map = {e["path"]: e["sha256"] for e in entries}

    # Verify editions.json
    rel_editions = (HADITH_DIR / "editions.json").resolve().relative_to(ROOT.resolve()).as_posix()
    assert rel_editions in manifest_map, f"Missing manifest entry for {rel_editions}"
    assert calculate_sha256(HADITH_DIR / "editions.json") == manifest_map[rel_editions]

    # Verify 10 collections
    editions = extract_arabic_editions(EDITIONS_FILE)
    for ed_name in editions:
        file_path = HADITH_DIR / f"{ed_name}.json"
        rel_path = file_path.resolve().relative_to(ROOT.resolve()).as_posix()
        expected_sha = manifest_map.get(rel_path)
        assert expected_sha is not None, f"No manifest checksum entry found for {rel_path}"

        computed_sha = calculate_sha256(file_path)
        assert computed_sha == expected_sha, (
            f"SHA-256 mismatch for {rel_path}: computed {computed_sha} != expected {expected_sha}"
        )

    # Verify MANIFEST.txt is recorded in data/raw/CHECKSUMS.txt
    assert CHECKSUMS_FILE.exists(), f"CHECKSUMS.txt missing at {CHECKSUMS_FILE}"
    root_entries = read_checksums(CHECKSUMS_FILE)
    rel_manifest = MANIFEST_FILE.resolve().relative_to(ROOT.resolve()).as_posix()
    manifest_root_entry = next((e for e in root_entries if e["path"] == rel_manifest), None)
    assert manifest_root_entry is not None, f"No entry for {rel_manifest} in {CHECKSUMS_FILE}"

    computed_manifest_sha = calculate_sha256(MANIFEST_FILE)
    assert computed_manifest_sha == manifest_root_entry["sha256"], (
        f"MANIFEST.txt sha256 mismatch in CHECKSUMS.txt: {computed_manifest_sha} != {manifest_root_entry['sha256']}"
    )
