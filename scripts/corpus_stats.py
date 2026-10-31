"""Compute and display statistics for Quranic Arabic Corpus morphology v0.4 (T1.4).

Computes:
- Total morpheme rows
- Distinct words (surah, ayah, word)
- Distinct ayat (surah, ayah)
- Distinct roots (ROOT:...)
- Top 10 most frequent roots
- Top POS tags
"""

from collections import Counter
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingest.quranic_corpus import (
    CORPUS_TXT_NAME,
    CORPUS_ZIP_PATH,
    compute_corpus_stats,
    parse_morphology_stream,
)

TANZIL_SIMPLE_CLEAN = ROOT / "data" / "raw" / "tanzil" / "quran-simple-clean.txt"


def print_corpus_stats() -> None:
    print(f"Reading morphology archive directly from: {CORPUS_ZIP_PATH}")
    if not CORPUS_ZIP_PATH.exists():
        print(f"ERROR: {CORPUS_ZIP_PATH} does not exist.")
        return

    with zipfile.ZipFile(CORPUS_ZIP_PATH, "r") as zf:
        members = zf.infolist()
        print(f"Archive members count: {len(members)}")
        for m in members:
            print(f"  - {m.filename} ({m.file_size:,} bytes uncompressed, {m.compress_size:,} compressed)")

    tag_counter: Counter[str] = Counter()
    root_counter: Counter[str] = Counter()
    pos_counter: Counter[str] = Counter()

    pos_pattern = re.compile(r"POS:([^|\s\r\n]+)")

    stats = compute_corpus_stats(CORPUS_ZIP_PATH)

    for row in parse_morphology_stream(CORPUS_ZIP_PATH):
        tag_counter[row["tag"]] += 1
        if row["root"]:
            root_counter[row["root"]] += 1
        pos_match = pos_pattern.search(row["features"])
        if pos_match:
            pos_counter[pos_match.group(1)] += 1

    print("\n--- Summary Statistics ---")
    print(f"Total morpheme rows:        {stats['morpheme_count']:,}")
    print(f"Distinct words (s, a, w):   {stats['distinct_words']:,}")
    print(f"Distinct ayat (s, a):       {stats['distinct_ayat']:,}")
    print(f"Distinct roots:             {stats['distinct_roots']:,}")

    if TANZIL_SIMPLE_CLEAN.exists():
        tanzil_ayat = set()
        with open(TANZIL_SIMPLE_CLEAN, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = stripped.split("|")
                if len(parts) >= 2:
                    tanzil_ayat.add((int(parts[0]), int(parts[1])))
        ayat_match = stats["ayat_set"] == tanzil_ayat
        print(f"Ayat match Tanzil clean:    {ayat_match} ({len(tanzil_ayat):,} ayat)")

    print("\n--- Top 10 Most Frequent Roots (Buckwalter) ---")
    for root, count in root_counter.most_common(10):
        print(f"  {root:<10} {count:>6,}")

    print("\n--- Top 10 Morpheme Tags ---")
    for tag, count in tag_counter.most_common(10):
        print(f"  {tag:<10} {count:>6,}")


if __name__ == "__main__":
    print_corpus_stats()
