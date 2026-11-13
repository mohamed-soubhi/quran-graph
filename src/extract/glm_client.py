"""GLM client for extracting hadith spans from Arabic tafsir text via Ollama HTTP API (T0.5, T4.5, T4.5b)."""

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

from src.extract.models import HadithSpanAnchor, HadithSpanAnchorList, HadithSpanList
from src.log import get_logger

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

logger = get_logger("glm_client")

SCHEMA_PATH = ROOT / "docs" / "extraction_schema.json"

PROMPT_VERSION = "1.3"

# Few-shot examples for HadithSpanAnchorList (T4.5, T4.5c - not from the gold set)
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

FEWSHOT_ANCHOR_3_INPUT = (
    "وقال أبو زرعة: حدثنا أحمد بن يونس، حدثنا أبو بكر بن عياش، عن الأعمش، عن إبراهيم النخعي قال: "
    "كان أصحاب عبد الله يعجبهم هذا الشرح. ورواه سعيد بن منصور من حديث الأعمش به."
)
FEWSHOT_ANCHOR_3_OUTPUT = {
    "spans": [
        {
            "start_anchor": "وقال أبو زرعة: حدثنا أحمد",
            "end_anchor": "يعجبهم هذا الشرح",
            "cue": "وقال أبو زرعة: حدثنا",
            "collection_hint": "other",
            "number_hint": None,
            "kind": "athar",
        },
        {
            "start_anchor": "ورواه سعيد بن منصور من حديث",
            "end_anchor": "حديث الأعمش به",
            "cue": "ورواه سعيد بن منصور",
            "collection_hint": "other",
            "number_hint": None,
            "kind": "athar",
        },
    ]
}

ANCHOR_SYSTEM_PROMPT = (
    "You are an expert Arabic hadith extraction assistant.\n"
    "Extract all HADITH spans (narrations, quotations, and chained takhrij lines) from the input Arabic tafsir window.\n"
    "Your response must be EXACTLY ONE JSON object and nothing else, with NO explanation, NO surrounding commentary, and NO markdown code fences.\n"
    "Any quote character \" inside an Arabic string MUST be written as an escaped quote \\\" (never a bare \").\n\n"
    "Extraction rules:\n"
    "1. WHAT IS A HADITH: A narration with an isnad (حدثنا / أخبرنا / سمعت), an explicit takhrij (رواه / أخرجه / أخرجاه / روى + collector), or the Prophet's ﷺ direct words or acts («قال رسول الله ﷺ», «وفي الحديث»). Reports of Companions and Successors (athar) are HADITH spans when they come with an isnad (حدثنا / أخبرنا / سمعت) or a takhrij verb + collector (رواه / أخرجه / روى), even when the content is tafsir; kind = 'athar'.\n"
    "2. START ANCHOR: The first 3-8 words of the span, copied EXACTLY from the input text, starting at the introducing formula (e.g. «قال الإمام أحمد: حدثنا», «وقد رواه مسلم»). Leading connectives like «ولهذا» stay outside.\n"
    "3. END ANCHOR: The last 3-8 words of the span, copied EXACTLY from the input text, ending after the last word of the matn or takhrij (including closing quotes). Sentence-final full stops stay outside.\n"
    "4. TAKHRIJ: A takhrij line with its own isnad/chain/route (e.g. «وقد رواه مسلم عن أبي بكر ... عن الجريري به», «رواه X من حديث / من طريق Y ... به», «... بنحوه») is its own separate HADITH span even when the hadith it refers to is not in this window. A chainless takhrij line (e.g. «وكذلك رواه ابن جرير», «وعلقه البخاري مجزوما») joins the hadith before it.\n"
    "5. KIND: 'marfu' if the quoted route reaches the Prophet ﷺ; 'athar' if it stops at a Companion or Successor (e.g. Ibn Abbas, Ibn Umar). Base this on the quoted route as written. Must be exactly 'marfu' or 'athar'.\n"
    "6. NOT HADITH: Tafsir opinions with short routes (a name + «عن» + a name with no transmission verb and no takhrij, e.g. «قال علي بن أبي طلحة عن ابن عباس», «قال مجاهد: ...») are commentary, NOT hadith. Dream or story reports (even with isnad) are commentary, NOT hadith.\n"
    "7. FOOTNOTES: Text inside [[...]] is an editor footnote. NEVER extract from [[...]], and anchors must never be inside [[...]].\n"
    "8. COLLECTION HINT: Must be one of 'bukhari', 'muslim', 'abudawud', 'tirmidhi', 'nasai', 'ibnmajah', 'malik', 'ahmad', 'darimi', or 'other' (for any other source like Tabari, Tabarani, Bazzar, Ibn Abi Hatim, Ibn Jarir), or null. Anything else MUST be written as \"other\"."
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


class GlmResponseError(Exception):
    """Raised when GLM response does not contain a valid JSON object."""


class GlmExtractionError(Exception):
    """Raised when hadith extraction fails after all retry attempts."""


@dataclass
class ParsedAnchors:
    """Parsed anchors from GLM response with error counters (T4.5b)."""

    spans: list[HadithSpanAnchor] = field(default_factory=list)
    unknown_collections: int = 0
    dropped_spans: int = 0
    dropped_items: list[dict] = field(default_factory=list)

    def __iter__(self):
        return iter(self.spans)

    def __len__(self):
        return len(self.spans)

    def __getitem__(self, idx):
        return self.spans[idx]


VALID_COLLECTIONS = {
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
}


def normalize_kind(raw_kind: Any) -> str | None:
    """Normalize kind by removing accents and non-letters (T4.5b F2).

    marfu' / marfū' / Marfu -> marfu
    athar / Athar -> athar
    Anything else -> None
    """
    if not isinstance(raw_kind, str):
        return None
    decomposed = unicodedata.normalize("NFKD", raw_kind)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    letters_only = re.sub(r"[^a-zA-Z]", "", stripped).lower()
    if letters_only in ("marfu", "athar"):
        return letters_only
    return None


def parse_anchor_response(raw: str) -> ParsedAnchors:
    """Parse raw GLM answer into ParsedAnchors without network calls (T4.5b).

    Rules:
    - take the first JSON object, ignore markdown fences and trailing text;
    - validate span by span: an unknown collection_hint becomes 'other' (keep the span, count it);
      an invalid span is dropped and counted, the others are kept; an unknown kind drops the span;
      kind is compared after removing accents and non-letters (F2);
    - dropped spans are preserved in dropped_items with their raw values (F2);
    - no JSON object at all -> raise GlmResponseError.
    """
    if not raw or not raw.strip():
        raise GlmResponseError("Empty GLM response")

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    brace_pos = cleaned.find("{")
    if brace_pos == -1:
        raise GlmResponseError(f"No JSON object found in response: {raw[:100]!r}")

    try:
        obj, _ = json.JSONDecoder().raw_decode(cleaned[brace_pos:])
    except Exception as exc:
        raise GlmResponseError(f"Failed to decode JSON object: {exc}") from exc

    if not isinstance(obj, dict) or "spans" not in obj:
        raise GlmResponseError(f"Response JSON is not an object with 'spans': {type(obj)}")

    raw_spans = obj["spans"]
    if not isinstance(raw_spans, list):
        raise GlmResponseError(f"'spans' must be a list, got {type(raw_spans)}")

    valid_spans: list[HadithSpanAnchor] = []
    unknown_collections = 0
    dropped_spans = 0
    dropped_items: list[dict] = []

    for item in raw_spans:
        if not isinstance(item, dict):
            dropped_spans += 1
            dropped_items.append({"raw": item})
            continue

        start_anchor = item.get("start_anchor")
        end_anchor = item.get("end_anchor")
        if not isinstance(start_anchor, str) or not start_anchor.strip():
            dropped_spans += 1
            dropped_items.append(dict(item))
            continue
        if not isinstance(end_anchor, str) or not end_anchor.strip():
            dropped_spans += 1
            dropped_items.append(dict(item))
            continue

        raw_kind = item.get("kind")
        kind = normalize_kind(raw_kind)
        if not kind:
            dropped_spans += 1
            dropped_items.append(dict(item))
            continue

        col = item.get("collection_hint")
        if col is None:
            col_hint = None
        elif isinstance(col, str):
            col_clean = col.strip().lower()
            if col_clean in VALID_COLLECTIONS:
                col_hint = col_clean
            else:
                col_hint = "other"
                unknown_collections += 1
        else:
            col_hint = "other"
            unknown_collections += 1

        cue = item.get("cue")
        if cue is not None and not isinstance(cue, str):
            cue = str(cue)

        num_hint = item.get("number_hint")
        if num_hint is not None and not isinstance(num_hint, str):
            num_hint = str(num_hint)

        try:
            anchor = HadithSpanAnchor(
                start_anchor=start_anchor.strip(),
                end_anchor=end_anchor.strip(),
                cue=cue.strip() if cue else None,
                collection_hint=col_hint,
                number_hint=num_hint.strip() if num_hint else None,
                kind=kind,
            )
            valid_spans.append(anchor)
        except Exception:
            dropped_spans += 1
            dropped_items.append(dict(item))

    return ParsedAnchors(
        spans=valid_spans,
        unknown_collections=unknown_collections,
        dropped_spans=dropped_spans,
        dropped_items=dropped_items,
    )


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

    logger.info(
        "Extracted hadith spans in %.2fs for text of length %d chars (model: %s)",
        elapsed,
        len(text),
        model,
    )

    cleaned = raw_content
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    span_list = HadithSpanList.model_validate_json(cleaned)

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
) -> ParsedAnchors:
    """Call Ollama /api/chat to extract hadith anchor phrases from Arabic tafsir text (T4.5, T4.5b).

    Performs up to 3 attempts. Raises GlmExtractionError on failure.
    An empty list now always means GLM really answered 'no spans'.

    Args:
        window_text: Raw verbatim Arabic tafsir window text (UTF-8).
        model: Ollama model tag, defaults to GLM_MODEL in .env.
        host: Ollama server URL, defaults to OLLAMA_HOST in .env.
        timeout: HTTP request timeout in seconds.

    Returns:
        Validated ParsedAnchors instance.

    Raises:
        GlmExtractionError: If extraction fails after 3 attempts.
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
        f"Example 3:\nInput: {FEWSHOT_ANCHOR_3_INPUT}\nOutput: {json.dumps(FEWSHOT_ANCHOR_3_OUTPUT, ensure_ascii=False)}\n\n"
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
    for attempt in range(1, 4):
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

            parsed = parse_anchor_response(raw_content)
            logger.info(
                "Extracted %d hadith anchors in %.2fs (attempt %d, model: %s)",
                len(parsed.spans),
                elapsed,
                attempt,
                model,
            )
            return parsed
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                logger.warning("Attempt %d failed for extract_hadith_anchors, retrying: %s", attempt, exc)
                time.sleep(1)
            else:
                logger.error("Attempt 3 failed for extract_hadith_anchors: %s", exc)

    raise GlmExtractionError(
        f"Failed to extract hadith anchors after 3 attempts: {last_error}"
    ) from last_error
