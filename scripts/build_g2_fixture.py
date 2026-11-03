"""Build tests/fixtures/g2/cases.json: the 3 real G2 schema cases with exact offsets from data/raw (G2).

Offsets are found from short phrases (T2.3 locator or exact search) and stored with the first characters of each
span, so the test can re-check them against the raw text.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extract.locate import locate  # noqa: E402
from src.extract.models import HadithSpanAnchor  # noqa: E402

TAFSIR = ROOT / "data" / "raw" / "tafsir" / "ibn-kathir"
OUT = ROOT / "tests" / "fixtures" / "g2" / "cases.json"
OPEN, CLOSE = "﴿", "﴾"  # ornate brackets as used in this edition


def text(surah: int, ayah: int) -> str:
    return json.loads((TAFSIR / str(surah) / f"{ayah}.json").read_text(encoding="utf-8"))["text"]


def span_by_anchors(t: str, start: str, end: str, window: int = 0) -> tuple[int, int]:
    a = HadithSpanAnchor(start_anchor=start, end_anchor=end, cue=None, collection_hint=None, number_hint=None)
    r = locate(t, a, window)
    assert r, (start, end)
    return r


def quran_span(t: str, start: str, end: str, window: int = 0) -> tuple[int, int]:
    """Quran quote span including both ornate brackets."""
    s, e = span_by_anchors(t, start, end, window)
    assert t[s - 1] == OPEN and t[e - 1] == CLOSE, (start, t[s - 1 : e])
    return s - 1, e


def find(t: str, phrase: str, after: int = 0) -> tuple[int, int]:
    """Diacritic-insensitive search outside footnotes (T2.3 locator with the same start and end phrase)."""
    return span_by_anchors(t, phrase, phrase, after)


def footnote_containing(t: str, needle: str, after: int = 0) -> tuple[int, int]:
    for m in re.finditer(r"\[\[.*?\]\]", t, re.S):
        if m.start() >= after and needle in m.group(0):
            return m.span()
    raise AssertionError(needle)


spans, links = [], []


def add(seg: str, t: str, kind: str, se: tuple[int, int], parent: str | None = None, **extra) -> str:
    sid = f"{seg}#{se[0]}-{se[1]}"
    spans.append({"span_id": sid, "segment_id": seg, "start": se[0], "end": se[1], "type": kind,
                  "parent": parent, "begins_with": t[se[0] : se[0] + 12], **extra})
    return sid


def link(span_id: str, rel: str, target: str, method: str, **props) -> None:
    links.append({"span_id": span_id, "rel": rel, "target": target, "method": method, **props})


# ---- Case 1: a verse explaining a verse (2:255) -------------------------------------------------
seg1 = "ibn-kathir:2:255-255:1"
t1 = text(2, 255)
q = add(seg1, t1, "QURAN", quran_span(t1, "الله لا إله إلا هو", "إلا هو", 22100))
link(q, "EXPLAINS", "2:255", "regex", note="«فقوله:» introduces the ayah being explained")
q = add(seg1, t1, "QURAN", quran_span(t1, "ومن آياته أن تقوم السماء", "والأرض بأمره", 22400))
link(q, "CITES", "30:25", "regex", ref_text="[الرُّومِ:٢٥]")
q = add(seg1, t1, "QURAN", quran_span(t1, "إن كل من في السماوات والأرض إلا آتي", "القيامة فردا", 27000))
for a in (93, 94, 95):
    link(q, "CITES", f"19:{a}", "regex", ref_text="[مَرْيَمَ: ٩٣-٩٥]")
# Quran quotes nested in a hadith (Anas, Musnad Ahmad 3/221 - not in our sources, so no CITES to a Hadith)
h_start = find(t1, "قال الإمام أحمد: حدثنا عبد الله بن الحارث")[0]
h_end = t1[: footnote_containing(t1, "(٣/٢٢١)", h_start)[0]].rstrip()  # hadith ends where the footnote begins
h_end = len(h_end)
anas = add(seg1, t1, "HADITH", (h_start, h_end), collection_hint="ahmad", number_hint=None,
           note="Musnad Ahmad 3/221 is volume/page; Musnad Ahmad not in our sources -> no CITES")
for start, end, target in [("قل هو الله أحد", "الله أحد", "112:1"), ("قل يا أيها الكافرون", "الكافرون", "109:1"),
                           ("إذا زلزلت", "إذا زلزلت", "99:1")]:
    q = add(seg1, t1, "QURAN", quran_span(t1, start, end, h_start), parent=anas)
    link(q, "CITES", target, "regex")
# Two quotes contain an editor footnote before the closing bracket (an anchor cannot reach past it):
# take each quote from its opening to its closing bracket and nest the footnote inside it.
for opening, target, rel, fn_text in [("إذا جاء نصر الله", "110:1", "CITES", "زيادة من و"),
                                      ("الله لا إله إلا هو", "2:255", "EXPLAINS", "هو الحي القيوم")]:
    k = find(t1, opening, find(t1, "إذا زلزلت", h_start)[1])[0] - 1
    assert t1[k] == OPEN, opening
    q = add(seg1, t1, "QURAN", (k, t1.index(CLOSE, k) + 1), parent=anas)
    link(q, rel, target, "regex")
    add(seg1, t1, "FOOTNOTE", footnote_containing(t1, fn_text, k), parent=q)

# ---- Case 3: an isnad with several narrators (Ahmad, 2:255, same span as the T0.5 fixture) -------
ubayy = add(seg1, t1, "HADITH", span_by_anchors(t1, "قال الإمام أحمد: حدثنا", "عند ساق العرش"),
            collection_hint="ahmad", number_hint=None, note="Musnad Ahmad 5/141; not in our sources -> no CITES")
chain = ["عبد الرزاق", "سفيان", "سعيد الجريري", "أبي السليل", "عبد الله بن رباح", "أبي -هو ابن كعب"]
names = ["عبد الرزاق", "سفيان", "سعيد الجريري", "أبو السليل", "عبد الله بن رباح", "أبي بن كعب"]
narrators, pos = [], 141
for i, (written, name) in enumerate(zip(chain, names), 1):
    s, e = find(t1, written, pos)
    pos = e
    narrators.append({"narrator_id": f"fixture:{i}", "name": name, "position": i, "mention": [s, e]})

# ---- Case 2: one hadith cited in several passages (Muslim 2865 = muslim:7207) ---------------------
case2 = []
for (s, f, l), (start, end), tail in [
    ((30, 30, 32), ("انفرد بإخراجه مسلم", "عن قتادة، به"), None),
    ((4, 116, 122), ("وفي صحيح مسلم، عن عياض بن حمار", "ما أحللت"), "لهم"),
    ((17, 15, 15), ("وفي صحيح مسلم، عن عياض بن حمار", "خلقت عبادي حنفاء"), None),
]:
    seg = f"ibn-kathir:{s}:{f}-{l}:1"
    t = text(s, f)
    hs, he = span_by_anchors(t, *[x for x in (start, end)], 6000 if s != 17 else 15000)
    if tail:  # the hadith continues after a nested editor note; the anchor cannot reach past it
        he = find(t, tail, he)[1]
    h = add(seg, t, "HADITH", (hs, he), collection_hint="muslim", number_hint=None)
    inner = [m.span() for m in re.finditer(r"\[\[.*?\]\]", t[hs:he], re.S)]
    for a, b in inner:
        add(seg, t, "FOOTNOTE", (hs + a, hs + b), parent=h)
    fn = footnote_containing(t, "٢٨٦٥", he)
    fid = add(seg, t, "FOOTNOTE", fn)
    link(h, "CITES", "muslim:7207", "regex", evidence=fid, ref_text=t[fn[0] : fn[1]])
    case2.append({"segment_id": seg, "surah": s, "first_ayah": f, "last_ayah": l})

cases = {
    "built_by": "scripts/build_g2_fixture.py",
    "segments": [{"segment_id": seg1, "surah": 2, "first_ayah": 255, "last_ayah": 255}] + case2,
    "spans": spans,
    "links": links,
    "isnad": {"span_id": ubayy, "narrators": narrators},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {OUT.relative_to(ROOT)}: {len(spans)} spans, {len(links)} links, {len(narrators)} narrators")
