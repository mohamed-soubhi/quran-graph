# Findings — Quran Tafsir Graph

Things we found in the sources and in our own method while building the graph, kept for a later report.
Each finding gives the evidence (exact counts, ids) and what the project did about it. Newest phase first.
Details of the decisions are in `docs/decisions.md`; ticket reports in `docs/tickets/reports/`.

Sources: Tafsir Ibn Kathir (`spa5k/tafsir_api`, commit eb82bb6), Tanzil Quran text v1.1 (Uthmani + Simple-Clean),
Quranic Arabic Corpus morphology v0.4, hadith collections from `fawazahmed0/hadith-api` (commit df57907).

---

## A. Tafsir Ibn Kathir — the edition

### A1. Written Quran references that point to the wrong ayah (Phase 4, T4.4)
Ibn Kathir's editors print a reference after many Quran quotes, e.g. ﴿…﴾ «[الْأَنْبِيَاءِ: ٣٥]». We checked all
**5,164** printed references against the quoted words. In **40** the words are not in the referenced ayah.
After reading each one: **34 are printing errors** (21 one wrong digit, e.g. «[الْأَنْبِيَاءِ: ٢٥]» for 21:35;
7 a digit missing or extra, e.g. «[النِّسَاءِ: ١١]» for 4:110; wrong surah name, e.g. «[الزُّمَرِ: ١٨]» for المزمل 73:18,
«[النَّمْلِ: ١٠]» for النحل 16:10), 3 are near-identical ayat where the reference may be what Ibn Kathir meant,
2 point to the start of a passage, and **1 is our own error** (see E1).
→ Full list with texts and suggested corrections: [`reference-typos.md`](reference-typos.md) / `reference-typos.csv`.
→ Action: the graph links the quote to the ayah that holds the words, keeps the printed reference on the link
(`ref_text`) and lowers `confidence` to 0.9. The text itself is never changed.

### A2. Quotes follow the "simple" spelling, not the mushaf (Uthmani) spelling (T4.4)
Ibn Kathir quotes «الْعَالَمِينَ», not «ٱلْعَٰلَمِينَ». Even after removing diacritics, Tanzil's Uthmani and Simple texts
differ in 3,777 ayat, so quotes are matched against the Simple text. Beyond that, **122 quotes** differ from
Tanzil Simple in the rasm of a word: نعمة/نعمت (5:11, 14:28), غيابة/غيابت (12:15), مرضاة/مرضات (66:1), داود/داوود
(2:251, 27:15, 38:24), المسيطرون/المصيطرون (52:37, 88:22), الجوار/الجواري (81:16), يحيا/يحيى (20:74).
→ Action: a spelling-tolerant key for quotes of 3+ words, `confidence: 0.8`.

### A3. Hamza seats differ between the tafsir and Tanzil (T4.1, T4.4)
Ibn Kathir «أَئِنَّا» vs Tanzil Simple «أإنا» (56:47). After Normalizer v2, about 200 links still needed a key that ignores
ا ئ ؤ (`confidence: 0.9`).

### A4. Edition quirks inside quote brackets (T4.4)
126 of 26,686 quotes (0.5 %) stay unlinked. Besides one-word glosses of ayat the passage does not cover (left
unlinked on purpose — one word is too ambiguous), the edition has: ayah numbers inside the brackets
(«…يُنفِقُونَ ٣﴾», «فَيُوَفِّيهِمْ (١) أُجُورَهُمْ»), a written reference inside the closing bracket
(«…[الْوَاقِعَةِ: ٣٨، ٣٩] ﴾»), two words joined («فَأَمَّاالَّذِينَ», 3:7), a doubled letter («مممن», 2:282), and a stray
digit inside a surah name («[٠الْفُرْقَانِ: ٧٢]»).

### A5. Editor footnotes `[[…]]` (T4.2, G2)
**31,203** footnotes in 1,857 of the 1,911 passages; 110 run over several lines; the longest has 7,075 characters
(`ibn-kathir:33:41-44:1`). **635** footnotes sit inside a Quran quote, and quotes sit inside hadith — up to three
levels (2:255: a footnote inside a quote inside Anas's hadith). → Schema v1.1 C1: nested spans (`INSIDE`).

### A6. The raw files repeat each passage once per ayah (T1.2, T3.4)
The source has one file per ayah (6,236) but a passage covering several ayat is copied into each: **48.2 M**
characters in total, **13.4 M** distinct, in **1,911** passages. The largest covers 74:11–30 (20 ayat).
→ Action: one `TafsirSegment` per passage, linked to each ayah with `COVERS`.

---

## B. Quran text and morphology

### B1. Tanzil puts the basmala at the start of ayah 1 in 112 surahs (T2.1)
In both Uthmani and Simple-Clean, except surahs 1 and 9. In the Hafs count the basmala is an ayah only in 1:1.
→ Action: the loader removes it and sets `Surah.has_basmala` (schema Q1).

### B2. The Quranic Corpus joins two words in 4 ayat (T2.1, T3.3)
«بَعْدَ مَا» in 2:181, 8:6, 13:37 and «إِلْ يَاسِينَ» in 37:130 are one word in the corpus, two in Tanzil.

### B3. Hamza / tatweel spelling between the corpus and Tanzil (T3.3, T4.1)
319 of 77,383 aligned words differed only in hamza seat or tatweel (corpus «ٱلْءَاخِرَةِ» vs Tanzil «ٱلْـَٔاخِرَةِ», 2:4).
After Normalizer v2: **2** (12:39 and 12:41, «يَٰصَىٰحِبَىِ» vs «يَٰصَٰحِبَىِ», a genuine variant).

### B4. Words with two stems or two roots (T2.1, T3.3)
486 corpus words have two stems (e.g. «مِمَّا» = مِن + ما) and so two lemmas; one word has two roots
(20:94, «يَبْنَؤُمَّ»). 175 lemmas have no root.

---

## C. Hadith collections (fawazahmed0)

### C1. Ibn Kathir's Muslim numbers are the source's `arabicnumber`, not `hadithnumber` (T2.1)
Footnote «صحيح مسلم برقم (٢٨٦٥)» = entry with `arabicnumber` 2865.01 (`hadithnumber` 7207). `hadithnumber` 2865 is
a different hadith. → Phase 5 links footnote numbers through `arabic_number`.

### C2. No grades for Bukhari and Muslim in this source (T1.3)
21,185 of 36,512 entries carry a grade from 9 named graders; Bukhari, Muslim and the 40-hadith books have none.
→ The graph stores "no grade in source"; it never infers a grade from the collection name (hard rule 2).

### C3. 408 entries with empty text (T1.3)
Muslim 203, Nasai 86, Tirmidhi 74, Malik 29, Bukhari 9, Ibn Majah 5, Abu Dawud 2 — mostly introduction
placeholders. Kept as they are, never filled.

### C4. Musnad Ahmad is missing
Ibn Kathir cites «قال الإمام أحمد» constantly (3 of the 24 gold hadith spans are his). Its isnads are still kept
(schema C2: narrators attach to the HADITH span) but there is no `Hadith` node to link to.

---

## D. Annotation (gold set, Phase 4)

### D1. What counts as a hadith span (T4.3, decided by Aya & Mohamed 2026-11-03)
- Athar (stopping at a Companion or Successor) are HADITH spans (`kind: athar`) and count toward the 4b targets.
- A dream or story report with an isnad is commentary, not hadith (gold W44, Ibn Asakir).
- A takhrij line without its own chain («وكذلك رواه ابن جرير من حديث حمزة الزيات») belongs to the hadith before it;
  one with its own chain («وقد رواه مسلم عن أبي بكر … عن الجريري به») is a separate span.
- `kind` follows what the quoted route says («عن علي مرفوعا» → marfu), even when Ibn Kathir then prefers the mawquf
  version («وهو أشبه») — weighing versions is grading, which is not the project's job.

### D2. Human review of the draft (T4.3)
50 windows, 177 draft spans: Mohamed marked 172 correct and 5 wrong (all resolved); one window had to be widened
because it started in the middle of a hadith.

### D3. Language models and character offsets (T0.5)
GLM returns valid structured output (5/5 runs) and finds both hadith in 2:255, but its character offsets move by a
few characters between runs, and it spends ~67 s per paragraph counting characters.
→ Phase 4b asks the model for short text anchors and locates them in code, instead of trusting its offsets.

---

## E. Our own errors found by checking

### E1. Reference check misses a dropped «ف» (T4.4) — open
«﴿وَيْلٌ يَوْمَئِذٍ لِلْمُكَذِّبِينَ﴾ [الطُّورِ: ١١]» (tafsir of 14:47–48): the reference is right (52:11 «فَوَيْلٌ…»), but
the check did not allow the missing «ف» and moved the link to 77:15. To fix: the reference check must accept a
dropped or added clitic (و ف ب ل) at the start of the quote, as the matcher already does elsewhere.

### E2. The gold-set draft cannot prove the matcher alone (T4.4 review)
The gold Quran links were drafted by a matcher similar to the one being tested, so 79/79 on the gold set proved
less than it seemed. A whole-book check found A1–A4. → Every extractor is also checked on the whole book, not only
on the gold set.
