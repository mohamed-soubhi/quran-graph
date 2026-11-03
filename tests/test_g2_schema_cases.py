"""G2 gate: the schema checked against 3 real cases (fixture built by scripts/build_g2_fixture.py).

1. A verse explaining a verse (2:255 quotes 30:25, 19:93-95; Quran quotes nested in a hadith).
2. One hadith cited in several passages (Muslim 2865 = muslim:7207 in 30:30-32, 4:116-122, 17:15).
3. An isnad with several narrators (Musnad Ahmad, Ubayy ibn Ka'b, in 2:255).

Nodes are loaded with an extra :Fixture label and deleted afterwards. The Neo4j part skips once real data with the
same IDs exists (after Phase 3), so it never touches real nodes.
"""

import json
import os
import unicodedata
from pathlib import Path

import pytest
from neo4j.exceptions import ServiceUnavailable

from src.extract.normalize import normalize_with_map
from src.graph.apply_schema import apply_schema
from src.graph.client import get_driver

ROOT = Path(__file__).resolve().parent.parent
CASES = json.loads((ROOT / "tests" / "fixtures" / "g2" / "cases.json").read_text(encoding="utf-8"))
RAW = ROOT / "data" / "raw"
SOURCE = "fixture:g2"
OPEN, CLOSE = "﴿", "﴾"


def _need_raw():
    if not (RAW / "tafsir" / "ibn-kathir" / "2" / "255.json").exists():
        pytest.skip("Raw data absent")


def _tafsir(segment_id: str) -> str:
    _, surah, rng, _ = segment_id.split(":")
    first = rng.split("-")[0]
    path = RAW / "tafsir" / "ibn-kathir" / surah / f"{first}.json"
    return json.loads(path.read_text(encoding="utf-8"))["text"]


def _bare(s: str) -> str:
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _tanzil() -> dict[str, str]:
    """Tanzil Uthmani text per ayah, with the basmala prefix removed from ayah 1 except in 1:1 (schema Q1)."""
    ayat = {}
    for line in (RAW / "tanzil" / "quran-uthmani.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split("|")
        if len(parts) == 3 and parts[0].isdigit():
            ayat[f"{parts[0]}:{parts[1]}"] = parts[2]
    basmala = [_bare(w) for w in ayat["1:1"].split()]
    for key, text in ayat.items():
        surah, ayah = key.split(":")
        words = text.split()
        if ayah == "1" and surah not in ("1", "9") and [_bare(w) for w in words[:4]] == basmala:
            ayat[key] = " ".join(words[4:])
    return ayat


# ---------------------------------------------------------------- offsets (no Neo4j needed)

def test_span_offsets_match_raw_text():
    """Every span starts with its recorded text; QURAN spans keep both brackets, FOOTNOTE spans keep [[ ]]."""
    _need_raw()
    for s in CASES["spans"]:
        text = _tafsir(s["segment_id"])
        piece = text[s["start"]:s["end"]]
        assert piece.startswith(s["begins_with"]), s["span_id"]
        assert s["span_id"] == f"{s['segment_id']}#{s['start']}-{s['end']}"
        if s["type"] == "QURAN":
            assert piece[0] == OPEN and piece[-1] == CLOSE, s["span_id"]
        if s["type"] == "FOOTNOTE":
            assert piece.startswith("[[") and piece.endswith("]]"), s["span_id"]


def test_span_nesting_rules():
    """Nested spans lie inside their parent; spans with the same parent never overlap."""
    by_id = {s["span_id"]: s for s in CASES["spans"]}
    groups: dict[tuple, list] = {}
    for s in CASES["spans"]:
        if s["parent"]:
            p = by_id[s["parent"]]
            assert p["start"] <= s["start"] and s["end"] <= p["end"], s["span_id"]
        groups.setdefault((s["segment_id"], s["parent"]), []).append((s["start"], s["end"]))
    for ranges in groups.values():
        ranges.sort()
        for (_, end), (start, _) in zip(ranges, ranges[1:]):
            assert end <= start


def test_q1_basmala_removed_except_fatiha():
    """Schema Q1: 112 ayah-1 lines lose the Tanzil basmala; 1:1 keeps it (it is the ayah)."""
    _need_raw()
    ayat = _tanzil()
    raw = {}
    for line in (RAW / "tanzil" / "quran-uthmani.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split("|")
        if len(parts) == 3 and parts[0].isdigit():
            raw[f"{parts[0]}:{parts[1]}"] = parts[2]
    changed = [k for k in ayat if ayat[k] != raw[k]]
    assert len(changed) == 112
    assert "1:1" not in changed and "9:1" not in changed
    assert normalize_with_map(ayat["112:1"])[0].split() == ["قل", "هو", "الله", "احد"]


# ---------------------------------------------------------------- Neo4j load + trace queries

@pytest.fixture(scope="module")
def graph():
    _need_raw()
    try:
        driver = get_driver()
    except (ServiceUnavailable, OSError) as exc:
        if os.getenv("SMOKE_STRICT") == "1":
            pytest.fail(f"Neo4j is unreachable: {exc}")
        pytest.skip(f"Neo4j is unreachable: {exc}")
    apply_schema(driver)
    with driver.session() as session:
        real = session.run(
            "MATCH (n) WHERE NOT n:Fixture AND (n:Ayah OR n:TafsirSegment OR n:Hadith) RETURN count(n) AS n"
        ).single()["n"]
        if real:
            driver.close()
            pytest.skip("Real data is loaded; G2 fixture would share its IDs")
        session.run("MATCH (n:Fixture) DETACH DELETE n").consume()
        _load(session)
    yield driver
    with driver.session() as session:
        session.run("MATCH (n:Fixture) DETACH DELETE n").consume()
    driver.close()


def _load(session) -> None:
    prov = {"source": SOURCE, "method": "dataset", "confidence": 1.0}
    ayat = _tanzil()
    wanted = {link["target"] for link in CASES["links"] if not link["target"].startswith("muslim:")}
    for seg in CASES["segments"]:
        wanted |= {f"{seg['surah']}:{a}" for a in range(seg["first_ayah"], seg["last_ayah"] + 1)}
    for ayah_id in sorted(wanted):
        session.run(
            "CREATE (:Ayah:Fixture {ayah_id: $id, surah_id: $s, number: $n, text: $t})",
            id=ayah_id, s=int(ayah_id.split(":")[0]), n=int(ayah_id.split(":")[1]), t=ayat[ayah_id],
        ).consume()

    session.run(
        "CREATE (m:Mufassir:Fixture {mufassir_id: 'ibn-kathir', name: 'إسماعيل بن عمر بن كثير', death_hijri: 774})"
        "-[:WROTE $p]->(:TafsirBook:Fixture {book_id: 'ibn-kathir', title: 'تفسير القرآن العظيم'})", p=prov,
    ).consume()
    for seg in CASES["segments"]:
        session.run(
            "MATCH (b:TafsirBook:Fixture {book_id: 'ibn-kathir'}) "
            "CREATE (b)-[:HAS_SEGMENT $p]->(g:TafsirSegment:Fixture {segment_id: $id, book_id: 'ibn-kathir', "
            "surah_id: $s, first_ayah: $f, last_ayah: $l, n: 1, text: $t}) "
            "WITH g UNWIND range($f, $l) AS a "
            "MATCH (y:Ayah:Fixture {ayah_id: toString($s) + ':' + toString(a)}) CREATE (g)-[:COVERS $p]->(y)",
            id=seg["segment_id"], s=seg["surah"], f=seg["first_ayah"], l=seg["last_ayah"],
            t=_tafsir(seg["segment_id"]), p=prov,
        ).consume()

    hadiths = json.loads((RAW / "hadith" / "fawazahmed0" / "ara-muslim.json").read_text(encoding="utf-8"))["hadiths"]
    h = next(x for x in hadiths if x["hadithnumber"] == 7207)
    session.run(
        "CREATE (b:HadithBook:Fixture {collection: 'muslim', edition: 'ara-muslim'}) "
        "CREATE (h:Hadith:Fixture {hadith_id: 'muslim:7207', collection: 'muslim', number: '7207', "
        "arabic_number: $an, book_number: $bn, number_in_book: $nb, text: $t})-[:IN_BOOK $p]->(b)",
        an=str(h["arabicnumber"]), bn=h["reference"]["book"], nb=h["reference"]["hadith"], t=h["text"], p=prov,
    ).consume()

    for s in CASES["spans"]:
        props = {k: s[k] for k in ("span_id", "segment_id", "start", "end", "type")}
        props.update({k: s.get(k) for k in ("collection_hint", "number_hint") if k in s})
        session.run(
            "MATCH (g:TafsirSegment:Fixture {segment_id: $seg}) "
            "CREATE (g)-[:HAS_SPAN $p]->(x:Span:Fixture) SET x = $props",
            seg=s["segment_id"], props=props, p=prov,
        ).consume()
    for s in CASES["spans"]:
        if s["parent"]:
            session.run(
                "MATCH (c:Span:Fixture {span_id: $c}), (p:Span:Fixture {span_id: $p}) CREATE (c)-[:INSIDE $prov]->(p)",
                c=s["span_id"], p=s["parent"], prov=prov,
            ).consume()

    for link in CASES["links"]:
        label = "Hadith" if link["target"].startswith("muslim:") else "Ayah"
        key = "hadith_id" if label == "Hadith" else "ayah_id"
        props = {"source": SOURCE, "method": link["method"], "confidence": 1.0}
        props.update({k: link[k] for k in ("evidence", "ref_text") if k in link})
        session.run(
            f"MATCH (s:Span:Fixture {{span_id: $s}}), (t:{label}:Fixture {{{key}: $t}}) "
            f"CREATE (s)-[r:{link['rel']}]->(t) SET r = $props",
            s=link["span_id"], t=link["target"], props=props,
        ).consume()

    isnad = CASES["isnad"]
    for n in isnad["narrators"]:
        session.run(
            "MATCH (s:Span:Fixture {span_id: $span}) "
            "CREATE (s)-[:IN_CHAIN {position: $pos, mention_start: $ms, mention_end: $me, "
            "source: $src, method: 'human', confidence: 1.0}]->(:Narrator:Fixture {narrator_id: $id, name: $name})",
            span=isnad["span_id"], pos=n["position"], ms=n["mention"][0], me=n["mention"][1],
            src=SOURCE, id=n["narrator_id"], name=n["name"],
        ).consume()
    for a, b in zip(isnad["narrators"], isnad["narrators"][1:]):
        session.run(
            "MATCH (x:Narrator:Fixture {narrator_id: $a}), (y:Narrator:Fixture {narrator_id: $b}) "
            "CREATE (x)-[:HEARD_FROM {chain_id: $chain, source: $src, method: 'human', confidence: 1.0}]->(y)",
            a=a["narrator_id"], b=b["narrator_id"], chain=isnad["span_id"], src=SOURCE,
        ).consume()


def test_case1_verse_explaining_verse(graph):
    with graph.session() as session:
        cited = session.run(
            "MATCH (:Ayah {ayah_id: '2:255'})<-[:COVERS]-(:TafsirSegment)-[:HAS_SPAN]->(q:Span {type: 'QURAN'})"
            "-[r:CITES]->(b:Ayah) RETURN b.ayah_id AS id, r.ref_text AS ref"
        ).data()
        assert {r["id"] for r in cited} == {"30:25", "19:93", "19:94", "19:95", "112:1", "109:1", "99:1", "110:1"}
        assert {r["ref"] for r in cited if r["id"] == "30:25"} == {"[الرُّومِ:٢٥]"}
        # the quoted text is read from the segment, not stored twice
        quote = session.run(
            "MATCH (g:TafsirSegment)-[:HAS_SPAN]->(q:Span)-[:CITES]->(:Ayah {ayah_id: '30:25'}) "
            "RETURN substring(g.text, q.start, q.end - q.start) AS t"
        ).single()["t"]
        assert _bare(quote) == OPEN + "ومن آياته أن تقوم السماء والأرض بأمره" + CLOSE
        explains = session.run(
            "MATCH (q:Span {type: 'QURAN'})-[:EXPLAINS]->(:Ayah {ayah_id: '2:255'}) RETURN count(q) AS n"
        ).single()["n"]
        assert explains == 2
        nested = session.run(
            "MATCH (q:Span {type: 'QURAN'})-[:INSIDE]->(h:Span {type: 'HADITH'}) RETURN count(q) AS n"
        ).single()["n"]
        assert nested == 5
        deep = session.run(
            "MATCH (:Span {type: 'FOOTNOTE'})-[:INSIDE]->(:Span {type: 'QURAN'})-[:INSIDE]->(:Span {type: 'HADITH'}) "
            "RETURN count(*) AS n"
        ).single()["n"]
        assert deep == 2


def test_case2_one_hadith_in_several_passages(graph):
    with graph.session() as session:
        rows = session.run(
            "MATCH (h:Hadith {hadith_id: 'muslim:7207'})<-[r:CITES]-(s:Span {type: 'HADITH'})<-[:HAS_SPAN]-(g) "
            "MATCH (g)-[:HAS_SPAN]->(f:Span {span_id: r.evidence}) "
            "RETURN g.segment_id AS seg, h.arabic_number AS an, substring(g.text, f.start, f.end - f.start) AS fn"
        ).data()
        assert sorted(r["seg"] for r in rows) == [
            "ibn-kathir:17:15-15:1", "ibn-kathir:30:30-32:1", "ibn-kathir:4:116-122:1"]
        assert all(r["an"] == "2865.01" and "٢٨٦٥" in r["fn"] for r in rows)
        ayat = session.run(
            "MATCH (:Hadith {hadith_id: 'muslim:7207'})<-[:CITES]-(:Span)<-[:HAS_SPAN]-(:TafsirSegment)"
            "-[:COVERS]->(a:Ayah) RETURN count(DISTINCT a) AS n"
        ).single()["n"]
        assert ayat == 3 + 7 + 1  # 30:30-32, 4:116-122, 17:15
        graded = session.run("MATCH (:Hadith {hadith_id: 'muslim:7207'})-[g:GRADED]->() RETURN count(g) AS n")
        assert graded.single()["n"] == 0  # Sahih Muslim has no grades in the source: none are invented


def test_case3_isnad_with_several_narrators(graph):
    with graph.session() as session:
        chain = session.run(
            "MATCH (s:Span {type: 'HADITH'})-[c:IN_CHAIN]->(n:Narrator) "
            "WHERE s.span_id ENDS WITH '#141-657' RETURN n.name AS name ORDER BY c.position"
        ).value()
        assert chain == ["عبد الرزاق", "سفيان", "سعيد الجريري", "أبو السليل", "عبد الله بن رباح", "أبي بن كعب"]
        hops = session.run(
            "MATCH p = (:Narrator {narrator_id: 'fixture:1'})-[:HEARD_FROM*]->(:Narrator {narrator_id: 'fixture:6'}) "
            "RETURN length(p) AS n"
        ).single()["n"]
        assert hops == 5
        linked = session.run(
            "MATCH (s:Span) WHERE s.span_id ENDS WITH '#141-657' OPTIONAL MATCH (s)-[r:CITES]->() RETURN count(r) AS n"
        ).single()["n"]
        assert linked == 0  # Musnad Ahmad is not in our sources: "not found", never guessed
