"""Tests for FOOTNOTE spans and Neo4j span writer (T4.2).

Verifies:
- Exactly 31,203 footnote spans extracted
- Every span text starts with '[[' and ends with ']]'
- No two footnote spans overlap in any segment
- G2 fixture footnote 'ibn-kathir:2:255-255:1#5030-5057' exists
- 110 multiline notes, longest note is 7,075 chars in 'ibn-kathir:33:41-44:1'
- Rerun extraction produces byte-identical output
- Neo4j has exactly 31,203 Span {type: 'FOOTNOTE'} and 31,203 HAS_SPAN edges
- A second write changes no count (idempotence)
- Reusable span writer creates INSIDE edges with provenance when parent is set
"""

import hashlib
import json
from pathlib import Path
import pytest
from neo4j.exceptions import ServiceUnavailable

from src.extract.footnotes import (
    DEFAULT_OUTPUT_PATH,
    DEFAULT_SEGMENTS_PATH,
    extract_footnotes,
    find_footnotes,
)
from src.graph.client import get_driver
from src.graph.spans import load_spans_file, write_spans

ROOT = Path(__file__).resolve().parent.parent


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope="module")
def neo4j_driver():
    """Provide a Neo4j driver if reachable, otherwise skip."""
    try:
        driver = get_driver()
    except (ServiceUnavailable, Exception) as exc:
        pytest.skip(f"Neo4j not reachable: {exc}")

    yield driver
    driver.close()


@pytest.fixture(scope="module")
def footnotes_jsonl() -> Path:
    """Ensure footnotes.jsonl is extracted once for the test module."""
    if not DEFAULT_SEGMENTS_PATH.exists():
        pytest.skip("segments.jsonl absent; skipping footnote tests.")
    return extract_footnotes()


def test_find_footnotes_unit():
    """Unit test find_footnotes regex behavior, multiline DOTALL, and boundaries."""
    text = "Intro [[note 1]] middle [[note 2\nwith newline]] end"
    notes = find_footnotes(text)
    assert len(notes) == 2
    assert text[notes[0][0] : notes[0][1]] == "[[note 1]]"
    assert text[notes[1][0] : notes[1][1]] == "[[note 2\nwith newline]]"
    assert find_footnotes("no notes here") == []
    assert find_footnotes("") == []


def test_extracted_footnotes_counts_and_properties(footnotes_jsonl):
    """Verify exactly 31,203 footnote spans, text markers, no overlaps, and facts."""
    with DEFAULT_SEGMENTS_PATH.open("r", encoding="utf-8") as f:
        segments = {s["segment_id"]: s["text"] for s in (json.loads(line) for line in f)}

    with footnotes_jsonl.open("r", encoding="utf-8") as f:
        spans = [json.loads(line) for line in f]

    # Exactly 31,203 footnote spans
    assert len(spans) == 31203

    spans_by_segment: dict[str, list[dict]] = {}
    multiline_count = 0
    longest_note_len = 0
    longest_note_segment = ""
    g2_found = False

    for span in spans:
        seg_id = span["segment_id"]
        start = span["start"]
        end = span["end"]
        span_id = span["span_id"]

        assert span_id == f"{seg_id}#{start}-{end}"
        assert span["type"] == "FOOTNOTE"
        assert span["parent"] is None
        assert span["method"] == "regex"
        assert span["confidence"] == 1.0
        assert span["source"].startswith("run:")

        seg_text = segments[seg_id]
        note_text = seg_text[start:end]

        # Every span text starts with [[ and ends with ]]
        assert note_text.startswith("[[")
        assert note_text.endswith("]]")

        if "\n" in note_text:
            multiline_count += 1

        note_len = end - start
        if note_len > longest_note_len:
            longest_note_len = note_len
            longest_note_segment = seg_id

        if span_id == "ibn-kathir:2:255-255:1#5030-5057":
            g2_found = True

        spans_by_segment.setdefault(seg_id, []).append(span)

    # Measured facts verification
    assert len(spans_by_segment) == 1857
    assert multiline_count == 110
    assert longest_note_len == 7075
    assert longest_note_segment == "ibn-kathir:33:41-44:1"
    assert g2_found, "G2 footnote ibn-kathir:2:255-255:1#5030-5057 not found"

    # No two overlap within any segment
    for seg_id, seg_spans in spans_by_segment.items():
        # Already ordered by start
        for prev_span, next_span in zip(seg_spans, seg_spans[1:]):
            assert prev_span["end"] <= next_span["start"], (
                f"Overlap in {seg_id}: {prev_span['span_id']} and {next_span['span_id']}"
            )


def test_byte_identical_rerun(tmp_path):
    """Extraction rerun produces byte-identical footnotes.jsonl."""
    out2 = tmp_path / "footnotes.jsonl"
    extract_footnotes(output_path=out2)
    assert _sha256(DEFAULT_OUTPUT_PATH) == _sha256(out2)


def test_neo4j_write_spans_and_idempotence(neo4j_driver, footnotes_jsonl):
    """Writing footnote spans loads exactly 31,203 Span nodes and HAS_SPAN edges.

    A second write changes no count.
    """
    # 1. First write (or ensure loaded)
    res1 = load_spans_file(footnotes_jsonl, driver=neo4j_driver)
    assert res1["spans"] == 31203
    assert res1["has_span"] == 31203

    with neo4j_driver.session() as session:
        span_count = session.run(
            "MATCH (s:Span {type: 'FOOTNOTE'}) RETURN count(s) AS cnt"
        ).single()["cnt"]
        assert span_count == 31203

        has_span_count = session.run(
            "MATCH (:TafsirSegment)-[r:HAS_SPAN]->(s:Span {type: 'FOOTNOTE'}) RETURN count(r) AS cnt"
        ).single()["cnt"]
        assert has_span_count == 31203

        # Verify G2 footnote in Neo4j
        g2_res = session.run(
            """
            MATCH (seg:TafsirSegment {segment_id: 'ibn-kathir:2:255-255:1'})-[r:HAS_SPAN]->(s:Span {span_id: 'ibn-kathir:2:255-255:1#5030-5057'})
            RETURN s.start AS start, s.end AS end, s.type AS type, r.source AS source, r.method AS method, r.confidence AS confidence
            """
        ).single()
        assert g2_res is not None
        assert g2_res["start"] == 5030
        assert g2_res["end"] == 5057
        assert g2_res["type"] == "FOOTNOTE"
        assert g2_res["method"] == "regex"
        assert g2_res["confidence"] == 1.0

        # 2. Second write must change no count
        res2 = load_spans_file(footnotes_jsonl, driver=neo4j_driver)
        assert res2["spans"] == 31203

        span_count_after = session.run(
            "MATCH (s:Span {type: 'FOOTNOTE'}) RETURN count(s) AS cnt"
        ).single()["cnt"]
        assert span_count_after == 31203

        has_span_count_after = session.run(
            "MATCH (:TafsirSegment)-[r:HAS_SPAN]->(s:Span {type: 'FOOTNOTE'}) RETURN count(r) AS cnt"
        ).single()["cnt"]
        assert has_span_count_after == 31203


def test_write_spans_with_inside_parent(neo4j_driver):
    """Span writer creates INSIDE relationships with provenance when parent is set (reusable for 4a-4c)."""
    # Use synthetic nested test spans attached to segment 1:1-1:1
    parent_span = {
        "span_id": "test:seg:1#100-200",
        "segment_id": "ibn-kathir:1:1-1:1",
        "start": 100,
        "end": 200,
        "type": "OTHER",
        "parent": None,
        "source": "test:parent",
        "method": "regex",
        "confidence": 1.0,
    }
    child_span = {
        "span_id": "test:seg:1#120-150",
        "segment_id": "ibn-kathir:1:1-1:1",
        "start": 120,
        "end": 150,
        "type": "FOOTNOTE",
        "parent": "test:seg:1#100-200",
        "source": "test:child",
        "method": "regex",
        "confidence": 1.0,
    }

    try:
        write_spans([parent_span, child_span], driver=neo4j_driver)

        with neo4j_driver.session() as session:
            inside_res = session.run(
                """
                MATCH (c:Span {span_id: 'test:seg:1#120-150'})-[r:INSIDE]->(p:Span {span_id: 'test:seg:1#100-200'})
                RETURN r.source AS source, r.method AS method, r.confidence AS confidence
                """
            ).single()
            assert inside_res is not None
            assert inside_res["source"] == "test:child"
            assert inside_res["method"] == "regex"
            assert inside_res["confidence"] == 1.0

            # Test idempotence on INSIDE
            write_spans([parent_span, child_span], driver=neo4j_driver)
            inside_count = session.run(
                """
                MATCH (c:Span {span_id: 'test:seg:1#120-150'})-[r:INSIDE]->(p:Span {span_id: 'test:seg:1#100-200'})
                RETURN count(r) AS cnt
                """
            ).single()["cnt"]
            assert inside_count == 1
    finally:
        # Clean up test nodes and relationships
        with neo4j_driver.session() as session:
            session.run(
                "MATCH (s:Span) WHERE s.span_id IN ['test:seg:1#100-200', 'test:seg:1#120-150'] DETACH DELETE s"
            ).consume()
