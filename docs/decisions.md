# Decisions log

Newest first. Each entry: date, decision, reason.
All external sources behind these decisions are listed in `docs/references.md`.

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
ayah of the group (73:2 = 73:3, 20,860 chars; 73:1 empty — see `docs/sources.md`).
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
