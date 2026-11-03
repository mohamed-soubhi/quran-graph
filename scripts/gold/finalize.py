"""T4.3: turn the reviewed draft into the gold set data/gold/phase4.jsonl.

Input: data/interim/gold/phase4-draft.jsonl (rebuilt after the review decisions) and the reviewer's export.
Every draft span is accepted when the reviewer marked it ok, or when it was corrected by a recorded decision below.
"""
import json
import sys

REVIEW = "data/gold/phase4-review-Mohamed-2026-11-03.json"
REVIEWED = "2026-11-03"
# Spans the reviewer marked wrong, and what was done (decisions confirmed by Aya & Mohamed, 2026-11-03).
DECISIONS = {
    "ibn-kathir:1:6-6:1#3406-3486": "chainless takhrij line merged into the hadith before it",
    "ibn-kathir:1:6-6:1#3565-3754": "kept marfu: the route says مرفوعا; weighing versions is grading",
    "ibn-kathir:53:42-55:1#121-487": "kept HADITH kind athar (mawquf on Mu'adh)",
    "ibn-kathir:4:95-96:1#7601-7621": "window moved back so the Abu Dawud hadith is whole",
    "ibn-kathir:13:27-29:1#7824-8290": "kept HADITH kind athar (mawquf on Abu Hurayra)",
    "ibn-kathir:13:6-6:1#3217-3617": "dream report: COMMENTARY, span removed",
}
# Windows whose spans changed after the review; they get a second look in the T4.3 user test.
RECHECK = {"W13", "W15"}

segs = {json.loads(l)["segment_id"]: json.loads(l) for l in open("data/interim/tafsir/ibn-kathir/segments.jsonl", encoding="utf-8")}
review = json.load(open(REVIEW, encoding="utf-8"))
out, problems = [], []
for w in map(json.loads, open("data/interim/gold/phase4-draft.jsonl", encoding="utf-8")):
    rw = review["windows"][w["window_id"]]
    marks = rw["spans"]
    for sp in w["spans"]:
        verdict = marks.get(sp["span_id"], {}).get("verdict")
        if verdict != "ok" and w["window_id"] not in RECHECK and sp["span_id"] not in DECISIONS:
            problems.append(f"{w['window_id']} {sp['span_id']}: verdict {verdict}")
        sp["method"] = "human"
        if "draft_note" in sp:
            sp["note"] = sp.pop("draft_note")
    for sid in marks:
        if marks[sid].get("verdict") == "bad" and sid not in DECISIONS:
            problems.append(f"{w['window_id']} {sid}: marked bad without a decision")
    text = segs[w["segment_id"]]["text"]
    out.append({**w, "window_text": text[w["window_start"]:w["window_end"]], "reviewed_by": [review["reviewer"]],
                "reviewed": REVIEWED, "review_note": rw.get("note", ""),
                "decisions": {k: v for k, v in DECISIONS.items() if k.startswith(w["segment_id"] + "#")}})

for p in problems:
    print("PROBLEM", p)
if problems:
    sys.exit(1)
with open("data/gold/phase4.jsonl", "w", encoding="utf-8", newline="\n") as f:
    for o in out:
        f.write(json.dumps(o, ensure_ascii=False, sort_keys=True) + "\n")
print("windows", len(out), "spans", sum(len(o["spans"]) for o in out))
