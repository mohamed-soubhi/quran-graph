"""Hadith collections parser -> interim JSONL (T5.1).

Parses 10 pinned fawazahmed0 Arabic hadith editions and writes:
- data/interim/hadith/hadith.jsonl (36,104 lines)
- data/interim/hadith/books.jsonl (10 lines)

Follows docs/schema.md L2 (HadithBook, Hadith, Grader) and T5.1 acceptance criteria.
"""

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extract.normalize import normalize_with_map
from src.log import get_logger

RAW_HADITH_DIR = ROOT / "data" / "raw" / "hadith" / "fawazahmed0"
INTERIM_HADITH_DIR = ROOT / "data" / "interim" / "hadith"

HADITH_SOURCE = "hadith-api@df57907"

# Pinned collections metadata: Arabic name from T5.1 table, English name from source metadata
COLLECTIONS_META: dict[str, dict[str, str]] = {
    "abudawud": {"name": "سنن أبي داود", "name_en": "Sunan Abu Dawud"},
    "bukhari": {"name": "صحيح البخاري", "name_en": "Sahih al Bukhari"},
    "dehlawi": {"name": "الأربعون للدهلوي", "name_en": "Forty Hadith of Shah Waliullah Dehlawi"},
    "ibnmajah": {"name": "سنن ابن ماجه", "name_en": "Sunan Ibn Majah"},
    "malik": {"name": "موطأ مالك", "name_en": "Muwatta Malik"},
    "muslim": {"name": "صحيح مسلم", "name_en": "Sahih Muslim"},
    "nasai": {"name": "سنن النسائي", "name_en": "Sunan an Nasai"},
    "nawawi": {"name": "الأربعون النووية", "name_en": "Forty Hadith of an-Nawawi"},
    "qudsi": {"name": "الأحاديث القدسية الأربعون", "name_en": "Forty Hadith Qudsi"},
    "tirmidhi": {"name": "جامع الترمذي", "name_en": "Jami At Tirmidhi"},
}

logger = get_logger("parse_hadith")


def format_hadith_number(num: int | float | str) -> str:
    """Format hadith number as string: str(int) for ints, str(float) for floats."""
    if isinstance(num, int):
        return str(num)
    if isinstance(num, float):
        if num.is_integer():
            return str(int(num))
        return str(num)
    return str(num)


def parse_books(raw_dir: Path | None = None) -> list[dict[str, Any]]:
    """Generate book records for the 10 collections."""
    raw_path = raw_dir or RAW_HADITH_DIR
    records = []
    for col in sorted(COLLECTIONS_META.keys()):
        meta = COLLECTIONS_META[col]
        edition_file = raw_path / f"ara-{col}.json"
        name_en = meta["name_en"]
        if edition_file.exists():
            with open(edition_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            name_en = data.get("metadata", {}).get("name", name_en)

        records.append({
            "collection": col,
            "edition": f"ara-{col}",
            "name": meta["name"],
            "name_en": name_en,
            "source": HADITH_SOURCE,
        })
    return records


def parse_hadiths(raw_dir: Path | None = None) -> list[dict[str, Any]]:
    """Parse hadiths from all 10 collections, filtering out empty texts."""
    raw_path = raw_dir or RAW_HADITH_DIR
    records = []

    for col in sorted(COLLECTIONS_META.keys()):
        edition_file = raw_path / f"ara-{col}.json"
        if not edition_file.exists():
            raise FileNotFoundError(f"Missing raw collection file: {edition_file}")

        with open(edition_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        hadiths = data.get("hadiths", [])
        col_loaded = 0
        for h in hadiths:
            raw_text = h.get("text", "")
            if not raw_text or not raw_text.strip():
                continue

            num_str = format_hadith_number(h["hadithnumber"])
            hadith_id = f"{col}:{num_str}"

            # arabic_number
            an_raw = h.get("arabicnumber")
            if an_raw is None:
                arabic_number = None
            else:
                arabic_number = str(an_raw)

            # book_number and number_in_book from reference
            ref = h.get("reference", {})
            book_number = ref.get("book")
            number_in_book = ref.get("hadith")

            # text_norm
            text_norm, _ = normalize_with_map(raw_text)

            # grades
            grades_list = [
                {"grader": g["name"], "grade": g["grade"]}
                for g in h.get("grades", [])
                if "name" in g and "grade" in g
            ]

            records.append({
                "arabic_number": arabic_number,
                "book_number": book_number,
                "collection": col,
                "grades": grades_list,
                "hadith_id": hadith_id,
                "number": num_str,
                "number_in_book": number_in_book,
                "text": raw_text,
                "text_norm": text_norm,
            })
            col_loaded += 1

        logger.info("Collection %s: loaded %d hadith", col, col_loaded)

    return records


def parse_hadith_all(
    raw_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    """Parse all 10 hadith collections and write interim JSONL files."""
    out_path = output_dir or INTERIM_HADITH_DIR
    out_path.mkdir(parents=True, exist_ok=True)

    books_records = parse_books(raw_dir)
    hadiths_records = parse_hadiths(raw_dir)

    books_file = out_path / "books.jsonl"
    with open(books_file, "w", encoding="utf-8", newline="\n") as f:
        for rec in books_records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    hadith_file = out_path / "hadith.jsonl"
    with open(hadith_file, "w", encoding="utf-8", newline="\n") as f:
        for rec in hadiths_records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    logger.info("Wrote %d books to %s", len(books_records), books_file)
    logger.info("Wrote %d hadith to %s", len(hadiths_records), hadith_file)

    return {
        "books": books_file,
        "hadith": hadith_file,
    }


def main() -> None:
    results = parse_hadith_all()
    print("Successfully generated hadith interim files:")
    for key, path in results.items():
        print(f"  {key}: {path}")


if __name__ == "__main__":
    main()
