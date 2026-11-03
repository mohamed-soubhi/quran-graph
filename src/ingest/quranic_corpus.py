"""Downloader verification and morphology reader for Quranic Arabic Corpus (T1.4, T3.3).

The Quranic Arabic Corpus morphology v0.4 file is distributed as a zip archive
containing `quranic-corpus-morphology-0.4.txt`. In accordance with Hard Rule 5
and project data management rules:
- The zip file in data/raw/ is read-only and is not unzipped on disk.
- Data is parsed directly from the zip archive using Python's `zipfile`.
- SHA-256 is recorded in data/raw/CHECKSUMS.txt.
- Parsed JSONL files are written to data/interim/corpus/.
"""

from collections import defaultdict
import json
from pathlib import Path
import re
import sys
import zipfile
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingest.buckwalter import split_lemma, to_arabic
from src.ingest.download import (
    append_checksum,
    calculate_sha256,
    read_checksums,
)
from src.log import get_logger

RAW_DIR = ROOT / "data" / "raw"
CORPUS_DIR = RAW_DIR / "quranic-corpus"
CORPUS_ZIP_PATH = CORPUS_DIR / "quranic-corpus-morphology-0.4.zip"
CORPUS_TXT_NAME = "quranic-corpus-morphology-0.4.txt"
CHECKSUMS_FILE = RAW_DIR / "CHECKSUMS.txt"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "interim" / "corpus"

CORPUS_URL = "https://corpus.quran.com/download/"
CORPUS_SHA256 = "fda26f87cc58b42fc992a3ad666a562805b636f34bcecb46326d048337ca7999"

# Verified exact baseline counts for morphology v0.4
EXPECTED_MORPHEMES = 128219
EXPECTED_WORDS = 77429
EXPECTED_AYAT = 6236
EXPECTED_ROOTS = 1642
EXPECTED_LEMMAS = 4832
EXPECTED_WORD_LEMMAS = 74608
EXPECTED_WORD_ROOTS = 49968
EXPECTED_LEMMA_ROOTS = 4657

logger = get_logger("quranic_corpus")

LOCATION_PATTERN = re.compile(r"^\((\d+):(\d+):(\d+):(\d+)\)$")
ROOT_PATTERN = re.compile(r"ROOT:([^|\s\r\n]+)")
LEM_PATTERN = re.compile(r"LEM:([^|\s\r\n]+)")


def verify_and_record_checksum(
    zip_path: Path | str = CORPUS_ZIP_PATH,
    checksums_path: Path | str = CHECKSUMS_FILE,
    date_str: str = "2026-10-31",
) -> str:
    """Verify SHA-256 of the morphology zip and record it in CHECKSUMS.txt if not present."""
    path = Path(zip_path)
    if not path.exists():
        raise FileNotFoundError(f"Corpus zip not found at {path}")

    actual_sha256 = calculate_sha256(path)
    if actual_sha256 != CORPUS_SHA256:
        raise ValueError(
            f"Checksum mismatch for {path}: expected {CORPUS_SHA256}, got {actual_sha256}"
        )

    try:
        rel_path = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel_path = path.as_posix()

    target_checksums = Path(checksums_path)
    existing_entries = read_checksums(target_checksums)
    already_recorded = any(entry.get("path") == rel_path for entry in existing_entries)

    if not already_recorded:
        append_checksum(
            sha256_hex=actual_sha256,
            rel_path=rel_path,
            url=CORPUS_URL,
            date_str=date_str,
            checksums_path=target_checksums,
        )
        logger.info("Recorded checksum for %s in %s", rel_path, target_checksums)
    else:
        logger.info("Checksum for %s already recorded in %s", rel_path, target_checksums)

    return actual_sha256


def parse_morphology_stream(
    zip_path: Path | str = CORPUS_ZIP_PATH,
) -> Iterator[dict[str, Any]]:
    """Stream parsed morphology records directly from the zip archive without extracting to disk.

    Yields dicts with:
      - surah (int)
      - ayah (int)
      - word (int)
      - segment (int)
      - location (str)
      - form (str)
      - tag (str)
      - features (str)
      - root (str | None)
    """
    path = Path(zip_path)
    if not path.exists():
        raise FileNotFoundError(f"Corpus zip not found at {path}")

    with zipfile.ZipFile(path, "r") as zf:
        namelist = zf.namelist()
        if CORPUS_TXT_NAME not in namelist:
            raise ValueError(
                f"Zip file {path} does not contain expected file {CORPUS_TXT_NAME}. Members: {namelist}"
            )

        with zf.open(CORPUS_TXT_NAME, "r") as member_file:
            header_seen = False
            for raw_line in member_file:
                line = raw_line.decode("utf-8")
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue

                if not header_seen and stripped.startswith("LOCATION"):
                    header_seen = True
                    continue

                parts = stripped.split("\t")
                if len(parts) < 4:
                    continue

                loc_str, form, tag, features = parts[0], parts[1], parts[2], parts[3]
                loc_match = LOCATION_PATTERN.match(loc_str)
                if not loc_match:
                    continue

                s, a, w, seg = map(int, loc_match.groups())
                root_match = ROOT_PATTERN.search(features)
                root = root_match.group(1) if root_match else None

                yield {
                    "surah": s,
                    "ayah": a,
                    "word": w,
                    "segment": seg,
                    "location": loc_str,
                    "form": form,
                    "tag": tag,
                    "features": features,
                    "root": root,
                }


def compute_corpus_stats(
    zip_path: Path | str = CORPUS_ZIP_PATH,
) -> dict[str, Any]:
    """Compute exact verification statistics across the morphology corpus."""
    morpheme_count = 0
    words: set[tuple[int, int, int]] = set()
    ayat: set[tuple[int, int]] = set()
    roots: set[str] = set()

    for row in parse_morphology_stream(zip_path):
        morpheme_count += 1
        words.add((row["surah"], row["ayah"], row["word"]))
        ayat.add((row["surah"], row["ayah"]))
        if row["root"]:
            roots.add(row["root"])

    return {
        "morpheme_count": morpheme_count,
        "distinct_words": len(words),
        "distinct_ayat": len(ayat),
        "distinct_roots": len(roots),
        "ayat_set": ayat,
        "words_set": words,
        "roots_set": roots,
    }


def parse_corpus(
    zip_path: Path | str = CORPUS_ZIP_PATH,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """Parse the Quranic Corpus morphology zip in place into interim JSONL datasets.

    Generates:
      - words.jsonl (77,429 words)
      - lemmas.jsonl (4,832 lemmas)
      - roots.jsonl (1,642 roots)
      - word_lemmas.jsonl (74,608 links)
      - word_roots.jsonl (49,968 links)
      - lemma_roots.jsonl (4,657 links)
    """
    path = Path(zip_path)
    if not path.exists():
        raise FileNotFoundError(f"Corpus zip not found at {path}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    words_dict: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)

    with zipfile.ZipFile(path, "r") as zf:
        if CORPUS_TXT_NAME not in zf.namelist():
            raise ValueError(f"Zip file {path} missing {CORPUS_TXT_NAME}")

        with zf.open(CORPUS_TXT_NAME, "r") as mf:
            header_seen = False
            for raw_line in mf:
                line = raw_line.decode("utf-8")
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not header_seen and stripped.startswith("LOCATION"):
                    header_seen = True
                    continue

                parts = stripped.split("\t")
                if len(parts) < 4:
                    continue

                loc_str, form, tag, features = parts[0], parts[1], parts[2], parts[3]
                loc_match = LOCATION_PATTERN.match(loc_str)
                if not loc_match:
                    continue

                s, a, w, seg = map(int, loc_match.groups())

                lem_match = LEM_PATTERN.search(features)
                lem = lem_match.group(1) if lem_match else None

                root_match = ROOT_PATTERN.search(features)
                root = root_match.group(1) if root_match else None

                words_dict[(s, a, w)].append(
                    {
                        "seg": seg,
                        "form": form,
                        "tag": tag,
                        "features": features,
                        "lem": lem,
                        "root": root,
                    }
                )

    words_records: list[dict[str, Any]] = []
    lemmas_dict: dict[str, dict[str, Any]] = {}
    roots_dict: dict[str, dict[str, Any]] = {}

    word_lemma_links: list[dict[str, Any]] = []
    word_root_links: list[dict[str, Any]] = []
    lemma_root_pairs: set[tuple[str, str]] = set()

    for (s, a, w), segs in sorted(words_dict.items()):
        # Sort segments by segment index to ensure deterministic form joining
        segs.sort(key=lambda x: x["seg"])

        word_id = f"{s}:{a}:{w}"
        ayah_id = f"{s}:{a}"
        position = w

        bw = "".join(seg["form"] for seg in segs)
        text = to_arabic(bw)

        stem_pos: str | None = None
        for seg in segs:
            if "STEM" in seg["features"]:
                stem_pos = seg["tag"]
                break

        if stem_pos is None:
            raise ValueError(f"Word {word_id} has no STEM segment")

        words_records.append(
            {
                "word_id": word_id,
                "ayah_id": ayah_id,
                "position": position,
                "text": text,
                "bw": bw,
                "pos": stem_pos,
            }
        )

        for seg in segs:
            seg_num = seg["seg"]
            lem_raw = seg["lem"]
            root_raw = seg["root"]

            lem_id: str | None = None
            if lem_raw:
                lem_bw, lem_sense = split_lemma(lem_raw)
                lem_text = to_arabic(lem_bw)
                lem_id = f"{lem_text}#{lem_sense}" if lem_sense is not None else lem_text

                if lem_id not in lemmas_dict:
                    lemmas_dict[lem_id] = {
                        "lemma_id": lem_id,
                        "text": lem_text,
                        "sense": lem_sense,
                        "bw": lem_bw,
                    }

                word_lemma_links.append(
                    {
                        "word_id": word_id,
                        "lemma_id": lem_id,
                        "segment": seg_num,
                    }
                )

            r_id: str | None = None
            if root_raw:
                r_bw = root_raw
                r_text = to_arabic(r_bw)
                r_id = r_text

                if r_id not in roots_dict:
                    roots_dict[r_id] = {
                        "root_id": r_id,
                        "text": r_text,
                        "bw": r_bw,
                    }

                word_root_links.append(
                    {
                        "word_id": word_id,
                        "root_id": r_id,
                    }
                )

            if lem_id and r_id:
                lemma_root_pairs.add((lem_id, r_id))

    # Sort records deterministically
    lemmas_records = sorted(lemmas_dict.values(), key=lambda x: x["lemma_id"])
    roots_records = sorted(roots_dict.values(), key=lambda x: x["root_id"])

    # word_lemma_links already in (s, a, w, seg) order from words_dict iteration
    # word_root_links already in (s, a, w) order; sort by (word_id_tuple, root_id)
    def _parse_wid(wid: str) -> tuple[int, int, int]:
        parts = wid.split(":")
        return int(parts[0]), int(parts[1]), int(parts[2])

    word_lemma_links.sort(key=lambda x: (_parse_wid(x["word_id"]), x["segment"]))
    word_root_links.sort(key=lambda x: (_parse_wid(x["word_id"]), x["root_id"]))

    lemma_root_records = [
        {"lemma_id": lem_id, "root_id": r_id}
        for lem_id, r_id in sorted(lemma_root_pairs, key=lambda p: (p[0], p[1]))
    ]

    # Write JSONL helper
    def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")

    files = {
        "words": out_dir / "words.jsonl",
        "lemmas": out_dir / "lemmas.jsonl",
        "roots": out_dir / "roots.jsonl",
        "word_lemmas": out_dir / "word_lemmas.jsonl",
        "word_roots": out_dir / "word_roots.jsonl",
        "lemma_roots": out_dir / "lemma_roots.jsonl",
    }

    _write_jsonl(files["words"], words_records)
    _write_jsonl(files["lemmas"], lemmas_records)
    _write_jsonl(files["roots"], roots_records)
    _write_jsonl(files["word_lemmas"], word_lemma_links)
    _write_jsonl(files["word_roots"], word_root_links)
    _write_jsonl(files["lemma_roots"], lemma_root_records)

    logger.info(
        "Parsed corpus: %d words, %d lemmas, %d roots, %d word_lemma links, %d word_root links, %d lemma_root links",
        len(words_records),
        len(lemmas_records),
        len(roots_records),
        len(word_lemma_links),
        len(word_root_links),
        len(lemma_root_records),
    )

    return {
        "words_count": len(words_records),
        "lemmas_count": len(lemmas_records),
        "roots_count": len(roots_records),
        "word_lemmas_count": len(word_lemma_links),
        "word_roots_count": len(word_root_links),
        "lemma_roots_count": len(lemma_root_records),
        "output_dir": out_dir,
        "files": files,
    }


if __name__ == "__main__":
    result = parse_corpus()
    print("Quranic Corpus parsed successfully:")
    print(f"  Words:       {result['words_count']}")
    print(f"  Lemmas:      {result['lemmas_count']}")
    print(f"  Roots:       {result['roots_count']}")
    print(f"  Word->Lemma: {result['word_lemmas_count']}")
    print(f"  Word->Root:  {result['word_roots_count']}")
    print(f"  Lemma->Root: {result['lemma_roots_count']}")
