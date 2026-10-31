"""Tests for raw Tanzil Quran text files (T1.1)."""

from pathlib import Path
import pytest

from src.ingest.download import calculate_sha256, read_checksums

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
TANZIL_DIR = RAW_DIR / "tanzil"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"

UTHMANI_FILE = TANZIL_DIR / "quran-uthmani.txt"
SIMPLE_FILE = TANZIL_DIR / "quran-simple-clean.txt"


def _check_files_present():
    if not UTHMANI_FILE.exists() or not SIMPLE_FILE.exists():
        pytest.skip("Tanzil raw files are absent; skipping raw data tests.")


def _parse_ayat(file_path: Path) -> list[tuple[int, int, str]]:
    ayat = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split("|", 2)
            assert len(parts) == 3, f"Invalid format in {file_path}: {line}"
            surah_num = int(parts[0])
            ayah_num = int(parts[1])
            text = parts[2]
            ayat.append((surah_num, ayah_num, text))
    return ayat


def test_tanzil_checksums():
    """Verify both files match their recorded SHA-256 in CHECKSUMS.txt."""
    _check_files_present()
    assert CHECKSUMS_FILE.exists(), f"CHECKSUMS.txt missing at {CHECKSUMS_FILE}"

    entries = read_checksums(CHECKSUMS_FILE)
    assert len(entries) >= 2, f"Expected at least 2 entries in CHECKSUMS.txt, got {len(entries)}"

    checksum_map = {}
    for entry in entries:
        # Map both full relpath and filename to sha256 for flexibility
        checksum_map[entry["path"]] = entry["sha256"]
        checksum_map[Path(entry["path"]).name] = entry["sha256"]

    for target_file in (UTHMANI_FILE, SIMPLE_FILE):
        computed_sha = calculate_sha256(target_file)
        expected_sha = checksum_map.get(target_file.name)
        assert expected_sha is not None, f"No checksum entry found for {target_file.name}"
        assert computed_sha == expected_sha, (
            f"SHA-256 mismatch for {target_file.name}: computed {computed_sha} != expected {expected_sha}"
        )


def test_tanzil_surah_and_ayah_counts():
    """Verify 114 distinct surahs and 6236 non-empty ayah lines in each file."""
    _check_files_present()

    for target_file in (UTHMANI_FILE, SIMPLE_FILE):
        ayat = _parse_ayat(target_file)
        assert len(ayat) == 6236, f"Expected 6236 ayat in {target_file.name}, got {len(ayat)}"

        surahs = {surah for surah, _, _ in ayat}
        assert len(surahs) == 114, f"Expected 114 distinct surahs in {target_file.name}, got {len(surahs)}"
        assert surahs == set(range(1, 115)), f"Surah numbers not continuous 1..114 in {target_file.name}"

        # Ensure no ayah text is empty
        for surah, ayah, text in ayat:
            assert len(text.strip()) > 0, f"Empty text for {surah}:{ayah} in {target_file.name}"


def test_tanzil_keys_match():
    """Verify both files have identical (surah, ayah) keys in the same order."""
    _check_files_present()

    uthmani_ayat = _parse_ayat(UTHMANI_FILE)
    simple_ayat = _parse_ayat(SIMPLE_FILE)

    uthmani_keys = [(surah, ayah) for surah, ayah, _ in uthmani_ayat]
    simple_keys = [(surah, ayah) for surah, ayah, _ in simple_ayat]

    assert uthmani_keys == simple_keys, "Ayah keys (surah, ayah) differ between Uthmani and Simple-Clean"
