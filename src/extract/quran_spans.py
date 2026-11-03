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
CONF_SKELETON = 0.8
CONF_AMBIGUOUS = 0.5
SPAN_TYPE_QURAN = "QURAN"
CLITICS: tuple[str, ...] = ("\u0648", "\u0641", "\u0628", "\u0644")  # و, ف, ب, ل
TR_SKELETON: dict[int, None] = str.maketrans(
    "", "", "\u0627\u0626\u0624\u0648\u064a\u0649"
)  # loose + delete و, ي, ى


def clean_tokens(text: str) -> list[str]:
    """Normalize Arabic text using v2 normalizer and split into clean alphanumeric tokens."""
    norm, _ = normalize_with_map(text)
    clean = "".join(c if c.isalnum() else " " for c in norm)
    return clean.split()


def skel_tokens_from_text(text: str) -> list[str]:
    """Transform text for skeleton matching: map ة->ت, ص->س, then loose key + delete و ي ى."""
    t = text.replace("ة", "ت").replace("ص", "س")
    toks = clean_tokens(t)
    return [tok.translate(TR_SKELETON) for tok in toks]


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
        self.suffix_map: dict[str, list[str]] = {}

        self.loose_stream: list[str] = []
        self.loose_index: dict[str, list[int]] = {}
        self.loose_suffix_map: dict[str, list[str]] = {}

        self.skel_stream: list[str] = []
        self.skel_index: dict[str, list[int]] = {}
        self.ayah_stream_range: dict[str, tuple[int, int]] = {}

        if self.ayat_path.exists():
            with self.ayat_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    a = json.loads(line)
                    ayah_id = a["ayah_id"]
                    raw_text = a.get("text_simple", "")
                    toks = clean_tokens(raw_text)
                    self.ayah_tokens[ayah_id] = set(toks)

                    pos_start = len(self.stream)
                    for tok in toks:
                        pos = len(self.stream)
                        self.stream.append(tok)
                        self.stream_ayah.append(ayah_id)
                        self.index.setdefault(tok, []).append(pos)

                        loose_tok = tok.translate(TR_LOOSE)
                        self.loose_stream.append(loose_tok)
                        self.loose_index.setdefault(loose_tok, []).append(pos)
                    self.ayah_stream_range[ayah_id] = (pos_start, len(self.stream))

                    sk_toks = skel_tokens_from_text(raw_text)
                    for sk_tok in sk_toks:
                        sk_pos = len(self.skel_stream)
                        self.skel_stream.append(sk_tok)
                        self.skel_index.setdefault(sk_tok, []).append(sk_pos)

        # Precompute suffix maps for edge token lookup (R3)
        for w in self.index:
            for i in range(1, len(w)):
                self.suffix_map.setdefault(w[i:], []).append(w)
        for w in self.loose_index:
            for i in range(1, len(w)):
                self.loose_suffix_map.setdefault(w[i:], []).append(w)


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


def get_exact_candidates(
    tokens: list[str], index: QuranCorpusIndex, edge: bool = False
) -> list[tuple[int, bool]]:
    """Return stream positions matching tokens exactly (and optionally with edge tokens)."""
    m = len(tokens)
    t0 = tokens[0]
    tm = tokens[-1]
    res: list[tuple[int, bool]] = []

    for k in index.index.get(t0, []):
        if k + m <= len(index.stream):
            if not edge:
                if index.stream[k : k + m] == tokens:
                    res.append((k, False))
            else:
                st = index.stream[k : k + m]
                if (st[-1] == tm or st[-1].startswith(tm)) and (m <= 2 or st[1:-1] == tokens[1:-1]):
                    res.append((k, st[-1] != tm))

    if edge:
        for w in index.suffix_map.get(t0, []):
            for k in index.index.get(w, []):
                if k + m <= len(index.stream):
                    st = index.stream[k : k + m]
                    if (st[-1] == tm or st[-1].startswith(tm)) and (m <= 2 or st[1:-1] == tokens[1:-1]):
                        res.append((k, True))
    return res


def get_loose_candidates(
    loose_tokens: list[str], index: QuranCorpusIndex, edge: bool = False
) -> list[tuple[int, bool]]:
    """Return stream positions matching loose tokens (and optionally with edge tokens)."""
    m = len(loose_tokens)
    t0 = loose_tokens[0]
    tm = loose_tokens[-1]
    res: list[tuple[int, bool]] = []

    for k in index.loose_index.get(t0, []):
        if k + m <= len(index.loose_stream):
            if not edge:
                if index.loose_stream[k : k + m] == loose_tokens:
                    res.append((k, False))
            else:
                st = index.loose_stream[k : k + m]
                if (st[-1] == tm or st[-1].startswith(tm)) and (m <= 2 or st[1:-1] == loose_tokens[1:-1]):
                    res.append((k, st[-1] != tm))

    if edge:
        for w in index.loose_suffix_map.get(t0, []):
            for k in index.loose_index.get(w, []):
                if k + m <= len(index.loose_stream):
                    st = index.loose_stream[k : k + m]
                    if (st[-1] == tm or st[-1].startswith(tm)) and (m <= 2 or st[1:-1] == loose_tokens[1:-1]):
                        res.append((k, True))
    return res


def get_skel_candidates(
    skel_tokens: list[str], index: QuranCorpusIndex
) -> list[int]:
    """Return stream positions matching skeleton tokens."""
    m = len(skel_tokens)
    first_ne = next((i for i, t in enumerate(skel_tokens) if t), None)
    if first_ne is None:
        return []
    anchor = skel_tokens[first_ne]
    res: list[int] = []
    for pos in index.skel_index.get(anchor, []):
        k = pos - first_ne
        if 0 <= k and k + m <= len(index.skel_stream):
            if index.skel_stream[k : k + m] == skel_tokens:
                res.append(k)
    return res


def first_token_matches_clitic(q0: str, s0: str) -> bool:
    """Return True if first quote token matches first Quran token with clitic / R3 edge rules.

    Matches if identical, if Quran token ends with quote token (mid-word or ayah has leading clitic),
    or if quote token has a leading clitic و/ف/ب/ل and ayah does not.
    """
    if q0 == s0:
        return True
    if s0.endswith(q0):
        return True
    if len(q0) > 1 and q0[0] in CLITICS and q0[1:] == s0:
        return True
    return False


def last_token_matches_edge(qm: str, sm: str) -> bool:
    """Return True if last quote token matches last Quran token with R3 edge rules (exact or startswith)."""
    if qm == sm:
        return True
    if sm.startswith(qm):
        return True
    return False


def matches_ref_with_clitic(
    tokens: list[str],
    ref_ayat: list[str],
    index: QuranCorpusIndex,
    allow_skel: bool = False,
    inner_text: str = "",
) -> bool:
    """Check if quote tokens match within the referenced ayat allowing dropped/added clitic and R3 edge tokens."""
    m = len(tokens)
    valid_ayat = [a for a in ref_ayat if a in index.ayah_stream_range]
    if not valid_ayat:
        return False
    ref_set = set(valid_ayat)

    if m == 1:
        tok = tokens[0]
        tok_loose = tok.translate(TR_LOOSE)
        for a in valid_ayat:
            c_toks = index.ayah_tokens.get(a, set())
            for c in c_toks:
                if first_token_matches_clitic(tok, c):
                    return True
                if first_token_matches_clitic(tok_loose, c.translate(TR_LOOSE)):
                    return True
        return False

    k_min = max(0, min(index.ayah_stream_range[a][0] for a in valid_ayat) - m + 1)
    k_max = min(len(index.stream) - m, max(index.ayah_stream_range[a][1] for a in valid_ayat))

    loose_tokens = [t.translate(TR_LOOSE) for t in tokens]
    skel_tokens = skel_tokens_from_text(inner_text) if (m >= 3 and allow_skel) else []

    for k in range(k_min, k_max + 1):
        hit_ayat = index.stream_ayah[k : k + m]
        if not any(a in ref_set for a in hit_ayat):
            continue

        # 1. Exact with clitic / R3 edge
        st = index.stream[k : k + m]
        if first_token_matches_clitic(tokens[0], st[0]) and last_token_matches_edge(tokens[-1], st[-1]):
            if m <= 2 or tokens[1:-1] == st[1:-1]:
                return True

        # 2. Loose with clitic / R3 edge
        st_loose = index.loose_stream[k : k + m]
        if first_token_matches_clitic(loose_tokens[0], st_loose[0]) and last_token_matches_edge(loose_tokens[-1], st_loose[-1]):
            if m <= 2 or loose_tokens[1:-1] == st_loose[1:-1]:
                return True

        # 3. Skeleton with clitic / R3 edge (only if allow_skel is True)
        if allow_skel and m >= 3 and skel_tokens:
            st_skel = index.skel_stream[k : k + m]
            if first_token_matches_clitic(skel_tokens[0], st_skel[0]) and last_token_matches_edge(skel_tokens[-1], st_skel[-1]):
                if m <= 2 or skel_tokens[1:-1] == st_skel[1:-1]:
                    return True

    return False


def match_quote(
    quote: str,
    covers: list[str],
    ref: dict[str, Any] | None = None,
    index: QuranCorpusIndex | None = None,
) -> tuple[list[str], str, float]:
    """Match quote text to ayah(s) according to T4.4 (with R1-R4) preference order.

    Order of preference:
    1. Written reference verification (R1):
       - If quote text (exact or loose) occurs in referenced ayat → reference links (regex, 1.0).
       - If quote text matches in Quran but NOT in referenced ayat → link text match instead,
         preferring occurrence in referenced surah nearest to referenced ayah (ngram, 0.9), keeping ref_text.
       - If quote text has no Quran match anywhere (spelling variant) → trust reference (regex, 1.0).
    2. One-word quote (R3): only matches inside covered ayat (exact or with prefix و/ف/ب/ل); otherwise no link.
    3. Multi-word exact match (without edge tokens): covered ayat (1.0), unique (1.0), ambiguous surah/mushaf (0.5).
    4. Multi-word exact match with edge tokens (R3): first token endswith, last startswith.
    5. Multi-word loose match (TR_LOOSE): covered (0.9), unique (0.9), ambiguous (0.5, R4).
    6. Multi-word loose match with edge tokens (R3).
    7. Multi-word skeleton match (quotes >= 3 words, R2): loose + delete و ي ى, map ة→ت, ص→س.
       Accept only inside covered ayat (0.8 / 0.5), in referenced surah (0.8 / 0.5), or unique (0.8).
    8. No match → return ([], ngram, 0.0). No guessing.

    Returns:
        (ayah_ids, method, confidence)
    """
    if index is None:
        index = get_quran_index()

    inner = FOOTNOTE_INNER_RE.sub(" ", quote).strip("﴿﴾")
    tokens = clean_tokens(inner)
    if not tokens:
        return [], METHOD_NGRAM, 0.0

    m = len(tokens)
    seg_surah = int(covers[0].split(":")[0]) if covers else None
    ref_ayat = ref.get("ayat", []) if ref else []
    ref_surah = int(ref_ayat[0].split(":")[0]) if ref_ayat else None
    ref_ayah = int(ref_ayat[0].split(":")[1]) if ref_ayat else None

    # --- 1-word quotes (R3) ---
    if m == 1:
        tok = tokens[0]
        # Exact inside covered ayat
        cands = [a for a in covers if a in index.ayah_tokens and tok in index.ayah_tokens[a]]
        if cands:
            if ref_ayat:
                if any(a in ref_ayat for a in cands) or any(
                    tok in index.ayah_tokens.get(a, set()) for a in ref_ayat
                ):
                    return list(ref_ayat), METHOD_REGEX, CONF_EXACT
            return [cands[0]], METHOD_NGRAM, CONF_EXACT

        # With prefix و/ف/ب/ل in covered ayat (R3)
        pref_cands = []
        for a in covers:
            c_toks = index.ayah_tokens.get(a, set())
            if any((p + tok) in c_toks for p in ("و", "ف", "ب", "ل")):
                pref_cands.append(a)
        if pref_cands:
            if ref_ayat:
                if any(a in ref_ayat for a in pref_cands):
                    return list(ref_ayat), METHOD_REGEX, CONF_EXACT
            return [pref_cands[0]], METHOD_NGRAM, CONF_EXACT

        # If ref was given, check if tok occurs in ref_ayat (exact or with prefix)
        if ref_ayat:
            for a in ref_ayat:
                c_toks = index.ayah_tokens.get(a, set())
                if tok in c_toks or any((p + tok) in c_toks for p in CLITICS):
                    return list(ref_ayat), METHOD_REGEX, CONF_EXACT
            if matches_ref_with_clitic(tokens, ref_ayat, index, allow_skel=False, inner_text=inner):
                return list(ref_ayat), METHOD_REGEX, CONF_EXACT
            logger.info("One-word quote with reference not in ref ayat: %s -> %s", ascii(quote), ref_ayat)
            return [], METHOD_NGRAM, 0.0

        logger.info("One-word quote not in covered ayat (no link): %s", ascii(quote))
        return [], METHOD_NGRAM, 0.0

    # --- Multi-word quotes ---
    # 1. Exact matches (without edge tokens)
    exact_cand = get_exact_candidates(tokens, index, edge=False)
    exact_matches = [list(dict.fromkeys(index.stream_ayah[k : k + m])) for k, _ in exact_cand]

    # 2. Exact matches with edge tokens (R3)
    edge_exact_matches: list[list[str]] = []
    if not exact_matches:
        edge_cand = get_exact_candidates(tokens, index, edge=True)
        edge_exact_matches = [list(dict.fromkeys(index.stream_ayah[k : k + m])) for k, _ in edge_cand]

    # 3. Loose matches
    loose_tokens = [t.translate(TR_LOOSE) for t in tokens]
    loose_matches: list[list[str]] = []
    if not exact_matches and not edge_exact_matches:
        l_cand = get_loose_candidates(loose_tokens, index, edge=False)
        loose_matches = [list(dict.fromkeys(index.stream_ayah[k : k + m])) for k, _ in l_cand]

    # 4. Loose matches with edge tokens (R3)
    edge_loose_matches: list[list[str]] = []
    if not exact_matches and not edge_exact_matches and not loose_matches:
        l_edge_cand = get_loose_candidates(loose_tokens, index, edge=True)
        edge_loose_matches = [list(dict.fromkeys(index.stream_ayah[k : k + m])) for k, _ in l_edge_cand]

    # 5. Skeleton matches (only if m >= 3, R2)
    skel_tokens = skel_tokens_from_text(inner)
    skel_matches: list[list[str]] = []
    if m >= 3 and not (exact_matches or edge_exact_matches or loose_matches or edge_loose_matches):
        sk_cand = get_skel_candidates(skel_tokens, index)
        skel_matches = [list(dict.fromkeys(index.stream_ayah[k : k + m])) for k in sk_cand]

    all_hits = exact_matches or edge_exact_matches or loose_matches or edge_loose_matches or skel_matches

    # R1: Reference check
    if ref and ref_ayat:
        ref_set = set(ref_ayat)
        if all_hits:
            # Does text match occur in ref_ayat?
            if any(set(h) & ref_set for h in all_hits):
                return list(ref_ayat), METHOD_REGEX, CONF_EXACT

            # T4.4b: Allow a dropped or added clitic with R3 edge-token logic (finding E1)
            has_exact_or_loose = bool(exact_matches or edge_exact_matches or loose_matches or edge_loose_matches)
            if matches_ref_with_clitic(tokens, ref_ayat, index, allow_skel=not has_exact_or_loose, inner_text=inner):
                return list(ref_ayat), METHOD_REGEX, CONF_EXACT

            # Text matches exist, but NONE occur in ref_ayat -> edition typo in written reference!
            logger.info(
                "Reference typo detected for %s: ref=%s (%s), text hits in surah=%s",
                ascii(quote),
                ref.get("ref_text"),
                ref_ayat,
                [h for h in all_hits if any(int(a.split(":")[0]) == ref_surah for a in h)],
            )
            surah_hits = [h for h in all_hits if any(int(a.split(":")[0]) == ref_surah for a in h)]
            if surah_hits and ref_ayah is not None:
                picked = min(surah_hits, key=lambda h: min(abs(int(a.split(":")[1]) - ref_ayah) for a in h))
                return picked, METHOD_NGRAM, CONF_LOOSE
            else:
                cov_hits = [h for h in all_hits if any(a in covers for a in h)]
                if cov_hits:
                    return cov_hits[0], METHOD_NGRAM, CONF_LOOSE
                if len(all_hits) == 1:
                    return all_hits[0], METHOD_NGRAM, CONF_LOOSE
                if seg_surah is not None:
                    seg_hits = [h for h in all_hits if any(int(a.split(":")[0]) == seg_surah for a in h)]
                    if seg_hits:
                        return seg_hits[0], METHOD_NGRAM, CONF_LOOSE
                return all_hits[0], METHOD_NGRAM, CONF_LOOSE
        else:
            # No text match anywhere in Quran (spelling variant): check skeleton on ref_ayat or trust reference
            if m >= 3 and matches_ref_with_clitic(tokens, ref_ayat, index, allow_skel=True, inner_text=inner):
                return list(ref_ayat), METHOD_REGEX, CONF_EXACT
            return list(ref_ayat), METHOD_REGEX, CONF_EXACT

    # No reference or reference not applicable:
    cur_exact = exact_matches or edge_exact_matches
    if cur_exact:
        cov = [c for c in cur_exact if any(a in covers for a in c)]
        if cov:
            return cov[0], METHOD_NGRAM, CONF_EXACT
        if len(cur_exact) == 1:
            return cur_exact[0], METHOD_NGRAM, CONF_EXACT
        if seg_surah is not None:
            surah_c = [c for c in cur_exact if any(int(a.split(":")[0]) == seg_surah for a in c)]
            if surah_c:
                logger.info("Ambiguous exact matches, picked surah match: %s -> %s", ascii(quote), surah_c[0])
                return surah_c[0], METHOD_NGRAM, CONF_AMBIGUOUS
        logger.info("Ambiguous exact matches, picked first in mushaf: %s -> %s", ascii(quote), cur_exact[0])
        return cur_exact[0], METHOD_NGRAM, CONF_AMBIGUOUS

    cur_loose = loose_matches or edge_loose_matches
    if cur_loose:
        cov = [c for c in cur_loose if any(a in covers for a in c)]
        if cov:
            return cov[0], METHOD_NGRAM, CONF_LOOSE
        if len(cur_loose) == 1:
            return cur_loose[0], METHOD_NGRAM, CONF_LOOSE
        # R4: Ambiguous loose -> 0.5!
        if seg_surah is not None:
            surah_c = [c for c in cur_loose if any(int(a.split(":")[0]) == seg_surah for a in c)]
            if surah_c:
                logger.info("Ambiguous loose matches, picked surah match: %s -> %s", ascii(quote), surah_c[0])
                return surah_c[0], METHOD_NGRAM, CONF_AMBIGUOUS
        logger.info("Ambiguous loose matches, picked first in mushaf: %s -> %s", ascii(quote), cur_loose[0])
        return cur_loose[0], METHOD_NGRAM, CONF_AMBIGUOUS

    # Skeleton matches (R2, R4):
    if skel_matches:
        cov = [c for c in skel_matches if any(a in covers for a in c)]
        if cov:
            conf = CONF_SKELETON if len(cov) == 1 else CONF_AMBIGUOUS
            return cov[0], METHOD_NGRAM, conf
        if ref_surah is not None:
            surah_c = [c for c in skel_matches if any(int(a.split(":")[0]) == ref_surah for a in c)]
            if surah_c:
                conf = CONF_SKELETON if len(surah_c) == 1 else CONF_AMBIGUOUS
                return surah_c[0], METHOD_NGRAM, conf
        if len(skel_matches) == 1:
            return skel_matches[0], METHOD_NGRAM, CONF_SKELETON

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
