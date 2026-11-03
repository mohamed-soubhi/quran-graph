# Graph schema (Phase 2)

**Status:** v1.1 (approved by Aya & Mohamed 2026-11-03). v1.0 = T2.1 (Q1–Q5, end of file); v1.1 adds C1–C4 found by
the G2 gate on real text (`docs/tickets/reports/G2.md`).
Background for Q2 and Q4: `docs/notes/schema-explained.md`. Changes after v1.0 go through `docs/decisions.md`.
Facts behind each choice: `docs/decisions.md`. Sources: `docs/sources.md`.

## Conventions
- **Arabic script is the main value** of every Arabic property (`text`, `name`). Buckwalter only in `bw`.
- Original text (Quran, tafsir, hadith) is stored **verbatim** from `data/raw/`. Derived forms (`text_norm`) are
  extra properties, never a replacement.
- `text_norm` = NFC → strip diacritics (Unicode Mn) → unify alef forms (أ إ آ ٱ → ا), ى → ي, ة → ه.
  Used only for matching and search; offsets always refer to the original `text`.
- IDs are strings except `surah_id` (int). Each ID is unique (see Constraints).

### Provenance on every relationship (hard rule 4)
| Property | Type | Meaning |
|---|---|---|
| `source` | string | Dataset + version, or extraction run id: `tanzil-1.1`, `quranic-corpus-0.4`, `spa5k@eb82bb6`, `hadith-api@df57907`, `run:<yyyymmdd-hhmm>-<script>` |
| `method` | enum | `dataset` (given by the source, deterministic load) · `regex` · `ngram` · `glm` · `embedding` · `human` |
| `confidence` | float 0–1 | 1.0 for `dataset` and `human` |

`dataset` is a new method value (Q3, approved). Structural edges (`HAS_AYAH`, `NEXT`, …) also carry the three properties.

## L0 — Text
| Label | Key | Properties |
|---|---|---|
| `Surah` | `surah_id` int 1–114 | `name` (Arabic, Tanzil metadata), `tname`, `type` (Meccan/Medinan), `revelation_order`, `ayah_count`, `has_basmala` bool (false for 9) |
| `Ayah` | `ayah_id` `"2:255"` | `surah_id`, `number`, `text` (Tanzil Uthmani), `text_simple` (Tanzil Simple-Clean), `text_norm`, `word_count` |
| `Word` | `word_id` `"2:255:3"` | `ayah_id`, `position` (1-based, corpus order), `text` (Arabic, all segments joined), `bw`, `pos` (part of speech of the stem) |
| `Root` | `root_id` = `text` `"سمو"` | `text` (letters, no spaces), `bw` `"smw"`; 1,642 nodes |
| `Lemma` | `lemma_id` = `text` + `#<sense>` if any, e.g. `"ٱسْم"`, `"عَاد#2"` | `text`, `sense` (int or null), `bw` (without the sense digit); 4,832 nodes (4,817 distinct texts, 15 with a sense number) |

`Lemma` is not in the plan's L0 list; it is added because one root has many words with different meanings
(سمو → اسم، سماء) and 486 words have two lemmas (Q4, approved).

**Basmala (Q1, approved):** only 1:1 keeps the basmala — it is an ayah of Al-Fatiha. For the 112 other surahs
Tanzil puts the basmala in front of ayah 1; the loader removes it from `Ayah.text` / `text_simple` and sets
`Surah.has_basmala = true` (false for surah 9). The raw Tanzil files stay unchanged. Test: 112 ayat stripped, 1:1 unchanged.

| Relationship | From → To | Properties (+ provenance) |
|---|---|---|
| `HAS_AYAH` | Surah → Ayah | |
| `NEXT` | Ayah → Ayah | reading order 1:1 → 114:6 |
| `HAS_WORD` | Ayah → Word | `position` |
| `HAS_LEMMA` | Word → Lemma | `segment` (corpus segment number) |
| `HAS_ROOT` | Word → Root | |
| `LEMMA_OF_ROOT` | Lemma → Root | |

Word morphology beyond `pos` (prefixes, suffixes, case, mood …) stays in the raw corpus for now; added when a use case needs it.

## L1 — Tafsir
| Label | Key | Properties |
|---|---|---|
| `Mufassir` | `mufassir_id` `"ibn-kathir"` | `name` «إسماعيل بن عمر بن كثير», `death_hijri` 774 |
| `TafsirBook` | `book_id` `"ibn-kathir"` | `title` «تفسير القرآن العظيم», `source` `spa5k@eb82bb6` |
| `TafsirSegment` | `segment_id` `"ibn-kathir:2:255-255:1"` | `book_id`, `surah_id`, `first_ayah`, `last_ayah`, `n`, `text` (the **whole** passage, verbatim), `text_norm`, `char_count` |

A segment is the **whole passage** (Q2, approved: not paragraphs). A passage shared by several ayat is **stored
once** and linked to every ayah of the group by `COVERS` (Option A, approved; decision of 2026-10-29 confirmed).

| Relationship | From → To | |
|---|---|---|
| `WROTE` | Mufassir → TafsirBook | |
| `HAS_SEGMENT` | TafsirBook → TafsirSegment | |
| `COVERS` | TafsirSegment → Ayah | one edge per ayah in `first_ayah..last_ayah` (decided 2026-10-29) |
| `NEXT` | TafsirSegment → TafsirSegment | reading order inside the book |

## L2 — Evidence
| Label | Key | Properties |
|---|---|---|
| `Span` | `span_id` `"<segment_id>#141-657"` | `segment_id`, `start`, `end` (offsets in the segment's original `text`, end exclusive), `type` ∈ QURAN, HADITH, COMMENTARY, FOOTNOTE, OTHER; HADITH only: `cue`, `collection_hint`, `number_hint`. Nested spans: see `INSIDE` (C1) |
| `HadithBook` | `collection` `"muslim"` | `name` (Arabic), `edition` `"ara-muslim"`, `source` `hadith-api@df57907` |
| `Hadith` | `hadith_id` `"muslim:7207"`, `"bukhari:402.2"` | `collection`, `number` (= source `hadithnumber`, string), `arabic_number` (= source `arabicnumber`, e.g. `"2865.01"`, may be null), `book_number`, `number_in_book` (= `reference`), `text` (verbatim, isnad + matn) |
| `Grader` | `name` `"Al-Albani"` | 9 nodes |
| `Narrator` | `narrator_id` (Phase 5, source: Sanadset) | `name` (Arabic) |

Hadith entries with empty `text` (408) are not loaded.
The span `text` is not stored twice: it is `substring(segment.text, start, end - start)`.

| Relationship | From → To | Properties (+ provenance) |
|---|---|---|
| `HAS_SPAN` | TafsirSegment → Span | every span, top-level or nested |
| `INSIDE` | Span → Span | the span lies inside its parent span (C1) |
| `EXPLAINS` | Span(QURAN) → Ayah | the quote is an ayah this segment `COVERS` |
| `CITES` | Span(QURAN) → Ayah | the quote is another ayah (tafsir of Quran by Quran); `ref_text` = a written reference after the quote, e.g. «[الرُّومِ:٢٥]» (C4) |
| `CITES` | Span(HADITH) → Hadith | linked hadith; `evidence` = span_id of the footnote that gave the number, if any |
| `IN_BOOK` | Hadith → HadithBook | |
| `GRADED` | Hadith → Grader | `grade` exactly as in the source (e.g. `"Sahih"`); no edge = no grade in source (Q5, approved) |
| `IN_CHAIN` | Hadith → Narrator, or Span(HADITH) → Narrator | `position` (1 = narrator nearest the collector); from a Span also `mention_start`, `mention_end` (C2) |
| `HEARD_FROM` | Narrator → Narrator | `chain_id` = hadith_id or span_id of the chain (one edge per chain link; used by GDS) (C2) |

A quote spanning several ayat gets one `EXPLAINS`/`CITES` edge per ayah. A HADITH span with no match (e.g. Musnad Ahmad,
not in our sources) keeps its hints and has no `CITES` edge: "not found", never guessed.

### Span rules
1. **Top-level spans** (no `INSIDE` edge) of one segment do not overlap and cover the whole text (Phase 4c gate: 100 %).
2. **Nested spans (C1):** a span may lie inside exactly one parent span — `(:Span)-[:INSIDE]->(:Span)` — e.g. a Quran
   quote inside a hadith, a footnote inside a Quran quote. A child lies within its parent's offsets; children of the
   same parent do not overlap. Nothing is split. Real example (G2): Anas's hadith in 2:255 contains 5 Quran quotes, and
   ﴿اللَّهُ لَا إِلَهَ إِلا هُوَ [[في أ: …]]﴾ inside it contains a footnote (3 levels).
3. **QURAN spans include both ornate brackets** ﴿ … ﴾ (U+FD3F … U+FD3E), as FOOTNOTE spans include `[[ ]]` (C3).
4. Editor additions in single brackets `[…]` stay inside the surrounding span.
5. **Written references (C4):** when a Quran quote is followed by «[<surah name>: <ayah or range>]», Phase 4a links it by
   regex first (surah name matched to Tanzil metadata after normalization), with `ref_text` on the `CITES`/`EXPLAINS` edge.
6. **Isnad without a Hadith node (C2):** narrators of a chain quoted in the tafsir from a collection we do not have
   (e.g. Musnad Ahmad) attach to the HADITH span via `IN_CHAIN`; the span has no `CITES` edge.

## L3 — Semantics (outline; detailed at the start of Phase 6)
| Label / property | Notes |
|---|---|
| `Topic` `topic_id` | fixed taxonomy, `name` (Arabic); `(:Topic)-[:BROADER]->(:Topic)` |
| `Concept` `concept_id` | named concepts (persons, places, rulings); may link to `Lemma` |
| `ABOUT` | TafsirSegment / Ayah → Topic, with provenance |
| `embedding` | 1024-float property on `Ayah` (bge-m3) + Neo4j vector index; passages longer than the model limit get temporary `Chunk` nodes for the index only (Phase 6) — the segment text stays whole |

## Constraints and indexes (T2.2)
Unique: `Surah.surah_id`, `Ayah.ayah_id`, `Word.word_id`, `Root.root_id`, `Lemma.lemma_id`, `Mufassir.mufassir_id`,
`TafsirBook.book_id`, `TafsirSegment.segment_id`, `Span.span_id`, `HadithBook.collection`, `Hadith.hadith_id`,
`Grader.name`, `Narrator.narrator_id`.
Indexes: `Span.type`, `Hadith.arabic_number`, `Hadith.collection`, full-text on `Ayah.text_norm` and `TafsirSegment.text_norm`.

## Expected counts after Phase 3 (from Phase 1 measurements)
Surah 114 · Ayah 6,236 · Word 77,429 · Root 1,642 · Lemma 4,832 · TafsirBook 1 · Mufassir 1 · Hadith 36,104 (36,512 − 408 empty) ·
HadithBook 10 · Grader 9. TafsirSegment 1,911 · COVERS 6,236 (every ayah exactly one Ibn Kathir segment).

## Answers (2026-10-31)
| # | Question | Answer |
|---|---|---|
| Q1 | Basmala in ayah 1 | **Approved:** kept only in 1:1 (Al-Fatiha); removed from ayah 1 of the other 112 surahs. |
| Q2 | Size of a `TafsirSegment` | **Whole passage** (not paragraphs), **stored once** and linked to each ayah by `COVERS` (Option A). |
| Q3 | Provenance method `dataset` | **Approved.** |
| Q4 | `Lemma` nodes | **Approved:** 4,832 Lemma nodes from the same corpus file (Word → Lemma → Root). |
| Q5 | Grades as `GRADED` edges to `Grader` | **Approved.** |

## Changes v1.0 → v1.1 (approved 2026-11-03, found by the G2 gate)
| # | Change |
|---|---|
| C1 | Nested spans via `INSIDE`; coverage/no-overlap rule applies to top-level spans; footnotes no longer split spans |
| C2 | `IN_CHAIN` also from a HADITH `Span`; `HEARD_FROM.chain_id` replaces `hadith_id` |
| C3 | QURAN spans include both ornate brackets ﴿ ﴾ |
| C4 | Written references «[سورة: آية]» after a quote are linked by regex first (`ref_text`) |
