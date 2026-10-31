"""Calculate and print statistics for Ibn Kathir Arabic tafsir (T1.2).

Computes:
- Total characters
- Number of empty texts
- Number of texts identical to previous ayah's (grouped passages)
- Number of distinct texts
- 5 largest groups (first ayah, size)
"""

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingest.tafsir_ibn_kathir import load_surah_ayah_pairs

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
TAFSIR_DIR = RAW_DIR / "tafsir" / "ibn-kathir"
TANZIL_SIMPLE_CLEAN = RAW_DIR / "tanzil" / "quran-simple-clean.txt"


def calculate_tafsir_stats(
    tafsir_dir: Path | str = TAFSIR_DIR,
    tanzil_path: Path | str = TANZIL_SIMPLE_CLEAN,
) -> dict[str, Any]:
    """Calculate statistics across all 6236 tafsir files."""
    base_dir = Path(tafsir_dir)
    ayat = load_surah_ayah_pairs(tanzil_path)

    total_chars = 0
    empty_texts = 0
    all_texts: list[str] = []
    ayah_records: list[tuple[int, int, str]] = []

    for surah, ayah in ayat:
        file_path = base_dir / str(surah) / f"{ayah}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Missing tafsir file: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        text = data.get("text", "")
        total_chars += len(text)
        if not text or not text.strip():
            empty_texts += 1

        all_texts.append(text)
        ayah_records.append((surah, ayah, text))

    # Identical to previous ayah
    identical_to_prev = 0
    for i in range(1, len(all_texts)):
        if all_texts[i] == all_texts[i - 1]:
            identical_to_prev += 1

    # Distinct texts
    distinct_texts = len(set(all_texts))

    # Groups of consecutive ayat with identical text within the same surah
    groups: list[dict[str, Any]] = []
    if ayah_records:
        cur_surah, cur_ayah, cur_text = ayah_records[0]
        cur_size = 1
        start_ayah = cur_ayah

        for surah, ayah, text in ayah_records[1:]:
            if surah == cur_surah and text == cur_text:
                cur_size += 1
                cur_ayah = ayah
            else:
                if cur_size > 1:
                    groups.append({
                        "surah": cur_surah,
                        "first_ayah": start_ayah,
                        "last_ayah": cur_ayah,
                        "size": cur_size,
                        "chars": len(cur_text),
                    })
                cur_surah = surah
                cur_ayah = ayah
                cur_text = text
                cur_size = 1
                start_ayah = ayah

        if cur_size > 1:
            groups.append({
                "surah": cur_surah,
                "first_ayah": start_ayah,
                "last_ayah": cur_ayah,
                "size": cur_size,
                "chars": len(cur_text),
            })

    # Sort groups by size descending, then by surah and first_ayah ascending
    groups_sorted = sorted(groups, key=lambda g: (-g["size"], g["surah"], g["first_ayah"]))
    top_5_groups = groups_sorted[:5]

    return {
        "total_ayat": len(ayat),
        "total_characters": total_chars,
        "empty_texts": empty_texts,
        "identical_to_prev": identical_to_prev,
        "distinct_texts": distinct_texts,
        "grouped_passages_count": len(groups),
        "top_5_groups": top_5_groups,
    }


def print_stats(stats: dict[str, Any]) -> None:
    print("=" * 60)
    print("Ibn Kathir (Arabic) Tafsir Statistics")
    print("=" * 60)
    print(f"Total ayat evaluated:                     {stats['total_ayat']}")
    print(f"Total characters:                         {stats['total_characters']:,}")
    print(f"Empty texts count:                        {stats['empty_texts']}")
    print(f"Texts identical to previous ayah:         {stats['identical_to_prev']}")
    print(f"Distinct texts count:                     {stats['distinct_texts']}")
    print(f"Grouped passages (runs > 1):              {stats['grouped_passages_count']}")
    print("-" * 60)
    print("Top 5 largest groups (consecutive ayat with identical text):")
    for i, g in enumerate(stats["top_5_groups"], 1):
        range_str = f"{g['surah']}:{g['first_ayah']}-{g['last_ayah']}"
        first_ayah_str = f"{g['surah']}:{g['first_ayah']}"
        print(f"  {i}. First ayah: {first_ayah_str:<8} (range: {range_str:<12}) -> size: {g['size']} ayat ({g['chars']:,} chars)")
    print("=" * 60)


if __name__ == "__main__":
    stats = calculate_tafsir_stats()
    print_stats(stats)
