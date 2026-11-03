"""GLM client for extracting hadith spans from Arabic tafsir text via Ollama HTTP API (T0.5)."""

import json
import os
import re
import time
from pathlib import Path
from dotenv import load_dotenv

from src.extract.models import HadithSpanAnchorList, HadithSpanList
from src.log import get_logger

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

logger = get_logger("glm_client")

SCHEMA_PATH = ROOT / "docs" / "extraction_schema.json"

# Few-shot examples for HadithSpanAnchorList (T4.5 - not from the gold set)
FEWSHOT_ANCHOR_1_INPUT = (
    "قال ابن ماجه: حدثنا محمد بن بشار حدثنا يحيى بن سعيد عن سفيان عن منصور عن ربعي بن حراش عن علي بن أبي طالب قال: "
    "قال رسول الله ﷺ: \"لا تكذبوا علي فإنه من يكذب علي يلج النار\". "
    "وقد رواه أحمد عن وكيع عن سفيان به [[سنن ابن ماجه برقم (٣١)]]."
)
FEWSHOT_ANCHOR_1_OUTPUT = {
    "spans": [
        {
            "start_anchor": "قال ابن ماجه: حدثنا محمد",
            "end_anchor": "علي يلج النار\"",
            "cue": "قال ابن ماجه: حدثنا",
            "collection_hint": "ibnmajah",
            "number_hint": None,
            "kind": "marfu",
        },
        {
            "start_anchor": "وقد رواه أحمد عن وكيع",
            "end_anchor": "عن سفيان به",
            "cue": "وقد رواه أحمد",
            "collection_hint": "ahmad",
            "number_hint": None,
            "kind": "marfu",
        },
    ]
}

FEWSHOT_ANCHOR_2_INPUT = (
    "وقوله تعالى: ﴿فَاهْدُوهُمْ إِلَى صِرَاطِ الْجَحِيمِ﴾ قال مجاهد: أي طريق النار. "
    "وقال عكرمة والسدي: هو السبل الموصلة إلى العذاب، وهذا قول جمهور المفسرين."
)
FEWSHOT_ANCHOR_2_OUTPUT = {
    "spans": [],
}

ANCHOR_SYSTEM_PROMPT = (
    "You are an expert Arabic hadith extraction assistant.\n"
    "Extract all HADITH spans (narrations, quotations, and chained takhrij lines) from the input Arabic tafsir window.\n"
    "Return ONLY a JSON object strictly conforming to the schema.\n\n"
    "Extraction rules:\n"
    "1. WHAT IS A HADITH: A narration with an isnad (حدثنا / أخبرنا / سمعت), an explicit takhrij (رواه / أخرجه / أخرجاه + collector), or the Prophet's ﷺ direct words or acts («قال رسول الله ﷺ», «وفي الحديث»).\n"
    "2. START ANCHOR: The first 3-8 words of the span, copied EXACTLY from the input text, starting at the introducing formula (e.g. «قال الإمام أحمد: حدثنا», «وقد رواه مسلم»). Leading connectives like «ولهذا» stay outside.\n"
    "3. END ANCHOR: The last 3-8 words of the span, copied EXACTLY from the input text, ending after the last word of the matn or takhrij (including closing quotes). Sentence-final full stops stay outside.\n"
    "4. TAKHRIJ: A takhrij line with its own isnad/chain (e.g. «وقد رواه مسلم عن أبي بكر ... عن الجريري به») is its own separate HADITH span. A chainless takhrij line (e.g. «وكذلك رواه ابن جرير», «وعلقه البخاري مجزوما») joins the hadith before it.\n"
    "5. KIND: 'marfu' if the quoted route reaches the Prophet ﷺ; 'athar' if it stops at a Companion or Successor (e.g. Ibn Abbas, Ibn Umar). Base this on the quoted route as written.\n"
    "6. NOT HADITH: Tafsir opinions with short routes or no transmission verbs (e.g. «قال علي بن أبي طلحة عن ابن عباس», «قال مجاهد: ...») are commentary, NOT hadith. Dream or story reports (even with isnad) are commentary, NOT hadith.\n"
    "7. FOOTNOTES: Text inside [[...]] is an editor footnote. NEVER extract from [[...]], and anchors must never be inside [[...]].\n"
    "8. COLLECTION HINT: Must be one of 'bukhari', 'muslim', 'abudawud', 'tirmidhi', 'nasai', 'ibnmajah', 'malik', 'ahmad', 'darimi', or 'other' (for any other source like Tabari, Tabarani, Bazzar, Ibn Abi Hatim), or null."
)

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


def ollama_format(schema: dict) -> dict:
    """Prepare a JSON schema for Ollama structured output (T2.3).

    Recursively removes schema metadata ($id, $schema) and extension keys starting
    with 'x-' (such as 'x-locator-rules') before the schema is sent as Ollama format.
    """
    if not isinstance(schema, dict):
        return schema
    clean = {}
    for k, v in schema.items():
        if k in ("$id", "$schema") or k.startswith("x-"):
            continue
        if isinstance(v, dict):
            clean[k] = ollama_format(v)
        elif isinstance(v, list):
            clean[k] = [
                ollama_format(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            clean[k] = v
    return clean


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


def extract_hadith_anchors(
    window_text: str,
    model: str | None = None,
    host: str | None = None,
    timeout: float = 120.0,
) -> HadithSpanAnchorList:
    """Call Ollama /api/chat to extract hadith anchor phrases from Arabic tafsir text.

    Args:
        window_text: Raw verbatim Arabic tafsir window text (UTF-8).
        model: Ollama model tag, defaults to GLM_MODEL in .env.
        host: Ollama server URL, defaults to OLLAMA_HOST in .env.
        timeout: HTTP request timeout in seconds.

    Returns:
        Validated HadithSpanAnchorList instance.
    """
    import requests

    load_dotenv(ROOT / ".env")
    host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
    model = model or os.getenv("GLM_MODEL", "glm-5.3-flash:cloud")

    schema_data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    format_schema = ollama_format(schema_data)

    user_prompt = (
        f"Example 1:\nInput: {FEWSHOT_ANCHOR_1_INPUT}\nOutput: {json.dumps(FEWSHOT_ANCHOR_1_OUTPUT, ensure_ascii=False)}\n\n"
        f"Example 2:\nInput: {FEWSHOT_ANCHOR_2_INPUT}\nOutput: {json.dumps(FEWSHOT_ANCHOR_2_OUTPUT, ensure_ascii=False)}\n\n"
        f"Input:\n{window_text}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": ANCHOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "format": format_schema,
        "stream": True,
        "options": {"temperature": 0},
    }

    last_error: Exception | None = None
    for attempt in range(2):
        t0 = time.time()
        try:
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

            cleaned = raw_content
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)

            # Extract first JSON object from '{' using raw_decode to handle any trailing commentary
            brace_pos = cleaned.find("{")
            if brace_pos != -1:
                try:
                    obj, _ = json.JSONDecoder().raw_decode(cleaned[brace_pos:])
                    anchor_list = HadithSpanAnchorList.model_validate(obj)
                except Exception:
                    anchor_list = HadithSpanAnchorList.model_validate_json(cleaned)
            else:
                anchor_list = HadithSpanAnchorList.model_validate_json(cleaned)
            logger.info(
                "Extracted %d hadith anchors in %.2fs for window of length %d chars (model: %s)",
                len(anchor_list.spans),
                elapsed,
                len(window_text),
                model,
            )
            return anchor_list
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                logger.warning("Attempt 1 failed for extract_hadith_anchors, retrying: %s", exc)
                time.sleep(1)
            else:
                logger.error("Attempt 2 failed for extract_hadith_anchors: %s", exc)

    logger.warning("Returning empty HadithSpanAnchorList after error: %s", last_error)
    return HadithSpanAnchorList(spans=[])
