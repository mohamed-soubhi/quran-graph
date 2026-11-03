"""Quran span extraction and ayah linker (T4.4, Gate 4a).

Extracts every ﴿…﴾ quote in Ibn Kathir segments, links to Ayah nodes:
- EXPLAINS: quoted ayah is covered by the segment (tafsir of the passage).
- CITES: quoted ayah is elsewhere in the Quran (tafsir of Quran by Quran).

Deterministic regex + token matching, no LLM.
Output: data/interim/spans/quran.jsonl
"""

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extract.normalize import normalize_with_map
from src.log import get_logger

logger = get_logger("quran_spans")

QUOTE_RE: re.Pattern[str] = re.compile(r"﴿[^﴾]*﴾")
FOOTNOTE_INNER_RE: re.Pattern[str] = re.compile(r"\[\[.*?\]\]", re.DOTALL)
REF_RE: re.Pattern[str] = re.compile(
    r"^\s*\[([^\[\]:]{1,40}):\s*([٠-٩0-9]+)(?:\s*[-–،,]\s*([٠-٩0-9]+))?\]"
)
AR_DIGITS: dict[int, str] = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
TR_LOOSE: dict[int, None] = str.maketrans("", "", "\u0627\u0626\u0624")  # delete ا, ئ, ؤ

DEFAULT_SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
DEFAULT_SURAH_PATH = ROOT / "data" / "interim" / "quran" / "surahs.jsonl"
DEFAULT_AYAT_PATH = ROOT / "data" / "interim" / "quran" / "ayat.jsonl"
DEFAULT_OUTPUT_PATH = ROOT / "data" / "interim" / "spans" / "quran.jsonl"
DEFAULT_SOURCE = "run:20261103-0000-quran-spans"

METHOD_REGEX = "regex"
METHOD_NGRAM = "ngram"
CONF_EXACT = 1.0
CONF_LOOSE = 0.9
CONF_AMBIGUOUS = 0.5
SPAN_TYPE_QURAN = "QURAN"


def clean_tokens(text: str) -> list[str]:
    """Normalize Arabic text using v2 normalizer and split into clean alphanumeric tokens."""
    norm, _ = normalize_with_map(text)
    clean = "".join(c if c.isalnum() else " " for c in norm)
    return clean.split()


class QuranCorpusIndex:
    """Precomputed token stream and lookup indexes for the simple Quran text."""

    def __init__(
        self,
        surahs_path: Path | str = DEFAULT_SURAH_PATH,
        ayat_path: Path | str = DEFAULT_AYAT_PATH,
    ) -> None:
        self.surahs_path = Path(surahs_path)
        self.ayat_path = Path(ayat_path)

        # 1. Load surahs
        self.surah_name_to_id: dict[str, int] = {}
        self.surah_ayah_counts: dict[int, int] = {}
        if self.surahs_path.exists():
            with self.surahs_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    s = json.loads(line)
                    sid = s["surah_id"]
                    self.surah_ayah_counts[sid] = s["ayah_count"]
                    norm, _ = normalize_with_map(s["name"])
                    cleaned = norm.replace(" ", "")
                    self.surah_name_to_id[cleaned] = sid
                    if cleaned.startswith("ال"):
                        self.surah_name_to_id[cleaned[2:]] = sid

        # 2. Load ayat and build token stream
        self.stream: list[str] = []
        self.stream_ayah: list[str] = []
        self.ayah_tokens: dict[str, set[str]] = {}
        self.index: dict[str, list[int]] = {}

        self.loose_stream: list[str] = []
        self.loose_index: dict[str, list[int]] = {}

        if self.ayat_path.exists():
            with self.ayat_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    a = json.loads(line)
                    ayah_id = a["ayah_id"]
                    toks = clean_tokens(a.get("text_simple", ""))
                    self.ayah_tokens[ayah_id] = set(toks)

                    for tok in toks:
                        pos = len(self.stream)
                        self.stream.append(tok)
                        self.stream_ayah.append(ayah_id)
                        self.index.setdefault(tok, []).append(pos)

                        loose_tok = tok.translate(TR_LOOSE)
                        self.loose_stream.append(loose_tok)
                        self.loose_index.setdefault(loose_tok, []).append(pos)


# Lazy singleton index
_GLOBAL_INDEX: QuranCorpusIndex | None = None


def get_quran_index(
    surahs_path: Path | str = DEFAULT_SURAH_PATH,
    ayat_path: Path | str = DEFAULT_AYAT_PATH,
) -> QuranCorpusIndex:
    """Return singleton Quran corpus index."""
    global _GLOBAL_INDEX
    if _GLOBAL_INDEX is None:
        _GLOBAL_INDEX = QuranCorpusIndex(surahs_path, ayat_path)
    return _GLOBAL_INDEX


def find_quotes(text: str) -> list[tuple[int, int]]:
    """Return all ﴿…﴾ quote spans in text as (start, end) tuples.

    Offsets are in the original verbatim text, end exclusive, brackets included (C3).
    """
    if not text:
        return []
    return [(m.start(), m.end()) for m in QUOTE_RE.finditer(text)]


def parse_ref(
    text_after: str,
    index: QuranCorpusIndex | None = None,
) -> dict[str, Any] | None:
    """Parse a written reference «[سورة: آية]» right after the closing ﴾.

    Looks within 60 chars after ﴾. Handles Arabic-Indic digits, ranges (- – ، ,),
    and stray digits in the surah name.

    Returns dict with keys 'ref_text' and 'ayat', or None if no valid reference found.
    """
    if not text_after:
        return None

    m = REF_RE.match(text_after[:60])
    if not m:
        return None

    if index is None:
        index = get_quran_index()

    raw_name = m.group(1)
    # Strip stray digits in the surah name, e.g. «[٠الْفُرْقَانِ: ٧٢]»
    raw_name = re.sub(r"^[٠-٩0-9]+", "", raw_name).strip()
    norm_name, _ = normalize_with_map(raw_name)
    cleaned_name = norm_name.replace(" ", "")
    if cleaned_name.startswith("سوره"):
        cleaned_name = cleaned_name[4:]

    sid = index.surah_name_to_id.get(cleaned_name) or index.surah_name_to_id.get(
        cleaned_name[2:] if cleaned_name.startswith("ال") else ("ال" + cleaned_name)
    )
    if not sid:
        return None

    a = int(m.group(2).translate(AR_DIGITS))
    b = int((m.group(3) or m.group(2)).translate(AR_DIGITS))

    max_ayat = index.surah_ayah_counts.get(sid, 286)
    if not (1 <= a <= max_ayat and a <= b <= max_ayat):
        logger.info(
            "Invalid ayah range %d-%d for surah %d (max %d): %s",
            a,
            b,
            sid,
            max_ayat,
            ascii(m.group(0)),
        )
        return None

    ayat = [f"{sid}:{x}" for x in range(a, b + 1)]
    return {
        "ref_text": m.group(0).strip(),
        "ayat": ayat,
    }


def match_quote(
    quote: str,
    covers: list[str],
    ref: dict[str, Any] | None = None,
    index: QuranCorpusIndex | None = None,
) -> tuple[list[str], str, float]:
    """Match quote text to ayah(s) according to T4.4 preference order.

    Order of preference:
    1. written reference → its ayat (method: regex, confidence: 1.0);
    2. exact match inside the ayat the segment covers (ngram, 1.0);
    3. exact unique match in the whole Quran (ngram, 1.0); several matches →
       prefer segment's surah, else first in mushaf order (ngram, 0.5);
    4. looser key deleting ا ئ ؤ from both sides (ngram, 0.9);
    5. one-word quote only matches inside covered ayat; otherwise no link.

    Returns:
        (ayah_ids, method, confidence)
    """
    if index is None:
        index = get_quran_index()

    # 1. Written reference preference
    if ref and ref.get("ayat"):
        # Verify if text matches to log deviations if any
        return list(ref["ayat"]), METHOD_REGEX, CONF_EXACT

    # Strip inner footnotes [[...]] and quote brackets ﴿ ﴾
    inner = FOOTNOTE_INNER_RE.sub(" ", quote)
    inner = inner.strip("﴿﴾")
    tokens = clean_tokens(inner)
    if not tokens:
        return [], METHOD_NGRAM, 0.0

    seg_surah = int(covers[0].split(":")[0]) if covers else None

    # 5. One-word quote: only matches inside covered ayat; otherwise no link
    if len(tokens) == 1:
        tok = tokens[0]
        cands = [a for a in covers if a in index.ayah_tokens and tok in index.ayah_tokens[a]]
        if cands:
            return [cands[0]], METHOD_NGRAM, CONF_EXACT
        logger.info("One-word quote not in covered ayat (no link): %s", ascii(quote))
        return [], METHOD_NGRAM, 0.0

    # Find exact contiguous matches in the Quran token stream
    m = len(tokens)
    first_tok = tokens[0]
    candidate_positions = index.index.get(first_tok, [])
    matches: list[list[str]] = []
    for k in candidate_positions:
        if index.stream[k : k + m] == tokens:
            touched = list(dict.fromkeys(index.stream_ayah[k : k + m]))
            matches.append(touched)

    if matches:
        # 2. Exact match inside covered ayat
        cov_matches = [c for c in matches if any(a in covers for a in c)]
        if cov_matches:
            return cov_matches[0], METHOD_NGRAM, CONF_EXACT

        # 3. Exact unique match in the whole Quran
        if len(matches) == 1:
            return matches[0], METHOD_NGRAM, CONF_EXACT

        # Several matches: prefer segment's surah, else first in mushaf order
        if seg_surah is not None:
            surah_matches = [
                c for c in matches if any(int(a.split(":")[0]) == seg_surah for a in c)
            ]
            if surah_matches:
                logger.info("Ambiguous matches for quote, picked surah match: %s -> %s", ascii(quote), surah_matches[0])
                return surah_matches[0], METHOD_NGRAM, CONF_AMBIGUOUS

        logger.info("Ambiguous matches for quote, picked first in mushaf order: %s -> %s", ascii(quote), matches[0])
        return matches[0], METHOD_NGRAM, CONF_AMBIGUOUS

    # 4. Looser key deleting ا ئ ؤ from both sides
    loose_tokens = [t.translate(TR_LOOSE) for t in tokens]
    first_loose = loose_tokens[0]
    loose_candidates = index.loose_index.get(first_loose, [])
    loose_matches: list[list[str]] = []
    for k in loose_candidates:
        if index.loose_stream[k : k + m] == loose_tokens:
            touched = list(dict.fromkeys(index.stream_ayah[k : k + m]))
            loose_matches.append(touched)

    if loose_matches:
        cov_matches = [c for c in loose_matches if any(a in covers for a in c)]
        if cov_matches:
            return cov_matches[0], METHOD_NGRAM, CONF_LOOSE

        if len(loose_matches) == 1:
            return loose_matches[0], METHOD_NGRAM, CONF_LOOSE

        if seg_surah is not None:
            surah_matches = [
                c for c in loose_matches if any(int(a.split(":")[0]) == seg_surah for a in c)
            ]
            if surah_matches:
                logger.info("Ambiguous loose matches, picked surah match: %s -> %s", ascii(quote), surah_matches[0])
                return surah_matches[0], METHOD_NGRAM, CONF_LOOSE

        logger.info("Ambiguous loose matches, picked first in mushaf: %s -> %s", ascii(quote), loose_matches[0])
        return loose_matches[0], METHOD_NGRAM, CONF_LOOSE

    # No match
    logger.info("No match found for quote: %s", ascii(quote))
    return [], METHOD_NGRAM, 0.0


def extract_quran_spans(
    segments_path: Path | str | None = None,
    output_path: Path | str | None = None,
    surahs_path: Path | str | None = None,
    ayat_path: Path | str | None = None,
    source: str = DEFAULT_SOURCE,
) -> Path:
    """Extract all ﴿…﴾ Quran quotes and ayah links from tafsir segments into JSONL.

    Preserves deterministic segment order, then start offset.
    Each span record contains:
    - span_id: <segment_id>#<start>-<end>
    - segment_id: segment identifier
    - start: int (start offset)
    - end: int (end exclusive offset)
    - type: "QURAN"
    - parent: None (null in JSON, set in T4.6)
    - source: provenance source string
    - method: "regex"
    - confidence: 1.0
    - ref_text: optional written reference string if present
    - links: list of {ayah_id, rel, method, confidence, ref_text?}

    Returns the written Path.
    """
    in_path = Path(segments_path) if segments_path else DEFAULT_SEGMENTS_PATH
    out_path = Path(output_path) if output_path else DEFAULT_OUTPUT_PATH

    if not in_path.exists():
        raise FileNotFoundError(
            f"Missing segments file: {in_path}. Run 'python scripts/tasks.py parse' first."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    index = get_quran_index(
        surahs_path or DEFAULT_SURAH_PATH,
        ayat_path or DEFAULT_AYAT_PATH,
    )

    total_spans = 0
    linked_spans = 0
    unlinked_spans = 0

    with in_path.open("r", encoding="utf-8") as in_f, out_path.open(
        "w", encoding="utf-8", newline="\n"
    ) as out_f:
        for line in in_f:
            line = line.strip()
            if not line:
                continue
            seg = json.loads(line)
            segment_id = seg["segment_id"]
            covers = seg.get("covers", [])
            text = seg.get("text", "")

            matches = find_quotes(text)
            for start, end in matches:
                q_text = text[start:end]
                after = text[end : end + 60]
                ref = parse_ref(after, index=index)
                ayah_ids, method, conf = match_quote(
                    q_text, covers, ref=ref, index=index
                )

                links = []
                for a in ayah_ids:
                    rel = "EXPLAINS" if a in covers else "CITES"
                    link_rec: dict[str, Any] = {
                        "ayah_id": a,
                        "confidence": conf,
                        "method": method,
                        "rel": rel,
                    }
                    if ref and ref.get("ref_text"):
                        link_rec["ref_text"] = ref["ref_text"]
                    links.append(link_rec)

                span_record: dict[str, Any] = {
                    "confidence": CONF_EXACT,
                    "end": end,
                    "links": links,
                    "method": METHOD_REGEX,
                    "parent": None,
                    "segment_id": segment_id,
                    "source": source,
                    "span_id": f"{segment_id}#{start}-{end}",
                    "start": start,
                    "type": SPAN_TYPE_QURAN,
                }
                if ref and ref.get("ref_text"):
                    span_record["ref_text"] = ref["ref_text"]

                out_f.write(json.dumps(span_record, ensure_ascii=False, sort_keys=True) + "\n")
                total_spans += 1
                if links:
                    linked_spans += 1
                else:
                    unlinked_spans += 1

    logger.info(
        "Extracted %d QURAN spans (%d linked, %d unlinked) into %s",
        total_spans,
        linked_spans,
        unlinked_spans,
        out_path,
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract ﴿…﴾ Quran quotes and links from Ibn Kathir segments.")
    parser.add_argument(
        "--segments",
        type=Path,
        default=DEFAULT_SEGMENTS_PATH,
        help="Path to segments.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Path to output quran.jsonl",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=DEFAULT_SOURCE,
        help="Provenance source tag",
    )
    args = parser.parse_args()
    out = extract_quran_spans(args.segments, args.output, source=args.source)
    print(f"Quran spans written to {out}")


if __name__ == "__main__":
    main()
