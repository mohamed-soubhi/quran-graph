"""Phase 4 gold set (T4.3): offsets match the tafsir text and the annotation rules hold."""

import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "data" / "gold" / "phase4.jsonl"
SEGMENTS = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
AYAT = ROOT / "data" / "interim" / "quran" / "ayat.jsonl"


@pytest.fixture(scope="module")
def gold():
    return [json.loads(line) for line in GOLD.open(encoding="utf-8")]


@pytest.fixture(scope="module")
def segments():
    if not SEGMENTS.exists():
        pytest.skip("segments.jsonl absent; run 'python scripts/tasks.py parse' first.")
    return {r["segment_id"]: r for r in map(json.loads, SEGMENTS.open(encoding="utf-8"))}


def test_counts(gold):
    assert len(gold) == 50
    assert all(w["reviewed_by"] and w["reviewed"] for w in gold)
    types = Counter(sp["type"] for w in gold for sp in w["spans"])
    assert types == {"QURAN": 83, "FOOTNOTE": 68, "HADITH": 24, "OTHER": 4}
    kinds = Counter(sp["kind"] for w in gold for sp in w["spans"] if sp["type"] == "HADITH")
    assert set(kinds) == {"marfu", "athar"}


def test_offsets_match_segment_text(gold, segments):
    for w in gold:
        text = segments[w["segment_id"]]["text"]
        assert text[w["window_start"]:w["window_end"]] == w["window_text"], w["window_id"]
        for sp in w["spans"]:
            assert w["window_start"] <= sp["start"] < sp["end"] <= w["window_end"], sp["span_id"]
            assert sp["span_id"] == f"{w['segment_id']}#{sp['start']}-{sp['end']}"
            body = text[sp["start"]:sp["end"]]
            assert body == body.strip(), sp["span_id"]
            if sp["type"] == "FOOTNOTE":
                assert body.startswith("[[") and body.endswith("]]"), sp["span_id"]
            if sp["type"] == "QURAN" and body.startswith("﴿"):
                assert body.endswith("﴾"), sp["span_id"]


def test_nesting(gold):
    for w in gold:
        by_id = {sp["span_id"]: sp for sp in w["spans"]}
        spans = sorted(w["spans"], key=lambda s: (s["start"], -s["end"]))
        for i, a in enumerate(spans):
            for b in spans[i + 1:]:
                assert not (b["start"] < a["end"] < b["end"]), f"partial overlap {a['span_id']} / {b['span_id']}"
            if a["parent"]:
                p = by_id[a["parent"]]
                assert p["start"] <= a["start"] and a["end"] <= p["end"], a["span_id"]


def test_quran_links(gold):
    if not AYAT.exists():
        pytest.skip("ayat.jsonl absent")
    ayat = {json.loads(line)["ayah_id"] for line in AYAT.open(encoding="utf-8")}
    for w in gold:
        for sp in w["spans"]:
            if sp["type"] == "QURAN":
                assert sp["links"], sp["span_id"]
                for link in sp["links"]:
                    assert link["ayah_id"] in ayat
                    assert link["rel"] == ("EXPLAINS" if link["ayah_id"] in w["covers"] else "CITES")


def test_t05_fixture(gold):
    w01 = next(w for w in gold if w["window_id"] == "W01")
    hadith = [(sp["start"], sp["end"]) for sp in w01["spans"] if sp["type"] == "HADITH"]
    assert hadith == [(141, 657), (658, 790)]


def test_review_decisions(gold):
    w = {x["window_id"]: x for x in gold}
    assert not any(sp["type"] == "HADITH" for sp in w["W44"]["spans"])  # dream report = COMMENTARY
    assert "ibn-kathir:1:6-6:1#2975-3486" in {sp["span_id"] for sp in w["W13"]["spans"]}  # takhrij line merged
    assert "ibn-kathir:4:95-96:1#7142-7621" in {sp["span_id"] for sp in w["W15"]["spans"]}  # whole Abu Dawud hadith
