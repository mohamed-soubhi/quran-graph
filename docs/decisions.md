# Decisions log

Newest first. Each entry: date, decision, reason.
All external sources behind these decisions are listed in `docs/references.md`.

## 2026-11-03 — Normalizer v2: tatweel, hamza, and small waw/yeh skipped (T4.1)
- `src/extract/normalize.py`: `normalize_with_map` skips tatweel `ـ` (U+0640), hamza `ء` (U+0621), small waw `ۥ` (U+06E5), and small yeh `ۦ` (U+06E6).
- Preserves 1-to-1 offset mapping (`len(norm) == len(index)`, strictly increasing index pointing to non-skipped characters).
- Measured on the 77,383 words where corpus and Tanzil Uthmani align 1:1:
  - Previous normalizer: 319 words differed (hamza seat / tatweel spelling variations).
  - Normalizer v2: **exactly 2** words differ (`12:39:1` and `12:41:1`: «يَٰصَىٰحِبَىِ» vs «يَٰصَٰحِبَىِ», a genuine corpus spelling variant).
- Reload: `Ayah.text_norm` and `TafsirSegment.text_norm` re-parsed and reloaded into Neo4j via `tasks.py parse` and `tasks.py load`. Node and relationship counts unchanged.

## 2026-11-03 — Ibn Kathir parser to interim JSONL verified (T3.4)
- Parsers: `src/ingest/parse_tafsir.py`, `scripts/tasks.py parse`.
- Output: `data/interim/tafsir/ibn-kathir/segments.jsonl` (1,911 lines), `mufassir.jsonl` (1 line), `book.jsonl` (1 line); deterministic, UTF-8, keys sorted.
- Exact counts:
  - Exactly 1,911 segments; `covers` total 6,236 (every ayah covered exactly once).
  - Verbatim raw text preserved across every covered ayah (`text` equals raw file).
  - Sum of `char_count` = 13,401,179 characters.
  - Largest group: 74:11–30 (20 ayat); second largest: 74:38–56 (19 ayat).
  - Target fixture IDs verified: `ibn-kathir:2:255-255:1`, `ibn-kathir:30:30-32:1`, `ibn-kathir:4:116-122:1`.
  - Mufassir: `mufassir_id = "ibn-kathir"`, `name = "إسماعيل بن عمر بن كثير"`, `death_hijri = 774`.
  - TafsirBook: `book_id = "ibn-kathir"`, `mufassir_id = "ibn-kathir"`, `title = "تفسير القرآن العظيم"`, `source = "spa5k@eb82bb6"`.
  - Rerun: byte-identical output files across runs.

## 2026-11-03 — Schema v1.1: changes C1–C4 (approved by Aya & Mohamed)
Found by the G2 gate on real Ibn Kathir text (`docs/tickets/reports/G2.md`); written into `docs/schema.md` v1.1.
- C1 nested spans via `(:Span)-[:INSIDE]->(:Span)`; the no-overlap/100 %-coverage rule is for top-level spans; footnotes do not split spans.
- C2 `IN_CHAIN` also from a HADITH Span (isnads of collections we do not have); `HEARD_FROM.chain_id` = hadith_id or span_id.
- C3 QURAN spans include both ornate brackets ﴿ ﴾ (U+FD3F, U+FD3E).
- C4 written references «[سورة: آية]» after a quote are linked by regex first (`ref_text` on the edge).

## 2026-11-03 — Corpus word text vs Tanzil Uthmani (T3.3 review)
- In ayat with equal word counts, corpus `Word.text` equals the Tanzil Uthmani word in **77,064** of 77,383 words.
  The other **319** differ only in hamza seat / tatweel spelling (corpus «ٱلْءَاخِرَةِ» vs Tanzil «ٱلْـَٔاخِرَةِ», 2:4).
- `normalize_with_map` does not merge them yet (keeps tatweel U+0640; ء vs hamza above U+0654). Phase 4a ticket:
  extend the normalizer (drop tatweel; unify hamza forms) and re-measure; `Word.text` stays the corpus form.

## 2026-11-03 — Quranic Corpus parser to interim JSONL verified (T3.3)
- Parsers: `src/ingest/buckwalter.py`, `src/ingest/quranic_corpus.py`, `scripts/tasks.py parse`.
- Output: `data/interim/corpus/words.jsonl` (77,429 lines), `lemmas.jsonl` (4,832 lines), `roots.jsonl` (1,642 lines), `word_lemmas.jsonl` (74,608 lines), `word_roots.jsonl` (49,968 lines), `lemma_roots.jsonl` (4,657 lines); deterministic, UTF-8, keys sorted.
- Exact counts:
  - Words: 77,429 words. First word 1:1:1 text is «بِسْمِ» (joined segments), POS = "N".
  - Lemmas: 4,832 lemmas, 4,817 distinct texts, 15 with homonym sense (all sense 2, e.g. `عَاد#2`).
  - Roots: 1,642 roots, root `smw` -> `سمو`.
  - Links:
    - Word→Lemma: 74,608 links, 486 words with 2 lemmas.
    - Word→Root: 49,968 links, 1 word with 2 roots (`20:94:2`: «يَبْنَؤُمَّ»).
    - Lemma→Root: 4,657 links, 0 lemmas with >1 root, 175 lemmas without root.
  - Round-trip: Arabic ↔ Buckwalter checked lossless for all 1,642 roots, 4,817 lemma texts, and 12,205 word forms (0 unmapped characters).
  - Ayah word counts: match T3.2 `data/interim/quran/ayat.jsonl` across all ayat except exactly the 4 known corpus join exceptions: 2:181 (13 vs 14), 8:6 (11 vs 12), 13:37 (19 vs 20), 37:130 (3 vs 4).
  - Rerun: byte-identical output files.

## 2026-11-03 — Quran parser to interim JSONL verified (T3.2)
- Parser: `src/ingest/parse_quran.py`, `scripts/tasks.py parse`.
- Output: `data/interim/quran/surahs.jsonl` (114 lines) and `ayat.jsonl` (6,236 lines), deterministic, UTF-8, keys sorted.
- Basmala rule (schema Q1): dropped the first 4 words of ayah 1 for 112 surahs (all except 1 and 9); 1:1 and 9:1 verbatim unchanged.
- Word counts: raw Uthmani total = 77,881 words; stripped basmala words = 448 (112 × 4); total word count after rule = 77,433.
- Verification: 112:1 normalized = «قل هو الله احد»; rerun produces byte-identical files.

## 2026-11-03 — Tanzil Quran metadata verified (T3.1)
- Source: Tanzil metadata XML v1.0 via `https://tanzil.net/res/text/metadata/quran-data.xml` (licence: `cc-by`, copyright (C) 2008-2009 Tanzil.info).
- File: `data/raw/tanzil/quran-data.xml` (77,234 bytes, SHA-256 `8867c1d88191472adec9db694b3cd9f135b1a2ef580574d32cf888dcb22c5c7a`).
- Verification: 114 suras (index 1..114), 6,236 total ayas matching Tanzil uthmani ayah counts per surah, continuous start offsets, 86 Meccan, 28 Medinan.

## 2026-10-31 — Schema v1.0: answers Q1–Q5 (approved by Aya & Mohamed)
- Q1: the basmala is an ayah only in Al-Fatiha (1:1). The loader removes the Tanzil basmala prefix from ayah 1 of the
  other 112 surahs and sets `Surah.has_basmala`; raw files unchanged.
- Q2: a `TafsirSegment` is the **whole** passage, not paragraphs, **stored once** and linked to each ayah by `COVERS`
  (Option A; the 2026-10-29 range-ID decision stands). Copying per ayah was considered and rejected: it would count
  shared evidence once per copy and multiply Phase 4 GLM work 3.6× — `docs/notes/schema-explained.md`.
  Embedding chunks (Phase 6) are temporary index data; the stored text stays whole.
- Q3: provenance `method` gains `dataset` (edge given directly by a source dataset, confidence 1.0).
- Q5: hadith grades are `(:Hadith)-[:GRADED {grade}]->(:Grader)` edges, values exactly as in the source.
- Q4: `Lemma` nodes added (4,832; Word → `HAS_LEMMA` → Lemma → `LEMMA_OF_ROOT` → Root), from the corpus file.

## 2026-10-31 — Facts found while drafting the schema (T2.1)
- **Muslim footnote numbers are `arabicnumber`, not `hadithnumber`.** Ibn Kathir footnote «صحيح مسلم برقم (٢٨٦٥)»
  = fawazahmed0 `arabicnumber` `2865.01` (entry `hadithnumber` 7207, text contains «خلقت عبادي حنفاء»).
  `hadithnumber` 2865 is a different hadith. → `hadith_id` uses `hadithnumber` (unique per collection in the source),
  and `arabic_number` is stored for Phase 5 footnote linking. Some entries have no `arabicnumber` key.
- 77 `hadithnumber` values are not integers (e.g. `bukhari` 402.2) → the number part of `hadith_id` is a string
  (`bukhari:402.2`); 0 duplicates per collection.
- **Tanzil prepends the basmala to ayah 1 of 112 surahs** (all except 1 and 9), in both Uthmani and Simple-Clean.
  It is not part of the ayah in the Hafs count (1:1 is the only basmala ayah) → see `docs/schema.md` open question Q1.
- Quranic Corpus words vs Tanzil Uthmani words (after removing that basmala): identical count in 6,232 ayat; 4 exceptions
  where the corpus joins two Tanzil words: «بَعْدَ مَا» in 2:181, 8:6, 13:37 and «إِلْ يَاسِينَ» in 37:130.
- 486 corpus words have 2 stems (e.g. «مِمَّا» = min + maA), so a word can have 2 lemmas; 1 word has 2 roots.
- Muslim 2865 is cited in 13 distinct Ibn Kathir passages (G2 test case "one hadith cited in several places").

## 2026-10-31 — Arabic script is the main value for roots, lemmas and words (approved by Aya & Mohamed)
The Quranic Corpus is written in extended Buckwalter transliteration (one Latin character = one Arabic letter/mark).
- The graph stores **Arabic script as the main value**: `Root.text = "سمو"`, `Lemma.text`, `Word.text`.
  Queries, search and display use Arabic.
- Buckwalter is kept only as a secondary property (`bw`) for traceability to the corpus; nothing is keyed on it.
- Lemma homonym numbers (e.g. `EaAd2`, 15 lemmas) are stripped into `Lemma.sense` (int or null).
- The raw zip stays verbatim (licence); conversion happens in the Phase 3 loader with the official table
  (https://corpus.quran.com/java/buckwalter.jsp). Round-trip Arabic ↔ Buckwalter checked lossless on all
  1,642 roots, 4,817 lemmas and 12,205 forms (0 unmapped characters); the loader test must assert these exact counts.

## 2026-10-31 — Quranic Corpus morphology verified (T1.4)
- Source: Quranic Arabic Corpus v0.4 via `https://corpus.quran.com/download/` (GNU GPL; verbatim copies only, credit + link to corpus.quran.com).
- File: `data/raw/quranic-corpus/quranic-corpus-morphology-0.4.zip` (1,028,754 bytes, SHA-256 `fda26f87cc58b42fc992a3ad666a562805b636f34bcecb46326d048337ca7999`).
- Verification: Archive contains exactly one file `quranic-corpus-morphology-0.4.txt` (6,309,503 bytes, UTF-8, 54 comment lines).
- Measured counts: **128,219** morpheme rows, **77,429** distinct words `(surah, ayah, word)`, **6,236** distinct ayat `(surah, ayah)` (identical 1:1 match with Tanzil 6,236 ayat), and **1,642** distinct `ROOT:` values.
- Zip file is read directly in-place via Python `zipfile` without unzipping into `data/raw/` (Hard Rule 5). Checksum recorded in `data/raw/CHECKSUMS.txt`.

## 2026-10-31 — Hadith raw data measured (T1.3)
- Source: `fawazahmed0/hadith-api` on branch `1`, pinned commit `df57907be35291c91ad6a6691180e22ca9920784` (2026-06-03).
- Files: `editions.json` + 10 diacritized Arabic editions (`ara-<collection>.json`) in `data/raw/hadith/fawazahmed0/`.
- Total hadiths: **36,512**; **21,185** have ≥ 1 grade (58.0%); **9 distinct graders** named.
- Grade distribution: Sahihayn (Bukhari, Muslim) along with Dehlawi, Nawawi, Qudsi have empty `grades: []`. Abu Dawud, Ibn Majah, Malik, Nasai, Tirmidhi have named graders. Hard Rule 2 applies: grades are stored and used as-is.
- Upstream artifacts: 408 hadiths contain `text: ""` (mostly Book 0 / Introduction structural placeholders, e.g. 203 in Muslim, 86 in Nasai, 74 in Tirmidhi); preserved verbatim byte-for-byte (Hard Rule 5). Diacritics verified on Bukhari #1 (249 marks).
- Integrity: Per-file SHA-256 recorded in `data/raw/hadith/fawazahmed0/MANIFEST.txt` and manifest SHA-256 (`941f350e3abefc58ebd4c8981df876f8143a65c862882fcb911d3b2fa9640e38`) recorded in `data/raw/CHECKSUMS.txt`.

## 2026-10-31 — Hadith raw data measured (T1.3)
- 10 collections, **36,512 entries**; **21,185 carry ≥1 grade** from 9 named graders (Al-Albani, Shuaib Al Arnaut, …).
- **Bukhari, Muslim and the three 40-hadith books have no grades** in this source (`grades: []`). The graph stores
  "no grade in source" — it must never infer "sahih" from the collection name (hard rule 2).
- **408 entries have empty text** (Muslim 203, Nasai 86, Tirmidhi 74, Malik 29, Bukhari 9, Ibn Majah 5, Abu Dawud 2),
  e.g. Sahih Muslim introduction entries 1, 2, 5…, `arabicnumber` null. Phase 3/5 skip them; never fill them.
  Exact per-collection counts are asserted in `tests/test_hadith_raw.py`.
- Musnad Ahmad is still missing (Ibn Kathir cites it often) — see TRACKER follow-ups.

## 2026-10-31 — Ibn Kathir raw data measured (T1.2)
- 6,236 files, 0 empty; **1,911 distinct passages**, every one a run of adjacent ayat inside one surah
  (no text repeats non-adjacently) → Phase 3 builds one `TafsirSegment` per run (range IDs, see below).
- Real text size: **13,401,179 characters** of distinct text (48.2 M including duplicates). Use 13.4 M for all
  Phase 4/5 GLM time and cost estimates.
- Largest passages: 74:11 (20 ayat), 74:38 (19), 17-ayah runs at 44:17, 55:62, 68:17, 70:19.

## 2026-10-31 — Tanzil raw Quran text verified (T1.1)
- Source: Tanzil v1.1 via `https://tanzil.net/pub/download/index.php?quranType=<uthmani|simple-clean>&outType=txt-2&agree=true`
- Formats: `data/raw/tanzil/quran-uthmani.txt` (full diacritics) and `data/raw/tanzil/quran-simple-clean.txt` (clean text).
- Verification: Both variants contain exactly 6,236 ayah lines (`surah|ayah|text`), exactly 114 distinct continuous surahs (1..114), and identical `(surah, ayah)` keys in matching order.
- Integrity: Verbatim downloads stored in binary mode; SHA-256 recorded in `data/raw/CHECKSUMS.txt`:
  - `quran-uthmani.txt`: `bf4f57b968d03f4131c070b1e285da9be0e0a108a21c910e872801ca273312c8`
  - `quran-simple-clean.txt`: `228df2a717671aeb9d2ff573002bd28d6b3f973f4bc7153554e3a81663d67610`

## 2026-10-30 — Extraction smoke test results (T0.5)
- Extraction model: `glm-5.3-flash:cloud` called via Ollama `/api/chat` with structured output JSON schema (`HadithSpanList`).
- Transport: `stream=True` in HTTP requests to handle remote reasoning model chunk delivery and avoid monolithic socket read timeouts.
- Prompt design: Short English instructions + few-shot example (custom, not the fixture) + explicit rule that editor notes in `[[…]]` are footnotes, not hadith + directive to directly estimate offsets without word-by-word transcription in thinking.
- Results across 5 smoke test runs on Ibn Kathir 2:255 para 0 (`tests/fixtures/tafsir_sample.txt`):
  - Schema validity: 5/5 runs (100%) produced valid `HadithSpanList` JSON.
  - Timings: `[96.60s, 68.25s, 96.62s, 37.67s, 36.56s]`. Mean: **67.14 s/paragraph** (min 36.56s, max 96.62s).
  - Overlap with expected spans (character overlap ≥ 50%):
    - Expected 1 `[141, 657)` (Ahmad): 1 matching predicted span in 5/5 runs (Run 1: 94.8%, Run 2: 97.1%, Run 3: 100.0% exact match `[141, 657)`, Run 4: 100.0%, Run 5: 100.0%).
    - Expected 2 `[658, 790)` (Muslim): 1 matching predicted span in 5/5 runs (Run 1: 99.2%, Run 2: 85.6%, Run 3: 100.0% match `[658, 792)`, Run 4: 92.4%, Run 5: 97.0%).
  - Footnote handling: In 5/5 runs, `[[…]]` editor notes were correctly excluded from extraction.
- Offset accuracy observations:
  - When asked for character offsets, reasoning models attempt to count Unicode characters in Arabic text one-by-one inside their thinking trace.
  - While offsets are accurate in this test (reaching exact `[141, 657)` in Run 3), offset boundaries vary slightly across runs (e.g. cue inclusion/exclusion by a few characters, or slight shifts at the ending boundary).
  - This empirically confirms the decision for Phase 4b: rather than relying on raw LLM integer offsets, the model should return quoted start/end text anchors that deterministic code locates against normalized text (NFC + diacritics stripped with character offset mapping).
- **Claude review (2026-10-30) — results above are optimistic:**
  - The smoke script's overlap = intersection / *expected* length, so an over-long prediction still scores 100%.
    Use IoU (intersection / union) plus start/end deltas from Phase 4b on.
  - An independent 6th run (same code, temperature 0) returned **1 span only**: Ahmad `[141, 631)`
    (IoU 0.95, end −26 chars, cut mid-word) and **missed the Muslim takhrij entirely**.
    Cloud GLM output is not deterministic at temperature 0; single-run results are not evidence.
  - Speed: ~37–97 s per 904-char paragraph (thinking model). Full Ibn Kathir is several million characters
    (exact size measured in T1.2); at this rate per-paragraph calls are far too slow → Phase 4b sends GLM only short windows around regex cues.
- **Decisions for Phase 4b** (from T0.5):
  1. GLM returns quoted start/end phrases (anchors), never integer offsets; code locates them (NFC, diacritic-insensitive).
  2. Recall comes from regex cues (حدثنا، رواه، أخرجه، قال رسول الله ﷺ) on normalized text; GLM only refines boundaries.
  3. Evaluation = IoU ≥ 0.9 per span over ≥ 3 runs, on the gold set, not a single paragraph.

## 2026-10-29 — Ollama models (T0.4)
- Embeddings: `bge-m3:latest` (id `790764642607`, BERT family, 566.70M params, F16, 1.2 GB, local).
  **Dimension: 1024.** Two Arabic inputs → equal-length vectors (~2 s per call incl. warm-up).
- GLM: `glm-5.3-flash:cloud` (bulk), `glm-5.3:cloud` (strong). Arabic summary of «الحمد لله رب العالمين»
  is coherent Arabic; ~3–4.5 s per short prompt via `/api/generate`.
- **Always call Ollama through the HTTP API** (`/api/generate`, `/api/chat`, `/api/embed`) from Python.
  `ollama run` from a non-interactive shell hung for 25 min in the T0.4 agy session (waits on a TTY).

## 2026-10-29 — Neo4j and GDS versions (T0.2)
- Neo4j: `5.26.32` Community Edition. Image pinned to `neo4j:5.26.32` in review; bump deliberately.
- Graph Data Science (GDS): `2.13.14` (installed via `NEO4J_PLUGINS=["graph-data-science"]`).
- Memory allocation: 4 GB initial/max heap, 4 GB page cache.

## 2026-10-29 — FOOTNOTE span type (approved by Aya & Mohamed)
The Ibn Kathir text contains editor (muhaqqiq) notes in `[[…]]` — 93 in 2:255 alone. They are not
Ibn Kathir's words, so they get their own span type instead of COMMENTARY/OTHER.
- Span `type` enum is now: `QURAN, HADITH, COMMENTARY, FOOTNOTE, OTHER`.
- A FOOTNOTE span includes the `[[` and `]]` markers. Spans inside a footnote are not created in Phase 4.
- Footnotes often carry exact hadith references, e.g. `صحيح مسلم برقم (٨١٠)`, `صحيح البخاري برقم (٢٣١١، ٣٢٧٥)`
  (Arabic-Indic digits). Phase 5 uses them as the **first** linking candidate, before fuzzy/embedding match.
  `المسند (٥/١٤١)` style references are volume/page, not hadith numbers.
- Plan files still list 4 types; update the Arabic plan, then the English one.

## 2026-10-29 — Normalize with Unicode NFC before any text matching
The tafsir stores shadda before the vowel (U+0651 U+064E) while normally typed Arabic has the vowel first
(U+064E U+0651). A literal search for typed «حَدَّثَنَا» finds 0 hits in 2:255; after stripping diacritics, 40.
- Every regex/n-gram match (Phase 4a and 4b) runs on normalized text: NFC → strip diacritics (Mn) →
  unify alef/ya/ta marbuta, with an offset map back to the ORIGINAL text.
- Stored offsets always refer to the original, un-normalized text.

## 2026-10-29 — Tafsir segments cover an ayah range (approved by Aya & Mohamed)
Ibn Kathir often explains several ayat in one passage; the source data copies the same text into each
ayah of the group (73:2 = 73:3, 20,860 chars — see `docs/sources.md`; an earlier "73:1 empty" note was a failed request, corrected 2026-10-31).
- `segment_id` = `<book>:<surah>:<first_ayah>-<last_ayah>:<n>`, e.g. `ibn-kathir:73:1-9:1`.
  A single-ayah passage still uses a range: `ibn-kathir:2:255-255:1`.
- `(:TafsirSegment)-[:COVERS]->(:Ayah)` for every ayah in the range.
- The duplicated text is stored once. Phase 3 gate "no ayah without tafsir" is checked through COVERS.
- span_id is unchanged in shape: `<segment_id>#<start>-<end>`, e.g. `ibn-kathir:73:1-9:1#120-245`.
- The plan files (`docs/plan/*.docx`) still show the old format; update the Arabic plan, then the English one.

## 2026-10-29 — Runtime: Windows native, not WSL2
agy, Ollama, Python 3.12 and Docker Desktop are installed on Windows; WSL Ubuntu is unused.
`make` is not available, so `scripts/tasks.py` replaces the Makefile (targets: up, down, test, smoke).

## 2026-10-29 — GLM runs on Ollama cloud
Models: `glm-5.3-flash:cloud` (bulk extraction), `glm-5.3:cloud` (harder cases / retries).
This differs from the plan's "free, local" tier 3: usage limits apply and text leaves the machine
(acceptable — inputs are public Quran/tafsir/hadith texts). Embeddings stay local (`bge-m3`, to pull in T0.4).

## 2026-10-29 — Repository
Private GitHub repo `quran-graph`. Repo root is `C:\MSA\QuranGDBExplanation`. Plans kept in `docs/plan/`.

## IDs (plan section 2, segment_id amended 2026-10-29)
| ID | Format | Example |
|---|---|---|
| surah_id | integer 1–114 | `2` |
| ayah_id | `<surah>:<ayah>` | `2:255` |
| segment_id | `<book>:<surah>:<first_ayah>-<last_ayah>:<n>` | `ibn-kathir:73:1-9:1` |
| span_id | `<segment_id>#<start>-<end>` | `ibn-kathir:73:1-9:1#120-245` |
| hadith_id | `<collection>:<number>` | `bukhari:1` |

## Open questions
- Arabic plan T0.5 uses a `Citation` model; English plan uses `HadithSpan`. Using `HadithSpan` (newer, span-based) unless the Arabic plan is updated.
