"""Tests for raw Ibn Kathir Arabic tafsir files (T1.2)."""

import json
from pathlib import Path
import pytest

from src.ingest.download import calculate_sha256, read_checksums
from src.ingest.tafsir_ibn_kathir import load_surah_ayah_pairs

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
TAFSIR_DIR = RAW_DIR / "tafsir" / "ibn-kathir"
MANIFEST_FILE = TAFSIR_DIR / "MANIFEST.txt"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"
TANZIL_SIMPLE_CLEAN = RAW_DIR / "tanzil" / "quran-simple-clean.txt"


def _check_files_present():
    if not TAFSIR_DIR.exists() or not MANIFEST_FILE.exists():
        pytest.skip("Ibn Kathir raw files or manifest absent; skipping tafsir tests.")
    sample = TAFSIR_DIR / "1" / "1.json"
    if not sample.exists():
        pytest.skip("Ibn Kathir raw files absent; skipping tafsir tests.")


def test_load_surah_ayah_pairs():
    """Verify Tanzil reader loads exactly 6236 continuous ayat pairs."""
    ayat = load_surah_ayah_pairs(TANZIL_SIMPLE_CLEAN)
    assert len(ayat) == 6236
    assert ayat[0] == (1, 1)
    assert ayat[-1] == (114, 6)
    surahs = {s for s, _ in ayat}
    assert len(surahs) == 114
    assert surahs == set(range(1, 115))


def test_tafsir_raw_counts_and_json_structure():
    """Verify exactly 6236 files match (surah, ayah) from Tanzil and parse as JSON."""
    _check_files_present()

    ayat = load_surah_ayah_pairs(TANZIL_SIMPLE_CLEAN)
    assert len(ayat) == 6236, f"Expected 6236 ayat, got {len(ayat)}"

    for surah, ayah in ayat:
        file_path = TAFSIR_DIR / str(surah) / f"{ayah}.json"
        assert file_path.exists(), f"Missing tafsir file: {file_path}"
        assert file_path.stat().st_size > 0, f"Empty tafsir file: {file_path}"

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "surah" in data, f"Missing 'surah' key in {file_path}"
        assert "ayah" in data, f"Missing 'ayah' key in {file_path}"
        assert "text" in data, f"Missing 'text' key in {file_path}"

        assert int(data["surah"]) == surah, (
            f"Surah mismatch in {file_path}: expected {surah}, got {data['surah']}"
        )
        assert int(data["ayah"]) == ayah, (
            f"Ayah mismatch in {file_path}: expected {ayah}, got {data['ayah']}"
        )


def test_tafsir_manifest_and_checksums():
    """Verify every file's sha256 matches MANIFEST.txt and MANIFEST.txt is in CHECKSUMS.txt."""
    _check_files_present()
    assert MANIFEST_FILE.exists(), f"MANIFEST.txt missing at {MANIFEST_FILE}"

    entries = read_checksums(MANIFEST_FILE)
    assert len(entries) == 6236, f"Expected 6236 entries in MANIFEST.txt, got {len(entries)}"

    manifest_map = {}
    for entry in entries:
        manifest_map[entry["path"]] = entry["sha256"]

    ayat = load_surah_ayah_pairs(TANZIL_SIMPLE_CLEAN)
    for surah, ayah in ayat:
        file_path = TAFSIR_DIR / str(surah) / f"{ayah}.json"
        rel_path = file_path.resolve().relative_to(ROOT.resolve()).as_posix()
        expected_sha = manifest_map.get(rel_path)
        assert expected_sha is not None, f"No manifest checksum entry found for {rel_path}"

        computed_sha = calculate_sha256(file_path)
        assert computed_sha == expected_sha, (
            f"SHA-256 mismatch for {rel_path}: computed {computed_sha} != expected {expected_sha}"
        )

    # Check that MANIFEST.txt itself is recorded in data/raw/CHECKSUMS.txt
    assert CHECKSUMS_FILE.exists(), f"CHECKSUMS.txt missing at {CHECKSUMS_FILE}"
    root_entries = read_checksums(CHECKSUMS_FILE)
    rel_manifest = MANIFEST_FILE.resolve().relative_to(ROOT.resolve()).as_posix()
    manifest_root_entry = next((e for e in root_entries if e["path"] == rel_manifest), None)
    assert manifest_root_entry is not None, f"No entry for {rel_manifest} in {CHECKSUMS_FILE}"

    computed_manifest_sha = calculate_sha256(MANIFEST_FILE)
    assert computed_manifest_sha == manifest_root_entry["sha256"], (
        f"MANIFEST.txt sha256 mismatch in CHECKSUMS.txt: {computed_manifest_sha} != {manifest_root_entry['sha256']}"
    )
