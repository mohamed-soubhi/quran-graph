"""Extraction smoke test (T0.5).

Runs GLM hadith extraction 5 times on the Ibn Kathir 2:255 paragraph 0 fixture,
validating JSON against the Pydantic schema and reporting character overlap
against expected spans.
"""

import json
import statistics
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extract.glm_client import extract_hadith_spans
from src.extract.models import HadithSpanList

FIXTURES_DIR = ROOT / "tests" / "fixtures"


def compute_overlap(e_start: int, e_end: int, p_start: int, p_end: int) -> float:
    """Compute character overlap fraction relative to expected span length."""
    inter = max(0, min(e_end, p_end) - max(e_start, p_start))
    expected_len = e_end - e_start
    if expected_len == 0:
        return 0.0
    return inter / expected_len


def main() -> None:
    txt_path = FIXTURES_DIR / "tafsir_sample.txt"
    expected_json_path = FIXTURES_DIR / "tafsir_sample.expected.json"

    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read()

    with open(expected_json_path, "r", encoding="utf-8") as f:
        expected_data = json.load(f)

    expected_hadith_spans = expected_data.get("hadith_spans", [])

    print("=" * 60)
    print("T0.5 Extraction Smoke Test (5 runs)")
    print(f"Input text length: {len(text)} characters")
    print(f"Expected hadith spans count: {len(expected_hadith_spans)}")
    for i, exp in enumerate(expected_hadith_spans, 1):
        print(f"  Expected {i}: [{exp['start']}, {exp['end']}) cue: {exp['cue']!r} collection: {exp.get('collection_hint')}")
    print("=" * 60)

    timings = []
    all_runs_results = []

    for run_idx in range(1, 6):
        print(f"\n--- Run {run_idx}/5 ---")
        t0 = time.time()
        try:
            span_list = extract_hadith_spans(text, timeout=180.0)
            elapsed = time.time() - t0
            timings.append(elapsed)
            print(f"Run {run_idx}: completed in {elapsed:.2f}s, extracted {len(span_list.spans)} spans", flush=True)

            for j, p in enumerate(span_list.spans, 1):
                print(f"  Predicted {j}: [{p.start}, {p.end}) cue: {p.cue!r} collection: {p.collection_hint} number: {p.number_hint}", flush=True)

            # Overlap analysis
            run_overlaps = []
            for i, exp in enumerate(expected_hadith_spans, 1):
                matching_preds = []
                for j, p in enumerate(span_list.spans, 1):
                    overlap_ratio = compute_overlap(exp["start"], exp["end"], p.start, p.end)
                    if overlap_ratio >= 0.5:
                        matching_preds.append((j, overlap_ratio))

                print(
                    f"  Expected {i} [{exp['start']}, {exp['end']}): "
                    f"{len(matching_preds)} predicted span(s) with >= 50% overlap "
                    f"({', '.join(f'pred #{idx} ({ratio*100:.1f}%)' for idx, ratio in matching_preds) or 'none'})",
                    flush=True,
                )
                run_overlaps.append({
                    "expected_idx": i,
                    "expected_span": (exp["start"], exp["end"]),
                    "matching_preds_count": len(matching_preds),
                    "matches": matching_preds,
                })

            all_runs_results.append({
                "run": run_idx,
                "elapsed": elapsed,
                "predicted_count": len(span_list.spans),
                "overlaps": run_overlaps,
            })

        except Exception as exc:
            print(f"Run {run_idx} FAILED: {exc}", file=sys.stderr)
            sys.exit(1)

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print(f"Successful runs: {len(timings)}/5 (100% schema-valid JSON)")
    mean_time = statistics.mean(timings)
    print(f"Timings: {', '.join(f'{t:.2f}s' for t in timings)}")
    print(f"Mean time per paragraph: {mean_time:.2f}s (min: {min(timings):.2f}s, max: {max(timings):.2f}s)")
    print("=" * 60)


if __name__ == "__main__":
    main()
