"""Quran text and surah metadata parser -> interim JSONL (T3.2).

Produces:
- data/interim/quran/surahs.jsonl (114 lines)
- data/interim/quran/ayat.jsonl (6,236 lines)

Following docs/schema.md (L0 Surah, Ayah) and decisions (Q1 basmala rule).
"""

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extract.normalize import normalize_with_map
from src.ingest.tanzil_metadata import DEFAULT_METADATA_PATH, read_suras
from src.log import get_logger

RAW_DIR = ROOT / "data" / "raw"
TANZIL_DIR = RAW_DIR / "tanzil"
DEFAULT_UTHMANI_PATH = TANZIL_DIR / "quran-uthmani.txt"
DEFAULT_SIMPLE_PATH = TANZIL_DIR / "quran-simple-clean.txt"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "interim" / "quran"

logger = get_logger("parse_quran")


def _read_raw_ayat(path: Path) -> list[tuple[int, int, str]]:
    """Parse raw Tanzil text file into (surah, ayah, text) tuples."""
    if not path.exists():
        raise FileNotFoundError(f"Raw Tanzil file not found at: {path}")

    ayat: list[tuple[int, int, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split("|", 2)
            if len(parts) != 3:
                raise ValueError(f"Malformed line in {path}: {line}")
            ayat.append((int(parts[0]), int(parts[1]), parts[2]))
    return ayat


def parse_surahs(metadata_path: Path | str = DEFAULT_METADATA_PATH) -> list[dict[str, Any]]:
    """Extract and format Surah records from Tanzil metadata.

    Returns 114 surah dicts ordered by surah_id (1..114), each containing:
    - surah_id: int (1..114)
    - name: str (Arabic name)
    - tname: str (transliterated name)
    - type: str ("Meccan" or "Medinan")
    - revelation_order: int (chronological revelation order)
    - ayah_count: int
    - has_basmala: bool (false only for surah 9)
    """
    raw_suras = read_suras(metadata_path)
    surahs: list[dict[str, Any]] = []

    for s in raw_suras:
        surah_id = int(s["index"])
        surahs.append(
            {
                "surah_id": surah_id,
                "name": s["name"],
                "tname": s["tname"],
                "type": s["type"],
                "revelation_order": int(s["order"]),
                "ayah_count": int(s["ayas"]),
                "has_basmala": surah_id != 9,
            }
        )

    surahs.sort(key=lambda s: s["surah_id"])
    return surahs


def parse_ayat(
    uthmani_path: Path | str = DEFAULT_UTHMANI_PATH,
    simple_path: Path | str = DEFAULT_SIMPLE_PATH,
) -> list[dict[str, Any]]:
    """Parse and align Tanzil Uthmani and Simple-Clean ayat with basmala handling.

    For ayah 1 of every surah except 1 and 9, drops the first 4 words when they
    equal the 4 normalized words of 1:1.

    Returns 6,236 ayah dicts ordered by (surah_id, number), each containing:
    - ayah_id: str ("<surah_id>:<ayah_num>")
    - surah_id: int
    - number: int
    - text: str (Uthmani after basmala rule)
    - text_simple: str (Simple-Clean after basmala rule)
    - text_norm: str (normalized text_simple)
    - word_count: int (word count of text after basmala rule)
    """
    uthmani_raw = _read_raw_ayat(Path(uthmani_path))
    simple_raw = _read_raw_ayat(Path(simple_path))

    if len(uthmani_raw) != len(simple_raw):
        raise ValueError(
            f"Line count mismatch between Uthmani ({len(uthmani_raw)}) and Simple ({len(simple_raw)})"
        )

    # Determine normalized basmala 4-word reference from 1:1
    fatiha_1 = next((text for s, a, text in uthmani_raw if s == 1 and a == 1), None)
    if not fatiha_1:
        raise ValueError("Could not find ayah 1:1 in raw Uthmani file")
    basmala_words_norm = [normalize_with_map(w)[0] for w in fatiha_1.split()[:4]]

    ayat: list[dict[str, Any]] = []
    stripped_count = 0

    for (s_uth, a_uth, text_uth), (s_sim, a_sim, text_sim) in zip(uthmani_raw, simple_raw):
        if (s_uth, a_uth) != (s_sim, a_sim):
            raise ValueError(f"Key mismatch between Uthmani ({s_uth}:{a_uth}) and Simple ({s_sim}:{a_sim})")

        surah_id = s_uth
        ayah_num = a_uth

        final_uth = text_uth
        final_sim = text_sim

        if ayah_num == 1 and surah_id not in (1, 9):
            uth_words = text_uth.split()
            sim_words = text_sim.split()

            if len(uth_words) >= 4 and [normalize_with_map(w)[0] for w in uth_words[:4]] == basmala_words_norm:
                final_uth = " ".join(uth_words[4:])

            if len(sim_words) >= 4 and [normalize_with_map(w)[0] for w in sim_words[:4]] == basmala_words_norm:
                final_sim = " ".join(sim_words[4:])

            if final_uth != text_uth:
                stripped_count += 1

        text_norm = normalize_with_map(final_sim)[0]
        word_count = len(final_uth.split())

        ayat.append(
            {
                "ayah_id": f"{surah_id}:{ayah_num}",
                "surah_id": surah_id,
                "number": ayah_num,
                "text": final_uth,
                "text_simple": final_sim,
                "text_norm": text_norm,
                "word_count": word_count,
            }
        )

    ayat.sort(key=lambda a: (a["surah_id"], a["number"]))
    logger.info("Parsed %d ayat (stripped basmala on %d ayat)", len(ayat), stripped_count)
    return ayat


def parse_quran(
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    metadata_path: Path | str = DEFAULT_METADATA_PATH,
    uthmani_path: Path | str = DEFAULT_UTHMANI_PATH,
    simple_path: Path | str = DEFAULT_SIMPLE_PATH,
) -> tuple[Path, Path]:
    """Parse Quran surahs and ayat and write deterministic JSONL files.

    Returns tuple of (surahs_jsonl_path, ayat_jsonl_path).
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    surahs = parse_surahs(metadata_path)
    ayat = parse_ayat(uthmani_path, simple_path)

    surahs_file = out_dir / "surahs.jsonl"
    with open(surahs_file, "w", encoding="utf-8", newline="\n") as f:
        for surah in surahs:
            f.write(json.dumps(surah, ensure_ascii=False, sort_keys=True) + "\n")

    ayat_file = out_dir / "ayat.jsonl"
    with open(ayat_file, "w", encoding="utf-8", newline="\n") as f:
        for ayah in ayat:
            f.write(json.dumps(ayah, ensure_ascii=False, sort_keys=True) + "\n")

    logger.info("Wrote %d surahs to %s", len(surahs), surahs_file)
    logger.info("Wrote %d ayat to %s", len(ayat), ayat_file)
    return surahs_file, ayat_file


def main() -> None:
    surahs_path, ayat_path = parse_quran()
    print(f"Successfully generated:\n  {surahs_path}\n  {ayat_path}")


if __name__ == "__main__":
    main()
