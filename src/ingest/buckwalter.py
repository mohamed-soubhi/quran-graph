"""Extended Buckwalter transliteration table and converters (T3.3).

Implements the official Quranic Arabic Corpus extended Buckwalter scheme:
https://corpus.quran.com/java/buckwalter.jsp
Bijective 1-to-1 mapping between extended Buckwalter characters and Arabic script.
"""

import re

# Extended Buckwalter character-to-Arabic mapping
BUCKWALTER_TABLE: dict[str, str] = {
    "'": "ء",
    ">": "أ",
    "&": "ؤ",
    "<": "إ",
    "}": "ئ",
    "A": "ا",
    "b": "ب",
    "p": "ة",
    "t": "ت",
    "v": "ث",
    "j": "ج",
    "H": "ح",
    "x": "خ",
    "d": "د",
    "*": "ذ",
    "r": "ر",
    "z": "ز",
    "s": "س",
    "$": "ش",
    "S": "ص",
    "D": "ض",
    "T": "ط",
    "Z": "ظ",
    "E": "ع",
    "g": "غ",
    "_": "ـ",
    "f": "ف",
    "q": "ق",
    "k": "ك",
    "l": "ل",
    "m": "م",
    "n": "ن",
    "h": "ه",
    "w": "و",
    "Y": "ى",
    "y": "ي",
    "F": "ً",
    "N": "ٌ",
    "K": "ٍ",
    "a": "َ",
    "u": "ُ",
    "i": "ِ",
    "~": "ّ",
    "o": "ْ",
    "^": "ٓ",
    "#": "ٔ",
    "`": "ٰ",
    "{": "ٱ",
    ":": "ۜ",
    "@": "۟",
    '"': "۠",
    "[": "ۢ",
    ";": "ۣ",
    ",": "ۥ",
    ".": "ۦ",
    "!": "ۨ",
    "-": "۪",
    "+": "۫",
    "%": "۬",
    "]": "ۭ",
    " ": " ",
}

# Alias for backwards compatibility / concise usage
BW = BUCKWALTER_TABLE
REV_BUCKWALTER_TABLE: dict[str, str] = {v: k for k, v in BUCKWALTER_TABLE.items()}
REV = REV_BUCKWALTER_TABLE

assert len(BUCKWALTER_TABLE) == len(REV_BUCKWALTER_TABLE), "Buckwalter mapping must be bijective"

_LEMMA_SPLIT_PATTERN = re.compile(r"^(.*?)(\d+)?$")


def to_arabic(s: str) -> str:
    """Convert extended Buckwalter transliteration to Arabic script.

    Raises:
        ValueError: If an unknown character not in the Buckwalter table is encountered.
    """
    chars: list[str] = []
    for c in s:
        ar = BUCKWALTER_TABLE.get(c)
        if ar is None:
            raise ValueError(f"Unknown Buckwalter character: {c!r} in string {s!r}")
        chars.append(ar)
    return "".join(chars)


def to_buckwalter(s: str) -> str:
    """Convert Arabic script to extended Buckwalter transliteration.

    Raises:
        ValueError: If an unknown character not in the reverse Buckwalter table is encountered.
    """
    chars: list[str] = []
    for c in s:
        bw = REV_BUCKWALTER_TABLE.get(c)
        if bw is None:
            raise ValueError(f"Unknown Arabic character: {c!r} in string {s!r}")
        chars.append(bw)
    return "".join(chars)


def split_lemma(lem: str) -> tuple[str, int | None]:
    """Split a lemma into base transliteration and optional homonym sense number.

    Example:
        split_lemma('EaAd2') -> ('EaAd', 2)
        split_lemma('EaAd')  -> ('EaAd', None)
    """
    m = _LEMMA_SPLIT_PATTERN.match(lem)
    if not m:
        return lem, None
    base, sense = m.group(1), m.group(2)
    return base, int(sense) if sense is not None else None
