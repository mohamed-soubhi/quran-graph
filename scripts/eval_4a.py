"""Evaluation script for Gate 4a (Quran spans + ayah links).

Compares predicted QURAN spans inside the 50 gold windows against data/gold/phase4.jsonl.
A prediction is correct when its offsets AND its set of (ayah_id, rel) are identical to a gold span.

Writes: logs/eval-4a-<yyyymmdd-hhmm>.json
Prints precision, recall (bracketed gold only, 79), link accuracy, and disagreements.
"""

from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extract.quran_spans import DEFAULT_OUTPUT_PATH, extract_quran_spans

DEFAULT_GOLD_PATH = ROOT / "data" / "gold" / "phase4.jsonl"
LOGS_DIR = ROOT / "logs"


def run_eval(
    gold_path: Path | str = DEFAULT_GOLD_PATH,
    pred_path: Path | str = DEFAULT_OUTPUT_PATH,
    log_dir: Path | str = LOGS_DIR,
) -> dict[str, Any]:
    g_path = Path(gold_path)
    p_path = Path(pred_path)
    l_dir = Path(log_dir)

    if not g_path.exists():
        raise FileNotFoundError(f"Missing gold set: {g_path}")

    if not p_path.exists():
        print(f"Pred file {p_path} not found; generating via extract_quran_spans()...")
        extract_quran_spans(output_path=p_path)

    # 1. Load predictions grouped by segment_id
    preds_by_seg: dict[str, list[dict[str, Any]]] = {}
    with p_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            span = json.loads(line)
            preds_by_seg.setdefault(span["segment_id"], []).append(span)

    # 2. Load gold windows
    gold_windows: list[dict[str, Any]] = []
    with g_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                gold_windows.append(json.loads(line))

    total_pred = 0
    correct_pred = 0
    offset_matched = 0
    gold_bracketed = 0
    gold_unbracketed = 0
    disagreements: list[dict[str, Any]] = []
    unbracketed_missed: list[dict[str, Any]] = []

    for w in gold_windows:
        wid = w["window_id"]
        seg_id = w["segment_id"]
        w_start = w["window_start"]
        w_end = w["window_end"]
        w_text = w["window_text"]

        # Gold spans in this window
        gold_qspans = [s for s in w.get("spans", []) if s.get("type") == "QURAN"]

        # Check bracketed vs unbracketed in gold
        for gs in gold_qspans:
            rel_s = gs["start"] - w_start
            rel_e = gs["end"] - w_start
            q_txt = w_text[rel_s:rel_e]
            if q_txt.startswith("﴿") and q_txt.endswith("﴾"):
                gold_bracketed += 1
            else:
                gold_unbracketed += 1
                unbracketed_missed.append({
                    "window_id": wid,
                    "span_id": gs["span_id"],
                    "start": gs["start"],
                    "end": gs["end"],
                    "text": q_txt,
                    "note": gs.get("note", "unbracketed quote"),
                })

        # Predicted spans inside this window
        seg_preds = preds_by_seg.get(seg_id, [])
        window_preds = [
            p for p in seg_preds if p["start"] >= w_start and p["end"] <= w_end
        ]

        for p in window_preds:
            total_pred += 1
            p_s = p["start"]
            p_e = p["end"]
            rel_s = p_s - w_start
            rel_e = p_e - w_start
            q_txt = w_text[rel_s:rel_e] if 0 <= rel_s < len(w_text) else ""

            pred_links = set(
                (l["ayah_id"], l.get("rel", "CITES")) for l in p.get("links", [])
            )

            # Match gold span by offset
            matching_gold = next(
                (gs for gs in gold_qspans if gs["start"] == p_s and gs["end"] == p_e),
                None,
            )

            if not matching_gold:
                disagreements.append({
                    "window_id": wid,
                    "type": "unexpected_prediction",
                    "span_id": p["span_id"],
                    "quote_text": q_txt,
                    "pred_links": list(pred_links),
                })
                continue

            offset_matched += 1
            gold_links = set(
                (l["ayah_id"], l.get("rel", "CITES"))
                for l in matching_gold.get("links", [])
            )

            if pred_links == gold_links:
                correct_pred += 1
            else:
                disagreements.append({
                    "window_id": wid,
                    "type": "links_mismatch",
                    "span_id": p["span_id"],
                    "quote_text": q_txt,
                    "pred_links": sorted(list(pred_links)),
                    "gold_links": sorted(list(gold_links)),
                })

    precision = correct_pred / total_pred if total_pred else 0.0
    recall = correct_pred / gold_bracketed if gold_bracketed else 0.0
    link_acc = correct_pred / offset_matched if offset_matched else 0.0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    log_file = l_dir / f"eval-4a-{timestamp}.json"
    l_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "timestamp": timestamp,
        "precision": precision,
        "recall_bracketed": recall,
        "link_accuracy": link_acc,
        "total_predicted": total_pred,
        "correct_predicted": correct_pred,
        "offset_matched": offset_matched,
        "gold_bracketed": gold_bracketed,
        "gold_unbracketed": gold_unbracketed,
        "disagreements": disagreements,
        "unbracketed_missed": unbracketed_missed,
    }

    with log_file.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("Gate 4a Evaluation Results")
    print("=" * 60)
    print(f"Total Gold QURAN spans:  {gold_bracketed + gold_unbracketed} (79 bracketed, 4 unbracketed)")
    print(f"Predicted QURAN spans:   {total_pred}")
    print(f"Correct (offset + links): {correct_pred}")
    print(f"Precision:               {precision * 100:.2f}% (target >= 98.0%)")
    print(f"Recall (bracketed only): {recall * 100:.2f}%")
    print(f"Link accuracy:           {link_acc * 100:.2f}%")
    print(f"Disagreements:           {len(disagreements)}")
    print(f"Unbracketed missed:      {len(unbracketed_missed)} (outside gate)")
    print(f"Log written to:          {log_file}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    run_eval()
