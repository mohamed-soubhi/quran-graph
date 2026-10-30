# AGENTS.md — read this first

Every agent (Claude, agy, GLM scripts) follows these rules. The full plan is in
`docs/plan/` (Arabic is the source of truth; English mirrors it).

## Roles
| Tier | Agent | Does |
|---|---|---|
| 1 | Claude | Plans, schema, writes tickets, builds gold sets, reviews samples |
| 2 | agy | Implements ONE ticket per session: code, tests, commit |
| 3 | GLM via Ollama | Bulk extraction to JSONL in `data/interim/` |

## Hard rules
1. LLMs extract and link only. They never write tafsir text and never assign hadith grades.
2. Hadith grades come from the source dataset, unchanged.
3. Original tafsir text is never cut or edited; structure is added as spans with character offsets.
4. Every relationship carries `source`, `method` (regex | ngram | glm | embedding | human) and `confidence`.
5. Files in `data/raw/` are read-only. Never edit or overwrite them.
6. Code, comments, logs and prints are in English.
   Arabic text is always read/written as UTF-8 (`encoding="utf-8"`); text matching runs on NFC-normalized,
   diacritic-stripped copies with an offset map — stored offsets refer to the original text.
   Span types: QURAN, HADITH, COMMENTARY, FOOTNOTE (`[[…]]` editor notes), OTHER.
7. A phase starts only after the previous phase passes its gate.

## How to work a ticket
1. Read `docs/tickets/<id>.md` and `docs/decisions.md`.
2. Work in small steps (1–2 lines of code or one command), run it, check the result, then continue.
3. Add or update a test in `tests/` for what you built.
4. Run `python scripts/tasks.py test` — all tests must pass.
5. In `docs/tickets/TRACKER.md`, set your ticket to `review` and fill the Notes column.
6. Any external URL you used (download, docs, dataset, model page) goes into `docs/references.md`
   with what it was used for and the date. Model tags, versions and counts go into `docs/decisions.md`.
7. BEFORE committing, write `docs/tickets/reports/<id>.md`: what changed, test output, anything unclear.
8. Commit with a message starting with the ticket id, e.g. `T0.3: add Neo4j client and smoke test`.
9. Do not start another ticket. Stop and report: what was done, test output, anything unclear.

## Environment
- Windows native. Python 3.12 venv in `.venv\` (`.venv\Scripts\python.exe`).
- Neo4j 5 + GDS in Docker Desktop (`docker compose`).
- Ollama at `http://localhost:11434`. Model tags are in `.env` and `docs/decisions.md`.
  Call it only through the HTTP API (`requests` to `/api/chat`, `/api/generate`, `/api/embed`).
  **Never run `ollama run` from a shell** — it waits for a terminal and hangs the session.
- Never start an interactive command (anything that waits for keyboard input). Use timeouts on network calls.
- No `make`: use `python scripts/tasks.py <up|down|test|smoke>`.
- Secrets live in `.env` (never committed). `.env.example` lists the keys.

## Layout
```
docs/      plan/, tickets/ (+ TRACKER.md), decisions.md, references.md, schema.md, sources.md
data/      raw/ (read-only), interim/ (JSONL), gold/ (human-reviewed)
src/       ingest/, extract/, graph/, analysis/
tests/  logs/  scripts/
```
