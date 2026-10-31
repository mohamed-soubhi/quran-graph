"""Calculate and print statistics for fawazahmed0 hadith collections (T1.3).

Per collection:
- Total hadith count
- Hadiths with >= 1 grade
- Distinct grader names (from grades[].name)
- Top 5 most common grade values (grades[].grade)

All data read as UTF-8. Hadith grades are reported as-is without alteration or interpretation.
"""

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingest.hadith_fawazahmed0 import extract_arabic_editions

RAW_DIR = ROOT / "data" / "raw"
HADITH_DIR = RAW_DIR / "hadith" / "fawazahmed0"
EDITIONS_FILE = HADITH_DIR / "editions.json"


def calculate_hadith_stats(
    hadith_dir: Path | str = HADITH_DIR,
    editions_path: Path | str = EDITIONS_FILE,
) -> dict[str, Any]:
    """Calculate statistics across all 10 raw Arabic hadith collections."""
    base_dir = Path(hadith_dir)
    editions_file = Path(editions_path)

    if not editions_file.exists():
        raise FileNotFoundError(f"editions.json not found at {editions_file}")

    editions = extract_arabic_editions(editions_file)

    collections_stats: list[dict[str, Any]] = []
    total_hadiths = 0
    total_with_grades = 0
    all_graders: set[str] = set()

    for ed_name in editions:
        file_path = base_dir / f"{ed_name}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Missing hadith file: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        hadiths = data.get("hadiths", [])
        hadith_count = len(hadiths)
        total_hadiths += hadith_count

        with_grade_count = 0
        graders: set[str] = set()
        grade_counter: Counter[str] = Counter()

        for h in hadiths:
            grades = h.get("grades", [])
            if grades:
                with_grade_count += 1
                for g in grades:
                    g_name = g.get("name")
                    g_val = g.get("grade")
                    if g_name and str(g_name).strip():
                        graders.add(str(g_name).strip())
                    if g_val and str(g_val).strip():
                        grade_counter[str(g_val).strip()] += 1

        total_with_grades += with_grade_count
        all_graders.update(graders)

        col_name = ed_name[4:] if ed_name.startswith("ara-") else ed_name
        collections_stats.append({
            "edition": ed_name,
            "collection": col_name,
            "count": hadith_count,
            "with_grades": with_grade_count,
            "graders": sorted(graders),
            "top_5_grades": grade_counter.most_common(5),
            "empty_texts": sum(1 for h in hadiths if not h.get("text", "").strip()),
        })

    return {
        "collections": collections_stats,
        "total_collections": len(collections_stats),
        "total_hadiths": total_hadiths,
        "total_with_grades": total_with_grades,
        "distinct_graders": sorted(all_graders),
    }


def format_markdown_table(stats: dict[str, Any]) -> str:
    """Format hadith statistics as a GitHub Flavored Markdown table."""
    lines = [
        "| Collection | Edition | Total Hadiths | With ≥1 Grade | Graders | Top 5 Grade Values |",
        "|---|---|---|---|---|---|",
    ]
    for c in stats["collections"]:
        col = c["collection"]
        ed = c["edition"]
        cnt = f"{c['count']:,}"
        wg = f"{c['with_grades']:,}"
        graders_str = ", ".join(c["graders"]) if c["graders"] else "—"
        if c["top_5_grades"]:
            top_grades_str = ", ".join(f"{g} ({n:,})" for g, n in c["top_5_grades"])
        else:
            top_grades_str = "—"
        lines.append(f"| {col} | `{ed}` | {cnt} | {wg} | {graders_str} | {top_grades_str} |")

    lines.append(
        f"| **Total** | **10 collections** | **{stats['total_hadiths']:,}** | **{stats['total_with_grades']:,}** | **{len(stats['distinct_graders'])} distinct graders** | — |"
    )
    return "\n".join(lines)


def print_stats(stats: dict[str, Any]) -> None:
    print("=" * 80)
    print("fawazahmed0 Hadith Collections (Arabic) Statistics")
    print("=" * 80)
    print(format_markdown_table(stats))
    print("=" * 80)
    print(f"Total collections:        {stats['total_collections']}")
    print(f"Total hadiths:            {stats['total_hadiths']:,}")
    print(f"Hadiths with >= 1 grade:  {stats['total_with_grades']:,} ({stats['total_with_grades'] / stats['total_hadiths']:.1%})")
    print(f"Distinct grader names ({len(stats['distinct_graders'])}): {', '.join(stats['distinct_graders'])}")
    print("=" * 80)


if __name__ == "__main__":
    stats = calculate_hadith_stats()
    print_stats(stats)
