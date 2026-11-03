# Project timeline (Gantt)

Live progress view. Ticket detail and status: `docs/tickets/TRACKER.md` (source of truth).
Claude updates this file whenever a ticket changes status.

**Legend:** green/grey = done · blue = in progress · red = waiting for Aya & Mohamed · hatched future bars = **estimates**
(re-planned at the start of each phase, when its tickets are written).

```mermaid
gantt
    title Quran Tafsir Graph — progress
    dateFormat YYYY-MM-DD
    axisFormat %d %b
    todayMarker stroke-width:3px,stroke:#d33

    section Phase 0 · Setup
    T0.1 Python env                 :done, t01, 2026-10-29, 1d
    T0.2 Neo4j + GDS                :done, t02, 2026-10-29, 1d
    T0.3 Python ↔ Neo4j             :done, t03, 2026-10-29, 1d
    T0.4 Ollama models              :done, t04, 2026-10-29, 1d
    T0.5 GLM extraction test        :done, t05, 2026-10-30, 1d
    T0.6 Logging + smoke            :done, t06, 2026-10-31, 1d
    T0.7 AGENTS.md validation       :done, t07, 2026-10-31, 1d
    G0 Phase 0 gate ✔               :milestone, done, g0, 2026-10-31, 0d

    section Phase 1 · Data acquisition
    T1.1 Downloader + Tanzil        :done, t11, 2026-10-31, 1d
    T1.2 Ibn Kathir (6236 files)    :done, t12, 2026-10-31, 1d
    T1.3 Hadith collections         :done, t13, 2026-10-31, 1d
    T1.4 Quranic Corpus            :done, t14, 2026-10-31, 1d
    G1 Phase 1 gate ✔               :milestone, done, g1, 2026-10-31, 0d

    section Phase 2 · Schema
    T2.1 schema.md v1.0            :done, t21, 2026-10-31, 1d
    T2.2 Constraints + indexes      :done, t22, 2026-10-31, 1d
    T2.3 Extraction contract        :done, t23, 2026-10-31, 1d
    G2 Phase 2 gate ✔               :milestone, done, g2, 2026-11-03, 0d

    section Phase 3 · Load L0 + L1
    T3.1 Tanzil metadata            :done, t31, 2026-11-03, 1d
    T3.2 Quran → JSONL              :done, t32, 2026-11-03, 1d
    T3.3 Corpus → JSONL (Arabic)    :done, t33, 2026-11-03, 1d
    T3.4 Tafsir segments → JSONL    :done, t34, 2026-11-03, 1d
    T3.5 Neo4j writers (MERGE)      :crit, active, p3b, 2026-11-03, 1d
    G3 Phase 3 gate                 :milestone, g3, after p3b, 0d

    section Phase 4 · Span annotation (est.)
    Gold set (~50 segments)         :crit, p4g, after g3, 4d
    4a Quran spans (n-gram)         :p4a, after g3, 4d
    4b Hadith spans (regex + GLM)   :p4b, after p4a, 7d
    4c Commentary + coverage        :p4c, after p4b, 3d
    G4 Phase 4 gate                 :milestone, g4, after p4c, 0d

    section Phase 5 · Hadith linking (est.)
    Footnote numbers → links        :p5a, after g4, 2d
    Fuzzy + embedding match         :p5b, after p5a, 4d
    Review queue (human)            :crit, p5c, after p5b, 2d
    G5 Phase 5 gate                 :milestone, g5, after p5c, 0d

    section Phase 6 · Semantics (est.)
    Topic taxonomy + GLM topics     :p6a, after g5, 4d
    Embeddings + vector index       :p6b, after g5, 2d
    GDS analysis                    :p6c, after p6a, 3d
    G6 Phase 6 gate                 :milestone, g6, after p6c, 0d

    section Phase 7 · GraphRAG (est.)
    Retrieval (vector + Cypher)     :p7a, after g6, 3d
    Answer with source path         :p7b, after p7a, 3d
    UI (Streamlit / Telegram)       :p7c, after p7b, 2d
    G7 20 test questions            :milestone, g7, after p7c, 0d
```

## Progress summary
| Phase | Tickets done | Status | Gate |
|---|---|---|---|
| 0 · Setup | 7 / 7 | ✅ done | G0 signed off 2026-10-31 |
| 1 · Data acquisition | 4 / 4 | ✅ G1 signed off 2026-10-31 | — |
| 2 · Schema | 3 / 3 | ✅ G2 signed off 2026-11-03; schema v1.1 (C1–C4) approved | — |
| 3 · Load L0 + L1 | 4 / 5 | 🔴 T3.5 waiting for your test approval | G3 next |
| 4 · Span annotation | 0 | ⏳ | — |
| 5 · Hadith linking | 0 | ⏳ | — |
| 6 · Semantics | 0 | ⏳ | — |
| 7 · GraphRAG | 0 | ⏳ | — |

## Waiting on Aya & Mohamed
- ~~T1.4: download the Quranic Corpus file~~ — done by Claude 2026-10-31.
- Plan updates (segment range ID, FOOTNOTE, NFC rule); `Citation` vs `HadithSpan`; review the T0.5 fixture.
- Approval of each ticket after its test scenarios.

## How to view
- **GitHub:** open `docs/GANTT.md` in the repo — the chart renders automatically.
- **VS Code:** Markdown preview (`Ctrl+Shift+V`) with a Mermaid extension (e.g. "Markdown Preview Mermaid Support").
- **Anywhere:** paste the `mermaid` block into https://mermaid.live.
