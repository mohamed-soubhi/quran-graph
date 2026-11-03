"""T4.3: auto-draft QURAN + FOOTNOTE spans and ayah links for the gold windows (Claude reviews, then humans)."""
import json
import re
import unicodedata

SKIP = "ـءۥۦ"


def norm_map(text):
    """Normalizer v2 copy (T4.1 rules) + punctuation → space; returns (norm, index)."""
    out, idx = [], []
    for i, c in enumerate(text):
        if unicodedata.category(c) == "Mn" or c in SKIP:
            continue
        c = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه"}.get(c, c)
        if not (c.isalpha() or c.isdigit()):
            c = " "
        out.append(c)
        idx.append(i)
    return "".join(out), idx


def toks(text):
    """Word tokens of the normalized text with original (start, end)."""
    n, idx = norm_map(text)
    return [(m.group(), idx[m.start()], idx[m.end() - 1] + 1) for m in re.finditer(r"\S+", n)]


SURAHS = [json.loads(l) for l in open("data/interim/quran/surahs.jsonl", encoding="utf-8")]
AYAT = [json.loads(l) for l in open("data/interim/quran/ayat.jsonl", encoding="utf-8")]
AY_TOK = {a["ayah_id"]: [t[0] for t in toks(a["text_simple"])] for a in AYAT}
ORDER = [a["ayah_id"] for a in AYAT]
POS = {a: i for i, a in enumerate(ORDER)}
# Full Quran token stream with ayah id per token, for multi-ayah quotes.
STREAM, STREAM_AY = [], []
for a in ORDER:
    STREAM += AY_TOK[a]
    STREAM_AY += [a] * len(AY_TOK[a])
FIRST = {}
for k in range(len(STREAM) - 1):
    FIRST.setdefault((STREAM[k], STREAM[k + 1]), []).append(k)
SNAME = {}
for s in SURAHS:
    b = norm_map(s["name"])[0].replace(" ", "")
    SNAME[b] = s["surah_id"]
    SNAME[b[2:] if b.startswith("ال") else b] = s["surah_id"]

AR_DIG = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def parse_ref(after):
    m = re.match(r"\s*\[([^\[\]:]{2,40}):\s*([٠-٩0-9]+)(?:\s*[-–،,]\s*([٠-٩0-9]+))?\]", after)
    if not m:
        return None
    name = norm_map(m.group(1))[0].replace(" ", "")
    if name.startswith("سوره"):
        name = name[4:]
    sid = SNAME.get(name) or SNAME.get(name[2:] if name.startswith("ال") else name)
    a = int(m.group(2).translate(AR_DIG))
    b = int((m.group(3) or m.group(2)).translate(AR_DIG))
    return {"ref_text": m.group(0).strip(), "ref_len": m.end(), "ayat": [f"{sid}:{x}" for x in range(a, b + 1)] if sid else None}


def match_quote(qt, covers):
    """Match a quote's tokens against the Quran stream; returns list of ayah ids or candidates."""
    q = [t[0] for t in toks(re.sub(r"\[\[.*?\]\]", " ", qt, flags=re.S))]
    # Drop ellipsis / "إلى قوله" pieces: match the longest piece.
    pieces, cur = [], []
    for w in q:
        if w in ("الي", "قوله") and False:
            continue
        cur.append(w)
    pieces = [cur]
    q = max(pieces, key=len)
    if len(q) == 1:
        inc = [a for a in covers if q[0] in AY_TOK[a]]
        if inc:
            return {"status": "one word, in covered ayah" + ("" if len(inc) == 1 else f", {len(inc)} candidates"), "candidates": [[x] for x in inc]}
        anyw = [a for a in ORDER if q[0] in AY_TOK[a]]
        return {"status": f"one word, not in covered ayat, {len(anyw)} candidates", "candidates": [[x] for x in anyw[:5]]}
    hits = []
    for k in FIRST.get((q[0], q[1]), []):
        n = 0
        while n < len(q) and k + n < len(STREAM) and STREAM[k + n] == q[n]:
            n += 1
        hits.append((n, k))
    if not hits:
        return {"status": "no-match", "candidates": []}
    best = max(h[0] for h in hits)
    cands = []
    for n, k in hits:
        if n == best:
            ay = list(dict.fromkeys(STREAM_AY[k:k + n]))
            cands.append(ay)
    full = best == len(q)
    pref = [c for c in cands if set(c) & set(covers)]
    pick = pref or cands
    status = ("exact" if full else f"prefix {best}/{len(q)}") + ("" if len(pick) == 1 else f", {len(pick)} candidates")
    return {"status": status, "candidates": pick[:5]}


if __name__ == "__main__":
    segs = {json.loads(l)["segment_id"]: json.loads(l) for l in open("data/interim/tafsir/ibn-kathir/segments.jsonl", encoding="utf-8")}
    out = []
    for w in map(json.loads, open("data/interim/gold/windows.jsonl", encoding="utf-8")):
        seg = segs[w["segment_id"]]
        t, a0, a1 = seg["text"], w["window_start"], w["window_end"]
        spans = []
        for m in re.finditer(r"\[\[.*?\]\]", t[a0:a1], flags=re.S):
            spans.append({"start": a0 + m.start(), "end": a0 + m.end(), "type": "FOOTNOTE"})
        for m in re.finditer(r"﴿[^﴾]*﴾", t[a0:a1]):
            s, e = a0 + m.start(), a0 + m.end()
            ref = parse_ref(t[e:e + 60])
            mt = match_quote(m.group(), seg["covers"])
            links, note = [], mt["status"]
            if ref and ref["ayat"]:
                links = ref["ayat"]
                note = "ref" + ("" if mt["candidates"] and set(links) & set(mt["candidates"][0]) else f" (text match: {mt['status']} {mt['candidates'][:1]})")
            elif mt["candidates"]:
                links = mt["candidates"][0]
            sp = {"start": s, "end": e, "type": "QURAN", "links": [
                {"ayah_id": x, "rel": "EXPLAINS" if x in seg["covers"] else "CITES"} for x in links], "draft_note": note}
            if ref:
                sp["ref_text"] = ref["ref_text"]
            spans.append(sp)
        spans.sort(key=lambda x: (x["start"], -x["end"]))
        out.append({**{k: w[k] for k in ("window_id", "segment_id", "window_start", "window_end", "why")}, "covers": seg["covers"], "spans": spans})

    with open("data/interim/gold/draft_qf.jsonl", "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    c = Counter(sp["type"] for r in out for sp in r["spans"])
    notes = Counter(sp["draft_note"].split(" (")[0].split(",")[0] for r in out for sp in r["spans"] if sp["type"] == "QURAN")
    print(c, notes)
    for r in out:
        for sp in r["spans"]:
            if sp["type"] == "QURAN" and not sp["draft_note"].startswith(("exact", "ref")) or (sp.get("draft_note", "").find("candidates") > 0):
                print(r["window_id"], sp["start"], sp["draft_note"], [l["ayah_id"] for l in sp["links"]], segs[r["segment_id"]]["text"][sp["start"]:sp["end"]][:80])
