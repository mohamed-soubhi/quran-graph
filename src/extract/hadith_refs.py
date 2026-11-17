"""Footnote hadith reference extraction and linking (T5.2).

Deterministic parsing of editor footnote citations, such as «صحيح البخاري برقم (٤٧٧٧)».
Resolves citations to Hadith nodes, following Decision D1 (Muslim narrations).
"""

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extract.normalize import normalize_with_map

DEFAULT_HADITH_PATH = ROOT / "data" / "interim" / "hadith" / "hadith.jsonl"
DEFAULT_FOOTNOTES_PATH = ROOT / "data" / "interim" / "spans" / "footnotes.jsonl"
DEFAULT_PARENTS_PATH = ROOT / "data" / "interim" / "spans" / "parents.jsonl"
DEFAULT_HADITH_SPANS_PATH = ROOT / "data" / "interim" / "spans" / "hadith.jsonl"
DEFAULT_SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
DEFAULT_OUTPUT_LINKS_PATH = ROOT / "data" / "interim" / "links" / "footnote_links.jsonl"
DEFAULT_OUTPUT_UNLINKED_PATH = ROOT / "data" / "interim" / "links" / "footnote_refs_unlinked.jsonl"

SOURCE_TAG = "run:20261117-0000-footnote-links"

ARABIC_INDIC_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def to_ascii_digits(s: str) -> str:
    """Convert Arabic-Indic digits to ASCII digits."""
    return s.translate(ARABIC_INDIC_MAP)


COLLECTIONS_ORDER = [
    "nasai_kubra",
    "bukhari",
    "muslim",
    "abudawud",
    "tirmidhi",
    "ibnmajah",
    "nasai",
]

COLLECTION_REGEXES = {
    "nasai_kubra": r"(?:سنن\s+النسائي\s+الكبر[ىي]|النسائي\s+في\s+(?:السنن\s+)?الكبر[ىي]|السنن\s+الكبر[ىي]\s+للنسائي)",
    "bukhari": r"(?:صحيح\s+البخاري|البخاري\s+في\s+صحيحه|البخاري)",
    "muslim": r"(?:صحيح\s+مسلم|مسلم\s+في\s+صحيحه|مسلم)",
    "abudawud": r"(?:سنن\s+أبي\s+داود|أبو\s+داود\s+في\s+(?:السنن|سننه)|أبو\s+داود)",
    "tirmidhi": r"(?:سنن\s+الترمذي|الترمذي\s+في\s+(?:السنن|سننه|جامعه)|الترمذي)",
    "ibnmajah": r"(?:سنن\s+ابن\s+ماج[هة]|ابن\s+ماج[هة]\s+في\s+(?:السنن|سننه)|ابن\s+ماج[هة])",
    "nasai": r"(?:سنن\s+النسائي|النسائي\s+في\s+(?:السنن|سننه)|النسائي)",
}

# Negative lookbehind ensures collection name is not preceded by an Arabic letter (e.g. للبخاري is rejected).
# Optional conjunction 'و' is allowed before collection names.
_PREFIX = r"(?<![\u0621-\u064A\u0671-\u06D3])(?:و)?"
COMPILED_PATTERNS = []
for _col in COLLECTIONS_ORDER:
    _c_pat = COLLECTION_REGEXES[_col]
    _full_pat = (
        _PREFIX +
        r"(" + _c_pat + r")" +
        r"\s+برقم\s*\(\s*([0-9٠-٩]+(?:\s*[،,]\s*[0-9٠-٩]+)*)\s*\)"
    )
    COMPILED_PATTERNS.append((_col, re.compile(_full_pat)))

EXTRA_RAQAM_RE = re.compile(r'^\s*و\s*برقم\s*\(\s*([0-9٠-٩]+(?:\s*[،,]\s*[0-9٠-٩]+)*)\s*\)')
AFTER_PUNCT_RE = re.compile(r'^[\s.,،:؛"»)]*$')


@dataclass(frozen=True)
class Ref:
    collection: str
    number: str
    ref_text: str


def _extract_numbers(s: str) -> list[str]:
    nums = re.findall(r'[0-9٠-٩]+', s)
    return [to_ascii_digits(n) for n in nums]


def parse_refs(footnote_text: str) -> list[Ref]:
    """Parse collection references from a footnote text.
    
    Collection patterns are tried in the specified order:
    nasai_kubra, bukhari, muslim, abudawud, tirmidhi, ibnmajah, nasai.
    A footnote position already matched is not matched again.
    """
    matched_spans: list[tuple[int, int]] = []
    # (start_pos, ref)
    raw_refs: list[tuple[int, Ref]] = []

    for col, pat in COMPILED_PATTERNS:
        for m in pat.finditer(footnote_text):
            m_start, m_end = m.span()
            if any(max(m_start, s) < min(m_end, e) for s, e in matched_spans):
                continue

            full_end = m_end
            extra_num_lists = []
            while True:
                sub = footnote_text[full_end:]
                m_extra = EXTRA_RAQAM_RE.match(sub)
                if m_extra:
                    extra_num_lists.append(m_extra.group(1))
                    full_end += m_extra.end()
                else:
                    break

            matched_spans.append((m_start, full_end))
            matched_text = footnote_text[m_start:full_end]

            primary_nums = _extract_numbers(m.group(2))
            for n in primary_nums:
                raw_refs.append((m_start, Ref(col, n, matched_text)))

            for extra_str in extra_num_lists:
                for n in _extract_numbers(extra_str):
                    raw_refs.append((m_start, Ref(col, n, matched_text)))

    # Stable sort by start position in text, preserving extraction order of numbers
    raw_refs.sort(key=lambda item: item[0])
    return [r for _, r in raw_refs]


def owner(
    footnote: dict,
    parent_map: dict[str, tuple[str, str]],
    hadith_by_seg: dict[str, list[dict]],
    segments: dict[str, str],
) -> Optional[str]:
    """Find the owning HADITH span for a footnote, or None if unattached.
    
    Rule:
    1. Inside wins: the footnote has a HADITH ancestor in parent_map.
    2. After: the footnote starts right after a HADITH span's end with only [\\s.,،:؛\"»)]* between them.
    """
    fn_id = footnote["span_id"]
    seg_id = footnote["segment_id"]
    fn_start = footnote["start"]

    # 1. Inside: follow parent chain
    curr = fn_id
    while curr in parent_map:
        p_id, p_type = parent_map[curr]
        if p_type == "HADITH":
            return p_id
        curr = p_id

    # 2. After: starts right after HADITH span in same segment
    seg_hadiths = hadith_by_seg.get(seg_id, [])
    seg_text = segments.get(seg_id, "")
    for h in seg_hadiths:
        if h["end"] <= fn_start:
            between = seg_text[h["end"]:fn_start]
            if AFTER_PUNCT_RE.match(between):
                return h["span_id"]

    return None


def resolve(
    ref: Ref,
    hadith_ids: set[str],
    muslim_arabic: dict[str, list[str]],
) -> tuple[list[str], Optional[str]]:
    """Resolve a Ref to a list of Hadith IDs, or return reason for no match."""
    col = ref.collection
    num = ref.number

    if col == "nasai_kubra":
        return ([], "not_in_sources")
    elif col == "muslim":
        hits = muslim_arabic.get(num, [])
        if hits:
            return (hits, None)
        return ([], "not_found")
    else:
        hid = f"{col}:{num}"
        if hid in hadith_ids:
            return ([hid], None)
        return ([], "not_found")


def compute_4gram_sim(span_clean_norm: str, hadith_clean_norm: str) -> float:
    """Compute 4-gram containment similarity: |A ∩ B| / min(|A|, |B|)."""
    if len(span_clean_norm) < 4 or len(hadith_clean_norm) < 4:
        return 0.0
    grams_a = {span_clean_norm[i:i+4] for i in range(len(span_clean_norm) - 3)}
    grams_b = {hadith_clean_norm[i:i+4] for i in range(len(hadith_clean_norm) - 3)}
    intersection = len(grams_a & grams_b)
    denom = min(len(grams_a), len(grams_b))
    if denom == 0:
        return 0.0
    return round(intersection / denom, 4)


def clean_span_text(raw_text: str) -> str:
    """Normalize span text with footnotes removed and whitespace collapsed."""
    no_fn = re.sub(r'\[\[.*?\]\]', '', raw_text, flags=re.DOTALL)
    norm, _ = normalize_with_map(no_fn)
    return re.sub(r'\s+', '', norm)


def build_footnote_links(
    hadith_path: Path = DEFAULT_HADITH_PATH,
    footnotes_path: Path = DEFAULT_FOOTNOTES_PATH,
    parents_path: Path = DEFAULT_PARENTS_PATH,
    hadith_spans_path: Path = DEFAULT_HADITH_SPANS_PATH,
    segments_path: Path = DEFAULT_SEGMENTS_PATH,
    output_links_path: Path = DEFAULT_OUTPUT_LINKS_PATH,
    output_unlinked_path: Path = DEFAULT_OUTPUT_UNLINKED_PATH,
    source_tag: str = SOURCE_TAG,
) -> dict:
    """Build footnote links JSONL and unlinked references JSONL, and return summary counts."""
    # 1. Load hadith data
    hadith_ids = set()
    muslim_arabic: dict[str, list[str]] = {}
    hadith_clean_norm: dict[str, str] = {}

    with open(hadith_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            hid = rec["hadith_id"]
            hadith_ids.add(hid)
            hadith_clean_norm[hid] = re.sub(r'\s+', '', rec["text_norm"])
            if rec["collection"] == "muslim":
                an = rec.get("arabic_number")
                if an:
                    base = an.split(".")[0]
                    muslim_arabic.setdefault(base, []).append(hid)

    # 2. Load segments
    segments: dict[str, str] = {}
    with open(segments_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            seg = json.loads(line)
            segments[seg["segment_id"]] = seg["text"]

    # 3. Load parents
    parent_map: dict[str, tuple[str, str]] = {}
    with open(parents_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            parent_map[row["span_id"]] = (row["parent"], row["parent_type"])

    # 4. Load hadith spans
    hadith_spans: dict[str, dict] = {}
    hadith_by_seg: dict[str, list[dict]] = {}
    with open(hadith_spans_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            h = json.loads(line)
            hadith_spans[h["span_id"]] = h
            hadith_by_seg.setdefault(h["segment_id"], []).append(h)

    for seg_id in hadith_by_seg:
        hadith_by_seg[seg_id].sort(key=lambda s: (s["start"], s["end"]))

    # 5. Load footnotes
    footnotes: list[dict] = []
    with open(footnotes_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            footnotes.append(json.loads(line))

    # Pre-clean span text cache
    span_clean_cache: dict[str, str] = {}

    def get_clean_span(span_id: str) -> str:
        if span_id not in span_clean_cache:
            h = hadith_spans[span_id]
            seg_text = segments[h["segment_id"]]
            raw = seg_text[h["start"]:h["end"]]
            span_clean_cache[span_id] = clean_span_text(raw)
        return span_clean_cache[span_id]

    links_acc: dict[tuple[str, str], dict] = {}
    unlinked_rows: list[dict] = []

    resolved_counts = {c: 0 for c in COLLECTIONS_ORDER}
    not_found_counts = {c: 0 for c in COLLECTIONS_ORDER}
    kubra_attached_count = 0
    kubra_unattached_count = 0
    unattached_our_count = 0

    for fn in footnotes:
        seg_text = segments.get(fn["segment_id"], "")
        fn_text = seg_text[fn["start"]:fn["end"]]
        refs = parse_refs(fn_text)
        if not refs:
            continue

        fn_owner = owner(fn, parent_map, hadith_by_seg, segments)

        for ref in refs:
            col = ref.collection
            num = ref.number

            if fn_owner:
                hits, reason = resolve(ref, hadith_ids, muslim_arabic)
                if hits:
                    resolved_counts[col] += 1
                    kind = "arabicnumber" if col == "muslim" else "hadithnumber"
                    for hid in hits:
                        key = (fn_owner, hid)
                        if key not in links_acc:
                            links_acc[key] = {
                                "evidence": set(),
                                "ref_text": set(),
                                "number_kind": kind,
                            }
                        links_acc[key]["evidence"].add(fn["span_id"])
                        links_acc[key]["ref_text"].add(ref.ref_text)
                else:
                    if col == "nasai_kubra":
                        kubra_attached_count += 1
                    else:
                        not_found_counts[col] += 1
                    unlinked_rows.append({
                        "footnote_id": fn["span_id"],
                        "span_id": fn_owner,
                        "collection": col,
                        "number": num,
                        "ref_text": ref.ref_text,
                        "reason": reason,
                    })
            else:
                if col == "nasai_kubra":
                    kubra_unattached_count += 1
                else:
                    unattached_our_count += 1
                unlinked_rows.append({
                    "footnote_id": fn["span_id"],
                    "span_id": None,
                    "collection": col,
                    "number": num,
                    "ref_text": ref.ref_text,
                    "reason": "unattached",
                })

    # Prepare links rows
    links_rows: list[dict] = []
    pairs_by_col = {c: 0 for c in COLLECTIONS_ORDER}
    distinct_spans = set()
    distinct_hadiths = set()

    for (sid, hid), data in links_acc.items():
        s_clean = get_clean_span(sid)
        h_clean = hadith_clean_norm.get(hid, "")
        sim = compute_4gram_sim(s_clean, h_clean)

        col = hid.split(":")[0]
        pairs_by_col[col] = pairs_by_col.get(col, 0) + 1
        distinct_spans.add(sid)
        distinct_hadiths.add(hid)

        links_rows.append({
            "span_id": sid,
            "hadith_id": hid,
            "evidence": sorted(list(data["evidence"])),
            "ref_text": sorted(list(data["ref_text"])),
            "number_kind": data["number_kind"],
            "outcome": "auto",
            "method": "regex",
            "confidence": 0.95,
            "source": source_tag,
            "text_sim": sim,
        })

    # Sort deterministically
    links_rows.sort(key=lambda r: (r["span_id"], r["hadith_id"]))
    unlinked_rows.sort(key=lambda r: (r["footnote_id"], r["collection"], r["number"]))

    # Write output files
    output_links_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_links_path, "w", encoding="utf-8") as f:
        for r in links_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    output_unlinked_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_unlinked_path, "w", encoding="utf-8") as f:
        for r in unlinked_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_resolved = sum(resolved_counts[c] for c in ["bukhari", "muslim", "tirmidhi", "abudawud", "ibnmajah", "nasai"])
    stats = {
        "resolved": resolved_counts,
        "not_found": not_found_counts,
        "total_resolved": total_resolved,
        "kubra_attached": kubra_attached_count,
        "kubra_unattached": kubra_unattached_count,
        "unattached_our": unattached_our_count,
        "distinct_pairs": len(links_rows),
        "distinct_spans": len(distinct_spans),
        "distinct_hadiths": len(distinct_hadiths),
        "pairs_by_col": pairs_by_col,
        "unlinked_count": len(unlinked_rows),
    }

    # Print summary matching Facts table shape
    print("\nCollection   | Resolved refs | Not found")
    print("----------------------------------------")
    for c in ["bukhari", "muslim", "tirmidhi", "abudawud", "ibnmajah", "nasai"]:
        print(f"{c:12s} | {resolved_counts[c]:13,d} | {not_found_counts[c]:9,d}")

    print(
        f"Total resolved: {total_resolved:,d}. Plus {kubra_attached_count:,d} Kubra (not linkable) "
        f"and {unattached_our_count:,d} references to our collections in footnotes not attached to any HADITH span "
        f"(+{kubra_unattached_count:,d} Kubra)."
    )
    print(
        f"Distinct pairs: {len(links_rows):,d} on {len(distinct_spans):,d} HADITH spans, "
        f"pointing to {len(distinct_hadiths):,d} distinct hadith."
    )
    pairs_str = ", ".join(f"{c} {pairs_by_col[c]:,d}" for c in ["muslim", "bukhari", "tirmidhi", "abudawud", "ibnmajah"])
    print(f"Pairs by collection: {pairs_str}.")

    return stats


if __name__ == "__main__":
    build_footnote_links()
