# quran-graph

A 4-layer Neo4j graph linking every Quran ayah to its tafsir, and every tafsir passage to its
evidence (other ayat, hadith), so any statement can be traced back to its source.

| Layer | Nodes |
|---|---|
| L0 Text | Surah, Ayah, Word, Root |
| L1 Tafsir | TafsirBook, Mufassir, TafsirSegment |
| L2 Evidence | Span, Hadith, HadithBook, Narrator |
| L3 Semantics | Topic, Concept, embeddings |

- Plan: `docs/plan/plan-ar.docx` (source of truth), `docs/plan/plan-en.docx`
- Agent rules: `AGENTS.md`
- Tickets: `docs/tickets/`, status in `docs/tickets/TRACKER.md`
- Decisions: `docs/decisions.md`
- Sources: `docs/sources.md`; every external link: `docs/references.md`

## Status
Phase 0 — environment setup.
