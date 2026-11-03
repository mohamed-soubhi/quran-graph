"""List the written references «[سورة: آية]» whose quote is not in the referenced ayat (T4.4 finding).

Reads data/interim/spans/quran.jsonl (a reference link redirected to the text match has method ngram + ref_text)
and writes docs/findings/reference-typos.html and docs/findings/reference-typos.csv.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TA = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")

segs = {json.loads(l)["segment_id"]: json.loads(l) for l in open(ROOT / "data/interim/tafsir/ibn-kathir/segments.jsonl", encoding="utf-8")}
ayat = {json.loads(l)["ayah_id"]: json.loads(l) for l in open(ROOT / "data/interim/quran/ayat.jsonl", encoding="utf-8")}
surahs = {json.loads(l)["surah_id"]: json.loads(l)["name"] for l in open(ROOT / "data/interim/quran/surahs.jsonl", encoding="utf-8")}
sys_path = str(ROOT)
import sys  # noqa: E402

sys.path.insert(0, sys_path)
from src.extract.quran_spans import parse_ref  # noqa: E402


# Claude's reading of the cases that are not a plain wrong digit (2026-11-03), by span_id.
TYPO = "printing error in the reference"
VERDICT = {
    "ibn-kathir:2:126-128:1#10941-11003": "similar ayat: the words are 2:126 (بلدا), the reference 14:35 (البلد) — Ibn Kathir may have meant 14:35",
    "ibn-kathir:4:29-31:1#25645-25662": "reference gives the start of the passage (25:68); the quoted words are in 25:70 — reference not wrong",
    "ibn-kathir:6:71-73:1#18943-18991": "reference range 36:60–64 starts one ayah after the quote (36:59)",
    "ibn-kathir:14:47-48:1#367-403": "OUR ERROR: the reference is right (52:11 «فويل…»); the quote drops the «ف» and the check did not allow it — link must go back to 52:11",
    "ibn-kathir:25:35-40:1#6012-6065": "similar ayat: the words are 23:42 (قرونا), the reference 23:31 (قرنا) — Ibn Kathir may have meant 23:31",
    "ibn-kathir:41:13-18:1#431-501": "similar ayat about 'Ad: the words are 41:14, the reference 46:21 (من بين يديه ومن خلفه)",
}


def kind(ref_ids, linked):
    """Short description of how the written reference differs from the ayat the words are in."""
    rs = {int(a.split(":")[0]) for a in ref_ids}
    ls = {int(a.split(":")[0]) for a in linked}
    if rs != ls:
        return "wrong surah"
    r = [a.split(":")[1] for a in ref_ids]
    l = [a.split(":")[1] for a in linked]
    if len(r) == len(l) and all(len(x) == len(y) and sum(c != d for c, d in zip(x, y)) == 1 for x, y in zip(r, l)):
        return "one digit wrong"
    if len(r) == len(l) and all(len(x) != len(y) for x, y in zip(r, l)):
        return "digit missing or extra"
    if len(r) != len(l):
        return "range differs"
    return "other ayah number"


rows = []
for line in open(ROOT / "data/interim/spans/quran.jsonl", encoding="utf-8"):
    sp = json.loads(line)
    links = sp["links"]
    if not links or links[0]["method"] != "ngram" or not links[0].get("ref_text"):
        continue
    seg = segs[sp["segment_id"]]
    text = seg["text"]
    ref_text = links[0]["ref_text"]
    ref = parse_ref(text[sp["end"]:sp["end"] + 60]) or {}
    ref_ids = ref.get("ayat", [])
    linked = [x["ayah_id"] for x in links]
    rows.append({
        "n": len(rows) + 1,
        "segment_id": sp["segment_id"],
        "span_id": sp["span_id"],
        "tafsir_of": seg["covers"][0] + ("–" + seg["covers"][-1].split(":")[1] if len(seg["covers"]) > 1 else ""),
        "quote": text[sp["start"]:sp["end"]],
        "ref_text": ref_text,
        "ref_ayat": " ".join(ref_ids),
        "ref_ayah_text": " | ".join(ayat[a]["text"] for a in ref_ids if a in ayat),
        "correct_ayat": " ".join(linked),
        "correct_ayah_text": " | ".join(ayat[a]["text"] for a in linked),
        "correct_ref": "[" + surahs[int(linked[0].split(":")[0])] + ": " + "، ".join(a.split(":")[1].translate(TA) for a in linked) + "]",
        "kind": kind(ref_ids, linked),
        "verdict": VERDICT.get(sp["span_id"], TYPO),
        "context": text[max(0, sp["start"] - 80):sp["start"]].replace("\n", " "),
    })

out = ROOT / "docs/findings"
out.mkdir(exist_ok=True)
with open(out / "reference-typos.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

from collections import Counter  # noqa: E402
from html import escape as e  # noqa: E402

CSS = (ROOT / "docs/findings/findings.css").read_text(encoding="utf-8")
kinds = Counter(r["kind"] for r in rows)


def group(v):
    if v == TYPO:
        return "typo"
    if v.startswith("OUR ERROR"):
        return "ours"
    if v.startswith("similar ayat"):
        return "similar"
    return "passage"


groups = Counter(group(r["verdict"]) for r in rows)
LABEL = {"typo": "Printing error", "similar": "Similar ayat", "passage": "Passage reference", "ours": "Our error"}


def ar(text, cls="ar"):
    return f'<span class="{cls}" dir="rtl">{e(text)}</span>'


summary = "\n".join(
    f'<tr class="{group(r["verdict"])}"><td>{r["n"]}</td><td>{r["tafsir_of"]}</td><td>{ar(r["ref_text"])}</td>'
    f'<td>{r["correct_ayat"]}</td><td>{ar(r["correct_ref"])}</td><td>{e(r["kind"])}</td>'
    f'<td><a href="#r{r["n"]}"><span class="tag {group(r["verdict"])}">{LABEL[group(r["verdict"])]}</span></a></td></tr>'
    for r in rows)
details = "\n".join(f"""<section class="case {group(r['verdict'])}" id="r{r['n']}">
<h3>{r['n']}. {ar(r['ref_text'])} → {r['correct_ayat']} <span class="tag {group(r['verdict'])}">{LABEL[group(r['verdict'])]}</span></h3>
<dl>
<dt>Passage</dt><dd>tafsir of {r['tafsir_of']} · <code>{e(r['span_id'])}</code></dd>
<dt>Context</dt><dd>{ar('…' + r['context'])}</dd>
<dt>Quote</dt><dd><div class="quote" dir="rtl">{e(r['quote'])}</div></dd>
<dt>Printed reference</dt><dd>{ar(r['ref_text'])} → {r['ref_ayat']}<div class="ayah bad" dir="rtl">{e(r['ref_ayah_text'])}</div></dd>
<dt>Words are in</dt><dd>{r['correct_ayat']}<div class="ayah good" dir="rtl">{e(r['correct_ayah_text'])}</div></dd>
<dt>Suggested reference</dt><dd>{ar(r['correct_ref'])}</dd>
<dt>Verdict</dt><dd>{e(r['verdict'])}</dd>
</dl></section>""" for r in rows)

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ibn Kathir reference errors</title><style>{CSS}</style></head><body><main>
<p class="crumb"><a href="findings.html">← All findings</a></p>
<h1>Written references that point to the wrong ayah</h1>
<p class="lead">Tafsir Ibn Kathir · found by T4.4 (2026-11-03) · generated by <code>scripts/report_ref_typos.py</code>;
the same rows are in <code>reference-typos.csv</code> (UTF-8, opens in Excel).</p>
<div class="card">
<p><b>Edition:</b> Tafsir Ibn Kathir as distributed by <code>spa5k/tafsir_api</code> (commit eb82bb6), Arabic text with
editor footnotes. Positions are character offsets in that text (<code>span_id</code> = passage#start-end).</p>
<p><b>Method:</b> for each Quran quote ﴿…﴾ followed by a written reference {ar('«[سورة: آية]»')}, the quoted words were
searched (diacritics and spelling differences removed) in the referenced ayat. In the cases below they are <b>not</b>
there; they were found in another ayah. The graph links the quote to the ayah that holds the words, keeps the printed
reference on the link (<code>ref_text</code>) and sets <code>confidence: 0.9</code>. The tafsir text is never changed.</p>
</div>
<div class="stats">
<div class="stat"><b>5,164</b><span>references checked</span></div>
<div class="stat"><b>{len(rows)}</b><span>words not in the referenced ayah</span></div>
<div class="stat typo"><b>{groups['typo']}</b><span>printing errors</span></div>
<div class="stat similar"><b>{groups['similar']}</b><span>similar ayat</span></div>
<div class="stat passage"><b>{groups['passage']}</b><span>passage references</span></div>
<div class="stat ours"><b>{groups['ours']}</b><span>our error</span></div>
</div>
<p class="muted">Kinds of difference: {', '.join(f'{e(k)} {v}' for k, v in kinds.most_common())}.</p>
<h2>Summary</h2>
<div class="scroll"><table><thead><tr><th>#</th><th>Tafsir of</th><th>Printed reference</th><th>Words are in</th>
<th>Suggested reference</th><th>Kind</th><th>Verdict</th></tr></thead><tbody>
{summary}
</tbody></table></div>
<h2>Details</h2>
{details}
</main></body></html>
"""
(out / "reference-typos.html").write_text(page, encoding="utf-8")
print(len(rows), dict(kinds), dict(groups))
