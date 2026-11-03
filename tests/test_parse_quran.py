"""Tests for Quran parser producing interim JSONL (T3.2)."""

import json
from pathlib import Path
import subprocess
import sys

from src.ingest.parse_quran import parse_quran

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "tanzil"
INTERIM_QURAN_DIR = ROOT / "data" / "interim" / "quran"
SURAHS_JSONL = INTERIM_QURAN_DIR / "surahs.jsonl"
AYAT_JSONL = INTERIM_QURAN_DIR / "ayat.jsonl"
RAW_UTHMANI = RAW_DIR / "quran-uthmani.txt"
RAW_SIMPLE = RAW_DIR / "quran-simple-clean.txt"


def _read_raw_lines(path: Path) -> dict[tuple[int, int], str]:
    data = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split("|", 2)
            data[(int(parts[0]), int(parts[1]))] = parts[2]
    return data


def test_parse_quran_counts_and_structure():
    """Verify line counts, keys, types, and ordering in surahs.jsonl and ayat.jsonl."""
    # Ensure generated
    parse_quran(output_dir=INTERIM_QURAN_DIR)

    assert SURAHS_JSONL.exists()
    assert AYAT_JSONL.exists()

    with open(SURAHS_JSONL, "r", encoding="utf-8") as f:
        surah_lines = [json.loads(line) for line in f]

    with open(AYAT_JSONL, "r", encoding="utf-8") as f:
        ayah_lines = [json.loads(line) for line in f]

    # Exactly 114 surahs and 6,236 ayat
    assert len(surah_lines) == 114
    assert len(ayah_lines) == 6236

    # Verify Surah structure and ordering
    expected_surah_keys = [
        "ayah_count",
        "has_basmala",
        "name",
        "revelation_order",
        "surah_id",
        "tname",
        "type",
    ]
    for idx, s in enumerate(surah_lines, start=1):
        assert list(s.keys()) == expected_surah_keys
        assert s["surah_id"] == idx
        assert isinstance(s["name"], str) and len(s["name"]) > 0
        assert isinstance(s["tname"], str) and len(s["tname"]) > 0
        assert s["type"] in ("Meccan", "Medinan")
        assert isinstance(s["revelation_order"], int)
        assert isinstance(s["ayah_count"], int)
        if idx == 9:
            assert s["has_basmala"] is False
        else:
            assert s["has_basmala"] is True

    # Verify Ayah structure and ordering
    expected_ayah_keys = [
        "ayah_id",
        "number",
        "surah_id",
        "text",
        "text_norm",
        "text_simple",
        "word_count",
    ]
    last_key = (0, 0)
    for a in ayah_lines:
        assert list(a.keys()) == expected_ayah_keys
        surah_id = a["surah_id"]
        number = a["number"]
        assert a["ayah_id"] == f"{surah_id}:{number}"
        assert (surah_id, number) > last_key
        last_key = (surah_id, number)
        assert len(a["text"]) > 0
        assert len(a["text_simple"]) > 0
        assert len(a["text_norm"]) > 0
        assert a["word_count"] > 0


def test_basmala_rule_and_differing_counts():
    """Verify exactly 112 ayat differ from raw, 1:1 and 9:1 equal raw, and 112:1 norm."""
    parse_quran(output_dir=INTERIM_QURAN_DIR)

    raw_uthmani = _read_raw_lines(RAW_UTHMANI)
    raw_simple = _read_raw_lines(RAW_SIMPLE)

    with open(AYAT_JSONL, "r", encoding="utf-8") as f:
        ayat = [json.loads(line) for line in f]

    uth_diff_count = 0
    sim_diff_count = 0

    for a in ayat:
        s_id = a["surah_id"]
        a_num = a["number"]
        raw_u = raw_uthmani[(s_id, a_num)]
        raw_s = raw_simple[(s_id, a_num)]

        if a["text"] != raw_u:
            uth_diff_count += 1
            # Must only differ on ayah 1 of surahs other than 1 and 9
            assert a_num == 1
            assert s_id not in (1, 9)

        if a["text_simple"] != raw_s:
            sim_diff_count += 1
            assert a_num == 1
            assert s_id not in (1, 9)

        # 1:1 and 9:1 must equal raw verbatim
        if (s_id, a_num) in ((1, 1), (9, 1)):
            assert a["text"] == raw_u
            assert a["text_simple"] == raw_s

        # Normalized 112:1
        if (s_id, a_num) == (112, 1):
            assert a["text_norm"] == "قل هو الله احد"

    # Exactly 112 ayat modified
    assert uth_diff_count == 112
    assert sim_diff_count == 112


def test_total_word_count():
    """Verify sum of word_count across all ayat = 77,881 - 448 = 77,433."""
    parse_quran(output_dir=INTERIM_QURAN_DIR)

    with open(AYAT_JSONL, "r", encoding="utf-8") as f:
        ayat = [json.loads(line) for line in f]

    total_words = sum(a["word_count"] for a in ayat)
    assert total_words == 77433


def test_byte_identical_rerun(tmp_path):
    """Running the parser twice gives byte-identical files."""
    run1_dir = tmp_path / "run1"
    run2_dir = tmp_path / "run2"

    parse_quran(output_dir=run1_dir)
    parse_quran(output_dir=run2_dir)

    for filename in ("surahs.jsonl", "ayat.jsonl"):
        b1 = (run1_dir / filename).read_bytes()
        b2 = (run2_dir / filename).read_bytes()
        assert b1 == b2, f"Files differ between runs for {filename}"


def test_tasks_parse_target():
    """Verify python scripts/tasks.py parse runs successfully."""
    cmd = [sys.executable, str(ROOT / "scripts" / "tasks.py"), "parse"]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, f"tasks.py parse failed with error: {res.stderr}"
    assert "Running parser: src/ingest/parse_quran.py" in res.stdout
