"""T4.3: build the local HTML review page for the Phase 4 gold draft."""
import html
import json

segs = {json.loads(l)["segment_id"]: json.loads(l) for l in open("data/interim/tafsir/ibn-kathir/segments.jsonl", encoding="utf-8")}
ayat = {json.loads(l)["ayah_id"]: json.loads(l) for l in open("data/interim/quran/ayat.jsonl", encoding="utf-8")}
draft = [json.loads(l) for l in open("data/interim/gold/phase4-draft.jsonl", encoding="utf-8")]


def tree(text, base, spans):
    """Nested render tree for text[base:...] with properly nested spans (sorted by start, -end)."""
    out, pos, i = [], 0, 0
    while i < len(spans):
        sp = spans[i]
        s, e = sp["start"] - base, sp["end"] - base
        if s > pos:
            out.append({"t": text[pos:s]})
        j = i + 1
        while j < len(spans) and spans[j]["end"] <= sp["end"]:
            j += 1
        out.append({"n": sp["n"], "c": tree(text[s:e], sp["start"], spans[i + 1:j])})
        pos, i = e, j
    if pos < len(text):
        out.append({"t": text[pos:]})
    return out


data, need = [], set()
for w in draft:
    t = segs[w["segment_id"]]["text"][w["window_start"]:w["window_end"]]
    spans = sorted(w["spans"], key=lambda x: (x["start"], -x["end"]))
    rows = []
    for n, sp in enumerate(spans, 1):
        sp["n"] = n
        rows.append({
            "n": n, "id": sp["span_id"], "type": sp["type"], "kind": sp.get("kind"),
            "start": sp["start"], "end": sp["end"], "parent": next((r["n"] for r in rows if r["id"] == sp["parent"]), None),
            "links": sp.get("links", []), "ref": sp.get("ref_text"), "cue": sp.get("cue"),
            "hint": sp.get("collection_hint"), "num": sp.get("number_hint"), "note": sp.get("draft_note", ""),
            "method": sp["method"],
        })
        need.update(l["ayah_id"] for l in sp.get("links", []))
    data.append({"id": w["window_id"], "seg": w["segment_id"], "ws": w["window_start"], "we": w["window_end"],
                 "why": w["why"], "covers": w["covers"], "tree": tree(t, w["window_start"], spans), "spans": rows})
ay = {a: {"u": ayat[a]["text"], "s": ayat[a]["text_simple"]} for a in sorted(need, key=lambda x: tuple(map(int, x.split(":"))))}

page = open("scripts/gold/review_template.html", encoding="utf-8").read()
page = page.replace("/*DATA*/", "const WINDOWS = " + json.dumps(data, ensure_ascii=False) + ";\nconst AYAT = " + json.dumps(ay, ensure_ascii=False) + ";")
open("data/interim/gold/phase4-review.html", "w", encoding="utf-8").write(page)
print("windows", len(data), "spans", sum(len(d["spans"]) for d in data), "ayat", len(ay), "bytes", len(page.encode()))
