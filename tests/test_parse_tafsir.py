"""Tests for Ibn Kathir tafsir parser producing interim JSONL (T3.4)."""

import hashlib
import json
from pathlib import Path
import pytest

from src.ingest.parse_tafsir import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_TAFSIR_DIR,
    DEFAULT_TANZIL_SIMPLE,
    parse_tafsir,
)

ROOT = Path(__file__).resolve().parent.parent
TAFSIR_RAW_DIR = ROOT / "data" / "raw" / "tafsir" / "ibn-kathir"
TANZIL_SIMPLE = ROOT / "data" / "raw" / "tanzil" / "quran-simple-clean.txt"
INTERIM_DIR = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir"
SEGMENTS_JSONL = INTERIM_DIR / "segments.jsonl"
MUFASSIR_JSONL = INTERIM_DIR / "mufassir.jsonl"
BOOK_JSONL = INTERIM_DIR / "book.jsonl"


def _check_raw_present():
    if not TAFSIR_RAW_DIR.exists() or not TANZIL_SIMPLE.exists():
        pytest.skip("Raw tafsir or Tanzil files absent; skipping parse tests.")
    sample = TAFSIR_RAW_DIR / "1" / "1.json"
    if not sample.exists():
        pytest.skip("Raw tafsir files absent; skipping parse tests.")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="module")
def built() -> Path:
    """Parse the 6,236 raw files once per module; the tests below read the output."""
    _check_raw_present()
    parse_tafsir(output_dir=INTERIM_DIR)
    return INTERIM_DIR


def test_parse_mufassir_and_book(built):
    """Verify mufassir.jsonl and book.jsonl have exact schema properties."""

    assert MUFASSIR_JSONL.exists()
    assert BOOK_JSONL.exists()

    with open(MUFASSIR_JSONL, "r", encoding="utf-8") as f:
        mufassir_records = [json.loads(line) for line in f]
    assert len(mufassir_records) == 1
    m = mufassir_records[0]
    assert m["mufassir_id"] == "ibn-kathir"
    assert m["name"] == "إسماعيل بن عمر بن كثير"
    assert m["death_hijri"] == 774

    with open(BOOK_JSONL, "r", encoding="utf-8") as f:
        book_records = [json.loads(line) for line in f]
    assert len(book_records) == 1
    b = book_records[0]
    assert b["book_id"] == "ibn-kathir"
    assert b["mufassir_id"] == "ibn-kathir"
    assert b["title"] == "تفسير القرآن العظيم"
    assert b["source"] == "spa5k@eb82bb6"


def test_segments_count_structure_and_ids(built):
    """Verify exactly 1,911 segments, fields, ordering, and G2 fixture IDs."""

    assert SEGMENTS_JSONL.exists()

    with open(SEGMENTS_JSONL, "r", encoding="utf-8") as f:
        segments = [json.loads(line) for line in f]

    # Exactly 1,911 segments
    assert len(segments) == 1911

    expected_keys = [
        "book_id",
        "char_count",
        "covers",
        "first_ayah",
        "last_ayah",
        "n",
        "segment_id",
        "surah_id",
        "text",
        "text_norm",
    ]

    seg_ids = set()
    prev_pos = (0, 0)

    for seg in segments:
        assert sorted(seg.keys()) == expected_keys
        assert seg["book_id"] == "ibn-kathir"
        assert seg["n"] == 1
        assert isinstance(seg["surah_id"], int)
        assert isinstance(seg["first_ayah"], int)
        assert isinstance(seg["last_ayah"], int)
        assert seg["first_ayah"] <= seg["last_ayah"]

        expected_id = f"ibn-kathir:{seg['surah_id']}:{seg['first_ayah']}-{seg['last_ayah']}:1"
        assert seg["segment_id"] == expected_id
        assert seg["char_count"] == len(seg["text"])

        # Check deterministic ascending ordering
        pos = (seg["surah_id"], seg["first_ayah"])
        assert pos > prev_pos
        prev_pos = pos

        seg_ids.add(seg["segment_id"])

    # G2 fixture IDs must exist
    assert "ibn-kathir:2:255-255:1" in seg_ids
    assert "ibn-kathir:30:30-32:1" in seg_ids
    assert "ibn-kathir:4:116-122:1" in seg_ids


def test_covers_total_6236_and_text_equals_raw(built):
    """Verify covers total 6,236 with every ayah covered once, and text equals raw files."""

    with open(SEGMENTS_JSONL, "r", encoding="utf-8") as f:
        segments = [json.loads(line) for line in f]

    all_covered = []
    for seg in segments:
        expected_covers = [
            f"{seg['surah_id']}:{a}"
            for a in range(seg["first_ayah"], seg["last_ayah"] + 1)
        ]
        assert seg["covers"] == expected_covers
        all_covered.extend(seg["covers"])

    # Total covers is 6,236 and every ayah covered exactly once
    assert len(all_covered) == 6236
    assert len(set(all_covered)) == 6236

    # Verify text equals raw file for each ayah
    for seg in segments:
        surah_id = seg["surah_id"]
        for ayah_str in seg["covers"]:
            ayah_num = int(ayah_str.split(":")[1])
            raw_file = TAFSIR_RAW_DIR / str(surah_id) / f"{ayah_num}.json"
            assert raw_file.exists(), f"Raw file {raw_file} not found"
            with open(raw_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            assert raw_data["text"] == seg["text"], (
                f"Text mismatch for ayah {ayah_str} in segment {seg['segment_id']}"
            )


def test_char_counts_and_largest_group(built):
    """Verify sum of char_count == 13,401,179 and largest group == 74:11-30 (20 ayat)."""

    with open(SEGMENTS_JSONL, "r", encoding="utf-8") as f:
        segments = [json.loads(line) for line in f]

    total_chars = sum(seg["char_count"] for seg in segments)
    assert total_chars == 13401179

    # Find largest group by number of covered ayat
    sorted_by_group_size = sorted(segments, key=lambda s: len(s["covers"]), reverse=True)
    largest = sorted_by_group_size[0]
    assert largest["segment_id"] == "ibn-kathir:74:11-30:1"
    assert largest["surah_id"] == 74
    assert largest["first_ayah"] == 11
    assert largest["last_ayah"] == 30
    assert len(largest["covers"]) == 20

    # Second largest is 74:38-56 (19 ayat)
    second_largest = sorted_by_group_size[1]
    assert second_largest["segment_id"] == "ibn-kathir:74:38-56:1"
    assert len(second_largest["covers"]) == 19


def test_byte_identical_rerun(built, tmp_path):
    """A second run produces byte-identical output to the module's first run."""
    dir1 = built
    dir2 = tmp_path / "run2"

    parse_tafsir(output_dir=dir2)

    for fname in ["segments.jsonl", "mufassir.jsonl", "book.jsonl"]:
        p1 = dir1 / fname
        p2 = dir2 / fname
        assert p1.exists() and p2.exists()
        assert _sha256(p1) == _sha256(p2)
