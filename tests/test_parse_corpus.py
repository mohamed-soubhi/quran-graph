"""Tests for Quranic Arabic Corpus morphology parser (T3.3)."""

from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess
import sys
import pytest

from src.ingest.buckwalter import (
    BW,
    REV,
    split_lemma,
    to_arabic,
    to_buckwalter,
)
from src.ingest.parse_quran import parse_quran
from src.ingest.quranic_corpus import (
    CORPUS_ZIP_PATH,
    DEFAULT_OUTPUT_DIR,
    EXPECTED_AYAT,
    EXPECTED_LEMMAS,
    EXPECTED_LEMMA_ROOTS,
    EXPECTED_ROOTS,
    EXPECTED_WORDS,
    EXPECTED_WORD_LEMMAS,
    EXPECTED_WORD_ROOTS,
    parse_corpus,
)

ROOT = Path(__file__).resolve().parent.parent
AYAT_JSONL = ROOT / "data" / "interim" / "quran" / "ayat.jsonl"


def _ensure_parsed():
    if not (DEFAULT_OUTPUT_DIR / "words.jsonl").exists():
        parse_corpus(output_dir=DEFAULT_OUTPUT_DIR)


def test_buckwalter_round_trip_and_errors():
    """Verify lossless round trip for all roots, lemma texts, and word forms."""
    _ensure_parsed()

    with open(DEFAULT_OUTPUT_DIR / "roots.jsonl", "r", encoding="utf-8") as f:
        roots = [json.loads(line) for line in f]
    with open(DEFAULT_OUTPUT_DIR / "lemmas.jsonl", "r", encoding="utf-8") as f:
        lemmas = [json.loads(line) for line in f]
    with open(DEFAULT_OUTPUT_DIR / "words.jsonl", "r", encoding="utf-8") as f:
        words = [json.loads(line) for line in f]

    # Exact count checks for vocabulary sets
    roots_bw = {r["bw"] for r in roots}
    assert len(roots_bw) == EXPECTED_ROOTS == 1642

    distinct_lemma_texts = {l["text"] for l in lemmas}
    assert len(distinct_lemma_texts) == 4817
    lemma_bw = {l["bw"] for l in lemmas}

    # Extract all distinct raw forms from corpus zip
    from src.ingest.quranic_corpus import parse_morphology_stream
    forms_bw = {row["form"] for row in parse_morphology_stream(CORPUS_ZIP_PATH)}
    assert len(forms_bw) == 12205

    # Verify 0 unmapped characters in roots, lemmas, and forms
    for r in roots_bw:
        for c in r:
            assert c in BW, f"Unknown character {c!r} in root {r}"
        assert to_buckwalter(to_arabic(r)) == r

    for l_bw in lemma_bw:
        for c in l_bw:
            assert c in BW, f"Unknown character {c!r} in lemma {l_bw}"
        assert to_buckwalter(to_arabic(l_bw)) == l_bw

    for f_bw in forms_bw:
        for c in f_bw:
            assert c in BW, f"Unknown character {c!r} in form {f_bw}"
        assert to_buckwalter(to_arabic(f_bw)) == f_bw

    # Specific checks
    assert to_arabic("smw") == "سمو"
    assert to_buckwalter("سمو") == "smw"

    # Error handling
    with pytest.raises(ValueError, match="Unknown Buckwalter character"):
        to_arabic("abc12")  # '1', '2' not in standard BW table

    with pytest.raises(ValueError, match="Unknown Arabic character"):
        to_buckwalter("abc")

    # split_lemma tests
    assert split_lemma("EaAd2") == ("EaAd", 2)
    assert split_lemma("EaAd") == ("EaAd", None)
    assert split_lemma("huwd2") == ("huwd", 2)


def test_parse_corpus_counts_and_structure():
    """Verify exact counts and structure of nodes and links."""
    _ensure_parsed()

    words_file = DEFAULT_OUTPUT_DIR / "words.jsonl"
    lemmas_file = DEFAULT_OUTPUT_DIR / "lemmas.jsonl"
    roots_file = DEFAULT_OUTPUT_DIR / "roots.jsonl"
    word_lemmas_file = DEFAULT_OUTPUT_DIR / "word_lemmas.jsonl"
    word_roots_file = DEFAULT_OUTPUT_DIR / "word_roots.jsonl"
    lemma_roots_file = DEFAULT_OUTPUT_DIR / "lemma_roots.jsonl"

    for p in [words_file, lemmas_file, roots_file, word_lemmas_file, word_roots_file, lemma_roots_file]:
        assert p.exists(), f"File {p} does not exist"

    with open(words_file, "r", encoding="utf-8") as f:
        words = [json.loads(line) for line in f]
    with open(lemmas_file, "r", encoding="utf-8") as f:
        lemmas = [json.loads(line) for line in f]
    with open(roots_file, "r", encoding="utf-8") as f:
        roots = [json.loads(line) for line in f]
    with open(word_lemmas_file, "r", encoding="utf-8") as f:
        word_lemmas = [json.loads(line) for line in f]
    with open(word_roots_file, "r", encoding="utf-8") as f:
        word_roots = [json.loads(line) for line in f]
    with open(lemma_roots_file, "r", encoding="utf-8") as f:
        lemma_roots = [json.loads(line) for line in f]

    # Exact counts
    assert len(words) == EXPECTED_WORDS == 77429
    assert len(lemmas) == EXPECTED_LEMMAS == 4832
    assert len(roots) == EXPECTED_ROOTS == 1642
    assert len(word_lemmas) == EXPECTED_WORD_LEMMAS == 74608
    assert len(word_roots) == EXPECTED_WORD_ROOTS == 49968
    assert len(lemma_roots) == EXPECTED_LEMMA_ROOTS == 4657

    # Word 1:1:1 check
    w1 = words[0]
    assert w1["word_id"] == "1:1:1"
    assert w1["ayah_id"] == "1:1"
    assert w1["position"] == 1
    assert w1["text"] == "بِسْمِ"
    assert w1["bw"] == "bisomi"
    assert w1["pos"] == "N"
    assert list(w1.keys()) == ["ayah_id", "bw", "pos", "position", "text", "word_id"]

    # Lemmas details
    with_sense = [l for l in lemmas if l["sense"] is not None]
    assert len(with_sense) == 15
    distinct_texts = {l["text"] for l in lemmas}
    assert len(distinct_texts) == 4817
    # All with_sense must have sense == 2 and '#' in lemma_id
    for l in with_sense:
        assert l["sense"] == 2
        assert "#2" in l["lemma_id"]

    # Root smw check
    root_smw = next((r for r in roots if r["root_id"] == "سمو"), None)
    assert root_smw is not None
    assert root_smw["text"] == "سمو"
    assert root_smw["bw"] == "smw"

    # Word->Lemma links (486 words with 2)
    w_lem_counts = Counter(l["word_id"] for l in word_lemmas)
    words_with_2_lemmas = [wid for wid, c in w_lem_counts.items() if c == 2]
    assert len(words_with_2_lemmas) == 486

    # Word->Root links (1 word with 2: 20:94:2)
    w_root_counts = Counter(r["word_id"] for r in word_roots)
    words_with_2_roots = [wid for wid, c in w_root_counts.items() if c == 2]
    assert len(words_with_2_roots) == 1
    assert words_with_2_roots[0] == "20:94:2"

    # Lemma->Root links (no lemma with 2 roots; 175 lemmas without root)
    lem_root_counts = Counter(lr["lemma_id"] for lr in lemma_roots)
    lemmas_with_2_roots = [lid for lid, c in lem_root_counts.items() if c > 1]
    assert len(lemmas_with_2_roots) == 0

    all_lemma_ids = {l["lemma_id"] for l in lemmas}
    lemmas_without_root = all_lemma_ids - set(lem_root_counts.keys())
    assert len(lemmas_without_root) == 175


def test_word_count_per_ayah_vs_t32():
    """Verify word count per ayah matches T3.2 except exactly 4 known joins."""
    _ensure_parsed()

    if not AYAT_JSONL.exists():
        parse_quran(output_dir=AYAT_JSONL.parent)

    with open(AYAT_JSONL, "r", encoding="utf-8") as f:
        t32_ayat = [json.loads(line) for line in f]
    t32_counts = {a["ayah_id"]: a["word_count"] for a in t32_ayat}

    with open(DEFAULT_OUTPUT_DIR / "words.jsonl", "r", encoding="utf-8") as f:
        words = [json.loads(line) for line in f]

    corpus_counts = defaultdict(int)
    for w in words:
        corpus_counts[w["ayah_id"]] += 1

    diff_ayat = []
    for ayah_id, c_cnt in corpus_counts.items():
        t_cnt = t32_counts[ayah_id]
        if c_cnt != t_cnt:
            diff_ayat.append((ayah_id, c_cnt, t_cnt))

    # Exactly 4 exceptions: 2:181, 8:6, 13:37, 37:130
    assert len(diff_ayat) == 4
    diff_dict = {d[0]: (d[1], d[2]) for d in diff_ayat}
    assert diff_dict == {
        "2:181": (13, 14),
        "8:6": (11, 12),
        "13:37": (19, 20),
        "37:130": (3, 4),
    }


def test_byte_identical_rerun(tmp_path):
    """Verify parser rerun produces byte-identical files."""
    run1_dir = tmp_path / "run1"
    run2_dir = tmp_path / "run2"

    parse_corpus(output_dir=run1_dir)
    parse_corpus(output_dir=run2_dir)

    filenames = [
        "words.jsonl",
        "lemmas.jsonl",
        "roots.jsonl",
        "word_lemmas.jsonl",
        "word_roots.jsonl",
        "lemma_roots.jsonl",
    ]

    for fname in filenames:
        bytes1 = (run1_dir / fname).read_bytes()
        bytes2 = (run2_dir / fname).read_bytes()
        assert bytes1 == bytes2, f"Rerun mismatch in {fname}"


def test_tasks_parse_target():
    """Verify that python scripts/tasks.py parse executes successfully."""
    py = sys.executable
    res = subprocess.run([py, "scripts/tasks.py", "parse"], cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, f"tasks.py parse failed: {res.stderr}"
    assert (DEFAULT_OUTPUT_DIR / "words.jsonl").exists()
