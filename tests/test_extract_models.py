"""Unit tests for extraction models (no network needed)."""

import json
from pathlib import Path
from src.extract.models import HadithSpan, HadithSpanList

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_expected_hadith_spans_validate():
    """Verify the expected hadith_spans from tafsir_sample.expected.json validate as HadithSpanList."""
    fixture_json = FIXTURES_DIR / "tafsir_sample.expected.json"
    fixture_txt = FIXTURES_DIR / "tafsir_sample.txt"

    with open(fixture_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(fixture_txt, "r", encoding="utf-8") as f:
        text = f.read()

    hadith_spans = data["hadith_spans"]
    span_list = HadithSpanList.model_validate({"spans": hadith_spans})

    assert len(span_list.spans) == 2

    # Check first hadith span (Ahmad)
    h1 = span_list.spans[0]
    assert h1.start == 141
    assert h1.end == 657
    assert "أَحْمَدُ" in h1.cue
    assert h1.collection_hint == "ahmad"
    assert h1.number_hint is None

    # Check second hadith span (Muslim)
    h2 = span_list.spans[1]
    assert h2.start == 658
    assert h2.end == 790
    assert "مُسْلِمٌ" in h2.cue
    assert h2.collection_hint == "muslim"
    assert h2.number_hint == "810"

    # Validate offsets within text length
    for span in span_list.spans:
        assert 0 <= span.start < span.end <= len(text)
