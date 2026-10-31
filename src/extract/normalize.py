"""Arabic text normalization with character offset mapping (T2.3)."""

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


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalize Arabic text by stripping diacritics and unifying letter variants.

    Maintains a 1-to-1 mapping from each character in the normalized text back to
    its 0-based character offset in the original verbatim text.

    Args:
        text: Original verbatim Arabic text (UTF-8).

    Returns:
        A tuple of (norm, index) where:
          - norm: The normalized string (diacritics stripped, letter variants mapped).
          - index: List of original character offsets such that len(norm) == len(index)
            and norm[k] originates from text[index[k]].
    """
    norm_chars: list[str] = []
    index: list[int] = []

    for i, c in enumerate(text):
        if unicodedata.category(c) == "Mn":
            continue
        c_mapped = NORM_MAP.get(c, c)
        norm_chars.append(c_mapped)
        index.append(i)

    return "".join(norm_chars), index
