"""T4.3: pick ~50 gold windows (fixed seed). Writes data/interim/gold/windows.jsonl."""
import json
import random
import re
import unicodedata
from pathlib import Path

SEED = 20261103
SEGS = [json.loads(l) for l in open("data/interim/tafsir/ibn-kathir/segments.jsonl", encoding="utf-8")]
SURAH = {json.loads(l)["surah_id"]: json.loads(l) for l in open("data/interim/quran/surahs.jsonl", encoding="utf-8")}


def bare(s):
    s = "".join(c for c in s if unicodedata.category(c) != "Mn" and c not in "ـءۥۦ")
    return s.translate(str.maketrans("أإآٱىة", "ااااايه"[:0] + "اااايه"))


def paragraphs(text):
    """(start, end) of each paragraph, end exclusive, separators excluded."""
    out, pos = [], 0
    for p in text.split("\n\n"):
        out.append((pos, pos + len(p)))
        pos += len(p) + 2
    return out


def windows(seg, lo=300, hi=1800, single_max=2500):
    """Candidate windows: runs of whole paragraphs."""
    ps = [p for p in paragraphs(seg["text"]) if p[1] > p[0]]
    out = []
    for i, (a, b) in enumerate(ps):
        if b - a > hi:
            if b - a <= single_max:
                out.append((a, b))
            continue
        end = b
        j = i
        while end - a < lo and j + 1 < len(ps) and ps[j + 1][1] - a <= hi:
            j += 1
            end = ps[j][1]
        if lo <= end - a <= hi:
            out.append((a, end))
    return out


rng = random.Random(SEED)
chosen, used = [], set()


def inside_marks(text, pos):
    """True if pos falls inside a [[…]] note or a ﴿…﴾ quote."""
    return text.rfind("[[", 0, pos) > text.rfind("]]", 0, pos) or text.rfind("﴿", 0, pos) > text.rfind("﴾", 0, pos)


def take(seg, w, why):
    if inside_marks(seg["text"], w[0]) or inside_marks(seg["text"], w[1]):
        return False
    key = (seg["segment_id"], w[0])
    if key in used or any(c["segment_id"] == seg["segment_id"] for c in chosen):
        return False
    used.add(key)
    chosen.append({"segment_id": seg["segment_id"], "window_start": w[0], "window_end": w[1], "why": why})
    return True


# 1. T0.5 fixture: 2:255 paragraph 0.
fx = next(s for s in SEGS if s["segment_id"].startswith("ibn-kathir:2:255-"))
take(fx, paragraphs(fx["text"])[0], "fixture T0.5")

# 2. Hard cases by pattern (searched on bare text of each candidate window).
HARD = [
    ("quran inside hadith", lambda t, b: re.search(r"حدثنا[^﴿]{0,400}﴿", b) is not None, 4),
    ("footnote inside quote", lambda t, b: re.search(r"﴿[^﴾]*\[\[", t) is not None, 3),
    ("written reference", lambda t, b: re.search(r"﴾ ?\[[^\[\]]{2,30}: ?[٠-٩]", t) is not None, 2),
    ("ahmad isnad", lambda t, b: "قال الامام احمد" in b, 2),
    ("ibn abi hatim / ibn jarir isnad", lambda t, b: "قال ابن ابي حاتم" in b or "قال ابن جرير" in b, 2),
    ("poetry", lambda t, b: re.search(r"قال الشاعر[^.]{0,40}\n\n[^\n]*\.\.\.", b) is not None, 2),
]
order = SEGS[:]
rng.shuffle(order)
for why, pred, n in HARD:
    got = 0
    for seg in order:
        if got >= n:
            break
        ws = windows(seg)
        rng.shuffle(ws)
        for w in ws:
            t = seg["text"][w[0]:w[1]]
            if pred(t, bare(t)) and take(seg, w, why):
                got += 1
                break

# 3. Unbracketed quotes: a >= 6-word run of some ayah's simple text outside ﴿…﴾, in a cited-surah-free window.
ayat = [json.loads(l) for l in open("data/interim/quran/ayat.jsonl", encoding="utf-8")]
grams = {}
for a in ayat:
    ws_ = bare(a["text_simple"]).split()
    for k in range(len(ws_) - 5):
        grams.setdefault(" ".join(ws_[k:k + 6]), a["ayah_id"])
got = 0
for seg in order:
    if got >= 3:
        break
    ws = windows(seg)
    rng.shuffle(ws)
    for w in ws:
        t = re.sub(r"﴿[^﴾]*﴾", " ", seg["text"][w[0]:w[1]])
        b = bare(re.sub(r"\[\[.*?\]\]", " ", t, flags=re.S))
        toks = re.sub(r"[^\w\s]", " ", b).split()
        if any(" ".join(toks[k:k + 6]) in grams for k in range(len(toks) - 5)) and take(seg, w, "unbracketed quote"):
            got += 1
            break

# 4. Stratified random: Meccan/Medinan x short/long segment (median char_count).
med = sorted(s["char_count"] for s in SEGS)[len(SEGS) // 2]
strata = {}
for s in SEGS:
    k = (SURAH[s["surah_id"]]["type"], "long" if s["char_count"] >= med else "short")
    strata.setdefault(k, []).append(s)
need = 50 - len(chosen)
per = {k: need // 4 + (1 if i < need % 4 else 0) for i, k in enumerate(sorted(strata))}
for k in sorted(strata):
    pool = strata[k][:]
    rng.shuffle(pool)
    got = 0
    for seg in pool:
        if got >= per[k]:
            break
        ws = windows(seg)
        if ws and take(seg, rng.choice(ws), f"random {k[0]}/{k[1]}"):
            got += 1

segtext = {s["segment_id"]: s["text"] for s in SEGS}
out = Path("data/interim/gold/windows.jsonl")
with out.open("w", encoding="utf-8") as f:
    for i, c in enumerate(chosen, 1):
        c = {"window_id": f"W{i:02d}", **c, "text": segtext[c["segment_id"]][c["window_start"]:c["window_end"]]}
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
print(len(chosen), "windows;", sum(c["window_end"] - c["window_start"] for c in chosen), "chars")
for c in chosen:
    print(c["segment_id"], c["window_start"], c["window_end"], c["window_end"] - c["window_start"], c["why"])
