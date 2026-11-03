"""Arabic text normalization with character offset mapping (T2.3, T4.1)."""

import unicodedata

# Letter normalization mapping:
# أ إ آ ٱ → ا
# ى → ي
# ة → ه
NORM_MAP: dict[str, str] = {
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٱ": "ا",
    "ى": "ي",
    "ة": "ه",
}

# Characters skipped without output or index entry (T4.1):
# tatweel ـ U+0640, hamza ء U+0621, small waw ۥ U+06E5, small yeh ۦ U+06E6
SKIP_CHARS: frozenset[str] = frozenset({
    "\u0640",  # tatweel ـ
    "\u0621",  # hamza ء
    "\u06e5",  # small waw ۥ
    "\u06e6",  # small yeh ۦ
})


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalize Arabic text by stripping diacritics and unifying letter variants.

    Maintains a 1-to-1 mapping from each character in the normalized text back to
    its 0-based character offset in the original verbatim text.

    Args:
        text: Original verbatim Arabic text (UTF-8).

    Returns:
        A tuple of (norm, index) where:
          - norm: The normalized string (diacritics stripped, letter variants mapped, skipped chars removed).
          - index: List of original character offsets such that len(norm) == len(index)
            and norm[k] originates from text[index[k]].
    """
    norm_chars: list[str] = []
    index: list[int] = []

    for i, c in enumerate(text):
        if unicodedata.category(c) == "Mn":
            continue
        if c in SKIP_CHARS:
            continue
        c_mapped = NORM_MAP.get(c, c)
        norm_chars.append(c_mapped)
        index.append(i)

    return "".join(norm_chars), index
