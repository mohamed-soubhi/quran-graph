"""Tests for footnote hadith reference parsing, owner resolution, linking and Neo4j loader (T5.2).

Validates:
- Every form in the Facts table, multi-number references, «ماجة»/«ماجه», Kubra != nasai, «للبخاري» negative.
- Owner rule for inside, inside through QURAN parent, after with punctuation, and word between.
- Muslim 2865 resolves to all 2865.* entries including muslim:7207.
- Build totals matching step 2 counts pinned as exact numbers.
- Idempotent writer on test fixture only ('test:' and 'test-coll:*'), skipped if Neo4j unreachable.
"""

from collections import Counter
import json
import os
from pathlib import Path
import pytest
from neo4j.exceptions import ServiceUnavailable

from src.extract.hadith_refs import (
    Ref,
    parse_refs,
    owner,
    resolve,
    compute_4gram_sim,
    COLLECTIONS_ORDER,
)
from src.graph.client import get_driver
from src.graph.hadith_links import write_cites

ROOT = Path(__file__).resolve().parent.parent
LINKS_FILE = ROOT / "data" / "interim" / "links" / "footnote_links.jsonl"
UNLINKED_FILE = ROOT / "data" / "interim" / "links" / "footnote_refs_unlinked.jsonl"
HADITH_FILE = ROOT / "data" / "interim" / "hadith" / "hadith.jsonl"


# ---------------------------------------------------------------------------
# 1. Parsing tests
# ---------------------------------------------------------------------------

def test_parse_facts_table_forms():
    """Verify parse_refs extracts correct collection and number for all Facts table forms."""
    cases = [
        ("صحيح مسلم برقم (١)", "muslim", "1"),
        ("صحيح البخاري برقم (٢)", "bukhari", "2"),
        ("سنن الترمذي برقم (٣)", "tirmidhi", "3"),
        ("سنن أبي داود برقم (٤)", "abudawud", "4"),
        ("سنن ابن ماجة برقم (٥)", "ibnmajah", "5"),
        ("سنن ابن ماجه برقم (٦)", "ibnmajah", "6"),
        ("سنن النسائي الكبرى برقم (٧)", "nasai_kubra", "7"),
        ("النسائي في السنن الكبرى برقم (٨)", "nasai_kubra", "8"),
        ("رواه البخاري في صحيحه برقم (٩)", "bukhari", "9"),
        ("رواه مسلم في صحيحه برقم (١٠)", "muslim", "10"),
        ("أبو داود في السنن برقم (١١)", "abudawud", "11"),
        ("رواه الترمذي في السنن برقم (١٢)", "tirmidhi", "12"),
        ("ابن ماجة في السنن برقم (١٣)", "ibnmajah", "13"),
        ("الترمذي في السنن برقم (١٤)", "tirmidhi", "14"),
    ]
    for text, exp_col, exp_num in cases:
        refs = parse_refs(f"[[{text}]]")
        assert len(refs) == 1, f"Failed for {text}: got {refs}"
        assert refs[0].collection == exp_col, f"Wrong collection for {text}: {refs[0]}"
        assert refs[0].number == exp_num, f"Wrong number for {text}: {refs[0]}"


def test_parse_multi_number_forms():
    """Verify parsing multiple numbers in one reference."""
    # Form 1: وبرقم (…)
    text1 = "[[صحيح البخاري برقم (٤٠٤٣) وبرقم (٣٩٨٦)]]"
    refs1 = parse_refs(text1)
    assert len(refs1) == 2
    assert [r.number for r in refs1] == ["4043", "3986"]
    assert all(r.collection == "bukhari" for r in refs1)

    # Form 2: برقم (٦٩، ٧٠)
    text2 = "[[صحيح مسلم برقم (٦٩، ٧٠)]]"
    refs2 = parse_refs(text2)
    assert len(refs2) == 2
    assert [r.number for r in refs2] == ["69", "70"]
    assert all(r.collection == "muslim" for r in refs2)


def test_parse_kubra_never_nasai():
    """Kubra must be classified as nasai_kubra, never plain nasai."""
    refs = parse_refs("[[سنن النسائي الكبرى برقم (٨٠١٣)]]")
    assert len(refs) == 1
    assert refs[0].collection == "nasai_kubra"
    assert refs[0].collection != "nasai"


def test_parse_negative_prefix():
    """A name that is part of a longer word like «للبخاري» gives no ref."""
    refs = parse_refs("[[للبخاري برقم (١)]]")
    assert refs == []


# ---------------------------------------------------------------------------
# 2. Owner rule tests
# ---------------------------------------------------------------------------

def test_owner_inside_direct():
    """Footnote directly inside HADITH span belongs to that HADITH span."""
    parent_map = {"fn1": ("h_span_1", "HADITH")}
    fn = {"span_id": "fn1", "segment_id": "seg1", "start": 100, "end": 150}
    assert owner(fn, parent_map, {}, {}) == "h_span_1"


def test_owner_inside_through_quran_parent():
    """Footnote inside QURAN quote inside HADITH span resolves to HADITH span."""
    parent_map = {
        "fn1": ("q_span_1", "QURAN"),
        "q_span_1": ("h_span_1", "HADITH"),
    }
    fn = {"span_id": "fn1", "segment_id": "seg1", "start": 120, "end": 140}
    assert owner(fn, parent_map, {}, {}) == "h_span_1"


def test_owner_after_with_punctuation():
    """Footnote right after HADITH span with only punctuation/whitespace belongs to it."""
    hadiths = [{"span_id": "h_span_1", "start": 0, "end": 50}]
    hadith_by_seg = {"seg1": hadiths}
    between = " .،:؛\"»)\n "
    seg_text = "x" * 50 + between + "[[note]]"
    segments = {"seg1": seg_text}
    fn_start = 50 + len(between)
    fn = {"span_id": "fn1", "segment_id": "seg1", "start": fn_start, "end": fn_start + 8}
    assert owner(fn, {}, hadith_by_seg, segments) == "h_span_1"


def test_owner_after_with_word_between_gives_none():
    """Footnote separated from HADITH span by a word gives None."""
    hadiths = [{"span_id": "h_span_1", "start": 0, "end": 50}]
    hadith_by_seg = {"seg1": hadiths}
    segments = {"seg1": "x" * 50 + " وقال رحمه الله " + "[[note]]"}
    fn = {"span_id": "fn1", "segment_id": "seg1", "start": 67, "end": 75}
    assert owner(fn, {}, hadith_by_seg, segments) is None


# ---------------------------------------------------------------------------
# 3. Muslim 2865 resolution test
# ---------------------------------------------------------------------------

def test_muslim_2865_resolves_all_narrations():
    """Muslim 2865 resolves to all 2865.* entries including muslim:7207."""
    hadith_ids = set()
    muslim_arabic: dict[str, list[str]] = {}

    with open(HADITH_FILE, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            hid = rec["hadith_id"]
            hadith_ids.add(hid)
            if rec["collection"] == "muslim":
                an = rec.get("arabic_number")
                if an:
                    base = an.split(".")[0]
                    muslim_arabic.setdefault(base, []).append(hid)

    ref = Ref(collection="muslim", number="2865", ref_text="صحيح مسلم برقم (٢٨٦٥)")
    hits, reason = resolve(ref, hadith_ids, muslim_arabic)
    assert reason is None
    assert len(hits) == 4
    assert "muslim:7207" in hits
    assert set(hits) == {"muslim:7207", "muslim:7208", "muslim:7209", "muslim:7210"}


# ---------------------------------------------------------------------------
# 4. Pinned build totals test
# ---------------------------------------------------------------------------

def test_build_totals_pinned():
    """Verify build output files match exact counts from Step 2 / tasks.py links."""
    assert LINKS_FILE.exists(), f"Missing {LINKS_FILE}. Run 'python scripts/tasks.py links' first."
    assert UNLINKED_FILE.exists(), f"Missing {UNLINKED_FILE}. Run 'python scripts/tasks.py links' first."

    links = []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                links.append(json.loads(line))

    unlinked = []
    with open(UNLINKED_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                unlinked.append(json.loads(line))

    # Total distinct links and unlinked
    assert len(links) == 7307
    assert len(unlinked) == 1370

    # Distinct spans and hadiths
    distinct_spans = {r["span_id"] for r in links}
    distinct_hadiths = {r["hadith_id"] for r in links}
    assert len(distinct_spans) == 2889
    assert len(distinct_hadiths) == 5165

    # Pairs by collection
    pairs_by_col = Counter(r["hadith_id"].split(":")[0] for r in links)
    assert pairs_by_col["muslim"] == 4136
    assert pairs_by_col["bukhari"] == 1407
    assert pairs_by_col["tirmidhi"] == 695
    assert pairs_by_col["abudawud"] == 590
    assert pairs_by_col["ibnmajah"] == 479

    # Unlinked breakdown
    reasons = Counter(r["reason"] for r in unlinked)
    assert reasons["not_in_sources"] == 409  # Kubra attached
    assert reasons["not_found"] == 45        # our collections attached but not found
    assert reasons["unattached"] == 916      # 882 our collections + 34 Kubra unattached

    # Verify every link has required fields and valid provenance
    for r in links:
        assert r["method"] == "regex"
        assert r["outcome"] == "auto"
        assert r["confidence"] == 0.95
        assert r["source"].startswith("run:") and "footnote-links" in r["source"]
        assert isinstance(r["evidence"], list) and len(r["evidence"]) >= 1
        assert isinstance(r["ref_text"], list) and len(r["ref_text"]) >= 1
        assert r["number_kind"] in ("hadithnumber", "arabicnumber")
        assert isinstance(r["text_sim"], float) and 0.0 <= r["text_sim"] <= 1.0


# ---------------------------------------------------------------------------
# 5. Neo4j writer fixture test (test: and test-coll:*)
# ---------------------------------------------------------------------------

@pytest.fixture
def driver():
    """Yield a connected Neo4j driver, skipping only if unreachable."""
    try:
        drv = get_driver()
    except (ServiceUnavailable, OSError) as exc:
        if os.getenv("SMOKE_STRICT") == "1":
            pytest.fail(f"Neo4j is unreachable: {exc}")
        pytest.skip(f"Neo4j is unreachable: {exc}")
    yield drv
    drv.close()


def test_write_cites_fixture(driver, tmp_path):
    """Test write_cites on fixture nodes starting with test: and test-coll:*.
    
    Verifies:
    - Rejection of missing / empty files
    - Rejection when referenced nodes do not exist
    - Writing CITES edges with all required properties
    - Idempotency on repeated write (count unchanged)
    - Full cleanup of fixture nodes and edges
    """
    test_span_id = "test:hadith_span:1"
    test_hadith_id = "test-coll:999"

    # Setup fixture in Neo4j
    with driver.session() as session:
        session.run(
            "MERGE (s:Span {span_id: $sid}) SET s.type = 'HADITH'",
            sid=test_span_id,
        ).consume()
        session.run(
            "MERGE (h:Hadith {hadith_id: $hid}) SET h.collection = 'test-coll', h.number = '999'",
            hid=test_hadith_id,
        ).consume()

    try:
        # 1. Reject missing file
        with pytest.raises(FileNotFoundError):
            write_cites(driver, tmp_path / "non_existent.jsonl")

        # 2. Reject empty file
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="empty"):
            write_cites(driver, empty_file)

        # 3. Reject non-existent node
        invalid_file = tmp_path / "invalid.jsonl"
        invalid_row = {
            "span_id": "test:span_does_not_exist",
            "hadith_id": test_hadith_id,
            "evidence": ["test:fn:1"],
            "ref_text": ["test ref"],
            "number_kind": "hadithnumber",
            "outcome": "auto",
            "method": "regex",
            "confidence": 0.95,
            "source": "run:20261117-0000-footnote-links",
            "text_sim": 0.75,
        }
        invalid_file.write_text(json.dumps(invalid_row) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="do not exist in Neo4j"):
            write_cites(driver, invalid_file)

        # 4. Valid write
        valid_file = tmp_path / "fixture_links.jsonl"
        valid_row = {
            "span_id": test_span_id,
            "hadith_id": test_hadith_id,
            "evidence": ["test:fn:1"],
            "ref_text": ["صحيح البخاري برقم (٩٩٩)"],
            "number_kind": "hadithnumber",
            "outcome": "auto",
            "method": "regex",
            "confidence": 0.95,
            "source": "run:20261117-0000-footnote-links",
            "text_sim": 0.85,
        }
        valid_file.write_text(json.dumps(valid_row) + "\n", encoding="utf-8")

        count1 = write_cites(driver, valid_file)
        assert count1 == 1

        # Check edge properties in Neo4j
        with driver.session() as session:
            record = session.run(
                """
                MATCH (s:Span {span_id: $sid})-[r:CITES]->(h:Hadith {hadith_id: $hid})
                RETURN r
                """,
                sid=test_span_id,
                hid=test_hadith_id,
            ).single()
            assert record is not None
            r = record["r"]
            assert r["evidence"] == ["test:fn:1"]
            assert r["ref_text"] == ["صحيح البخاري برقم (٩٩٩)"]
            assert r["number_kind"] == "hadithnumber"
            assert r["outcome"] == "auto"
            assert r["method"] == "regex"
            assert r["confidence"] == 0.95
            assert r["source"] == "run:20261117-0000-footnote-links"
            assert r["text_sim"] == 0.85

        # 5. Idempotent reload: second write produces identical count
        count2 = write_cites(driver, valid_file)
        assert count2 == 1

        with driver.session() as session:
            edge_count = session.run(
                "MATCH (s:Span {span_id: $sid})-[r:CITES]->(h:Hadith {hadith_id: $hid}) RETURN count(r) AS c",
                sid=test_span_id,
                hid=test_hadith_id,
            ).single()["c"]
            assert edge_count == 1

    finally:
        # Cleanup fixture only
        with driver.session() as session:
            session.run("MATCH (s:Span {span_id: $sid}) DETACH DELETE s", sid=test_span_id).consume()
            session.run("MATCH (h:Hadith {hadith_id: $hid}) DETACH DELETE h", hid=test_hadith_id).consume()
