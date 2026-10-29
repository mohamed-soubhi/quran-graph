# Ticket tracker

Single source of truth for ticket status. Update this file in the same commit as the work.

**Status:** `todo` → `in-progress` → `review` (agy done, waiting for Claude) → `done` (accepted) | `blocked` | `fix` (review found issues; fix ticket linked)

| ID | Title | Phase | Owner | Status | Depends on | Commit | Notes |
|---|---|---|---|---|---|---|---|
| T0.0 | Repo skeleton, AGENTS.md, decisions, tickets | 0 | Claude | done | — | af3c104 | |
| T0.1 | Python environment + tasks script | 0 | agy | done | T0.0 | 6b2659e | Reviewed 2026-10-29: 1 test passes. Follow-up (tasks.py fails if `.venv` is missing) fixed in T0.2. |
| T0.2 | Neo4j + GDS in Docker | 0 | agy | done | T0.1 | 88ffac6 | Neo4j 5.26.32 + GDS 2.13.14; persistence re-verified by Claude. Review fixes: image pinned, GDS test skips without password and no longer hardcodes the version. |
| T0.3 | Python driver smoke test | 0 | agy | todo | T0.2 | | |
| T0.4 | Ollama models (bge-m3, GLM Arabic check) | 0 | agy | in-progress | T0.1 | | |
| T0.5 | Extraction smoke test (GLM → HadithSpan JSON) | 0 | agy + GLM | todo | T0.4 | | Fixture + expected spans ready (Ibn Kathir 2:255 para 0); expected spans are a Claude draft, need human review |
| T0.6 | Logging + smoke target | 0 | agy | todo | T0.3, T0.5 | | |
| T0.7 | AGENTS.md validation (re-do T0.3 cold) | 0 | agy + Claude | todo | T0.6 | | |
| G0 | Phase 0 gate | 0 | Claude | todo | T0.1–T0.7 | | |
| T1.1 | Download framework + Tanzil text | 1 | agy | todo | G0 | | |
| T1.2 | Download Ibn Kathir (Arabic) | 1 | agy | todo | T1.1 | | Use raw.githubusercontent.com, not jsDelivr |
| T1.3 | Download hadith collections | 1 | agy | todo | T1.1 | | |
| T1.4 | Quranic Corpus morphology | 1 | Human + agy | todo | T1.1 | | Human downloads via email form |
| G1 | Phase 1 gate | 1 | Claude | todo | T1.1–T1.4 | | 114 surahs, 6236 ayat, licences documented |

## Plan-level follow-ups
| Item | Owner | Status |
|---|---|---|
| Update Arabic plan (then English) with the segment range ID | Aya & Mohamed | todo |
| Resolve T0.5 model name: `Citation` (AR) vs `HadithSpan` (EN) | Aya & Mohamed | todo |
| Update plans: FOOTNOTE span type + NFC normalization rule | Aya & Mohamed | todo |
| Review `tests/fixtures/tafsir_sample.expected.json` (then it can seed `data/gold/`) | Aya & Mohamed | todo |
| Phase 5: parse `[[…برقم (n)]]` footnotes as first linking candidate | Claude (ticket) | todo |
| Find a licensed Musnad Ahmad source | Claude | todo (Phase 5) |
