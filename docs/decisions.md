# Decisions log

Newest first. Each entry: date, decision, reason.

## 2026-10-29 — Runtime: Windows native, not WSL2
agy, Ollama, Python 3.12 and Docker Desktop are installed on Windows; WSL Ubuntu is unused.
`make` is not available, so `scripts/tasks.py` replaces the Makefile (targets: up, down, test, smoke).

## 2026-10-29 — GLM runs on Ollama cloud
Models: `glm-5.3-flash:cloud` (bulk extraction), `glm-5.3:cloud` (harder cases / retries).
This differs from the plan's "free, local" tier 3: usage limits apply and text leaves the machine
(acceptable — inputs are public Quran/tafsir/hadith texts). Embeddings stay local (`bge-m3`, to pull in T0.4).

## 2026-10-29 — Repository
Private GitHub repo `quran-graph`. Repo root is `C:\MSA\QuranGDBExplanation`. Plans kept in `docs/plan/`.

## IDs (from plan section 2)
| ID | Format | Example |
|---|---|---|
| surah_id | integer 1–114 | `2` |
| ayah_id | `<surah>:<ayah>` | `2:255` |
| segment_id | `<book>:<ayah_id>:<n>` | `ibn-kathir:2:255:1` |
| span_id | `<segment_id>#<start>-<end>` | `ibn-kathir:2:255:1#120-245` |
| hadith_id | `<collection>:<number>` | `bukhari:1` |

## Open questions
- Arabic plan T0.5 uses a `Citation` model; English plan uses `HadithSpan`. Using `HadithSpan` (newer, span-based) unless the Arabic plan is updated.
