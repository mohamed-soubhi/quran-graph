# quran-graph — شبكة تفسير القرآن

A 4-layer Neo4j graph linking every Quran ayah to Ibn Kathir's tafsir, and every tafsir passage to its
evidence (other ayat, hadith), so any statement can be traced back to its source.

**Project page:** https://mohamed-soubhi.github.io/quran-graph/ (Arabic) ·
[English](https://mohamed-soubhi.github.io/quran-graph/en.html): overview, progress, Gantt timeline and findings.

A project by Aya & Mohamed, started 2026-10-29.

## Layers
| Layer | Nodes | Loaded |
|---|---|---|
| L0 Text | Surah, Ayah, Word, Lemma, Root | 114 · 6,236 · 77,429 · 4,832 · 1,642 |
| L1 Tafsir | Mufassir, TafsirBook, TafsirSegment | 1,911 segments, 6,236 `COVERS` |
| L2 Evidence | Span, Hadith, HadithBook, Grader, Narrator | 31,203 FOOTNOTE + 26,686 QURAN spans; HADITH spans in review |
| L3 Semantics | Topic, Concept, embeddings | Phase 6 |

Rules that never change: language models only extract and link (no tafsir writing, no hadith grading); hadith grades
come from the source unchanged; the tafsir text is never edited (structure is added as character offsets); every
relationship carries `source`, `method` and `confidence`. Full rules: [`AGENTS.md`](AGENTS.md).

## Status (2026-11-13)
| Phase | Status |
|---|---|
| 0 Setup | ✅ G0 signed off 2026-10-31 |
| 1 Data acquisition | ✅ G1 signed off 2026-10-31 |
| 2 Schema | ✅ G2 signed off 2026-11-03 (schema v1.1) |
| 3 Load L0 + L1 | ✅ G3 signed off 2026-11-03 |
| 4 Span annotation | 🔵 7 of 9 tickets. Footnotes and Quran quotes done; whole-book hadith run done (12,770 windows, 0 failed, 10,667 spans); T4.5c second pass for missed athar in progress; then T4.6 nesting and coverage |
| 5 Hadith linking | ⏳ |
| 6 Semantics | ⏳ |
| 7 GraphRAG | ⏳ |

Ticket detail: [`docs/tickets/TRACKER.md`](docs/tickets/TRACKER.md) · timeline: [`docs/GANTT.md`](docs/GANTT.md) ·
findings: [`docs/findings/findings.html`](docs/findings/findings.html) ([Arabic](docs/findings/findings-ar.html)).

## Sources
Tanzil v1.1 (Quran text) · Quranic Arabic Corpus v0.4 (morphology) · Ibn Kathir via spa5k/tafsir_api ·
fawazahmed0/hadith-api (10 collections, 36,512 hadith) · Sanadset (narrators, Phase 5).
Versions, licences and checksums: [`docs/sources.md`](docs/sources.md); every external link: [`docs/references.md`](docs/references.md).

## Run it
Windows, Python 3.12 venv in `.venv\`, Neo4j 5 + GDS in Docker, Ollama on `localhost:11434`. Copy `.env.example` to `.env` and fill it in.

```
python scripts/tasks.py up        # start Neo4j
python scripts/tasks.py schema    # constraints + indexes
python scripts/tasks.py parse     # raw sources -> data/interim JSONL
python scripts/tasks.py load      # L0 + L1 into Neo4j
python scripts/tasks.py spans --write   # FOOTNOTE + QURAN spans, written to Neo4j
python scripts/tasks.py test      # test suite
```

## Documents
- Plan: `docs/plan/plan-ar.docx` (source of truth), `docs/plan/plan-en.docx`; ideas for later: [`docs/plan/advanced-ideas.md`](docs/plan/advanced-ideas.md)
- Schema: [`docs/schema.md`](docs/schema.md) · decisions: [`docs/decisions.md`](docs/decisions.md)
- Tickets and reports: [`docs/tickets/`](docs/tickets/) · test queries: [`docs/notes/test-queries.html`](docs/notes/test-queries.html)

## Team
Aya & Mohamed (owners; approve every ticket after running its tests) · Claude (plans, schema, gold set, reviews) ·
agy (implements one ticket per session) · GLM via Ollama (bulk extraction).
