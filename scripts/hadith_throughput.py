#!/usr/bin/env python3
"""Hadith extraction throughput measurement on sample cue paragraphs (T4.5)."""

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.extract.hadith_spans import (
    find_cue_paragraphs,
    split_long_paragraph,
    locate_and_check_anchors,
)
from src.extract.glm_client import extract_hadith_anchors
from src.log import get_logger

logger = get_logger("hadith_throughput")

SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
TOTAL_BOOK_PARAS = 11527  # As measured in T4.5 facts


def collect_all_cue_paragraphs() -> tuple[list[tuple[str, int, int]], int]:
    """Collect all cue paragraphs across the 1,911 segments."""
    all_cue_paras = []
    total_windows = 0
    with open(SEGMENTS_PATH, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            seg_id = d["segment_id"]
            text = d["text"]
            paras = find_cue_paragraphs(text)
            for p_start, p_end in paras:
                all_cue_paras.append((seg_id, p_start, p_end))
                p_text = text[p_start:p_end]
                sub_wins = split_long_paragraph(p_text, p_start, max_len=3000)
                total_windows += len(sub_wins)

    return all_cue_paras, total_windows


def process_sample_paragraph(
    item: tuple[str, int, int],
    segments: dict[str, str],
    model: str,
) -> dict:
    seg_id, p_start, p_end = item
    seg_text = segments[seg_id]
    para_text = seg_text[p_start:p_end]

    sub_wins = split_long_paragraph(para_text, p_start, max_len=3000)
    total_located = 0
    total_anchors = 0
    errors = 0
    call_times = []

    for sw_s, sw_e in sub_wins:
        sw_text = seg_text[sw_s:sw_e]
        t0 = time.time()
        try:
            anchor_list = extract_hadith_anchors(sw_text, model=model)
            elapsed = time.time() - t0
            call_times.append(elapsed)
            total_anchors += len(anchor_list.spans)

            located = locate_and_check_anchors(
                seg_text,
                anchor_list.spans,
                window_start=sw_s,
                segment_id=seg_id,
                run_id="throughput",
                model=model,
            )
            total_located += len(located)
        except Exception as exc:
            elapsed = time.time() - t0
            call_times.append(elapsed)
            errors += 1
            logger.error("Throughput call error: %s", exc)

    return {
        "calls": len(sub_wins),
        "call_times": call_times,
        "anchors": total_anchors,
        "located": total_located,
        "errors": errors,
    }


def measure_level(
    concurrency: int,
    sample_items: list[tuple[str, int, int]],
    segments: dict[str, str],
    model: str,
) -> dict:
    print(f"\nTesting Concurrency {concurrency} on {len(sample_items)} paragraphs...")
    t_start = time.time()

    def worker(item):
        return process_sample_paragraph(item, segments, model)

    results = []
    has_error_429 = False

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for res in executor.map(worker, sample_items):
            results.append(res)
            if res["errors"] > 0:
                print(f"  Encountered error/timeout in call.")

    wall_time = time.time() - t_start

    total_calls = sum(r["calls"] for r in results)
    all_call_times = [t for r in results for t in r["call_times"]]
    total_anchors = sum(r["anchors"] for r in results)
    total_located = sum(r["located"] for r in results)
    total_errors = sum(r["errors"] for r in results)

    mean_sec_call = sum(all_call_times) / len(all_call_times) if all_call_times else 0.0
    spans_per_para = total_located / len(sample_items) if sample_items else 0.0
    error_rate = total_errors / total_calls if total_calls > 0 else 0.0
    rejected_anchors = total_anchors - total_located

    # Effective throughput: paragraphs per second wall time
    paras_per_sec = len(sample_items) / wall_time if wall_time > 0 else 0.0
    projected_hours_all = (
        (TOTAL_BOOK_PARAS / paras_per_sec) / 3600 if paras_per_sec > 0 else 0.0
    )

    print(f"  Wall time:            {wall_time:.2f}s")
    print(f"  GLM calls:            {total_calls}")
    print(f"  Mean seconds/call:    {mean_sec_call:.2f}s")
    print(f"  Error/timeout rate:   {error_rate * 100:.1f}%")
    print(f"  Located anchors:      {total_located}")
    print(f"  Rejected anchors:     {rejected_anchors}")
    print(f"  Spans/paragraph:      {spans_per_para:.2f}")
    print(f"  Projected whole-book: {projected_hours_all:.2f} hours ({projected_hours_all * 60:.1f} minutes)")

    return {
        "concurrency": concurrency,
        "sample_size": len(sample_items),
        "wall_time_sec": round(wall_time, 2),
        "mean_seconds_per_call": round(mean_sec_call, 2),
        "total_calls": total_calls,
        "error_rate": round(error_rate, 4),
        "located_anchors": total_located,
        "rejected_anchors": rejected_anchors,
        "spans_per_paragraph": round(spans_per_para, 2),
        "projected_wall_hours_all_11527": round(projected_hours_all, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Measure GLM throughput on cue paragraphs.")
    parser.add_argument("--sample", type=int, default=100, help="Total sample size drawn (default: 100)")
    parser.add_argument("--model", type=str, default=None, help="Ollama model tag")
    parser.add_argument("--seed", type=int, default=42, help="Fixed random seed (default: 42)")
    args = parser.parse_args()

    model = args.model or os.getenv("GLM_MODEL", "glm-5.3-flash:cloud")

    print(f"Collecting cue paragraphs across whole book (segments.jsonl)...")
    all_cue_paras, total_windows = collect_all_cue_paragraphs()
    print(
        f"Found {len(all_cue_paras)} cue paragraphs ({total_windows} windows after splitting long paras)."
    )

    # Draw fixed sample
    rng = random.Random(args.seed)
    sample_size = min(args.sample, len(all_cue_paras))
    sampled_paras = rng.sample(all_cue_paras, sample_size)
    print(f"Drawn {sample_size} sample paragraphs (fixed seed {args.seed}).")

    # Load segment texts for sampled items
    needed_seg_ids = {item[0] for item in sampled_paras}
    segments: dict[str, str] = {}
    with open(SEGMENTS_PATH, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d["segment_id"] in needed_seg_ids:
                segments[d["segment_id"]] = d["text"]

    # Partition sample across concurrency levels:
    # E.g. for sample 100: 10 at c=1, 30 at c=4, 60 at c=8
    # Or test slices so total = sample_size
    n = len(sampled_paras)
    c1_n = max(5, int(n * 0.10))
    c4_n = max(10, int(n * 0.30))
    c8_n = n - c1_n - c4_n

    items_c1 = sampled_paras[:c1_n]
    items_c4 = sampled_paras[c1_n : c1_n + c4_n]
    items_c8 = sampled_paras[c1_n + c4_n :]

    results = []
    for c, items in [(1, items_c1), (4, items_c4), (8, items_c8)]:
        res = measure_level(c, items, segments, model)
        results.append(res)
        if res["error_rate"] > 0.50:
            print(f"Stopping concurrency tests due to high error rate at concurrency {c}")
            break

    # Print summary markdown table for ticket report
    print("\n=======================================================")
    print("Throughput Summary Table")
    print("=======================================================")
    print("| Concurrency | Sample | Sec/call (mean) | Error rate | Located/Rejected | Spans/para | Projected whole book (11,527 paras) |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        print(
            f"| {r['concurrency']} | {r['sample_size']} | {r['mean_seconds_per_call']:.1f}s | "
            f"{r['error_rate']*100:.1f}% | {r['located_anchors']}/{r['rejected_anchors']} | "
            f"{r['spans_per_paragraph']:.2f} | {r['projected_wall_hours_all_11527']:.1f} hours ({r['projected_wall_hours_all_11527']*60:.0f} min) |"
        )
    print("=======================================================")


if __name__ == "__main__":
    main()
