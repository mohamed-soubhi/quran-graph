"""Tests for Phase 4b extraction contract and anchor locator (T2.3)."""

import json
from pathlib import Path
import unicodedata
import jsonschema

from src.extract.glm_client import ollama_format
from src.extract.models import HadithSpanAnchor, HadithSpanAnchorList
from src.extract.locate import locate
from src.extract.normalize import normalize_with_map

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "docs" / "extraction_schema.json"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "tafsir_sample.txt"


def test_schema_is_valid_json_schema():
    """docs/extraction_schema.json is a valid JSON Schema (Draft 2020-12)."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    assert schema["$id"].endswith("/1.1")
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)


def test_model_matches_schema_item():
    """HadithSpanAnchor fields and required list match schema items definition."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    schema_item = schema["properties"]["spans"]["items"]
    schema_fields = set(schema_item["properties"].keys())
    model_fields = set(HadithSpanAnchor.model_fields.keys())

    assert schema_fields == model_fields

    schema_required = sorted(schema_item["required"])
    model_required = sorted(HadithSpanAnchor.model_json_schema()["required"])

    assert schema_required == model_required


def test_fixture_example_validates_against_schema():
    """Fixture example objects validate against the contract schema and pydantic model."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    example = {
        "spans": [
            {
                "start_anchor": "قال الإمام أحمد: حدثنا",
                "end_anchor": "عند ساق العرش",
                "cue": "قال الإمام أحمد: حدثنا",
                "collection_hint": "ahmad",
                "number_hint": None,
                "kind": "marfu",
            },
            {
                "start_anchor": "وقد رواه مسلم",
                "end_anchor": "عن الجريري-به",
                "cue": "وقد رواه مسلم",
                "collection_hint": "muslim",
                "number_hint": None,
                "kind": "marfu",
            },
        ]
    }

    # Validate against JSON schema
    jsonschema.validate(instance=example, schema=schema)

    # Validate against Pydantic model
    parsed = HadithSpanAnchorList.model_validate(example)
    assert len(parsed.spans) == 2
    assert parsed.spans[0].collection_hint == "ahmad"
    assert parsed.spans[1].collection_hint == "muslim"


def test_locate_exact_fixture_offsets():
    """locate returns exactly (141, 657) and (658, 790) for the fixture anchors."""
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    assert len(fixture_text) == 904

    ahmad_anchor = HadithSpanAnchor(
        start_anchor="قال الإمام أحمد: حدثنا",
        end_anchor="عند ساق العرش",
        cue="قال الإمام أحمد: حدثنا",
        collection_hint="ahmad",
        number_hint=None,
    )
    ahmad_span = locate(fixture_text, ahmad_anchor)
    assert ahmad_span == (141, 657)

    muslim_anchor = HadithSpanAnchor(
        start_anchor="وقد رواه مسلم",
        end_anchor="عن الجريري-به",
        cue="وقد رواه مسلم",
        collection_hint="muslim",
        number_hint=None,
    )
    muslim_span = locate(fixture_text, muslim_anchor)
    assert muslim_span == (658, 790)


def test_locate_not_found_and_footnote():
    """locate returns None for non-existent anchor and for anchor inside [[...]] footnote."""
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")

    # Missing anchor
    missing_anchor = HadithSpanAnchor(
        start_anchor="حديث ليس في النص مطلقا",
        end_anchor="نهاية غير موجودة",
    )
    assert locate(fixture_text, missing_anchor) is None

    # Anchor occurring only inside [[...]] editor footnote
    footnote_anchor = HadithSpanAnchor(
        start_anchor="وصحيح مسلم برقم",
        end_anchor="(٨١٠)",
    )
    assert locate(fixture_text, footnote_anchor) is None


def test_normalize_with_map_properties():
    """normalize_with_map preserves lengths, has strictly increasing index, and strips Mn."""
    fixture_text = FIXTURE_PATH.read_text(encoding="utf-8")
    norm, index = normalize_with_map(fixture_text)

    # Length equality
    assert len(norm) == len(index)

    # Strictly increasing index
    assert all(index[i] < index[i + 1] for i in range(len(index) - 1))

    # All characters in norm are non-Mn
    assert all(unicodedata.category(c) != "Mn" for c in norm)

    # Verify letter mapping
    letter_pairs = [("أحمد", "احمد"), ("إلى", "الي"), ("آية", "ايه")]
    for orig, expected in letter_pairs:
        n, _ = normalize_with_map(orig)
        assert n == expected


def test_ollama_format_strips_metadata_and_extensions():
    """ollama_format removes $id, $schema, and x-* keys recursively."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    cleaned = ollama_format(schema)

    assert "$schema" not in cleaned
    assert "$id" not in cleaned
    assert "x-locator-rules" not in cleaned
    assert "title" in cleaned
    assert "properties" in cleaned
    assert "spans" in cleaned["properties"]


def test_locate_skips_footnote_matches():
    """Anchor matches inside [[...]] are skipped: a later real match is used; an end only in a footnote fails."""
    mk = lambda s, e: HadithSpanAnchor(start_anchor=s, end_anchor=e, cue=None, collection_hint=None, number_hint=None)
    text = "[[رواه مسلم برقم ١]] ثم قال: رواه مسلم عن فلان."
    start, end = locate(text, mk("رواه مسلم", "عن فلان"))
    assert text[start:end] == "رواه مسلم عن فلان"
    text = "قال رسول الله ﷺ: كذا [[انظر صحيح البخاري]] وبعد"
    assert locate(text, mk("قال رسول الله", "صحيح البخاري")) is None
