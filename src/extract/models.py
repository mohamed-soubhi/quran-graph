"""Data models for extracted spans."""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class HadithSpan(BaseModel):
    """A span of text identified as a hadith quotation or narration."""

    start: int = Field(description="Start character offset (0-based, inclusive) in the input text")
    end: int = Field(description="End character offset (0-based, exclusive) in the input text")
    cue: str = Field(description="Introductory formula or cue phrase introducing the hadith (e.g. قال رسول الله, حدثنا)")
    collection_hint: Optional[str] = Field(default=None, description="Name or abbreviation of the collection if mentioned (e.g. bukhari, muslim, ahmad)")
    number_hint: Optional[str] = Field(default=None, description="Hadith number if mentioned or referenced")


class HadithSpanList(BaseModel):
    """List of extracted hadith spans."""

    spans: list[HadithSpan] = Field(default_factory=list, description="List of hadith spans found in the text")


# ---------------------------------------------------------------------------
# T2.3 extraction contract models (docs/extraction_schema.json)
# ---------------------------------------------------------------------------

CollectionHint = Literal[
    "bukhari",
    "muslim",
    "abudawud",
    "tirmidhi",
    "nasai",
    "ibnmajah",
    "malik",
    "ahmad",
    "darimi",
    "other",
]


class HadithSpanAnchor(BaseModel):
    """A hadith quotation or narration anchor matching the Phase 4b extraction schema."""

    model_config = ConfigDict(extra="forbid")

    start_anchor: str = Field(
        min_length=1,
        description="The first 3-8 words of the hadith span, copied exactly from the input (diacritics may be omitted).",
    )
    end_anchor: str = Field(
        min_length=1,
        description="The last 3-8 words of the hadith span, copied exactly from the input (diacritics may be omitted).",
    )
    cue: str | None = Field(
        description="The introducing formula as written, e.g. 'قال الإمام أحمد: حدثنا', 'وقد رواه مسلم'.",
    )
    collection_hint: CollectionHint | None = Field(
        description="Collection named in the span itself (not guessed). 'other' for a named source outside this list.",
    )
    number_hint: str | None = Field(
        description="A hadith number written in the span itself, copied as written (Arabic-Indic digits allowed). Never from memory.",
    )

    def __init__(self, /, **data):
        data.setdefault("cue", None)
        data.setdefault("collection_hint", None)
        data.setdefault("number_hint", None)
        super().__init__(**data)


class HadithSpanAnchorList(BaseModel):
    """Container for a list of hadith span anchors matching docs/extraction_schema.json."""

    model_config = ConfigDict(extra="forbid")

    spans: list[HadithSpanAnchor] = Field(
        description="One item per hadith narration or takhrij reference in the input window. Empty if none. Editor notes in [[...]] are never hadith spans.",
    )

    def __init__(self, /, **data):
        data.setdefault("spans", [])
        super().__init__(**data)
