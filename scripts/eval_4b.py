#!/usr/bin/env python3
"""Gate 4b evaluation script: evaluate hadith span extraction against gold set (T4.5)."""

import argparse
import datetime
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Set project root and configure UTF-8
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.extract.hadith_spans import (
    find_cue_paragraphs,
    split_long_paragraph,
    locate_and_check_anchors,
    compute_iou,
    match_spans_one_to_one,
)
from src.extract.glm_client import extract_hadith_anchors
from src.log import get_logger

logger = get_logger("eval_4b")

GOLD_PATH = ROOT / "data" / "gold" / "phase4.jsonl"
SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
OUTPUT_DIR = ROOT / "data" / "interim" / "spans"
LOGS_DIR = ROOT / "logs"


def load_gold_and_segments() -> tuple[list[dict], dict[str, str], list[dict]]:
    gold_windows = []
    with open(GOLD_PATH, encoding="utf-8") as f:
        for line in f:
            gold_windows.append(json.loads(line))

    segments = {}
    with open(SEGMENTS_PATH, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            segments[d["segment_id"]] = d["text"]

    all_gold_hadiths = []
    for w in gold_windows:
        for sp in w.get("spans", []):
            if sp.get("type") == "HADITH":
                all_gold_hadiths.append({
                    "window_id": w["window_id"],
                    "segment_id": w["segment_id"],
                    "start": sp["start"],
                    "end": sp["end"],
                    "kind": sp.get("kind"),
                    "cue": sp.get("cue"),
                    "collection_hint": sp.get("collection_hint"),
                    "number_hint": sp.get("number_hint"),
                })

    return gold_windows, segments, all_gold_hadiths


def evaluate_window(
    w: dict,
    segments: dict[str, str],
    run_id: str,
    model: str,
) -> tuple[str, list[dict], int, list[float]]:
    seg_id = w["segment_id"]
    w_start, w_end = w["window_start"], w["window_end"]
    seg_text = segments[seg_id]

    cue_paras = find_cue_paragraphs(seg_text)
    intersecting_paras = [
        p for p in cue_paras if max(p[0], w_start) < min(p[1], w_end)
    ]

    predicted_spans: list[dict] = []
    call_times: list[float] = []
    calls = 0

    for p_start, p_end in intersecting_paras:
        para_text = seg_text[p_start:p_end]
        sub_wins = split_long_paragraph(para_text, p_start, max_len=3000)
        for sw_s, sw_e in sub_wins:
            sw_text = seg_text[sw_s:sw_e]
            t0 = time.time()
            anchors = extract_hadith_anchors(sw_text, model=model)
            elapsed = time.time() - t0
            calls += 1
            call_times.append(elapsed)

            located = locate_and_check_anchors(
                seg_text,
                anchors.spans,
                window_start=sw_s,
                segment_id=seg_id,
                run_id=run_id,
                model=model,
            )
            for sp in located:
                # keep predicted spans that overlap the window
                if max(sp["start"], w_start) < min(sp["end"], w_end):
                    sp["window_id"] = w["window_id"]
                    predicted_spans.append(sp)

    return w["window_id"], predicted_spans, calls, call_times


def run_single_evaluation(
    run_index: int,
    gold_windows: list[dict],
    segments: dict[str, str],
    all_gold_hadiths: list[dict],
    model: str,
    concurrency: int = 4,
) -> dict:
    run_id = f"run{run_index}"
    print(f"\n=======================================================")
    print(f"Starting Run {run_index} (model: {model}, concurrency: {concurrency})")
    print(f"=======================================================")

    t_start = time.time()
    total_calls = 0
    all_call_times: list[float] = []
    all_predicted: list[dict] = []

    def task(w):
        return evaluate_window(w, segments, run_id, model)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        window_results = list(executor.map(task, gold_windows))

    for wid, preds, n_calls, c_times in window_results:
        total_calls += n_calls
        all_call_times.extend(c_times)
        seen = set()
        for sp in preds:
            key = (sp["start"], sp["end"])
            if key not in seen:
                seen.add(key)
                all_predicted.append(sp)

    wall_time = time.time() - t_start

    # Save predicted spans to data/interim/spans/hadith-gold-run<k>.jsonl
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / f"hadith-gold-run{run_index}.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for sp in all_predicted:
            f.write(json.dumps(sp, ensure_ascii=False) + "\n")

    # Match spans
    pairs, false_positives, misses = match_spans_one_to_one(
        all_predicted, all_gold_hadiths, min_iou=0.5
    )

    n_pred = len(all_predicted)
    n_gold = len(all_gold_hadiths)
    n_match = len(pairs)

    precision = n_match / n_pred if n_pred > 0 else 0.0
    recall = n_match / n_gold if n_gold > 0 else 0.0
    mean_iou = sum(p[2] for p in pairs) / n_match if n_match > 0 else 0.0
    iou_90_count = sum(1 for p in pairs if p[2] >= 0.9)
    kind_acc = (
        sum(1 for p, g, _ in pairs if p.get("kind") == g.get("kind")) / n_match
        if n_match > 0
        else 0.0
    )

    mean_sec_call = sum(all_call_times) / total_calls if total_calls > 0 else 0.0
    n_fallback = sum(1 for sp in all_predicted if sp.get("fallback_used"))

    # Gate 4b checks
    gate_pass = precision >= 0.90 and recall >= 0.80 and mean_iou >= 0.90

    # Print summary block
    print(f"\n--- Run {run_index} Summary ---")
    print(f"Predicted spans: {n_pred}")
    print(f"Gold spans:      {n_gold}")
    print(f"Matched spans:   {n_match}")
    print(f"Precision:       {precision * 100:.2f}% (target >= 90.0%)")
    print(f"Recall:          {recall * 100:.2f}% (target >= 80.0%)")
    print(f"Mean IoU:        {mean_iou:.4f} (target >= 0.90)")
    print(f"IoU >= 0.9:      {iou_90_count}/{n_match}")
    print(f"Kind accuracy:   {kind_acc * 100:.2f}%")
    print(f"Fallback spans:  {n_fallback}/{n_pred}")
    print(f"GLM calls:       {total_calls}")
    print(f"Wall time:       {wall_time:.2f}s")
    print(f"Mean call time:  {mean_sec_call:.2f}s")
    print(f"Saved run spans: {out_file}")

    if false_positives:
        print(f"\nFalse positives ({len(false_positives)}):")
        for fp in false_positives:
            txt = segments[fp["segment_id"]][fp["start"]:fp["end"]]
            print(f"  [{fp.get('window_id')}] [{fp['start']}, {fp['end']}): {txt[:60]!r}")

    if misses:
        print(f"\nMisses ({len(misses)}):")
        for m in misses:
            txt = segments[m["segment_id"]][m["start"]:m["end"]]
            print(f"  [{m.get('window_id')}] [{m['start']}, {m['end']}): {txt[:60]!r}")

    print(f"\nRun {run_index} Result: {'PASS' if gate_pass else 'FAIL'}")

    return {
        "run_index": run_index,
        "run_id": run_id,
        "model": model,
        "wall_time_seconds": round(wall_time, 2),
        "total_glm_calls": total_calls,
        "mean_seconds_per_call": round(mean_sec_call, 2),
        "predicted_count": n_pred,
        "gold_count": n_gold,
        "matched_count": n_match,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "mean_iou": round(mean_iou, 4),
        "iou_90_count": iou_90_count,
        "kind_accuracy": round(kind_acc, 4),
        "fallback_count": n_fallback,
        "gate_pass": gate_pass,
        "false_positives": [
            {
                "window_id": fp.get("window_id"),
                "start": fp["start"],
                "end": fp["end"],
                "text_snippet": segments[fp["segment_id"]][fp["start"]:fp["end"]][:60],
            }
            for fp in false_positives
        ],
        "misses": [
            {
                "window_id": m.get("window_id"),
                "start": m["start"],
                "end": m["end"],
                "text_snippet": segments[m["segment_id"]][m["start"]:m["end"]][:60],
            }
            for m in misses
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate hadith span extraction (Gate 4b).")
    parser.add_argument("--runs", type=int, default=3, help="Number of evaluation runs (default: 3)")
    parser.add_argument("--model", type=str, default=None, help="Ollama model tag")
    parser.add_argument("--concurrency", type=int, default=4, help="Thread pool concurrency (default: 4)")
    args = parser.parse_args()

    model = args.model or os.getenv("GLM_MODEL", "glm-5.3-flash:cloud")

    gold_windows, segments, all_gold_hadiths = load_gold_and_segments()
    print(f"Loaded {len(gold_windows)} gold windows ({len(all_gold_hadiths)} HADITH spans)")

    run_summaries = []
    all_passed = True

    for k in range(1, args.runs + 1):
        summary = run_single_evaluation(
            run_index=k,
            gold_windows=gold_windows,
            segments=segments,
            all_gold_hadiths=all_gold_hadiths,
            model=model,
            concurrency=args.concurrency,
        )
        run_summaries.append(summary)
        if not summary["gate_pass"]:
            all_passed = False

    # Save summary json to logs/eval-4b-<timestamp>.json
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    summary_path = LOGS_DIR / f"eval-4b-{ts}.json"
    eval_report = {
        "timestamp": ts,
        "model": model,
        "runs_requested": args.runs,
        "gate_target": {
            "precision": ">= 0.90",
            "recall": ">= 0.80",
            "mean_iou": ">= 0.90",
        },
        "all_passed": all_passed,
        "runs": run_summaries,
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(eval_report, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\n=======================================================")
    print(f"Final Gate 4b Verdict across {args.runs} runs: {'PASS' if all_passed else 'FAIL'}")
    print(f"Summary saved to: {summary_path}")
    print(f"=======================================================")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
