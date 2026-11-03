"""T4.3: merge auto Quran/footnote draft + Claude's manual spans → resolved, validated draft + review page."""
import json
import re
import sys
import unicodedata

sys.path.insert(0, "scripts/gold")
from draft import norm_map  # noqa: E402

exec(open("scripts/gold/manual.py", encoding="utf-8").read())  # defines M, TRIM_END_BEFORE

CLOSE = set('"”»)]﴾!?؟')
segs = {json.loads(l)["segment_id"]: json.loads(l) for l in open("data/interim/tafsir/ibn-kathir/segments.jsonl", encoding="utf-8")}
ayat = {json.loads(l)["ayah_id"]: json.loads(l) for l in open("data/interim/quran/ayat.jsonl", encoding="utf-8")}


def squeeze(text):
    """norm_map with runs of spaces collapsed; returns (norm, index into text)."""
    n, idx = norm_map(text)
    out, oi = [], []
    for c, i in zip(n, idx):
        if c == " " and (not out or out[-1] == " "):
            continue
        out.append(c)
        oi.append(i)
    return "".join(out), oi


def footnote_ranges(text):
    return [(m.start(), m.end()) for m in re.finditer(r"\[\[.*?\]\]", text, flags=re.S)]


def find(text, anchor, from_orig, fns):
    """First match of anchor at or after original offset from_orig, not inside a footnote. Returns (start, end)."""
    n, idx = squeeze(text)
    a = squeeze(anchor)[0].strip()
    k = 0
    while True:
        k = n.find(a, k)
        if k < 0:
            return None
        s, e = idx[k], idx[k + len(a) - 1] + 1
        # whole-word match only
        okL = k == 0 or n[k - 1] == " "
        okR = k + len(a) == len(n) or n[k + len(a)] == " "
        if s >= from_orig and okL and okR and not any(fs <= s < fe for fs, fe in fns):
            return s, e
        k += 1


def extend(text, e, ext="", mn_only=False):
    while e < len(text):
        c = text[e]
        if unicodedata.category(c) == "Mn" or c in "ـءۥۦ" or (not mn_only and (c in CLOSE or c in ext)):
            e += 1
        elif not mn_only and c == " " and e + 1 < len(text) and (text[e + 1] in '"”»' or (ext and text[e + 1] in ext)):
            e += 1
        else:
            break
    while e > 0 and text[e - 1] == " ":
        e -= 1
    return e


out, errors = [], []
for r in map(json.loads, open("data/interim/gold/draft_qf.jsonl", encoding="utf-8")):
    wid = r["window_id"]
    seg = segs[r["segment_id"]]
    a0, a1 = r["window_start"], r["window_end"]
    if wid in TRIM_END_BEFORE:
        hit = find(seg["text"][a0:a1], TRIM_END_BEFORE[wid], 0, [])
        a1 = a0 + hit[0]
        while seg["text"][a1 - 1] == " ":
            a1 -= 1
    wt = seg["text"][a0:a1]
    fns = footnote_ranges(wt)
    spans = [dict(sp, method="regex") for sp in r["spans"] if sp["end"] <= a1]
    for m in M[wid]:
        st = find(wt, m["s"], 0, fns)
        if not st:
            errors.append(f"{wid}: start anchor not found: {m['s']}")
            continue
        en = find(wt, m["e"], st[0], fns)
        if not en:
            errors.append(f"{wid}: end anchor not found: {m['e']}")
            continue
        sp = {"start": a0 + st[0], "end": a0 + extend(wt, en[1], m.get("ext", ""), mn_only=m["type"] == "QURAN"), "type": m["type"], "method": "human-draft"}
        if m["type"] == "HADITH":
            sp.update(kind=m["kind"], cue=m.get("cue"), collection_hint=m.get("hint"), number_hint=m.get("num"))
        elif m["type"] == "OTHER":
            sp["kind"] = m["kind"]
        elif m["type"] == "QURAN":
            sp["links"] = [{"ayah_id": x, "rel": "EXPLAINS" if x in r["covers"] else "CITES"} for x in m["links"]]
            sp["draft_note"] = m.get("note", "")
        if m.get("note") and m["type"] != "QURAN":
            sp["draft_note"] = m["note"]
        spans.append(sp)
    for sp in spans:
        fix = LINK_FIX.get((wid, sp["start"] - a0))
        if fix:
            sp["links"] = [{"ayah_id": x, "rel": "EXPLAINS" if x in r["covers"] else "CITES"} for x in fix[0]]
            sp["draft_note"] = fix[1]
    spans.sort(key=lambda x: (x["start"], -x["end"]))
    # Nesting: parent = smallest span that contains this one.
    for i, sp in enumerate(spans):
        sp["span_id"] = f"{r['segment_id']}#{sp['start']}-{sp['end']}"
        par = [p for j, p in enumerate(spans) if j != i and p["start"] <= sp["start"] and sp["end"] <= p["end"] and (p["end"] - p["start"]) > (sp["end"] - sp["start"])]
        sp["parent"] = min(par, key=lambda p: p["end"] - p["start"])["span_id"] if par else None
        if par:
            pass
    for i, x in enumerate(spans):
        x["parent"] = next((f"{r['segment_id']}#{p['start']}-{p['end']}" for p in sorted(spans, key=lambda p: p["end"] - p["start"])
                            if p is not x and p["start"] <= x["start"] and x["end"] <= p["end"] and (p["end"] - p["start"]) > (x["end"] - x["start"])), None)
        for y in spans[i + 1:]:
            if y["start"] < x["end"] and y["end"] > x["end"]:
                errors.append(f"{wid}: partial overlap {x['type']} {x['start']}-{x['end']} / {y['type']} {y['start']}-{y['end']}")
        if not (a0 <= x["start"] < x["end"] <= a1):
            errors.append(f"{wid}: span outside window {x['start']}-{x['end']}")
        txt = seg["text"][x["start"]:x["end"]]
        if x["type"] == "FOOTNOTE" and not (txt.startswith("[[") and txt.endswith("]]")):
            errors.append(f"{wid}: bad footnote {txt[:30]}")
    out.append({"window_id": wid, "segment_id": r["segment_id"], "window_start": a0, "window_end": a1, "why": r["why"],
                "covers": r["covers"], "spans": spans})

for e in errors:
    print("ERROR", e)
w01 = next(o for o in out if o["window_id"] == "W01")
print("W01 hadith offsets:", [(s["start"], s["end"]) for s in w01["spans"] if s["type"] == "HADITH"])
from collections import Counter
print(Counter(s["type"] for o in out for s in o["spans"]), "nested:", sum(1 for o in out for s in o["spans"] if s["parent"]))
with open("data/interim/gold/phase4-draft.jsonl", "w", encoding="utf-8") as f:
    for o in out:
        f.write(json.dumps(o, ensure_ascii=False) + "\n")
