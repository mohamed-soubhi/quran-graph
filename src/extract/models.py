"""Data models for extracted spans."""

from typing import Optional
from pydantic import BaseModel, Field


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
