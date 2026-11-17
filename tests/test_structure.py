"""Tests for Phase 4c structure extraction and loader (T4.6).

Tests:
- Verse rule: W09-style line with trailing footnote -> trimmed;
  150-char prose line with ' ... ' -> not a verse;
  two verse lines with \n\n -> one poem;
  a verse inside a footnote -> skipped.
- Parent = smallest container: footnote in quote in hadith -> parent is the quote.
- Partial overlap -> error.
- COMMENTARY fills gaps exactly, blank true for " .\n\n";
  segment with no spans -> one span.
- Gate 4c on a tiny fixture passes and fails on a 1-char hole.
- Neo4j loader test: operates ONLY on span_ids starting with 'test:'.
"""

import os
from pathlib import Path
import pytest

from src.extract.poetry import (
    extract_poetry_from_text,
    is_verse_line,
)
from src.extract.structure import (
    build_commentary,
    build_parents,
    check_partial_overlaps,
    find_parent_for_span,
)
from scripts.gate_4c import evaluate_gate_4c


def test_is_verse_line_trailing_footnote():
    """W09-style line with trailing footnote should be detected as a verse line."""
    line = (
        "وَمَنْ كَانَ ذَا مَالٍ وَيَبْخَلْ بِمَالِهِ ... عَلَى قَوْمِهِ يُسْتَغْنَ عَنْهُ وَيُذْمَمِ "
        "[[البيت في ديوانه (ص٣٠) .]]"
    )
    assert is_verse_line(line) is True


def test_is_verse_line_long_prose():
    """A 150-char prose line with ' ... ' is not a verse line."""
    long_prose = "هذا نص نثري طويل يحتوي على كلام كثير وتوضيح للمسألة الفقهية وبيان لما ذكره أهل العلم ... وفيه تفصيل مفيد ومهم جدا يتجاوز مائة حرف بكثير لبيان الحكم الشرعي المستفاد من الآية الكريمة"
    assert len(long_prose) > 100
    assert " ... " in long_prose
    assert is_verse_line(long_prose) is False


def test_two_verse_lines_one_poem():
    """Two verse lines separated only by whitespace form one poem with lines=2."""
    v1 = "يَا رَاحِلِينَ إِلَى البَيت الْعَتِيقِ لَقَدْ ... سرْتُم جُسُوما وسرْنا نحنُ أَرْوَاحَا ..."
    v2 = "إنَّا أقَمنا عَلَى عُذْرٍ وعَنْ قَدَرٍ ... ومَنْ أقامَ على عذْرٍ فقد راحا ..."
    text = f"مقدمة:\n\n{v1}\n\n{v2}\n\nخاتمة"

    poems = extract_poetry_from_text(text, segment_id="test:1")
    assert len(poems) == 1
    p = poems[0]
    assert p["lines"] == 2
    assert p["start"] == text.index(v1)
    assert p["end"] == text.index(v2) + len(v2)
    assert p["type"] == "OTHER"


def test_verse_inside_footnote_skipped():
    """A verse line lying inside a FOOTNOTE span is skipped (never becomes a span)."""
    verse = "لَا يَجْبر النَّاسُ عَظمًا أَنْتَ كاسرُه ... وَلَا يَهِيضُون عَظمًا أَنْتَ جَابِره"
    # The entire verse line is inside [[...]]
    text = f"نص عادي [[هذا هامش كبير وفيه بيت شعر:\n\n{verse}\n\nانتهى الهامش]] وباقي النص."
    fn_start = text.index("[[")
    fn_end = text.index("]]") + 2
    fn_spans = [(fn_start, fn_end)]

    poems = extract_poetry_from_text(text, segment_id="test:2", fn_spans=fn_spans)
    assert len(poems) == 0


def test_trailing_footnote_trimmed():
    """A trailing footnote at the end of a poem is trimmed backwards."""
    v = "مَتَى مَا يَشَأ ذُو الوُدِّ يصْرِمْ خَليله ... ويَعْبَدُ عَلَيه لَا مِحَالَة ظَالمًا"
    fn = "[[البيت في تفسير الطبري (٢٥/٦٠) .]]"
    text = f"{v} {fn}\n\nكلام بعده"
    fn_start = text.index(fn)
    fn_end = fn_start + len(fn)
    fn_spans = [(fn_start, fn_end)]

    poems = extract_poetry_from_text(text, segment_id="test:3", fn_spans=fn_spans)
    assert len(poems) == 1
    assert poems[0]["end"] == len(v)
    assert text[poems[0]["start"]:poems[0]["end"]] == v


def test_parent_smallest_container():
    """Parent = smallest container: footnote in quote in hadith -> parent is the quote."""
    hadith = {
        "span_id": "test:seg#0-100",
        "segment_id": "test:seg",
        "start": 0,
        "end": 100,
        "type": "HADITH",
    }
    quote = {
        "span_id": "test:seg#20-80",
        "segment_id": "test:seg",
        "start": 20,
        "end": 80,
        "type": "QURAN",
    }
    footnote = {
        "span_id": "test:seg#30-50",
        "segment_id": "test:seg",
        "start": 30,
        "end": 50,
        "type": "FOOTNOTE",
    }

    candidates = [hadith, quote]
    p = find_parent_for_span(footnote, candidates)
    assert p is not None
    assert p["span_id"] == "test:seg#20-80"
    assert p["type"] == "QURAN"


def test_partial_overlap_raises():
    """Partial overlap between spans raises ValueError."""
    s1 = {"span_id": "test:seg#10-30", "start": 10, "end": 30}
    s2 = {"span_id": "test:seg#20-40", "start": 20, "end": 40}

    with pytest.raises(ValueError, match="Partial overlap detected"):
        check_partial_overlaps([s1, s2])


def test_commentary_fills_gaps_and_blank():
    """COMMENTARY fills gaps exactly; blank is True for whitespace/punctuation only."""
    text = "بداية الكلام ﴿قُلْ هُوَ اللَّهُ أَحَدٌ﴾ .\n\n خاتمة النص."
    quote_text = "﴿قُلْ هُوَ اللَّهُ أَحَدٌ﴾"
    q_start = text.index(quote_text)
    q_end = q_start + len(quote_text)

    quran_span = {
        "span_id": f"test:seg#{q_start}-{q_end}",
        "segment_id": "test:seg",
        "start": q_start,
        "end": q_end,
        "type": "QURAN",
    }
    segments = [{"segment_id": "test:seg", "text": text}]
    spans_by_seg = {"test:seg": [quran_span]}

    comm = build_commentary(
        segments=segments,
        spans_by_segment=spans_by_seg,
        nested_span_ids=set(),
        output_path=Path(".scratch/test_comm.jsonl"),
    )

    # Two commentary spans: prefix [0:q_start] and suffix [q_end:len(text)]
    assert len(comm) == 2
    c1, c2 = comm[0], comm[1]
    assert c1["start"] == 0 and c1["end"] == q_start
    assert c1["blank"] is False  # contains letters
    assert c2["start"] == q_end and c2["end"] == len(text)
    assert c2["blank"] is False

    # Now test a gap that has only " .\n\n"
    mid_gap = " .\n\n"
    text_with_blank_gap = f"{quote_text}{mid_gap}{quote_text}"
    q1_span = {"span_id": f"test:seg#0-{len(quote_text)}", "segment_id": "test:seg", "start": 0, "end": len(quote_text), "type": "QURAN"}
    q2_start = len(quote_text) + len(mid_gap)
    q2_span = {"span_id": f"test:seg#{q2_start}-{len(text_with_blank_gap)}", "segment_id": "test:seg", "start": q2_start, "end": len(text_with_blank_gap), "type": "QURAN"}

    comm2 = build_commentary(
        segments=[{"segment_id": "test:seg", "text": text_with_blank_gap}],
        spans_by_segment={"test:seg": [q1_span, q2_span]},
        nested_span_ids=set(),
        output_path=Path(".scratch/test_comm2.jsonl"),
    )
    assert len(comm2) == 1
    assert comm2[0]["start"] == len(quote_text)
    assert comm2[0]["end"] == q2_start
    assert comm2[0]["blank"] is True


def test_segment_with_no_spans_becomes_one_commentary():
    """A segment with no typed spans becomes exactly one COMMENTARY span covering all text."""
    text = "نص كامل بدون أي اقتباس قرآني أو حديثي أو هامش"
    segments = [{"segment_id": "test:seg_empty", "text": text}]
    comm = build_commentary(
        segments=segments,
        spans_by_segment={"test:seg_empty": []},
        nested_span_ids=set(),
        output_path=Path(".scratch/test_comm3.jsonl"),
    )
    assert len(comm) == 1
    assert comm[0]["start"] == 0
    assert comm[0]["end"] == len(text)
    assert comm[0]["type"] == "COMMENTARY"
    assert comm[0]["blank"] is False


def test_gate_tiny_fixture_passes_and_fails_on_hole():
    """Gate 4c logic passes on a clean fixture and fails if a 1-char hole is introduced."""
    text = "كلمة أولى ﴿آية﴾ كلمة ثانية"
    seg = {"segment_id": "test:gate_seg", "text": text}
    q_start = text.index("﴿آية﴾")
    q_end = q_start + len("﴿آية﴾")
    q_span = {"span_id": f"test:gate_seg#{q_start}-{q_end}", "segment_id": "test:gate_seg", "start": q_start, "end": q_end, "type": "QURAN"}

    c1 = {"span_id": f"test:gate_seg#0-{q_start}", "segment_id": "test:gate_seg", "start": 0, "end": q_start, "type": "COMMENTARY", "blank": False}
    c2 = {"span_id": f"test:gate_seg#{q_end}-{len(text)}", "segment_id": "test:gate_seg", "start": q_end, "end": len(text), "type": "COMMENTARY", "blank": False}

    # Pass case
    passed = evaluate_gate_4c(
        segments=[seg],
        spans_by_segment={"test:gate_seg": [q_span]},
        parents=[],
        commentary=[c1, c2],
        expected_total_chars=len(text),
        check_gold=False,
    )
    assert passed is True

    # With hole, evaluate_gate_4c must fail
    c1_hole = {"span_id": f"test:gate_seg#0-{q_start - 1}", "segment_id": "test:gate_seg", "start": 0, "end": q_start - 1, "type": "COMMENTARY", "blank": False}
    failed = evaluate_gate_4c(
        segments=[seg],
        spans_by_segment={"test:gate_seg": [q_span]},
        parents=[],
        commentary=[c1_hole, c2],
        expected_total_chars=len(text),
        check_gold=False,
    )
    assert failed is False


def test_neo4j_structure_writer_test_spans_only():
    """Test write_spans and write_inside_edges on Neo4j using ONLY 'test:' span_ids."""
    from src.graph.client import get_driver
    from src.graph.spans import write_inside_edges, write_spans

    driver = get_driver()
    # Check connection
    try:
        with driver.session() as sess:
            sess.run("RETURN 1").consume()
    except Exception:
        pytest.skip("Neo4j not reachable")

    test_seg_id = "test:seg_neo4j"
    test_p_id = "test:span_parent"
    test_c_id = "test:span_child"

    # Setup test nodes
    with driver.session() as sess:
        sess.run("MERGE (s:TafsirSegment {segment_id: $id})", id=test_seg_id).consume()

    try:
        parent_span = {
            "span_id": test_p_id,
            "segment_id": test_seg_id,
            "start": 0,
            "end": 50,
            "type": "OTHER",
            "lines": 2,
            "source": "test:src",
            "method": "regex",
            "confidence": 1.0,
        }
        child_span = {
            "span_id": test_c_id,
            "segment_id": test_seg_id,
            "start": 10,
            "end": 30,
            "type": "COMMENTARY",
            "blank": True,
            "source": "test:src",
            "method": "regex",
            "confidence": 1.0,
        }

        # Write spans
        res = write_spans([parent_span, child_span], driver=driver)
        assert res["spans"] == 2

        # Write inside edge
        inside_row = {
            "span_id": test_c_id,
            "parent": test_p_id,
            "source": "test:inside",
            "method": "regex",
            "confidence": 1.0,
        }
        inside_cnt = write_inside_edges([inside_row], driver=driver)
        assert inside_cnt == 1

        # Verify properties in DB
        with driver.session() as sess:
            p_node = sess.run("MATCH (s:Span {span_id: $id}) RETURN s.lines AS lines, s.type AS type", id=test_p_id).single()
            assert p_node["lines"] == 2
            assert p_node["type"] == "OTHER"

            c_node = sess.run("MATCH (s:Span {span_id: $id}) RETURN s.blank AS blank, s.type AS type", id=test_c_id).single()
            assert c_node["blank"] is True
            assert c_node["type"] == "COMMENTARY"

            edge = sess.run("MATCH (c:Span {span_id: $cid})-[r:INSIDE]->(p:Span {span_id: $pid}) RETURN r.source AS src", cid=test_c_id, pid=test_p_id).single()
            assert edge["src"] == "test:inside"

    finally:
        # STRICT SAFETY: Delete ONLY spans starting with 'test:'
        with driver.session() as sess:
            sess.run("MATCH (s:Span) WHERE s.span_id STARTS WITH 'test:' DETACH DELETE s").consume()
            sess.run("MATCH (s:TafsirSegment {segment_id: $id}) DETACH DELETE s", id=test_seg_id).consume()
        driver.close()
