"""Build the T0.5 fixture (Ibn Kathir 2:255, paragraph 0) and its hand-checked expected spans.

Usage: python scripts/build_fixture.py <path to ar-tafsir-ibn-kathir/2/255.json>
Writes tafsir_sample.txt and tafsir_sample.expected.json to the current directory.
"""
import json, re, sys, unicodedata
src = json.load(open(sys.argv[1], encoding="utf-8"))["text"]
para = [p for p in src.split("\n\n") if p.strip()][0]
assert src.find(para) >= 0
seg_off = src.find(para)

def diac_strip(s):
    return "".join(c for c in s if not unicodedata.category(c) == "Mn")

MARKS = "[ً-ٰٟ]*"
def find(anchor, frm=0):
    """Locate anchor ignoring diacritics; return (start, end) in the original text."""
    pat = MARKS.join(re.escape(c) for c in diac_strip(anchor)) + MARKS
    m = re.compile(pat).search(para, frm)
    if not m:
        raise ValueError(anchor)
    return m.start(), m.end()

def span(start_anchor, end_anchor, frm=0):
    s = find(start_anchor, frm)[0]
    return s, find(end_anchor, s)[1]

h1 = span("قَالَ الْإِمَامُ أَحْمَدُ", "سَاقِ الْعَرْشِ\"")
h1_isnad = span("حَدَّثَنَا عَبْدُ الرَّزَّاقِ", "-هُوَ ابْنُ كَعْبٍ-")
h1_matn = (find("أَنَّ النَّبِيَّ ﷺ سَأَلَهُ")[0], h1[1])
h2 = span("وَقَدْ رَوَاهُ مُسْلِمٌ", "الْجُرَيْرِيِّ-بِهِ")
fn = span("[[", "]]")
q_end = len(para)

spans = [
    {"start": 0, "end": h1[0], "type": "COMMENTARY"},
    {"start": h1[0], "end": h1[1], "type": "HADITH", "collection_hint": "ahmad", "number_hint": None,
     "isnad": list(h1_isnad), "matn": list(h1_matn), "note": "Musnad Ahmad 5/141 (vol/page, not a hadith number)"},
    {"start": h1[1], "end": h2[0], "type": "COMMENTARY"},
    {"start": h2[0], "end": h2[1], "type": "HADITH", "collection_hint": "muslim", "number_hint": "810",
     "isnad": [find("عَنْ أَبِي بَكْرِ", h2[0])[0], h2[1]], "matn": None,
     "note": "Takhrij reference: Muslim's chain, matn given by reference ('bihi'). Number 810 comes from the footnote."},
    {"start": h2[1], "end": fn[0], "type": "COMMENTARY"},
    {"start": fn[0], "end": fn[1], "type": "FOOTNOTE", "note": "Editor's note, not Ibn Kathir: المسند (5/141) وصحيح مسلم برقم (810)"},
    {"start": fn[1], "end": q_end, "type": "COMMENTARY"},
]
# coverage + no overlap (gate 4c shape)
pos = 0
for s in spans:
    assert s["start"] == pos and s["end"] > s["start"], s
    pos = s["end"]
assert pos == len(para)
for s in spans:
    s["text"] = para[s["start"]:s["end"]]

hadith_spans = [{"start": s["start"], "end": s["end"], "cue": c, "collection_hint": s["collection_hint"], "number_hint": s["number_hint"]}
                for s, c in zip([x for x in spans if x["type"] == "HADITH"], ["قَالَ الْإِمَامُ أَحْمَدُ: حَدَّثَنَا", "وَقَدْ رَوَاهُ مُسْلِمٌ"])]
out = {
    "source": "spa5k/tafsir_api ar-tafsir-ibn-kathir 2/255.json, paragraph 0 (split on blank line)",
    "source_url": "https://raw.githubusercontent.com/spa5k/tafsir_api/main/tafsir/ar-tafsir-ibn-kathir/2/255.json",
    "offset_in_source_text": seg_off,
    "length": len(para),
    "annotated_by": "Claude (draft) — needs human review before joining data/gold/",
    "hadith_spans": hadith_spans,
    "spans": spans,
}
open("tafsir_sample.txt", "w", encoding="utf-8", newline="").write(para)
json.dump(out, open("tafsir_sample.expected.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
for s in spans:
    print(s["type"], s["start"], s["end"], "|", s["text"][:50].replace("\n", " "), "…", s["text"][-25:])
