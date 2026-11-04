#!/usr/bin/env python3
"""Whole-book hadith extraction runner and build step (T4.5b).

Usage:
  # Extraction runner:
  python scripts/run_hadith_book.py [--limit N] [--concurrency 4] [--model TAG]

  # Build step (pure extraction to JSONL, no GLM calls, safe to repeat):
  python scripts/run_hadith_book.py --build
"""

import argparse
import collections
import datetime
import json
import os
import statistics
import sys
import threading
import time
from collections import Counter, deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from src.extract.glm_client import (
    ANCHOR_SYSTEM_PROMPT,
    FEWSHOT_ANCHOR_1_INPUT,
    FEWSHOT_ANCHOR_1_OUTPUT,
    FEWSHOT_ANCHOR_2_INPUT,
    FEWSHOT_ANCHOR_2_OUTPUT,
    PROMPT_VERSION,
    GlmResponseError,
    ollama_format,
    parse_anchor_response,
)
from src.extract.hadith_spans import (
    find_cue_paragraphs,
    locate_and_check_anchors,
    split_long_paragraph,
)
from src.log import get_logger

logger = get_logger("run_hadith_book")

SEGMENTS_PATH = ROOT / "data" / "interim" / "tafsir" / "ibn-kathir" / "segments.jsonl"
SCHEMA_PATH = ROOT / "docs" / "extraction_schema.json"
RAW_OUTPUT_PATH = ROOT / "data" / "interim" / "spans" / "hadith-raw.jsonl"
SPANS_OUTPUT_PATH = ROOT / "data" / "interim" / "spans" / "hadith.jsonl"
REJECTED_OUTPUT_PATH = ROOT / "data" / "interim" / "spans" / "hadith-rejected.jsonl"


def get_process_memory_mb() -> tuple[float, float]:
    """Get current Working Set and Peak Working Set memory usage in MB."""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        success = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        )
        if success:
            return counters.WorkingSetSize / (1024 * 1024), counters.PeakWorkingSetSize / (1024 * 1024)
    except Exception:
        pass
    return 0.0, 0.0


def collect_book_windows(segments_path: Path = SEGMENTS_PATH) -> list[tuple[str, str, int, int]]:
    """Generate all cue windows across segments in fixed deterministic order.

    Returns:
        List of tuples: (key, segment_id, window_start, window_end)
        where key is '<segment_id>#<start>-<end>'.
    """
    windows = []
    with open(segments_path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            seg_id = d["segment_id"]
            text = d["text"]
            cue_paras = find_cue_paragraphs(text)
            for p_start, p_end in cue_paras:
                para_text = text[p_start:p_end]
                sub_wins = split_long_paragraph(para_text, p_start, max_len=3000)
                for w_start, w_end in sub_wins:
                    key = f"{seg_id}#{w_start}-{w_end}"
                    windows.append((key, seg_id, w_start, w_end))
    return windows


def load_raw_status(raw_path: Path = RAW_OUTPUT_PATH) -> dict[str, str]:
    """Read existing hadith-raw.jsonl and return mapping key -> latest status.

    A half-written / corrupted last line is ignored.
    """
    status_by_key = {}
    if not raw_path.exists():
        return status_by_key

    with open(raw_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                k = rec.get("key")
                st = rec.get("status")
                if k and st:
                    status_by_key[k] = st
            except json.JSONDecodeError:
                logger.warning("Ignoring corrupted / half-written line in %s", raw_path)
                continue

    return status_by_key


def should_stop_for_failures(
    history: Sequence[bool],
    min_evaluated: int = 200,
    window_size: int = 200,
    max_failure_rate: float = 0.20,
) -> bool:
    """Return True if more than 20% of the last 200 windows failed."""
    if len(history) < min_evaluated:
        return False
    window = list(history)[-window_size:]
    failures = sum(1 for ok in window if not ok)
    return (failures / len(window)) > max_failure_rate


def call_glm_for_window(
    win_text: str,
    model: str,
    host: str,
    timeout: float = 120.0,
) -> tuple[str, str | None, float, int]:
    """Call Ollama /api/chat up to 3 attempts.

    Returns:
        tuple of (raw_text, error_message or None, elapsed_seconds, attempts_needed)
    """
    import requests

    schema_data = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    format_schema = ollama_format(schema_data)

    user_prompt = (
        f"Example 1:\nInput: {FEWSHOT_ANCHOR_1_INPUT}\nOutput: {json.dumps(FEWSHOT_ANCHOR_1_OUTPUT, ensure_ascii=False)}\n\n"
        f"Example 2:\nInput: {FEWSHOT_ANCHOR_2_INPUT}\nOutput: {json.dumps(FEWSHOT_ANCHOR_2_OUTPUT, ensure_ascii=False)}\n\n"
        f"Input:\n{win_text}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": ANCHOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "format": format_schema,
        "stream": True,
        "options": {"temperature": 0},
    }

    last_error: Exception | None = None
    last_raw = ""
    t0 = time.time()

    for attempt in range(1, 4):
        try:
            resp = requests.post(f"{host}/api/chat", json=payload, stream=True, timeout=timeout)
            resp.raise_for_status()

            parts = []
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})
                    if "content" in msg and msg["content"]:
                        parts.append(msg["content"])

            raw = "".join(parts).strip()
            last_raw = raw

            # Verify it parses into ParsedAnchors
            parse_anchor_response(raw)

            elapsed = time.time() - t0
            return raw, None, elapsed, attempt
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(1)

    elapsed = time.time() - t0
    return last_raw, str(last_error), elapsed, 3


def resolve_overlapping_spans(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge identical spans and keep longer span in partial overlaps (T4.5b).

    Returns:
        tuple of (kept_spans, rejected_spans_with_reason_overlap)
    """
    if not candidates:
        return [], []

    # Sort candidates by length descending, then non-fallback first, then start offset
    sorted_candidates = sorted(
        candidates,
        key=lambda s: (s["end"] - s["start"], not s.get("fallback_used", False), -s["start"]),
        reverse=True,
    )

    kept: list[dict] = []
    rejected: list[dict] = []

    for sp in sorted_candidates:
        # Check identical with an already kept span -> merge (keep one, no rejection record)
        if any(sp["start"] == k["start"] and sp["end"] == k["end"] for k in kept):
            continue

        # Check partial overlap with any already kept span
        overlapping_kept = None
        for k in kept:
            if max(sp["start"], k["start"]) < min(sp["end"], k["end"]):
                overlapping_kept = k
                break

        if overlapping_kept is not None:
            rejected.append({
                "segment_id": sp["segment_id"],
                "span_id": sp["span_id"],
                "start": sp["start"],
                "end": sp["end"],
                "reason": "overlap",
                "kind": sp.get("kind"),
                "cue": sp.get("cue"),
                "start_anchor": sp.get("start_anchor"),
                "end_anchor": sp.get("end_anchor"),
                "overlapped_by": overlapping_kept["span_id"],
            })
        else:
            kept.append(sp)

    kept.sort(key=lambda s: (s["start"], s["end"]))
    return kept, rejected


def run_build(
    raw_path: Path = RAW_OUTPUT_PATH,
    out_path: Path = SPANS_OUTPUT_PATH,
    rejected_path: Path = REJECTED_OUTPUT_PATH,
    segments_path: Path = SEGMENTS_PATH,
) -> dict:
    """Build step: parse latest ok windows from raw file, locate, resolve overlaps, write outputs."""
    print(f"\n=======================================================")
    print(f"Starting Build Step (reading {raw_path})")
    print(f"=======================================================")

    if not raw_path.exists():
        print(f"Error: Raw file {raw_path} not found.")
        return {}

    # Load segments
    segments_text: dict[str, str] = {}
    with open(segments_path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            segments_text[d["segment_id"]] = d["text"]

    # Read latest record per key
    latest_by_key: dict[str, dict] = {}
    with open(raw_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                k = rec.get("key")
                if k:
                    latest_by_key[k] = rec
            except json.JSONDecodeError:
                continue

    windows_ok = 0
    windows_failed = 0
    windows_no_span = 0
    total_unknown_collections = 0
    total_dropped_spans = 0

    ok_by_segment: dict[str, list[dict]] = collections.defaultdict(list)
    for rec in latest_by_key.values():
        if rec.get("status") == "ok":
            windows_ok += 1
            ok_by_segment[rec["segment_id"]].append(rec)
        else:
            windows_failed += 1

    all_kept_spans: list[dict] = []
    all_rejections: list[dict] = []

    for seg_id, recs in ok_by_segment.items():
        seg_text = segments_text.get(seg_id, "")
        if not seg_text:
            continue

        candidate_spans: list[dict] = []
        seg_rejected: list[dict] = []

        for rec in recs:
            raw_text = rec.get("raw_text", "")
            w_s = rec["window_start"]
            w_e = rec["window_end"]
            model = rec.get("model", "")

            try:
                parsed = parse_anchor_response(raw_text)
            except GlmResponseError as exc:
                logger.warning("Failed to parse raw_text for %s: %s", rec["key"], exc)
                continue

            total_unknown_collections += parsed.unknown_collections
            total_dropped_spans += parsed.dropped_spans

            for dropped in parsed.dropped_items:
                seg_rejected.append({
                    "segment_id": seg_id,
                    "span_id": None,
                    "window_start": w_s,
                    "window_end": w_e,
                    "start": None,
                    "end": None,
                    "reason": "invalid_span",
                    "raw": dropped,
                })

            if len(parsed.spans) == 0:
                windows_no_span += 1
                continue

            located = locate_and_check_anchors(
                seg_text,
                parsed.spans,
                window_start=w_s,
                window_end=w_e,
                segment_id=seg_id,
                run_id="book",
                model=model,
                rejected=seg_rejected,
            )
            for sp in located:
                # Confidence: 0.9, or 0.8 when fallback_used
                sp["confidence"] = 0.8 if sp.get("fallback_used") else 0.9
                candidate_spans.append(sp)

        kept_spans, overlap_rejected = resolve_overlapping_spans(candidate_spans)
        all_kept_spans.extend(kept_spans)
        all_rejections.extend(seg_rejected)
        all_rejections.extend(overlap_rejected)

    # Sort kept spans by segment_id then start offset
    all_kept_spans.sort(key=lambda s: (s["segment_id"], s["start"], s["end"]))

    # Write hadith.jsonl
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for sp in all_kept_spans:
            f.write(json.dumps(sp, ensure_ascii=False) + "\n")

    # Write hadith-rejected.jsonl
    with open(rejected_path, "w", encoding="utf-8") as f:
        for r in all_rejections:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Totals and stats
    spans_by_kind = Counter(s.get("kind") for s in all_kept_spans)
    rejected_by_reason = Counter(r.get("reason") for r in all_rejections)
    fallback_count = sum(1 for s in all_kept_spans if s.get("fallback_used"))

    lengths = [s["end"] - s["start"] for s in all_kept_spans]
    min_len = min(lengths) if lengths else 0
    max_len = max(lengths) if lengths else 0
    median_len = round(statistics.median(lengths), 1) if lengths else 0.0

    print(f"\n--- Build Totals ---")
    print(f"Windows ok:           {windows_ok}")
    print(f"Windows failed:       {windows_failed}")
    print(f"Windows with no span: {windows_no_span}")
    print(f"Total spans kept:     {len(all_kept_spans)}")
    print(f"Dropped spans:        {total_dropped_spans}")
    print(f"Unknown collections:  {total_unknown_collections}")
    print(f"Spans by kind:        marfu={spans_by_kind.get('marfu', 0)}, athar={spans_by_kind.get('athar', 0)}")
    print(f"Fallback count:       {fallback_count} (confidence 0.8)")
    print(f"Exact match count:    {len(all_kept_spans) - fallback_count} (confidence 0.9)")
    print(f"Span length min/median/max: {min_len} / {median_len} / {max_len} chars")
    print(f"\nRejected by reason ({len(all_rejections)} total):")
    for reason, count in sorted(rejected_by_reason.items(), key=lambda x: -x[1]):
        print(f"  {reason:18s}: {count}")

    print(f"\nOutput written:")
    print(f"  Spans:    {out_path}")
    print(f"  Rejected: {rejected_path}")
    print(f"=======================================================\n")

    return {
        "windows_ok": windows_ok,
        "windows_failed": windows_failed,
        "windows_no_span": windows_no_span,
        "total_spans": len(all_kept_spans),
        "dropped_spans": total_dropped_spans,
        "unknown_collections": total_unknown_collections,
        "spans_by_kind": dict(spans_by_kind),
        "rejected_by_reason": dict(rejected_by_reason),
        "fallback_count": fallback_count,
        "length_min": min_len,
        "length_median": median_len,
        "length_max": max_len,
    }


def run_extraction(
    limit: int | None = None,
    concurrency: int = 4,
    model: str | None = None,
    host: str | None = None,
    raw_path: Path = RAW_OUTPUT_PATH,
    segments_path: Path = SEGMENTS_PATH,
) -> None:
    """Run whole-book extraction with resume, batching, and stopping rules."""
    model = model or os.getenv("GLM_MODEL", "glm-5.3-flash:cloud")
    host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")

    print(f"\n=======================================================")
    print(f"Hadith Book Extraction Runner (T4.5b)")
    print(f"Model: {model}, Host: {host}, Concurrency: {concurrency}")
    if limit is not None:
        print(f"Limit: {limit} windows")
    print(f"Raw output: {raw_path}")
    print(f"=======================================================")

    all_windows = collect_book_windows(segments_path)
    total_book_windows = len(all_windows)
    print(f"Total cue windows in book: {total_book_windows}")

    # Load existing status
    raw_status = load_raw_status(raw_path)
    print(f"Existing raw records: {len(raw_status)} ({sum(1 for s in raw_status.values() if s == 'ok')} 'ok')")

    # Filter windows to process
    pending = []
    for win in all_windows:
        key = win[0]
        if raw_status.get(key) == "ok":
            continue
        pending.append(win)

    print(f"Windows needing processing: {len(pending)}")
    if limit is not None:
        pending = pending[:limit]
        print(f"Applying limit: will process {len(pending)} windows in this run.")

    if not pending:
        print("No windows to process. Exiting.")
        return

    # Load segments for pending windows
    needed_seg_ids = {w[1] for w in pending}
    segments: dict[str, str] = {}
    with open(segments_path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d["segment_id"] in needed_seg_ids:
                segments[d["segment_id"]] = d["text"]

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure raw file ends in newline before appending (F6)
    if raw_path.exists() and raw_path.stat().st_size > 0:
        with open(raw_path, "rb") as f_check:
            f_check.seek(-1, os.SEEK_END)
            last_byte = f_check.read(1)
            if last_byte != b"\n":
                with open(raw_path, "a", encoding="utf-8") as f_fix:
                    f_fix.write("\n")

    raw_file = open(raw_path, "a", encoding="utf-8")
    file_lock = threading.Lock()

    recent_outcomes: deque[bool] = deque(maxlen=200)
    call_durations: deque[float] = deque(maxlen=200)
    attempts_counter: Counter = Counter()

    processed_in_run = 0
    ok_in_run = 0
    failed_in_run = 0

    t_run_start = time.time()

    def worker(win_item):
        key, seg_id, w_s, w_e = win_item
        seg_text = segments[seg_id]
        win_text = seg_text[w_s:w_e]

        raw_text, err, sec, attempt_num = call_glm_for_window(win_text, model=model, host=host)
        status = "ok" if err is None else "failed"

        record = {
            "key": key,
            "segment_id": seg_id,
            "window_start": w_s,
            "window_end": w_e,
            "status": status,
            "attempts": attempt_num,
            "raw_text": raw_text,
            "error": err,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "seconds": round(sec, 2),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        with file_lock:
            raw_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw_file.flush()

        return status == "ok", sec, key, err, attempt_num

    print(f"\nProcessing {len(pending)} windows with sliding window concurrency of {concurrency}...")

    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            in_flight: dict = {}
            pending_iter = iter(pending)

            # Fill up to concurrency tasks
            for _ in range(concurrency):
                try:
                    item = next(pending_iter)
                    fut = executor.submit(worker, item)
                    in_flight[fut] = item
                except StopIteration:
                    break

            while in_flight:
                done, _ = wait(list(in_flight.keys()), return_when=FIRST_COMPLETED)
                for fut in done:
                    item = in_flight.pop(fut)
                    ok, sec, key, err, attempt_num = fut.result()
                    processed_in_run += 1
                    recent_outcomes.append(ok)
                    call_durations.append(sec)
                    attempts_counter[attempt_num] += 1

                    if ok:
                        ok_in_run += 1
                    else:
                        failed_in_run += 1
                        logger.warning("Window %s failed: %s", key, err)

                    # Check stop rule (> 20% failed in last 200 windows)
                    if should_stop_for_failures(recent_outcomes, min_evaluated=200):
                        print(
                            f"\nERROR: More than 20% of the last 200 windows failed! "
                            f"Stopping runner automatically (cloud outage or quota limit)."
                        )
                        # F6: Drain remaining in-flight calls before closing raw file
                        for rem_fut in list(in_flight.keys()):
                            try:
                                rem_fut.result()
                            except Exception:
                                pass
                        raw_file.close()
                        sys.exit(2)

                    # Print progress every 100 windows (or first, or last in run)
                    if processed_in_run % 100 == 0 or processed_in_run == len(pending):
                        elapsed_so_far = time.time() - t_run_start
                        real_sec_per_window = elapsed_so_far / processed_in_run if processed_in_run > 0 else 0.0
                        total_done_book = sum(1 for s in raw_status.values() if s == "ok") + ok_in_run
                        remaining_book = total_book_windows - total_done_book
                        hours_left = (remaining_book * real_sec_per_window) / 3600 if real_sec_per_window > 0 else 0.0
                        mean_sec = sum(call_durations) / len(call_durations) if call_durations else 0.0

                        print(
                            f"[{processed_in_run}/{len(pending)} in run | {total_done_book}/{total_book_windows} book] "
                            f"ok: {ok_in_run}, failed: {failed_in_run}, "
                            f"{mean_sec:.1f}s/call (real {real_sec_per_window:.1f}s/win), ~{hours_left:.1f}h left"
                        )

                    # Submit next window if available
                    try:
                        next_item = next(pending_iter)
                        new_fut = executor.submit(worker, next_item)
                        in_flight[new_fut] = next_item
                    except StopIteration:
                        pass
    finally:
        raw_file.close()

    total_time = time.time() - t_run_start
    real_sec_per_window_all = total_time / processed_in_run if processed_in_run > 0 else 0.0
    mean_sec_all = sum(call_durations) / len(call_durations) if call_durations else 0.0
    rss_mb, peak_mb = get_process_memory_mb()

    print(f"\n=======================================================")
    print(f"Extraction run finished in {total_time:.1f}s.")
    print(f"Processed: {processed_in_run} windows (ok: {ok_in_run}, failed: {failed_in_run})")
    print(f"Attempts needed: 1 attempt: {attempts_counter[1]}, 2 attempts: {attempts_counter[2]}, 3 attempts: {attempts_counter[3]}")
    print(f"Mean call duration: {mean_sec_all:.1f}s (real wall duration: {real_sec_per_window_all:.1f}s per window)")
    remaining_all = total_book_windows - (sum(1 for s in raw_status.values() if s == "ok") + ok_in_run)
    projected_hours_remaining = (remaining_all * real_sec_per_window_all) / 3600 if real_sec_per_window_all > 0 else 0.0
    projected_hours_full_book = (total_book_windows * real_sec_per_window_all) / 3600 if real_sec_per_window_all > 0 else 0.0
    print(f"Projected whole-book time (12,770 windows at c={concurrency}): ~{projected_hours_full_book:.1f} hours (remaining: ~{projected_hours_remaining:.1f} hours)")
    print(f"Memory use of process: Working set: {rss_mb:.1f} MB, Peak working set: {peak_mb:.1f} MB")
    print(f"=======================================================")


def main():
    parser = argparse.ArgumentParser(description="Whole-book hadith extraction runner & build step.")
    parser.add_argument("--build", action="store_true", help="Run build step from raw JSONL (no network calls)")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrency for GLM calls (default: 4)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of windows to process")
    parser.add_argument("--model", type=str, default=None, help="Ollama model tag")
    parser.add_argument("--host", type=str, default=None, help="Ollama host URL")
    parser.add_argument("--raw-path", type=Path, default=RAW_OUTPUT_PATH, help="Path to raw JSONL file")
    parser.add_argument("--out-path", type=Path, default=SPANS_OUTPUT_PATH, help="Path to hadith.jsonl output")
    parser.add_argument("--rejected-path", type=Path, default=REJECTED_OUTPUT_PATH, help="Path to hadith-rejected.jsonl output")
    args = parser.parse_args()

    if args.build:
        run_build(
            raw_path=args.raw_path,
            out_path=args.out_path,
            rejected_path=args.rejected_path,
        )
    else:
        run_extraction(
            limit=args.limit,
            concurrency=args.concurrency,
            model=args.model,
            host=args.host,
            raw_path=args.raw_path,
        )


if __name__ == "__main__":
    main()
