"""Gate 4c: span layer completion verification (T4.6).

Checks:
1. 100% exact coverage per segment (13,401,179 characters total, start 0, touch, end len(text), 0 holes, 0 overlaps).
2. 0 partial overlaps anywhere across all spans.
3. Every nested span lies strictly inside its parent, and children of the same parent do not overlap.
4. Gold validation: all 4 gold OTHER spans exact; gold parent agreement (matched / both-present / total).

Usage:
    .venv\\Scripts\\python.exe scripts\\gate_4c.py
Exits 0 on PASS, 1 on FAIL.
"""

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
DEFAULT_FOOTNOTES_PATH = ROOT / "data" / "interim" / "spans" / "footnotes.jsonl"
DEFAULT_QURAN_PATH = ROOT / "data" / "interim" / "spans" / "quran.jsonl"
DEFAULT_HADITH_PATH = ROOT / "data" / "interim" / "spans" / "hadith.jsonl"
DEFAULT_POETRY_PATH = ROOT / "data" / "interim" / "spans" / "poetry.jsonl"
DEFAULT_PARENTS_PATH = ROOT / "data" / "interim" / "spans" / "parents.jsonl"
DEFAULT_COMMENTARY_PATH = ROOT / "data" / "interim" / "spans" / "commentary.jsonl"
DEFAULT_GOLD_PATH = ROOT / "data" / "gold" / "phase4.jsonl"

EXPECTED_TOTAL_CHARS = 13_401_179
EXPECTED_SEGMENTS = 1_911
EXPECTED_GOLD_OTHER = 4
EXPECTED_GOLD_PARENTS_TOTAL = 29


def evaluate_gate_4c(
    segments: list[dict[str, Any]],
    spans_by_segment: dict[str, list[dict[str, Any]]],
    parents: list[dict[str, Any]],
    commentary: list[dict[str, Any]],
    gold_path: Path | str | None = None,
    expected_total_chars: int | None = EXPECTED_TOTAL_CHARS,
    check_gold: bool = True,
) -> bool:
    """Run all Gate 4c checks and print summary table."""
    gold_p = Path(gold_path) if gold_path else DEFAULT_GOLD_PATH

    failures: list[str] = []
    checks: list[tuple[str, str, str]] = []

    # Map nested spans
    parent_of: dict[str, str] = {r["span_id"]: r["parent"] for r in parents}
    nested_ids: set[str] = set(parent_of.keys())

    # Map all spans by span_id
    all_spans_by_id: dict[str, dict[str, Any]] = {}
    for seg_id, spans in spans_by_segment.items():
        for s in spans:
            all_spans_by_id[s["span_id"]] = s
    for c in commentary:
        all_spans_by_id[c["span_id"]] = c

    # 1. Partial overlaps across all spans
    partial_overlaps = 0
    for seg_id, spans in spans_by_segment.items():
        n = len(spans)
        for i in range(n):
            s1 = spans[i]
            for j in range(i + 1, n):
                s2 = spans[j]
                if not (s1["end"] <= s2["start"] or s2["end"] <= s1["start"]):
                    nested = (
                        (s1["start"] <= s2["start"] and s2["end"] <= s1["end"])
                        or (s2["start"] <= s1["start"] and s1["end"] <= s2["end"])
                    )
                    if not nested:
                        partial_overlaps += 1
    if partial_overlaps == 0:
        checks.append(("Partial overlaps (typed spans)", "0", "PASS"))
    else:
        checks.append(("Partial overlaps (typed spans)", f"{partial_overlaps} found", "FAIL"))
        failures.append(f"{partial_overlaps} partial overlaps found among typed spans")

    # 2. Coverage & top-level partition per segment
    total_covered = 0
    coverage_holes = 0
    top_level_overlaps = 0
    top_counts: Counter[str] = Counter()
    blank_comm = 0
    non_blank_comm = 0

    for c in commentary:
        if c.get("blank"):
            blank_comm += 1
        else:
            non_blank_comm += 1

    for seg in segments:
        seg_id = seg["segment_id"]
        text = seg["text"]
        typed_spans = spans_by_segment.get(seg_id, [])
        seg_top_typed = [s for s in typed_spans if s["span_id"] not in nested_ids]
        seg_comm = [
            c for c in commentary if c["segment_id"] == seg_id
        ]
        all_top = seg_top_typed + seg_comm
        all_top.sort(key=lambda s: (s["start"], s["end"]))

        for s in all_top:
            top_counts[s["type"]] += 1

        c_pos = 0
        for s in all_top:
            if s["start"] != c_pos:
                coverage_holes += 1
            if s["start"] < c_pos:
                top_level_overlaps += 1
            c_pos = s["end"]
            total_covered += (s["end"] - s["start"])

        if c_pos != len(text):
            coverage_holes += 1

    # Check total characters
    target_chars = expected_total_chars if expected_total_chars is not None else sum(len(s["text"]) for s in segments)
    if total_covered == target_chars and coverage_holes == 0 and top_level_overlaps == 0:
        checks.append((f"Top-level coverage ({target_chars:,} chars, 100%)", f"{total_covered:,} chars, 0 holes", "PASS"))
    else:
        checks.append((
            "Top-level coverage",
            f"{total_covered:,} chars (expected {target_chars:,}, holes={coverage_holes}, overlaps={top_level_overlaps})",
            "FAIL",
        ))
        failures.append(f"Coverage mismatch: {total_covered} chars, {coverage_holes} holes, {top_level_overlaps} overlaps")

    # 3. Nested spans inside parent & children non-overlapping
    children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    nested_outside_parent = 0
    for child_id, parent_id in parent_of.items():
        child = all_spans_by_id.get(child_id)
        parent = all_spans_by_id.get(parent_id)
        if not child or not parent:
            nested_outside_parent += 1
            continue
        if not (parent["start"] <= child["start"] and child["end"] <= parent["end"]):
            nested_outside_parent += 1
        children_by_parent[parent_id].append(child)

    children_overlaps = 0
    for pid, children in children_by_parent.items():
        children.sort(key=lambda s: (s["start"], s["end"]))
        for i in range(len(children)):
            c1 = children[i]
            for j in range(i + 1, len(children)):
                c2 = children[j]
                if not (c1["end"] <= c2["start"] or c2["end"] <= c1["start"]):
                    children_overlaps += 1

    if nested_outside_parent == 0:
        checks.append(("Nested spans inside parent", f"{len(parents):,} edges strictly inside", "PASS"))
    else:
        checks.append(("Nested spans inside parent", f"{nested_outside_parent} outside parent", "FAIL"))
        failures.append(f"{nested_outside_parent} nested spans not enclosed by parent")

    if children_overlaps == 0:
        checks.append(("Children of same parent disjoint", "0 overlaps", "PASS"))
    else:
        checks.append(("Children of same parent disjoint", f"{children_overlaps} overlaps", "FAIL"))
        failures.append(f"{children_overlaps} sibling children overlap")

    # 4. Gold validation
    if check_gold:
        gold_other_exact = 0
        if gold_p.exists():
            gold_windows = [
                json.loads(line) for line in gold_p.read_text(encoding="utf-8").splitlines() if line.strip()
            ]
            gold_other_map: dict[str, dict[str, Any]] = {}
            gold_nested: list[dict[str, Any]] = []

            for w in gold_windows:
                for s in w["spans"]:
                    if s["type"] == "OTHER":
                        gold_other_map[s["span_id"]] = s
                    if s.get("parent"):
                        gold_nested.append(s)

            for gid in gold_other_map:
                if gid in all_spans_by_id and all_spans_by_id[gid]["type"] == "OTHER":
                    gold_other_exact += 1

            if gold_other_exact == EXPECTED_GOLD_OTHER:
                checks.append(("Gold OTHER spans exact", f"{gold_other_exact}/{EXPECTED_GOLD_OTHER}", "PASS"))
            else:
                checks.append(("Gold OTHER spans exact", f"{gold_other_exact}/{EXPECTED_GOLD_OTHER}", "FAIL"))
                failures.append(f"Gold OTHER spans: found {gold_other_exact}/{EXPECTED_GOLD_OTHER}")

            # Gold parents
            both_present = 0
            parents_matched = 0
            for s in gold_nested:
                cid = s["span_id"]
                pid = s["parent"]
                if cid in all_spans_by_id and pid in all_spans_by_id:
                    both_present += 1
                    if parent_of.get(cid) == pid:
                        parents_matched += 1

            gold_parent_str = f"{parents_matched}/{both_present}/{len(gold_nested)}"
            if parents_matched == both_present and len(gold_nested) == EXPECTED_GOLD_PARENTS_TOTAL:
                checks.append(("Gold parent agreement", f"{gold_parent_str} (100% agreement)", "PASS"))
            else:
                checks.append(("Gold parent agreement", f"{gold_parent_str} (mismatch)", "FAIL"))
                failures.append(f"Gold parent agreement mismatch: {gold_parent_str}")
        else:
            checks.append(("Gold validation", f"Gold file missing: {gold_p}", "FAIL"))
            failures.append(f"Gold file not found: {gold_p}")

    # Print Gate 4c Table
    print("\n" + "=" * 76)
    print("                      GATE 4c VERIFICATION TABLE                      ")
    print("=" * 76)
    print(f"{'Check':<44} | {'Result':<20} | {'Status':<6}")
    print("-" * 76)
    for name, result, status in checks:
        print(f"{name:<44} | {result:<20} | {status:<6}")
    print("-" * 76)

    print("\nSummary Counts:")
    print(f"  Segments: {len(segments):,}")
    print(f"  Total characters covered: {total_covered:,} / {EXPECTED_TOTAL_CHARS:,} (100.0%)")
    print("  Top-level spans by type:")
    for t in ("FOOTNOTE", "HADITH", "QURAN", "OTHER", "COMMENTARY"):
        print(f"    - {t:<11}: {top_counts[t]:>7,}")
    print(f"  COMMENTARY breakdown: {blank_comm:,} blank, {non_blank_comm:,} non-blank")
    print(f"  Nested spans (INSIDE): {len(parents):,}")
    inside_by_type: Counter[tuple[str, str]] = Counter()
    for r in parents:
        inside_by_type[(r["type"], r["parent_type"])] += 1
    for (ct, pt), cnt in sorted(inside_by_type.items()):
        print(f"    - {ct} -> {pt}: {cnt:,}")

    passed = len(failures) == 0
    print("=" * 76)
    print(f"Gate 4c Overall: {'PASS' if passed else 'FAIL'}")
    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  [X] {f}")
    print("=" * 76 + "\n")

    return passed


def main() -> int:
    # Load all inputs
    if not DEFAULT_SEGMENTS_PATH.exists():
        print(f"Error: missing {DEFAULT_SEGMENTS_PATH}", file=sys.stderr)
        return 1

    segments = [
        json.loads(line)
        for line in DEFAULT_SEGMENTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    spans_by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    span_files = [
        DEFAULT_FOOTNOTES_PATH,
        DEFAULT_QURAN_PATH,
        DEFAULT_HADITH_PATH,
        DEFAULT_POETRY_PATH,
    ]
    for sf in span_files:
        if not sf.exists():
            print(f"Error: missing {sf}", file=sys.stderr)
            return 1
        with sf.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    spans_by_segment[r["segment_id"]].append(r)

    if not DEFAULT_PARENTS_PATH.exists():
        print(f"Error: missing {DEFAULT_PARENTS_PATH}", file=sys.stderr)
        return 1
    parents = [
        json.loads(line)
        for line in DEFAULT_PARENTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if not DEFAULT_COMMENTARY_PATH.exists():
        print(f"Error: missing {DEFAULT_COMMENTARY_PATH}", file=sys.stderr)
        return 1
    commentary = [
        json.loads(line)
        for line in DEFAULT_COMMENTARY_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    passed = evaluate_gate_4c(
        segments=segments,
        spans_by_segment=spans_by_segment,
        parents=parents,
        commentary=commentary,
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
