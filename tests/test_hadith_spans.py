"""Unit tests for Hadith span extractor (T4.5 - no network)."""

import json
from pathlib import Path
import pytest

from src.extract.hadith_spans import (
    find_cue_paragraphs,
    split_long_paragraph,
    locate_and_check_anchors,
)
from src.extract.locate import locate
from src.extract.models import HadithSpanAnchor

ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = ROOT / "data" / "gold" / "phase4.jsonl"


def _load_w01() -> dict:
    with open(GOLD_PATH, encoding="utf-8") as f:
        return json.loads(f.readline())


def test_cue_finder_w01_and_skips_footnotes():
    """Cue finder finds W01's paragraph and skips cues occurring only inside footnotes."""
    w01 = _load_w01()
    text = w01["window_text"]

    paras = find_cue_paragraphs(text)
    assert paras == [(0, len(text))]

    # Text where the only cue is inside a [[...]] footnote
    footnote_only = "هذا تفسير كلام عادي [[رواه البخاري ومسلم في الصحيح]] ليس فيه حديث إطلاقا."
    assert find_cue_paragraphs(footnote_only) == []

    # Text with a real cue outside
    real_cue = "وقال الإمام أحمد: حدثنا فلان عن علان."
    assert len(find_cue_paragraphs(real_cue)) == 1


def test_long_paragraph_splitter_never_cuts_quotes_or_footnotes():
    """Splitter never cuts inside [[...]] or ﴿...﴾ and creates overlapping windows."""
    # Construct a paragraph > 3000 chars with footnotes and quotes around candidate split points
    sentence = "قال الإمام أحمد: حدثنا عبد الرزاق عن فلان. "
    footnote = "[[انظر المسند (١/٢٣) وصحيح مسلم برقم (١٢٣)]]. "
    quote = "﴿وَإِذَا سَمِعُوا مَا أُنزلَ إِلَى الرَّسُولِ: تَرَى أَعْيُنَهُمْ تَفِيضُ مِنَ الدَّمْعِ﴾. "

    parts = []
    # Build a text of ~4500 chars
    while len("".join(parts)) < 4500:
        parts.extend([sentence, footnote, quote])
    para_text = "".join(parts)
    assert len(para_text) > 3000

    windows = split_long_paragraph(para_text, para_start=100, max_len=3000)
    assert len(windows) >= 2

    # Verify no window boundary cuts inside a footnote or quote
    for win_start, win_end in windows:
        rel_start = win_start - 100
        rel_end = win_end - 100
        # Check footnotes
        import re
        from src.extract.footnotes import FOOTNOTE_RE
        from src.extract.quran_spans import QUOTE_RE

        for m in FOOTNOTE_RE.finditer(para_text):
            s, e = m.span()
            assert not (s < rel_start < e), f"Window start {rel_start} cuts footnote [{s}, {e})"
            assert not (s < rel_end < e), f"Window end {rel_end} cuts footnote [{s}, {e})"

        for m in QUOTE_RE.finditer(para_text):
            s, e = m.span()
            assert not (s < rel_start < e), f"Window start {rel_start} cuts quote [{s}, {e})"
            assert not (s < rel_end < e), f"Window end {rel_end} cuts quote [{s}, {e})"

    # Verify consecutive windows overlap
    for i in range(len(windows) - 1):
        assert windows[i][1] > windows[i + 1][0]


def test_anchor_checks_rejects_spans_inside_quote_or_footnote():
    """Anchor check rejects spans ending/starting strictly inside quote or footnote, or > 6000 chars."""
    text = (
        "قال رسول الله: هذا كلام النبوة الشريفة. "
        "[[هذا هامش محقق طويل جدا]] "
        "ثم قال: ﴿إِنَّ هَذَا الْقُرْآنَ يَهْدِي لِلَّتِي هِيَ أَقْوَمُ﴾ وبعدها."
    )

    # Valid anchor
    valid = HadithSpanAnchor(
        start_anchor="قال رسول الله",
        end_anchor="كلام النبوة الشريفة",
        cue="قال رسول الله",
        kind="marfu",
    )
    res = locate_and_check_anchors(text, [valid], segment_id="seg:1:1-1:1")
    assert len(res) == 1
    assert res[0]["start"] == 0

    # Anchor ending strictly inside footnote
    fn_bad = HadithSpanAnchor(
        start_anchor="قال رسول الله",
        end_anchor="هامش محقق طويل",
        kind="marfu",
    )
    assert locate_and_check_anchors(text, [fn_bad], segment_id="seg:1:1-1:1") == []

    # Anchor ending strictly inside quote
    quote_bad = HadithSpanAnchor(
        start_anchor="قال رسول الله",
        end_anchor="إِنَّ هَذَا الْقُرْآنَ",
        kind="marfu",
    )
    assert locate_and_check_anchors(text, [quote_bad], segment_id="seg:1:1-1:1") == []


def test_w01_anchors_from_five_words_locate_exactly():
    """Anchors made from first and last 5 words of W01's two gold spans locate to exact offsets."""
    w01 = _load_w01()
    text = w01["window_text"]

    gold_hadiths = [s for s in w01["spans"] if s.get("type") == "HADITH"]
    assert len(gold_hadiths) == 2

    # Span 1: [141, 657)
    s1_text = text[gold_hadiths[0]["start"]:gold_hadiths[0]["end"]]
    s1_words = s1_text.split()
    s1_start = " ".join(s1_words[:5])
    s1_end = " ".join(s1_words[-5:])

    anchor1 = HadithSpanAnchor(
        start_anchor=s1_start,
        end_anchor=s1_end,
        kind="marfu",
    )
    loc1 = locate(text, anchor1)
    assert loc1 == (141, 657)

    # Span 2: [658, 790)
    s2_text = text[gold_hadiths[1]["start"]:gold_hadiths[1]["end"]]
    s2_words = s2_text.split()
    s2_start = " ".join(s2_words[:5])
    s2_end = " ".join(s2_words[-5:])

    anchor2 = HadithSpanAnchor(
        start_anchor=s2_start,
        end_anchor=s2_end,
        kind="marfu",
    )
    loc2 = locate(text, anchor2)
    assert loc2 == (658, 790)


def test_iou_matcher_cases():
    """IoU matcher on hand-made cases: exact, shifted, competing one-to-one."""
    from src.extract.hadith_spans import match_spans_one_to_one

    # Exact match
    p = [{"start": 100, "end": 200, "kind": "marfu"}]
    g = [{"start": 100, "end": 200, "kind": "marfu"}]
    pairs, fp, miss = match_spans_one_to_one(p, g)
    assert len(pairs) == 1
    assert pairs[0][2] == 1.0
    assert len(fp) == 0 and len(miss) == 0

    # Shifted match (start delta +5, end delta +5 on length 100)
    p = [{"start": 100, "end": 200}]
    g = [{"start": 105, "end": 205}]
    pairs, fp, miss = match_spans_one_to_one(p, g)
    assert len(pairs) == 1
    assert round(pairs[0][2], 4) == 0.9048

    # Competing: one gold, two predicted spans with different IoUs
    p = [
        {"start": 100, "end": 200, "id": "p1"},  # exact, iou 1.0
        {"start": 105, "end": 200, "id": "p2"},  # partial, iou 0.95
    ]
    g = [{"start": 100, "end": 200, "id": "g1"}]
    pairs, fp, miss = match_spans_one_to_one(p, g)
    assert len(pairs) == 1
    assert pairs[0][0]["id"] == "p1"
    assert pairs[0][2] == 1.0
    assert len(fp) == 1 and fp[0]["id"] == "p2"
    assert len(miss) == 0


def test_locate_fallback_minimum_three_words():
    """Fallback in locate only accepts prefixes/suffixes of >= 3 words, never 2 words."""
    text = "وقال الإمام أحمد: حدثنا عبد الرزاق بن همام قال أخبرنا معمر عن قتادة به."

    # Full exact match: no fallback used
    a_exact = HadithSpanAnchor(
        start_anchor="وقال الإمام أحمد: حدثنا",
        end_anchor="عن قتادة به",
        kind="marfu",
    )
    res_exact = locate(text, a_exact)
    assert res_exact is not None
    assert res_exact.used_fallback is False

    # Start anchor with an extra hallucinated trailing word:
    # 4 words match ("وقال الإمام أحمد: حدثنا")
    a_4w = HadithSpanAnchor(
        start_anchor="وقال الإمام أحمد: حدثنا زائد",
        end_anchor="عن قتادة به",
        kind="marfu",
    )
    res_4w = locate(text, a_4w)
    assert res_4w is not None
    assert res_4w.used_fallback is True

    # Start anchor where only 2 words match ("وقال الإمام"), remainder differs:
    # Since min words is 3, fallback should NOT match and return None
    a_2w = HadithSpanAnchor(
        start_anchor="وقال الإمام شيء آخر تماما",
        end_anchor="عن قتادة به",
        kind="marfu",
    )
    res_2w = locate(text, a_2w)
    assert res_2w is None

    # End anchor with extra prefix word where 3 words match ("عن قتادة به")
    a_end_3w = HadithSpanAnchor(
        start_anchor="وقال الإمام أحمد: حدثنا",
        end_anchor="غيرموجود عن قتادة به",
        kind="marfu",
    )
    res_end_3w = locate(text, a_end_3w)
    assert res_end_3w is not None
    assert res_end_3w.used_fallback is True

    # End anchor where only 2 words match ("قتادة به"), min words is 3 so should return None
    a_end_2w = HadithSpanAnchor(
        start_anchor="وقال الإمام أحمد: حدثنا",
        end_anchor="شيء غير موجود قتادة به",
        kind="marfu",
    )
    res_end_2w = locate(text, a_end_2w)
    assert res_end_2w is None

