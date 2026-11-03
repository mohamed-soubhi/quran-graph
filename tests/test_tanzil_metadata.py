"""Tests for raw Tanzil Quran metadata XML (T3.1)."""

from pathlib import Path
import pytest

from src.ingest.download import calculate_sha256, read_checksums
from src.ingest.tanzil_metadata import read_suras

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
TANZIL_DIR = RAW_DIR / "tanzil"
METADATA_FILE = TANZIL_DIR / "quran-data.xml"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"
UTHMANI_FILE = TANZIL_DIR / "quran-uthmani.txt"


def _check_files_present():
    if not METADATA_FILE.exists():
        pytest.skip("Tanzil metadata XML file is absent; skipping metadata tests.")


def test_tanzil_metadata_checksum():
    """Verify quran-data.xml matches its recorded SHA-256 in CHECKSUMS.txt."""
    _check_files_present()
    assert CHECKSUMS_FILE.exists(), f"CHECKSUMS.txt missing at {CHECKSUMS_FILE}"

    entries = read_checksums(CHECKSUMS_FILE)
    checksum_map = {}
    for entry in entries:
        checksum_map[entry["path"]] = entry["sha256"]
        checksum_map[Path(entry["path"]).name] = entry["sha256"]

    assert "quran-data.xml" in checksum_map, "quran-data.xml entry missing from CHECKSUMS.txt"

    expected_sha256 = checksum_map["quran-data.xml"]
    actual_sha256 = calculate_sha256(METADATA_FILE)
    assert actual_sha256 == expected_sha256, (
        f"Checksum mismatch for {METADATA_FILE}: expected {expected_sha256}, got {actual_sha256}"
    )


def test_tanzil_metadata_suras():
    """Verify suras metadata: 114 suras, 6236 ayas, start offsets, names, and Meccan/Medinan split."""
    _check_files_present()

    suras = read_suras(METADATA_FILE)

    # Exactly 114 suras, index 1..114
    assert len(suras) == 114, f"Expected 114 suras, got {len(suras)}"
    indices = [s["index"] for s in suras]
    assert indices == list(range(1, 115)), "Surah indices must be 1..114 in order"

    # Type check for required keys
    for s in suras:
        assert isinstance(s["index"], int)
        assert isinstance(s["ayas"], int)
        assert isinstance(s["start"], int)
        assert isinstance(s["name"], str) and len(s["name"]) > 0
        assert isinstance(s["tname"], str) and len(s["tname"]) > 0
        assert isinstance(s["ename"], str) and len(s["ename"]) > 0
        assert isinstance(s["type"], str)
        assert isinstance(s["order"], int)
        assert isinstance(s["rukus"], int)

    # Sum of ayas = 6,236
    total_ayas = sum(s["ayas"] for s in suras)
    assert total_ayas == 6236, f"Expected total 6236 ayas, got {total_ayas}"

    # Verify each surah's ayas equals ayah count in quran-uthmani.txt
    if UTHMANI_FILE.exists():
        uthmani_counts: dict[int, int] = {}
        with open(UTHMANI_FILE, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = stripped.split("|", 2)
                s_idx = int(parts[0])
                uthmani_counts[s_idx] = uthmani_counts.get(s_idx, 0) + 1

        for s in suras:
            s_idx = s["index"]
            assert uthmani_counts[s_idx] == s["ayas"], (
                f"Surah {s_idx} ({s['name']}) ayas mismatch: metadata has {s['ayas']}, "
                f"uthmani text has {uthmani_counts[s_idx]}"
            )

    # start of surah n+1 = start + ayas of surah n
    assert suras[0]["start"] == 0, f"Expected surah 1 start to be 0, got {suras[0]['start']}"
    for i in range(len(suras) - 1):
        expected_next_start = suras[i]["start"] + suras[i]["ayas"]
        actual_next_start = suras[i + 1]["start"]
        assert actual_next_start == expected_next_start, (
            f"Start offset mismatch between surah {suras[i]['index']} and {suras[i + 1]['index']}: "
            f"expected {expected_next_start}, got {actual_next_start}"
        )

    # Specific surah names
    assert suras[0]["name"] == "الفاتحة", f"Surah 1 name mismatch: {suras[0]['name']}"
    assert suras[1]["name"] == "البقرة", f"Surah 2 name mismatch: {suras[1]['name']}"
    assert suras[29]["name"] == "الروم", f"Surah 30 name mismatch: {suras[29]['name']}"

    # 86 Meccan + 28 Medinan
    meccan_count = sum(1 for s in suras if s["type"] == "Meccan")
    medinan_count = sum(1 for s in suras if s["type"] == "Medinan")
    assert (meccan_count, medinan_count) == (86, 28), (
        f"Expected (86 Meccan, 28 Medinan), got ({meccan_count} Meccan, {medinan_count} Medinan)"
    )
    assert set(s["type"] for s in suras) == {"Meccan", "Medinan"}
