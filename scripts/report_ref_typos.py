"""List the written references «[سورة: آية]» whose quote is not in the referenced ayat (T4.4 finding).

Reads data/interim/spans/quran.jsonl (a reference link redirected to the text match has method ngram + ref_text)
and writes docs/findings/reference-typos.html, reference-typos-ar.html and reference-typos.csv.
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

VERDICT_AR = {
    "ibn-kathir:2:126-128:1#10941-11003": "آيتان متشابهتان: الكلمات في 2:126 (بلدا) والإحالة إلى 14:35 (البلد) — ربما أراد ابن كثير 14:35",
    "ibn-kathir:4:29-31:1#25645-25662": "الإحالة إلى أول المقطع (25:68)، والكلمات المقتبسة في 25:70 — الإحالة ليست خطأ",
    "ibn-kathir:6:71-73:1#18943-18991": "نطاق الإحالة 36:60–64 يبدأ بعد الآية المقتبسة بآية (36:59)",
    "ibn-kathir:14:47-48:1#367-403": "خطؤنا: الإحالة صحيحة (52:11 «فويل…»)؛ الاقتباس سقطت منه «ف» ولم يسمح الفحص بذلك — يجب أن يعود الربط إلى 52:11",
    "ibn-kathir:25:35-40:1#6012-6065": "آيتان متشابهتان: الكلمات في 23:42 (قرونا) والإحالة إلى 23:31 (قرنا) — ربما أراد ابن كثير 23:31",
    "ibn-kathir:41:13-18:1#431-501": "آيتان متشابهتان عن عاد: الكلمات في 41:14، والإحالة إلى 46:21 (من بين يديه ومن خلفه)",
}
TYPO_AR = "خطأ طباعي في الإحالة"
KIND_AR = {"one digit wrong": "رقم واحد خطأ", "digit missing or extra": "رقم ناقص أو زائد", "wrong surah": "سورة خطأ",
           "other ayah number": "رقم آية آخر", "range differs": "نطاق مختلف"}
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


def ar(text, cls="ar"):
    return f'<span class="{cls}" dir="rtl">{e(text)}</span>'


def ids(text):
    return f'<span class="ltr">{e(text)}</span>'


T = {
    "en": dict(
        dir="ltr", title="Ibn Kathir reference errors", back="← All findings", index="findings.html",
        other='<a href="reference-typos-ar.html">العربية</a>',
        h1="Written references that point to the wrong ayah",
        lead="Tafsir Ibn Kathir · found by T4.4 (2026-11-03) · generated by <code>scripts/report_ref_typos.py</code>; "
             "the same rows are in <code>reference-typos.csv</code> (UTF-8, opens in Excel).",
        edition="<b>Edition:</b> Tafsir Ibn Kathir as distributed by <code>spa5k/tafsir_api</code> (commit eb82bb6), Arabic "
                "text with editor footnotes. Positions are character offsets in that text (<code>span_id</code> = passage#start-end).",
        method="<b>Method:</b> for each Quran quote ﴿…﴾ followed by a written reference " + ar("«[سورة: آية]»") + ", the quoted "
               "words were searched (diacritics and spelling differences removed) in the referenced ayat. In the cases below "
               "they are <b>not</b> there; they were found in another ayah. The graph links the quote to the ayah that holds "
               "the words, keeps the printed reference on the link (<code>ref_text</code>) and sets <code>confidence: 0.9</code>. "
               "The tafsir text is never changed.<br><b>Second source (2026-11-03):</b> quran.com's Arabic Ibn Kathir prints the same reference in 38 of these 39; "
               "it differs only in the tafsir of 73:1–9, where it has the correct 17:79 (<code>reference-crosscheck.csv</code>). No printed volume was compared.",
        stats=["references checked", "words not in the referenced ayah", "printing errors", "similar ayat",
               "passage references", "our error"],
        kinds="Kinds of difference", sep=", ", summary="Summary", details="Details",
        cols=["#", "Tafsir of", "Printed reference", "Words are in", "Suggested reference", "Kind", "Verdict"],
        label={"typo": "Printing error", "similar": "Similar ayat", "passage": "Passage reference", "ours": "Our error"},
        dt=["Passage", "Context", "Quote", "Printed reference", "Words are in", "Suggested reference", "Verdict"],
        tafsir_of="tafsir of", arrow="→", kind=lambda k: k, verdict=lambda r: r["verdict"],
    ),
    "ar": dict(
        dir="rtl", title="أخطاء الإحالات في ابن كثير", back="→ كل النتائج", index="findings-ar.html",
        other='<a href="reference-typos.html">English</a>',
        h1="إحالات مكتوبة تشير إلى غير الآية المقتبسة",
        lead="تفسير ابن كثير · كُشفت في T4.4 (2026-11-03) · يولّدها <code>scripts/report_ref_typos.py</code>؛ "
             "والصفوف نفسها في <code>reference-typos.csv</code> (يُفتح في Excel).",
        edition="<b>الطبعة:</b> تفسير ابن كثير كما في <code>spa5k/tafsir_api</code> (الإيداع eb82bb6)، نص عربي مع حواشي المحقق. "
                "المواضع أرقام حروف في هذا النص (<code>span_id</code> = المقطع#البداية-النهاية).",
        method="<b>الطريقة:</b> لكل اقتباس قرآني ﴿…﴾ تليه إحالة مكتوبة «[سورة: آية]»، بحثنا عن الكلمات المقتبسة — بعد حذف "
               "التشكيل وفروق الرسم — في الآيات المُحال إليها. في الحالات أدناه <b>ليست</b> فيها، ووُجدت في آية أخرى. "
               "يربط الرسمُ البياني الاقتباسَ بالآية التي فيها الكلمات فعلًا، ويحتفظ بنص الإحالة المطبوع على الرابط "
               "(<code>ref_text</code>)، ويجعل الثقة <code>0.9</code>. لا يُغيَّر نص التفسير أبدًا.<br><b>مصدر ثانٍ (2026-11-03):</b> نص ابن كثير العربي في quran.com فيه الإحالة نفسها في 38 من هذه الـ39؛ "
               "ويختلف في تفسير ٧٣:١–٩ فقط، إذ فيه الصحيح ١٧:٧٩ (<code>reference-crosscheck.csv</code>). لم نقارن بنسخة ورقية.",
        stats=["إحالة فُحصت", "الكلمات ليست في الآية المُحال إليها", "خطأ طباعي", "آيات متشابهة", "إحالة إلى أول المقطع",
               "خطؤنا"],
        kinds="أنواع الاختلاف", sep="، ", summary="الجدول المختصر", details="التفاصيل",
        cols=["#", "تفسير الآية", "الإحالة المطبوعة", "الكلمات في", "الإحالة المقترحة", "النوع", "الحكم"],
        label={"typo": "خطأ طباعي", "similar": "آيات متشابهة", "passage": "إحالة إلى المقطع", "ours": "خطؤنا"},
        dt=["المقطع", "السياق", "الاقتباس", "الإحالة المطبوعة", "الكلمات في", "الإحالة المقترحة", "الحكم"],
        tafsir_of="تفسير", arrow="←", kind=lambda k: KIND_AR[k], verdict=lambda r: VERDICT_AR.get(r["span_id"], TYPO_AR),
    ),
}


def render(lang):
    t = T[lang]
    lab = t["label"]
    summary = "\n".join(
        f'<tr class="{group(r["verdict"])}"><td>{r["n"]}</td><td>{ids(r["tafsir_of"])}</td><td>{ar(r["ref_text"])}</td>'
        f'<td>{ids(r["correct_ayat"])}</td><td>{ar(r["correct_ref"])}</td><td>{e(t["kind"](r["kind"]))}</td>'
        f'<td><a href="#r{r["n"]}"><span class="tag {group(r["verdict"])}">{lab[group(r["verdict"])]}</span></a></td></tr>'
        for r in rows)
    d = t["dt"]
    details = "\n".join(f"""<section class="case {group(r['verdict'])}" id="r{r['n']}">
<h3>{r['n']}. {ar(r['ref_text'])} {t['arrow']} {ids(r['correct_ayat'])} <span class="tag {group(r['verdict'])}">{lab[group(r['verdict'])]}</span></h3>
<dl>
<dt>{d[0]}</dt><dd>{t['tafsir_of']} {ids(r['tafsir_of'])} · <code>{e(r['span_id'])}</code></dd>
<dt>{d[1]}</dt><dd>{ar('…' + r['context'])}</dd>
<dt>{d[2]}</dt><dd><div class="quote" dir="rtl">{e(r['quote'])}</div></dd>
<dt>{d[3]}</dt><dd>{ar(r['ref_text'])} = {ids(r['ref_ayat'])}<div class="ayah bad" dir="rtl">{e(r['ref_ayah_text'])}</div></dd>
<dt>{d[4]}</dt><dd>{ids(r['correct_ayat'])}<div class="ayah good" dir="rtl">{e(r['correct_ayah_text'])}</div></dd>
<dt>{d[5]}</dt><dd>{ar(r['correct_ref'])}</dd>
<dt>{d[6]}</dt><dd>{e(t['verdict'](r))}</dd>
</dl></section>""" for r in rows)
    stats = "\n".join(f'<div class="stat {c}"><b>{n}</b><span>{label}</span></div>' for c, n, label in zip(
        ["", "", "typo", "similar", "passage", "ours"],
        ["5,164", len(rows), groups["typo"], groups["similar"], groups["passage"], groups["ours"]], t["stats"]))
    kind_list = t["sep"].join(f"{e(t['kind'](k))} {v}" for k, v in kinds.most_common())
    head = "".join(f"<th>{c}</th>" for c in t["cols"])
    return f"""<!doctype html>
<html lang="{lang}" dir="{t['dir']}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t['title']}</title><style>{CSS}</style></head><body><main>
<p class="crumb"><span class="lang">{t['other']}</span><a href="{t['index']}">{t['back']}</a></p>
<h1>{t['h1']}</h1>
<p class="lead">{t['lead']}</p>
<div class="card"><p>{t['edition']}</p><p>{t['method']}</p></div>
<div class="stats">
{stats}
</div>
<p class="muted">{t['kinds']}: {kind_list}.</p>
<h2>{t['summary']}</h2>
<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>
{summary}
</tbody></table></div>
<h2>{t['details']}</h2>
{details}
</main></body></html>
"""


(out / "reference-typos.html").write_text(render("en"), encoding="utf-8")
(out / "reference-typos-ar.html").write_text(render("ar"), encoding="utf-8")
print(len(rows), dict(kinds), dict(groups))
