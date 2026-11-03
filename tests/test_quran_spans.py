"""Tests for QURAN spans and ayah links in Neo4j (T4.4, Gate 4a).

Verifies:
- parse_ref on the 3 reference shapes and the stray-digit shape
- Quote with inner footnote in 2:255 links to 2:255 (EXPLAINS)
- 56:47 matches via the loose key
- Exactly 26,686 QURAN spans extracted into data/interim/spans/quran.jsonl
- Every span starts with ﴿ and ends with ﴾
- Footnote overlap invariant: no partial overlaps; footnotes inside are fully enclosed
- Gate test: precision >= 0.98 on gold set (Phase 4a)
- Neo4j writing: exactly 26,686 Span {type: 'QURAN'} nodes, all link edges carry provenance
- Idempotence: a second write changes no count
"""

import json
from pathlib import Path
import pytest
from neo4j.exceptions import ServiceUnavailable

from scripts.eval_4a import run_eval
from src.extract.footnotes import DEFAULT_OUTPUT_PATH as FOOTNOTES_PATH
from src.extract.quran_spans import (
    DEFAULT_OUTPUT_PATH,
    DEFAULT_SEGMENTS_PATH,
    extract_quran_spans,
    find_quotes,
    match_quote,
    parse_ref,
)
from src.graph.client import get_driver
from src.graph.spans import load_spans_file

ROOT = Path(__file__).resolve().parent.parent


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
def quran_spans_jsonl() -> Path:
    """Ensure quran.jsonl is extracted once for the test module."""
    if not DEFAULT_SEGMENTS_PATH.exists():
        pytest.skip("segments.jsonl absent; skipping quran spans tests.")
    if not DEFAULT_OUTPUT_PATH.exists():
        extract_quran_spans()
    return DEFAULT_OUTPUT_PATH


def test_parse_ref_shapes():
    """parse_ref handles single ayah, comma list, range, and stray digit in surah name."""
    # Shape 1: single ayah «[الرُّومِ: ٢٥]»
    ref1 = parse_ref(" [الرُّومِ: ٢٥] ")
    assert ref1 is not None
    assert ref1["ref_text"] == "[الرُّومِ: ٢٥]"
    assert ref1["ayat"] == ["30:25"]

    # Shape 2: comma list «[الصافات: ٢٢، ٢٣]»
    ref2 = parse_ref(" [الصَّافَّاتِ: ٢٢، ٢٣] .")
    assert ref2 is not None
    assert ref2["ref_text"] == "[الصَّافَّاتِ: ٢٢، ٢٣]"
    assert ref2["ayat"] == ["37:22", "37:23"]

    # Shape 3: range «[النساء: ٨٢-٨٣]»
    ref3 = parse_ref(" [النِّسَاءِ: ٨٢-٨٣] ")
    assert ref3 is not None
    assert ref3["ref_text"] == "[النِّسَاءِ: ٨٢-٨٣]"
    assert ref3["ayat"] == ["4:82", "4:83"]

    # Stray digit shape: «[٠الْفُرْقَانِ: ٧٢]»
    ref4 = parse_ref(" [٠الْفُرْقَانِ: ٧٢] .")
    assert ref4 is not None
    assert ref4["ref_text"] == "[٠الْفُرْقَانِ: ٧٢]"
    assert ref4["ayat"] == ["25:72"]


def test_quote_with_inner_footnote_links_explains():
    """Quote with inner [[...]] footnote links to 2:255 (EXPLAINS)."""
    quote = "﴿اللَّهُ لَا إِلَهَ إِلا هُوَ [[في أ: هو الحي القيوم.]] الْحَيُّ الْقَيُّومُ﴾"
    covers = ["2:255"]
    ayat_ids, method, conf = match_quote(quote, covers)
    assert ayat_ids == ["2:255"]
    assert method == "ngram"
    assert conf == 1.0


def test_loose_key_matching_56_47():
    """56:47 matches via the loose key (Ibn Kathir 'أئنا' vs Tanzil 'أإنا')."""
    # Quote from 56:47 in Ibn Kathir
    quote = "﴿وَكَانُوا يَقُولُونَ أَئِذَا مِتْنَا وَكُنَّا تُرَابًا وَعِظَامًا أَئِنَّا لَمَبْعُوثُونَ﴾"
    covers = ["56:41", "56:42", "56:43", "56:44", "56:45", "56:46", "56:47"]
    ayat_ids, method, conf = match_quote(quote, covers)
    assert ayat_ids == ["56:47"]
    assert method == "ngram"
    assert conf in (0.9, 1.0)


def test_extracted_quran_spans_facts(quran_spans_jsonl):
    """Verify exactly 26,686 QURAN spans, bracket markers, and footnote enclosing invariant."""
    with DEFAULT_SEGMENTS_PATH.open("r", encoding="utf-8") as f:
        segments = {s["segment_id"]: s["text"] for s in (json.loads(line) for line in f)}

    with quran_spans_jsonl.open("r", encoding="utf-8") as f:
        spans = [json.loads(line) for line in f]

    # Exactly 26,686 spans
    assert len(spans) == 26686

    # Load footnotes to check overlap invariant
    with FOOTNOTES_PATH.open("r", encoding="utf-8") as f:
        footnotes_by_seg: dict[str, list[tuple[int, int]]] = {}
        for line in f:
            fn = json.loads(line)
            footnotes_by_seg.setdefault(fn["segment_id"], []).append((fn["start"], fn["end"]))

    inside_footnotes = 0
    for span in spans:
        seg_id = span["segment_id"]
        start = span["start"]
        end = span["end"]
        span_id = span["span_id"]

        assert span_id == f"{seg_id}#{start}-{end}"
        assert span["type"] == "QURAN"
        assert span["parent"] is None
        assert span["method"] == "regex"
        assert span["confidence"] == 1.0
        assert span["source"].startswith("run:")

        seg_text = segments[seg_id]
        quote_text = seg_text[start:end]

        # Every span text starts with ﴿ and ends with ﴾
        assert quote_text.startswith("﴿")
        assert quote_text.endswith("﴾")

        # Footnote overlap invariant: no partial overlaps
        for fn_start, fn_end in footnotes_by_seg.get(seg_id, []):
            if not (end <= fn_start or fn_end <= start):
                # Must be fully inside quote
                assert start <= fn_start and fn_end <= end, (
                    f"Partial footnote overlap in {seg_id}: quote [{start}, {end}], fn [{fn_start}, {fn_end}]"
                )
                inside_footnotes += 1

    # Exactly 635 footnotes enclosed inside Quran quotes
    assert inside_footnotes == 635


def test_gate_precision_gold():
    """Gate 4a: precision >= 0.98 on the gold set data/gold/phase4.jsonl."""
    eval_res = run_eval()
    assert eval_res["precision"] >= 0.98
    assert eval_res["recall_bracketed"] >= 0.98
    assert len(eval_res["disagreements"]) == 0
    assert eval_res["gold_bracketed"] == 79
    assert eval_res["gold_unbracketed"] == 4


def test_neo4j_write_quran_spans_and_idempotence(neo4j_driver, quran_spans_jsonl):
    """Writing Quran spans loads exactly 26,686 Span {type: 'QURAN'} nodes and link edges.

    Every link edge has source, method, confidence.
    A second write changes no count (idempotence).
    """
    # 1. First write
    res1 = load_spans_file(quran_spans_jsonl, driver=neo4j_driver)
    assert res1["spans"] == 26686

    with neo4j_driver.session() as session:
        span_count = session.run(
            "MATCH (s:Span {type: 'QURAN'}) RETURN count(s) AS cnt"
        ).single()["cnt"]
        assert span_count == 26686

        # Check provenance on all EXPLAINS and CITES edges
        missing_provenance = session.run(
            """
            MATCH ()-[r:EXPLAINS|CITES]->()
            WHERE r.source IS NULL OR r.method IS NULL OR r.confidence IS NULL
            RETURN count(r) AS cnt
            """
        ).single()["cnt"]
        assert missing_provenance == 0

        # Check link counts in Neo4j
        explains_in_db = session.run(
            "MATCH (:Span {type: 'QURAN'})-[r:EXPLAINS]->(:Ayah) RETURN count(r) AS cnt"
        ).single()["cnt"]
        cites_in_db = session.run(
            "MATCH (:Span {type: 'QURAN'})-[r:CITES]->(:Ayah) RETURN count(r) AS cnt"
        ).single()["cnt"]
        assert explains_in_db == 20717
        assert cites_in_db == 8847

        # 2. Second write must change no count
        res2 = load_spans_file(quran_spans_jsonl, driver=neo4j_driver)
        assert res2["spans"] == 26686

        span_count_after = session.run(
            "MATCH (s:Span {type: 'QURAN'}) RETURN count(s) AS cnt"
        ).single()["cnt"]
        assert span_count_after == 26686

        explains_after = session.run(
            "MATCH (:Span {type: 'QURAN'})-[r:EXPLAINS]->(:Ayah) RETURN count(r) AS cnt"
        ).single()["cnt"]
        cites_after = session.run(
            "MATCH (:Span {type: 'QURAN'})-[r:CITES]->(:Ayah) RETURN count(r) AS cnt"
        ).single()["cnt"]
        assert explains_after == explains_in_db
        assert cites_after == cites_in_db
