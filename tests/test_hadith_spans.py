"""Unit tests for Hadith span extractor (T4.5, T4.5b - no network)."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from neo4j.exceptions import ServiceUnavailable

from src.extract.hadith_spans import (
    find_cue_paragraphs,
    split_long_paragraph,
    locate_and_check_anchors,
)
from src.extract.locate import locate
from src.extract.models import HadithSpanAnchor
from src.extract.glm_client import (
    GlmExtractionError,
    GlmResponseError,
    extract_hadith_anchors,
    parse_anchor_response,
)
from scripts.run_hadith_book import (
    load_raw_status,
    resolve_overlapping_spans,
    should_stop_for_failures,
)
from src.graph.client import get_driver
from src.graph.spans import delete_spans_by_type, write_spans

ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = ROOT / "data" / "gold" / "phase4.jsonl"


@pytest.fixture(scope="module")
def neo4j_driver():
    """Provide a Neo4j driver if reachable, otherwise skip."""
    try:
        driver = get_driver()
    except (ServiceUnavailable, Exception) as exc:
        pytest.skip(f"Neo4j not reachable: {exc}")

    yield driver
    driver.close()


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
    sentence = "قال الإمام أحمد: حدثنا عبد الرزاق عن فلان. "
    footnote = "[[انظر المسند (١/٢٣) وصحيح مسلم برقم (١٢٣)]]. "
    quote = "﴿وَإِذَا سَمِعُوا مَا أُنزلَ إِلَى الرَّسُولِ: تَرَى أَعْيُنَهُمْ تَفِيضُ مِنَ الدَّمْعِ﴾. "

    parts = []
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
        {"start": 100, "end": 200, "id": "p1"},
        {"start": 105, "end": 200, "id": "p2"},
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

    # Start anchor with an extra hallucinated trailing word: 4 words match
    a_4w = HadithSpanAnchor(
        start_anchor="وقال الإمام أحمد: حدثنا زائد",
        end_anchor="عن قتادة به",
        kind="marfu",
    )
    res_4w = locate(text, a_4w)
    assert res_4w is not None
    assert res_4w.used_fallback is True

    # Start anchor where only 2 words match -> returns None
    a_2w = HadithSpanAnchor(
        start_anchor="وقال الإمام شيء آخر تماما",
        end_anchor="عن قتادة به",
        kind="marfu",
    )
    res_2w = locate(text, a_2w)
    assert res_2w is None

    # End anchor with extra prefix word where 3 words match
    a_end_3w = HadithSpanAnchor(
        start_anchor="وقال الإمام أحمد: حدثنا",
        end_anchor="غيرموجود عن قتادة به",
        kind="marfu",
    )
    res_end_3w = locate(text, a_end_3w)
    assert res_end_3w is not None
    assert res_end_3w.used_fallback is True

    # End anchor where only 2 words match -> returns None
    a_end_2w = HadithSpanAnchor(
        start_anchor="وقال الإمام أحمد: حدثنا",
        end_anchor="شيء غير موجود قتادة به",
        kind="marfu",
    )
    res_end_2w = locate(text, a_end_2w)
    assert res_end_2w is None


# ---------------------------------------------------------------------------
# T4.5b Tests
# ---------------------------------------------------------------------------


def test_parse_anchor_response_logged_failures():
    """Test the three logged failures from T4.5 as raw strings (T4.5b Step 9)."""
    # 1. Trailing text after JSON
    raw_trailing = '{"spans": []}\n\n**Explanation: There are no hadith narrations in this passage.**'
    parsed1 = parse_anchor_response(raw_trailing)
    assert len(parsed1.spans) == 0
    assert parsed1.unknown_collections == 0
    assert parsed1.dropped_spans == 0

    # 2. Unknown collection_hint: 'tabari' is kept as 'other' and counted
    raw_tabari = (
        '{"spans": [{'
        '"start_anchor": "قال ابن جرير: حدثنا فلان", '
        '"end_anchor": "عن مجاهد في الجنة", '
        '"cue": "قال ابن جرير: حدثنا", '
        '"collection_hint": "tabari", '
        '"number_hint": null, '
        '"kind": "marfu"'
        '}]}'
    )
    parsed2 = parse_anchor_response(raw_tabari)
    assert len(parsed2.spans) == 1
    assert parsed2.spans[0].collection_hint == "other"
    assert parsed2.unknown_collections == 1
    assert parsed2.dropped_spans == 0

    # 3. Unescaped quote inside string -> raises GlmResponseError; retry with escaped quote succeeds
    raw_unescaped = '{"spans": [{"start_anchor": "قال "رسول" الله", "end_anchor": "في الجنة", "kind": "marfu"}]}'
    with pytest.raises(GlmResponseError):
        parse_anchor_response(raw_unescaped)

    raw_escaped = '{"spans": [{"start_anchor": "قال \\"رسول\\" الله", "end_anchor": "في الجنة", "kind": "marfu"}]}'
    parsed3 = parse_anchor_response(raw_escaped)
    assert len(parsed3.spans) == 1
    assert parsed3.spans[0].start_anchor == 'قال "رسول" الله'


def test_mocked_client_three_failures_raises_not_empty():
    """Mocked client failing 3 times raises GlmExtractionError and does not return empty list (T4.5b)."""
    with patch("requests.post") as mock_post:
        mock_post.side_effect = Exception("Ollama server timeout")
        with pytest.raises(GlmExtractionError) as exc_info:
            extract_hadith_anchors("نص تجريبي للحديث الشريف")

        assert "Failed to extract hadith anchors after 3 attempts" in str(exc_info.value)
        assert mock_post.call_count == 3


def test_outside_window_rejection():
    """Anchor located outside window [window_start, window_end] is rejected with reason outside_window (T4.5b)."""
    text = (
        "قال رسول الله ﷺ: من صام رمضان إيمانا واحتسابا غفر له ما تقدم من ذنبه. "
        "وهذا خاتمة الكلام."
    )
    # The hadith starts at offset 0 and ends around offset 69
    anchor = HadithSpanAnchor(
        start_anchor="قال رسول الله",
        end_anchor="من ذنبه",
        kind="marfu",
    )

    # Window given is [0, 50). Anchor starts at 0, but ends at ~69 > 50 (locate has no upper limit).
    rejected = []
    res = locate_and_check_anchors(
        text,
        [anchor],
        window_start=0,
        window_end=50,
        segment_id="test:seg:1",
        rejected=rejected,
    )
    assert len(res) == 0
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "outside_window"
    assert rejected[0]["start"] == 0
    assert rejected[0]["end"] > 50


def test_resume_skips_ok_and_retries_failed(tmp_path):
    """Resume logic skips 'ok' keys and retries 'failed' keys (T4.5b)."""
    raw_file = tmp_path / "hadith-raw.jsonl"
    lines = [
        {"key": "seg1#0-100", "status": "ok"},
        {"key": "seg2#0-200", "status": "failed"},
        {"key": "seg3#0-150", "status": "failed"},
        {"key": "seg3#0-150", "status": "ok"},  # retried and succeeded
    ]
    with open(raw_file, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")

    status = load_raw_status(raw_file)
    assert status["seg1#0-100"] == "ok"
    assert status["seg2#0-200"] == "failed"
    assert status["seg3#0-150"] == "ok"  # latest status is ok


def test_half_written_last_line_ignored(tmp_path):
    """Corrupted or half-written trailing line in raw JSONL is safely ignored (T4.5b)."""
    raw_file = tmp_path / "hadith-raw.jsonl"
    with open(raw_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"key": "seg1#0-100", "status": "ok"}) + "\n")
        f.write('{"key": "seg2#0-200", "status": "ok", "raw_text": "half-w')  # truncated

    status = load_raw_status(raw_file)
    assert "seg1#0-100" in status
    assert "seg2#0-200" not in status


def test_stop_rule_at_over_twenty_percent():
    """Stopping rule triggers when > 20% of the last 200 windows failed (T4.5b)."""
    # 200 windows with 41 failures = 20.5% -> stops
    history_41 = [True] * 159 + [False] * 41
    assert should_stop_for_failures(history_41, min_evaluated=200) is True

    # 200 windows with 40 failures = 20.0% -> does not stop
    history_40 = [True] * 160 + [False] * 40
    assert should_stop_for_failures(history_40, min_evaluated=200) is False

    # Fewer than min_evaluated windows -> does not stop yet
    history_short = [False] * 50
    assert should_stop_for_failures(history_short, min_evaluated=200) is False


def test_build_merges_identical_spans_and_rejects_partial_overlaps():
    """Build step merges identical spans and keeps longer span in partial overlaps (T4.5b)."""
    candidates = [
        # Span 1: [100, 250) (length 150)
        {
            "segment_id": "seg1",
            "span_id": "seg1#100-250",
            "start": 100,
            "end": 250,
            "kind": "marfu",
            "fallback_used": False,
        },
        # Span 2: [100, 250) identical offsets -> merged, no duplicate
        {
            "segment_id": "seg1",
            "span_id": "seg1#100-250",
            "start": 100,
            "end": 250,
            "kind": "marfu",
            "fallback_used": False,
        },
        # Span 3: [120, 200) (length 80) partial overlap with Span 1 -> rejected with reason 'overlap'
        {
            "segment_id": "seg1",
            "span_id": "seg1#120-200",
            "start": 120,
            "end": 200,
            "kind": "athar",
            "fallback_used": False,
        },
        # Span 4: [300, 450) non-overlapping -> kept
        {
            "segment_id": "seg1",
            "span_id": "seg1#300-450",
            "start": 300,
            "end": 450,
            "kind": "marfu",
            "fallback_used": True,
        },
    ]

    kept, rejected = resolve_overlapping_spans(candidates)
    assert len(kept) == 2
    assert kept[0]["span_id"] == "seg1#100-250"
    assert kept[1]["span_id"] == "seg1#300-450"

    assert len(rejected) == 1
    assert rejected[0]["span_id"] == "seg1#120-200"
    assert rejected[0]["reason"] == "overlap"
    assert rejected[0]["overlapped_by"] == "seg1#100-250"


def test_neo4j_write_hadith_spans_stores_kind(neo4j_driver):
    """Span writer stores 'kind' on HADITH spans and delete_spans_by_type cleans up (T4.5b Step 8)."""
    test_hadith = {
        "span_id": "test:seg:hadith#500-600",
        "segment_id": "ibn-kathir:1:1-1:1",
        "start": 500,
        "end": 600,
        "type": "HADITH",
        "kind": "marfu",
        "cue": "قال رسول الله",
        "source": "test:pilot",
        "method": "glm",
        "confidence": 0.9,
    }

    try:
        write_spans([test_hadith], driver=neo4j_driver)

        with neo4j_driver.session() as session:
            rec = session.run(
                """
                MATCH (s:Span {span_id: 'test:seg:hadith#500-600'})
                RETURN s.type AS type, s.kind AS kind, s.cue AS cue
                """
            ).single()
            assert rec is not None
            assert rec["type"] == "HADITH"
            assert rec["kind"] == "marfu"
            assert rec["cue"] == "قال رسول الله"

        # Test idempotence
        write_spans([test_hadith], driver=neo4j_driver)
        with neo4j_driver.session() as session:
            count = session.run(
                "MATCH (s:Span {span_id: 'test:seg:hadith#500-600'}) RETURN count(s) AS cnt"
            ).single()["cnt"]
            assert count == 1

        # Test deletion
        deleted = delete_spans_by_type("HADITH", driver=neo4j_driver)
        assert deleted >= 1
        with neo4j_driver.session() as session:
            count_after = session.run(
                "MATCH (s:Span {span_id: 'test:seg:hadith#500-600'}) RETURN count(s) AS cnt"
            ).single()["cnt"]
            assert count_after == 0
    finally:
        delete_spans_by_type("HADITH", driver=neo4j_driver)
