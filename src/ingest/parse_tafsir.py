"""Ibn Kathir Arabic tafsir parser -> interim JSONL (T3.4).

Produces:
- data/interim/tafsir/ibn-kathir/segments.jsonl (1,911 lines)
- data/interim/tafsir/ibn-kathir/mufassir.jsonl (1 line)
- data/interim/tafsir/ibn-kathir/book.jsonl (1 line)

Following docs/schema.md (L1 Mufassir, TafsirBook, TafsirSegment) and decisions
(2026-10-29 range-ID + Q2 whole passage stored once).
"""

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extract.normalize import normalize_with_map
from src.ingest.tafsir_ibn_kathir import load_surah_ayah_pairs
from src.log import get_logger

RAW_DIR = ROOT / "data" / "raw"
DEFAULT_TAFSIR_DIR = RAW_DIR / "tafsir" / "ibn-kathir"
DEFAULT_TANZIL_SIMPLE = RAW_DIR / "tanzil" / "quran-simple-clean.txt"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir"

BOOK_ID = "ibn-kathir"
MUFASSIR_ID = "ibn-kathir"
MUFASSIR_NAME = "إسماعيل بن عمر بن كثير"
MUFASSIR_DEATH_HIJRI = 774
BOOK_TITLE = "تفسير القرآن العظيم"
BOOK_SOURCE = "spa5k@eb82bb6"

logger = get_logger("parse_tafsir")


def parse_mufassir() -> list[dict[str, Any]]:
    """Return Mufassir record according to schema L1."""
    return [
        {
            "death_hijri": MUFASSIR_DEATH_HIJRI,
            "mufassir_id": MUFASSIR_ID,
            "name": MUFASSIR_NAME,
        }
    ]


def parse_book() -> list[dict[str, Any]]:
    """Return TafsirBook record according to schema L1."""
    return [
        {
            "book_id": BOOK_ID,
            "mufassir_id": MUFASSIR_ID,
            "source": BOOK_SOURCE,
            "title": BOOK_TITLE,
        }
    ]


def parse_segments(
    tafsir_dir: Path | str = DEFAULT_TAFSIR_DIR,
    tanzil_path: Path | str = DEFAULT_TANZIL_SIMPLE,
) -> list[dict[str, Any]]:
    """Parse Ibn Kathir passages into segment dictionaries.

    A passage is a contiguous run of ayat within one surah that share identical
    raw text.
    """
    tafsir_path = Path(tafsir_dir)
    if not tafsir_path.exists():
        raise FileNotFoundError(f"Raw Ibn Kathir tafsir dir not found at: {tafsir_path}")

    pairs = load_surah_ayah_pairs(tanzil_path)
    logger.info("Loaded %d ayah pairs from Tanzil source", len(pairs))

    passages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for surah_num, ayah_num in pairs:
        file_path = tafsir_path / str(surah_num) / f"{ayah_num}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Missing tafsir raw file: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_text: str = data["text"]
        ayah_id = f"{surah_num}:{ayah_num}"

        if (
            current is not None
            and current["surah_id"] == surah_num
            and current["text"] == raw_text
        ):
            current["last_ayah"] = ayah_num
            current["covers"].append(ayah_id)
        else:
            if current is not None:
                passages.append(current)
            current = {
                "surah_id": surah_num,
                "first_ayah": ayah_num,
                "last_ayah": ayah_num,
                "text": raw_text,
                "covers": [ayah_id],
            }

    if current is not None:
        passages.append(current)

    # Convert passages to final TafsirSegment schema records
    segments: list[dict[str, Any]] = []
    for p in passages:
        surah_id = p["surah_id"]
        first_ayah = p["first_ayah"]
        last_ayah = p["last_ayah"]
        text = p["text"]
        text_norm, _ = normalize_with_map(text)
        char_count = len(text)
        segment_id = f"{BOOK_ID}:{surah_id}:{first_ayah}-{last_ayah}:1"

        segments.append(
            {
                "book_id": BOOK_ID,
                "char_count": char_count,
                "covers": p["covers"],
                "first_ayah": first_ayah,
                "last_ayah": last_ayah,
                "n": 1,
                "segment_id": segment_id,
                "surah_id": surah_id,
                "text": text,
                "text_norm": text_norm,
            }
        )

    segments.sort(key=lambda s: (s["surah_id"], s["first_ayah"]))
    logger.info("Built %d segments from %d ayat", len(segments), len(pairs))
    return segments


def parse_tafsir(
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    tafsir_dir: Path | str = DEFAULT_TAFSIR_DIR,
    tanzil_path: Path | str = DEFAULT_TANZIL_SIMPLE,
) -> dict[str, Path]:
    """Parse Ibn Kathir tafsir and write deterministic JSONL files.

    Writes:
    - segments.jsonl
    - mufassir.jsonl
    - book.jsonl
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mufassir_records = parse_mufassir()
    book_records = parse_book()
    segment_records = parse_segments(tafsir_dir, tanzil_path)

    mufassir_file = out_dir / "mufassir.jsonl"
    with open(mufassir_file, "w", encoding="utf-8", newline="\n") as f:
        for rec in mufassir_records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    book_file = out_dir / "book.jsonl"
    with open(book_file, "w", encoding="utf-8", newline="\n") as f:
        for rec in book_records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    segments_file = out_dir / "segments.jsonl"
    with open(segments_file, "w", encoding="utf-8", newline="\n") as f:
        for rec in segment_records:
            f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    logger.info("Wrote %d records to %s", len(mufassir_records), mufassir_file)
    logger.info("Wrote %d records to %s", len(book_records), book_file)
    logger.info("Wrote %d records to %s", len(segment_records), segments_file)

    return {
        "mufassir": mufassir_file,
        "book": book_file,
        "segments": segments_file,
    }


def main() -> None:
    results = parse_tafsir()
    print("Successfully generated:")
    for key, path in results.items():
        print(f"  {key}: {path}")


if __name__ == "__main__":
    main()
