# Decisions log

Newest first. Each entry: date, decision, reason.
All external sources behind these decisions are listed in `docs/references.md`.

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
