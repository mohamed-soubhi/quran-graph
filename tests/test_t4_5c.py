"""Unit tests for T4.5c (no network).

Covers:
- Prompt version stored in raw records (PROMPT_VERSION = "1.3")
- Selection skips a window whose cue is only inside a footnote that started before the window
- --keys-file restricts the windows in runner
- With two raw files, the later ok answer wins and prompt_version is recorded on kept spans
- Kind rule:
  - «ورواه النسائي من حديث حماد به» after a marfu span -> marfu (with kind_glm and kind_rule)
  - A line with «حدثنا» -> unchanged
  - Gap >= 300 -> unchanged
  - Over 400 characters -> unchanged
  - A chain of two takhrij lines -> both follow the hadith
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.run_hadith_book import run_build, run_extraction
from scripts.select_recheck_windows import extract_window_outside_footnotes, select_recheck_keys
from src.extract.glm_client import PROMPT_VERSION, ANCHOR_SYSTEM_PROMPT


def test_prompt_version_is_1_3():
    """Verify PROMPT_VERSION is bumped to 1.3 and system prompt contains updated rules."""
    assert PROMPT_VERSION == "1.3"
    assert "Reports of Companions and Successors (athar) are HADITH spans" in ANCHOR_SYSTEM_PROMPT
    assert "even when the hadith it refers to is not in this window" in ANCHOR_SYSTEM_PROMPT
    assert "a name + «عن» + a name with no transmission verb and no takhrij" in ANCHOR_SYSTEM_PROMPT


def test_selection_skips_window_crossing_footnote():
    """Selection skips a window whose cue is inside a footnote that started before the window."""
    # Segment text: normal text, then footnote starts at index 20 and ends at index 100
    # Footnote contains «رواه الترمذي»
    # Window spans [30, 90), so the window starts inside the footnote and does not see '[['
    seg_text = "كلام عادي في التفسير [[وهذا الحديث رواه الترمذي وقال حسن صحيح وهو مخرج]] ثم كلام عادي بعد الحاشية"
    fn_start = seg_text.index("[[")
    fn_end = seg_text.index("]]") + 2
    fn_spans = [(fn_start, fn_end)]

    # Window starts inside the footnote
    w_start = fn_start + 10
    w_end = fn_end - 5
    assert w_start < w_end
    # The raw window text contains the cue
    assert "رواه" in seg_text[w_start:w_end]

    # But extract_window_outside_footnotes strips all footnote characters using segment positions
    clean = extract_window_outside_footnotes(seg_text, w_start, w_end, fn_spans)
    assert clean == ""
    assert "رواه" not in clean


def test_keys_file_restricts_windows(tmp_path):
    """--keys-file restricts the windows processed by run_extraction."""
    keys_file = tmp_path / "recheck-keys.txt"
    keys_file.write_text("segA#100-200\nsegB#300-400\n", encoding="utf-8")

    # Mock collect_book_windows to return 4 windows
    mock_windows = [
        ("segA#100-200", "segA", 100, 200),
        ("segA#500-600", "segA", 500, 600),
        ("segB#300-400", "segB", 300, 400),
        ("segC#100-200", "segC", 100, 200),
    ]

    raw_path = tmp_path / "raw.jsonl"
    with patch("scripts.run_hadith_book.collect_book_windows", return_value=mock_windows), \
         patch("scripts.run_hadith_book.load_raw_status", return_value={}):
        # Mock call_glm_for_window
        with patch("scripts.run_hadith_book.call_glm_for_window", return_value=('{"spans": []}', None, 1.0, 1)):
            # Mock open segments
            mock_segments = tmp_path / "segments.jsonl"
            with open(mock_segments, "w", encoding="utf-8") as f:
                f.write(json.dumps({"segment_id": "segA", "text": " " * 1000}) + "\n")
                f.write(json.dumps({"segment_id": "segB", "text": " " * 1000}) + "\n")

            run_extraction(
                keys_file=keys_file,
                raw_path=raw_path,
                segments_path=mock_segments,
                limit=10,
            )

    # Only the 2 keys in keys_file should be written to raw.jsonl
    with open(raw_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    written_keys = {r["key"] for r in records}
    assert written_keys == {"segA#100-200", "segB#300-400"}
    for r in records:
        assert r["prompt_version"] == "1.3"


def test_two_raw_files_later_ok_answer_wins(tmp_path):
    """When building with two raw files, the later file's latest ok answer wins."""
    seg_id = "test:1:1"
    # Create segment text containing hadith
    hadith_text = "حدثنا سفيان عن منصور قال قال رسول الله ص لا تكذبوا علي ورواه النسائي من حديث حماد به"
    seg_text = hadith_text + " " * 200
    segments_path = tmp_path / "segments.jsonl"
    with open(segments_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"segment_id": seg_id, "text": seg_text}) + "\n")

    key = f"{seg_id}#0-{len(hadith_text)}"

    # File 1 (Pass 1): ok, 0 spans, prompt 1.2
    raw1 = tmp_path / "raw1.jsonl"
    with open(raw1, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "key": key,
            "segment_id": seg_id,
            "window_start": 0,
            "window_end": len(hadith_text),
            "status": "ok",
            "raw_text": '{"spans": []}',
            "prompt_version": "1.2",
        }) + "\n")

    # File 2 (Pass 2): ok, 1 span, prompt 1.3
    raw2 = tmp_path / "raw2.jsonl"
    with open(raw2, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "key": key,
            "segment_id": seg_id,
            "window_start": 0,
            "window_end": len(hadith_text),
            "status": "ok",
            "raw_text": json.dumps({
                "spans": [
                    {
                        "start_anchor": "حدثنا سفيان عن منصور",
                        "end_anchor": "لا تكذبوا علي",
                        "cue": "حدثنا سفيان",
                        "collection_hint": "other",
                        "number_hint": None,
                        "kind": "marfu",
                    }
                ]
            }),
            "prompt_version": "1.3",
        }) + "\n")

    out_spans = tmp_path / "out_spans.jsonl"
    out_rejected = tmp_path / "out_rejected.jsonl"

    stats = run_build(
        raw_path=[raw1, raw2],
        out_path=out_spans,
        rejected_path=out_rejected,
        segments_path=segments_path,
    )

    assert stats["total_spans"] == 1
    assert stats["spans_by_prompt_version"] == {"1.3": 1}

    with open(out_spans, "r", encoding="utf-8") as f:
        kept = [json.loads(line) for line in f]
    assert len(kept) == 1
    assert kept[0]["prompt_version"] == "1.3"
    assert kept[0]["kind"] == "marfu"


def test_kind_rule_cases(tmp_path):
    """Test all 5 kind rule cases:
    1. «ورواه النسائي من حديث حماد به» after a marfu span -> marfu (with kind_glm, kind_rule)
    2. A line with «حدثنا» -> unchanged
    3. Gap >= 300 -> unchanged
    4. Over 400 characters -> unchanged
    5. A chain of two takhrij lines -> both follow the hadith
    """
    seg_id = "test:kind:1"
    # Construct distinct texts so locate finds each at its exact offset
    p1 = "قال الإمام أحمد: حدثنا وكيع قال قال رسول الله صلى الله عليه وسلم اتقوا النار ولو بشق تمرة."
    takhrij_good = "ورواه النسائي من حديث حماد به."
    takhrij_hadathana = "ورواه أبو داود حدثنا مسدد به."
    takhrij_gap = "ورواه ابن ماجه من حديث هشام به."
    takhrij_long = "ورواه الدارمي من طريق سفيان به " + ("مع زيادة في متنه " * 30) + "."
    p2 = "وقال البخاري: حدثنا الحميدي قال قال رسول الله صلى الله عليه وسلم إنما الأعمال بالنيات."
    chain1 = "ورواه مسلم من طريق يحيى به."
    chain2 = "واخرجاه في السنن بنحوه من حديث شعبة به."

    full_text = []
    def add_span(txt, gap=10):
        s = len("".join(full_text)) + gap
        full_text.append(" " * gap + txt)
        e = s + len(txt)
        return s, e

    # Initial anchor layout
    s_p1, e_p1 = add_span(p1, gap=0)
    s_good, e_good = add_span(takhrij_good, gap=10)
    s_hadathana, e_hadathana = add_span(takhrij_hadathana, gap=10)
    s_gap, e_gap = add_span(takhrij_gap, gap=350)
    s_long, e_long = add_span(takhrij_long, gap=10)
    s_p2, e_p2 = add_span(p2, gap=20)
    s_c1, e_c1 = add_span(chain1, gap=10)
    s_c2, e_c2 = add_span(chain2, gap=10)

    seg_full = "".join(full_text)
    segments_path = tmp_path / "segments.jsonl"
    with open(segments_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"segment_id": seg_id, "text": seg_full}) + "\n")

    # Build raw record with these spans located exactly
    spans_def = [
        {"start_anchor": p1[:20], "end_anchor": p1[-20:], "cue": "قال الإمام أحمد", "kind": "marfu", "collection_hint": "ahmad"},
        {"start_anchor": takhrij_good[:15], "end_anchor": takhrij_good[-10:], "cue": "ورواه النسائي", "kind": "athar", "collection_hint": "nasai"},
        {"start_anchor": takhrij_hadathana[:15], "end_anchor": takhrij_hadathana[-10:], "cue": "ورواه أبو داود", "kind": "athar", "collection_hint": "abudawud"},
        {"start_anchor": takhrij_gap[:15], "end_anchor": takhrij_gap[-10:], "cue": "ورواه ابن ماجه", "kind": "athar", "collection_hint": "ibnmajah"},
        {"start_anchor": takhrij_long[:15], "end_anchor": takhrij_long[-15:], "cue": "ورواه الدارمي", "kind": "athar", "collection_hint": "darimi"},
        {"start_anchor": p2[:20], "end_anchor": p2[-20:], "cue": "وقال البخاري", "kind": "marfu", "collection_hint": "bukhari"},
        {"start_anchor": chain1[:15], "end_anchor": chain1[-10:], "cue": "ورواه مسلم", "kind": "athar", "collection_hint": "muslim"},
        {"start_anchor": chain2[:15], "end_anchor": chain2[-10:], "cue": "واخرجاه", "kind": "athar", "collection_hint": "other"},
    ]

    raw_path = tmp_path / "raw.jsonl"
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "key": f"{seg_id}#0-{len(seg_full)}",
            "segment_id": seg_id,
            "window_start": 0,
            "window_end": len(seg_full),
            "status": "ok",
            "raw_text": json.dumps({"spans": spans_def}),
            "prompt_version": "1.3",
        }) + "\n")

    out_spans = tmp_path / "out_spans.jsonl"
    out_rejected = tmp_path / "out_rejected.jsonl"

    stats = run_build(
        raw_path=raw_path,
        out_path=out_spans,
        rejected_path=out_rejected,
        segments_path=segments_path,
    )

    with open(out_spans, "r", encoding="utf-8") as f:
        built = [json.loads(line) for line in f]

    assert len(built) == 8

    # 1. takhrij_good: changed to marfu
    sp_good = built[1]
    assert sp_good["kind"] == "marfu"
    assert sp_good["kind_glm"] == "athar"
    assert sp_good["kind_rule"] == "chained_takhrij"

    # 2. takhrij_hadathana: contains حدثنا -> unchanged (remains athar)
    sp_hadathana = built[2]
    assert sp_hadathana["kind"] == "athar"
    assert "kind_rule" not in sp_hadathana

    # 3. takhrij_gap: gap = 350 >= 300 -> unchanged (remains athar)
    sp_gap = built[3]
    assert sp_gap["kind"] == "athar"
    assert "kind_rule" not in sp_gap

    # 4. takhrij_long: length > 400 chars -> unchanged (remains athar)
    sp_long = built[4]
    assert sp_long["kind"] == "athar"
    assert "kind_rule" not in sp_long

    # 5. chain of two takhrij lines (built[6] and built[7]) after p2 (built[5], marfu)
    assert built[5]["kind"] == "marfu"
    sp_c1 = built[6]
    assert sp_c1["kind"] == "marfu"
    assert sp_c1["kind_glm"] == "athar"
    assert sp_c1["kind_rule"] == "chained_takhrij"

    sp_c2 = built[7]
    assert sp_c2["kind"] == "marfu"
    assert sp_c2["kind_glm"] == "athar"
    assert sp_c2["kind_rule"] == "chained_takhrij"
