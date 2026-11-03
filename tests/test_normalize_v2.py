"""Tests for Normalizer v2 (T4.1)."""

from collections import defaultdict
import json
from pathlib import Path
import unicodedata

from src.extract.locate import locate
from src.extract.models import HadithSpanAnchor
from src.extract.normalize import NORM_MAP, SKIP_CHARS, normalize_with_map

ROOT = Path(__file__).resolve().parent.parent
WORDS_JSONL = ROOT / "data" / "interim" / "corpus" / "words.jsonl"
AYAT_JSONL = ROOT / "data" / "interim" / "quran" / "ayat.jsonl"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "tafsir_sample.txt"


def test_corpus_vs_tanzil_uthmani_token_alignment():
    """Corpus Word.text vs Tanzil Uthmani token in aligned ayat has exactly 2 diffs: 12:39:1, 12:41:1."""
    assert WORDS_JSONL.exists(), f"Missing {WORDS_JSONL}; run tasks.py parse first"
    assert AYAT_JSONL.exists(), f"Missing {AYAT_JSONL}; run tasks.py parse first"

    with open(WORDS_JSONL, "r", encoding="utf-8") as f:
        corpus_words = [json.loads(line) for line in f]

    with open(AYAT_JSONL, "r", encoding="utf-8") as f:
        ayat = [json.loads(line) for line in f]

    corpus_by_ayah: dict[str, list[dict]] = defaultdict(list)
    for w in corpus_words:
        corpus_by_ayah[w["ayah_id"]].append(w)

    aligned_word_count = 0
    diff_word_ids: list[str] = []

    for a in ayat:
        aid = a["ayah_id"]
        t_tokens = a["text"].split()
        c_list = corpus_by_ayah[aid]
        if len(t_tokens) == len(c_list):
            aligned_word_count += len(t_tokens)
            for t_tok, c_word in zip(t_tokens, c_list):
                c_tok = c_word["text"]
                if normalize_with_map(t_tok)[0] != normalize_with_map(c_tok)[0]:
                    diff_word_ids.append(c_word["word_id"])

    assert aligned_word_count == 77383
    assert diff_word_ids == ["12:39:1", "12:41:1"]
    assert len(diff_word_ids) == 2


def test_hamza_tatweel_spelling_equality():
    """normalize_with_map unifies Tanzil and corpus spellings of hamza/tatweel."""
    tanzil_spelling = "وَبِٱلْـَٔاخِرَةِ"
    corpus_spelling = "وَبِٱلْءَاخِرَةِ"
    norm_tanzil, _ = normalize_with_map(tanzil_spelling)
    norm_corpus, _ = normalize_with_map(corpus_spelling)
    assert norm_tanzil == norm_corpus
    assert norm_tanzil == "وبالاخره"


def test_normalize_v2_index_and_skipped_properties():
    """Index is strictly increasing and text[index[k]] is never a skipped character."""
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    norm, index = normalize_with_map(fixture_text)

    assert len(norm) == len(index)
    assert all(index[i] < index[i + 1] for i in range(len(index) - 1))
    assert all(unicodedata.category(c) != "Mn" for c in norm)
    assert all(c not in SKIP_CHARS for c in norm)
    assert all(fixture_text[k] not in SKIP_CHARS for k in index)
    assert all(unicodedata.category(fixture_text[k]) != "Mn" for k in index)

    # Test synthetic text with all skipped characters:
    # tatweel \u0640, hamza \u0621, small waw \u06e5, small yeh \u06e6
    sample = "بِـسْمِ ٱللَّهِ ۥ ۦ ء"
    s_norm, s_index = normalize_with_map(sample)
    assert len(s_norm) == len(s_index)
    assert all(s_index[i] < s_index[i + 1] for i in range(len(s_index) - 1))
    for k in s_index:
        assert sample[k] not in SKIP_CHARS
        assert unicodedata.category(sample[k]) != "Mn"


def test_existing_t23_locator_offsets_and_g2_fixture():
    """T2.3 locator offsets (141, 657) and (658, 790) and G2 fixture 112:1 remain exact."""
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    assert len(fixture_text) == 904

    ahmad_anchor = HadithSpanAnchor(
        start_anchor="قال الإمام أحمد: حدثنا",
        end_anchor="عند ساق العرش",
        cue="قال الإمام أحمد: حدثنا",
        collection_hint="ahmad",
        number_hint=None,
    )
    ahmad_span = locate(fixture_text, ahmad_anchor)
    assert ahmad_span == (141, 657)

    muslim_anchor = HadithSpanAnchor(
        start_anchor="وقد رواه مسلم",
        end_anchor="عن الجريري-به",
        cue="وقد رواه مسلم",
        collection_hint="muslim",
        number_hint=None,
    )
    muslim_span = locate(fixture_text, muslim_anchor)
    assert muslim_span == (658, 790)

    # G2 112:1 normalization check
    tanzil_112_1 = "قُلْ هُوَ ٱللَّهُ أَحَدٌ"
    norm_112_1, _ = normalize_with_map(tanzil_112_1)
    assert norm_112_1.split() == ["قل", "هو", "الله", "احد"]
