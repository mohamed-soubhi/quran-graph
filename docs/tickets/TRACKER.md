# Ticket tracker

Single source of truth for ticket status. Update this file in the same commit as the work.

**Status:** `todo` → `in-progress` → `review` (agy done, waiting for Claude) → `user-test` (Claude accepted; waiting for
Aya & Mohamed to run the scenarios in `docs/tickets/reports/<id>.md`) → `done` (user approved) | `blocked` | `fix` (issues found; fix ticket linked)

**User approval gate (from 2026-10-31):** no next ticket starts until the previous one is `done`, i.e. approved by
Aya & Mohamed after running its test scenarios. T0.0–T0.5 were accepted before this rule and are covered by the G0 checklist.

| ID | Title | Phase | Owner | Status | Depends on | Commit | Notes |
|---|---|---|---|---|---|---|---|
| T0.0 | Repo skeleton, AGENTS.md, decisions, tickets | 0 | Claude | done | — | af3c104 | |
| T0.1 | Python environment + tasks script | 0 | agy | done | T0.0 | 6b2659e | Reviewed 2026-10-29: 1 test passes. Follow-up (tasks.py fails if `.venv` is missing) fixed in T0.2. |
| T0.2 | Neo4j + GDS in Docker | 0 | agy | done | T0.1 | 88ffac6 | Neo4j 5.26.32 + GDS 2.13.14; persistence re-verified by Claude. Review fixes: image pinned, GDS test skips without password and no longer hardcodes the version. |
| T0.3 | Python driver smoke test | 0 | agy | done | T0.2 | 90222b7 | Neo4j client with verify_connectivity(); test passes, skips if unreachable. Review fix: wrong password now fails (was skipped); driver closed on failed connect. |
| T0.4 | Ollama models (bge-m3, GLM Arabic check) | 0 | agy + Claude | done | T0.1 | (see log) | agy pulled bge-m3 and wrote tests/test_ollama.py, then hung on `ollama run` and hit the 25-min timeout. Claude verified (2 tests pass, dim 1024), wrote decisions + AGENTS.md HTTP-only rule, committed. |
| T0.5 | Extraction smoke test (GLM → HadithSpan JSON) | 0 | agy + GLM | done | T0.4 | 8989740 | Acceptance met: 5/5 valid JSON, mean 67 s/para. agy timed out after committing (no final report). Claude review: overlap metric was one-sided; an extra run missed the Muslim span → Phase 4b uses regex cues + GLM anchor phrases + IoU (see decisions). |
| T0.6 | Logging + smoke target | 0 | agy | done | T0.3, T0.5 | 9f297db | **User approved 2026-10-31.** src/log.py, logger in both clients, `--runs`, `tasks.py smoke`. First run with report-before-commit + 40 min limit: finished in time. Review fix: smoke sets SMOKE_STRICT=1 so an unreachable Neo4j fails instead of skipping. Report: docs/tickets/reports/T0.6.md |
| T0.7 | AGENTS.md validation (re-do T0.3 cold) | 0 | agy + Claude | done | T0.6 | (sandbox) | **User approved 2026-10-31**; sandbox + branch deleted. PASS on attempt 2 (history-free sandbox, new agy project): real rewrite, all 4 behaviours correct, workflow followed. Attempt 1 invalid (byte-identical copy). Report: docs/tickets/reports/T0.7.md |
| G0 | Phase 0 gate | 0 | Claude + Aya & Mohamed | done | T0.1–T0.7 | | **Signed off by Aya & Mohamed 2026-10-31.** Claude: all 5 gate items PASS. Report: docs/tickets/reports/G0.md |
| T1.1 | Download framework + Tanzil text | 1 | agy | done | G0 | 0539e2a | **User approved 2026-10-31.** Claude review: hashes, 6236/114, verbatim (LF, no BOM, copyright block) verified independently; no re-download; tamper detected. Fix: `pytest.ini` keeps tmp_path in `.scratch/` (was %TEMP%). Reusable downloader in src/ingest/download.py. Both uthmani and simple-clean raw Tanzil texts downloaded and checksummed in data/raw/CHECKSUMS.txt. 114 surahs, 6236 ayat validated in tests/test_tanzil_raw.py. Report: docs/tickets/reports/T1.1.md |
| T1.2 | Download Ibn Kathir (Arabic) | 1 | agy | done | T1.1 | f99b10c | **User approved 2026-10-31.** Claude review: stats reproduced independently; 5/5 random files identical to pinned GitHub + MANIFEST; real size 13.4 M chars in 1,911 passages. All 6236 per-ayah files downloaded & verified; MANIFEST.txt recorded in CHECKSUMS.txt; stats generated |
| T1.3 | Download hadith collections | 1 | agy | done | T1.1 | 75939ac | **User approved 2026-10-31.** Claude review: numbers reproduced; fix: exact empty-text counts per collection (agy had relaxed to >98%); AGENTS.md "Deviations" rule. Pinned df57907; all 10 diacritized Arabic editions (36,512 hadiths, 21,185 with grades) downloaded and verified; MANIFEST.txt recorded in CHECKSUMS.txt; tests pass; stats generated. Report: docs/tickets/reports/T1.3.md |
| T1.4 | Quranic Corpus morphology | 1 | Claude + agy | done | T1.3 | 8d4f274 | **User approved 2026-10-31.** Claude review: zip read in place, exact counts, no deviations; 30 tests pass. agy: Recorded SHA-256 in data/raw/CHECKSUMS.txt; src/ingest/quranic_corpus.py direct zip stream; tests/test_corpus_raw.py passes (128,219 morphemes, 77,429 words, 6,236 ayat, 1,642 roots; 1:1 Tanzil match); scripts/corpus_stats.py; docs updated. Report: docs/tickets/reports/T1.4.md |
| G1 | Phase 1 gate | 1 | Claude + Aya & Mohamed | user-test | T1.1–T1.4 | | Claude: all gate items PASS (4 per-ayah sources 114/6236 identical; 6,252/6,252 raw files checksummed; licences + version + date in sources.md). Report: docs/tickets/reports/G1.md |

## Plan-level follow-ups
| Item | Owner | Status |
|---|---|---|
| Update Arabic plan (then English) with the segment range ID | Aya & Mohamed | todo |
| Resolve T0.5 model name: `Citation` (AR) vs `HadithSpan` (EN) | Aya & Mohamed | todo |
| Update plans: FOOTNOTE span type + NFC normalization rule | Aya & Mohamed | todo |
| Review `tests/fixtures/tafsir_sample.expected.json` (then it can seed `data/gold/`) | Aya & Mohamed | todo |
| Phase 5: parse `[[…برقم (n)]]` footnotes as first linking candidate | Claude (ticket) | todo |
| Find a licensed Musnad Ahmad source | Claude | todo (Phase 5) |
