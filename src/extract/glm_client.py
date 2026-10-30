"""GLM client for extracting hadith spans from Arabic tafsir text via Ollama HTTP API (T0.5)."""

import json
import os
import re
import time
from pathlib import Path
from dotenv import load_dotenv

from src.extract.models import HadithSpanList
from src.log import get_logger

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

logger = get_logger("glm_client")

# Default few-shot example (custom short example, not the fixture)
FEWSHOT_INPUT = (
    "وقوله تعالى: {فَسَبِّحْ بِحَمْدِ رَبِّكَ} قال ابن كثير: "
    "روى البخاري في صحيحه: حدثنا حفص بن عمر حدثنا شعبة عن منصور عن أبي الضحى عن مسروق عن عائشة قالت: "
    "كان النبي ﷺ يكثر أن يقول في ركوعه وسجوده: سبحانك اللهم ربنا وبحمدك اللهم اغفر لي. "
    "[[أخرجه البخاري برقم (794)]] وهذا إسناد صحيح."
)

FEWSHOT_OUTPUT = {
    "spans": [
        {
            "start": 56,
            "end": 233,
            "cue": "روى البخاري في صحيحه: حدثنا",
            "collection_hint": "bukhari",
            "number_hint": None,
        }
    ]
}


def build_system_prompt() -> str:
    """Build the system prompt containing instructions, JSON schema, and rules."""
    schema = HadithSpanList.model_json_schema()
    return (
        "You are an expert Arabic data extraction assistant.\n"
        "Extract all hadith spans (narrations and quotations) from the input Arabic tafsir text.\n"
        "Return ONLY a JSON object strictly matching this schema with a 'spans' list:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        "Field definitions:\n"
        "- 'start': 0-based character start offset (inclusive) in the verbatim input text.\n"
        "- 'end': 0-based character end offset (exclusive) in the verbatim input text.\n"
        "- 'cue': Introductory formula introducing the hadith (e.g. قال الإمام أحمد: حدثنا, وقد رواه مسلم).\n"
        "- 'collection_hint': Canonical collection name if mentioned (e.g. 'ahmad', 'muslim', 'bukhari'), otherwise null.\n"
        "- 'number_hint': Hadith number if explicitly mentioned in the text, otherwise null.\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Text enclosed in [[...]] is an editor footnote (takhrij note), NOT part of Ibn Kathir's hadith narration. Never extract text inside [[...]] as a hadith.\n"
        "2. DO NOT count characters or transcribe text character-by-character in your thinking. Directly estimate start and end offsets.\n"
        "3. Keep your thinking concise (under 5 sentences). Output the JSON immediately."
    )


def extract_hadith_spans(
    text: str,
    model: str | None = None,
    host: str | None = None,
    timeout: float = 180.0,
) -> HadithSpanList:
    """Call Ollama /api/chat to extract hadith spans from Arabic tafsir text.

    Args:
        text: Raw verbatim Arabic tafsir text (UTF-8).
        model: Ollama model tag, defaults to GLM_MODEL in .env.
        host: Ollama server URL, defaults to OLLAMA_HOST in .env.
        timeout: HTTP request timeout in seconds.

    Returns:
        Validated HadithSpanList instance.

    Raises:
        ValueError: If offsets are invalid (not 0 <= start < end <= len(text)).
        requests.RequestException: If the HTTP request fails.
        pydantic.ValidationError: If response does not match HadithSpanList schema.
    """
    import requests

    load_dotenv(ROOT / ".env")
    host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = model or os.getenv("GLM_MODEL", "glm-5.3-flash:cloud")

    system_prompt = build_system_prompt()
    user_prompt = (
        f"Example:\nInput: {FEWSHOT_INPUT}\nOutput: {json.dumps(FEWSHOT_OUTPUT, ensure_ascii=False)}\n\n"
        f"Now extract hadith spans from this text:\n{text}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "format": HadithSpanList.model_json_schema(),
        "stream": True,
        "options": {"temperature": 0},
    }

    t0 = time.time()
    response = requests.post(f"{host}/api/chat", json=payload, stream=True, timeout=timeout)
    response.raise_for_status()

    content_parts = []
    for line in response.iter_lines():
        if line:
            chunk = json.loads(line)
            msg = chunk.get("message", {})
            if "content" in msg and msg["content"]:
                content_parts.append(msg["content"])

    elapsed = time.time() - t0
    raw_content = "".join(content_parts).strip()

    # Log duration per paragraph
    logger.info(
        "Extracted hadith spans in %.2fs for text of length %d chars (model: %s)",
        elapsed,
        len(text),
        model,
    )

    # Strip markdown code blocks if the model wrapped the JSON
    cleaned = raw_content
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    span_list = HadithSpanList.model_validate_json(cleaned)

    # Validate offsets: 0 <= start < end <= len(text)
    for span in span_list.spans:
        if not (0 <= span.start < span.end <= len(text)):
            raise ValueError(
                f"Invalid span offsets [{span.start}, {span.end}) for text of length {len(text)}"
            )

    return span_list
