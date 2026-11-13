# quran-graph — شبكة تفسير القرآن

<div dir="rtl">

## بالعربية

قاعدة بيانات رسومية (Neo4j) من أربع طبقات، تربط كل آية بتفسيرها عند ابن كثير، وتربط كل مقطع من التفسير بأدلّته
من آيات وأحاديث، بحيث يمكن تتبّع كل صلة إلى مصدرها.

**صفحة المشروع:** https://mohamed-soubhi.github.io/quran-graph/ — الفكرة، والتقدّم، والجدول الزمني، والملاحظات.

مشروع آية ومحمد، بدأ في 29 أكتوبر 2026.

### الطبقات
| الطبقة | العقد | المحمَّل |
|---|---|---|
| L0 النص | السور، الآيات، الكلمات، اللمّات، الجذور | 114 · 6,236 · 77,429 · 4,832 · 1,642 |
| L1 التفسير | المفسِّر، الكتاب، مقاطع التفسير | 1,911 مقطعًا، و6,236 علاقة تغطية |
| L2 الأدلّة | المقاطع المعلَّمة، الأحاديث، كتب الحديث، المحكِّمون، الرواة | 31,203 حاشية و26,686 اقتباسًا قرآنيًا؛ مقاطع الأحاديث قيد المراجعة |
| L3 الدلالات | الموضوعات والمفاهيم والتضمينات | المرحلة السادسة |

قواعد ثابتة: النماذج اللغوية تستخرج وتربط فقط، فلا تكتب تفسيرًا ولا تحكم على حديث؛ درجات الأحاديث تؤخذ من المصدر كما هي؛
نص التفسير لا يُعدَّل، والبنية تُضاف بمواضع الحروف؛ وكل علاقة تحمل مصدرها وطريقتها ودرجة الثقة فيها.

### الحالة (13 نوفمبر 2026)
| المرحلة | الحالة |
|---|---|
| 0 التجهيز | ✅ اعتُمدت البوابة في 31 أكتوبر |
| 1 جمع البيانات | ✅ اعتُمدت البوابة في 31 أكتوبر |
| 2 المخطط | ✅ اعتُمدت البوابة في 3 نوفمبر (المخطط 1.1) |
| 3 تحميل النص والتفسير | ✅ اعتُمدت البوابة في 3 نوفمبر |
| 4 تعليم المقاطع | 🔵 7 من 9 مهام: الحواشي والقرآن تمّا؛ استخراج الأحاديث من الكتاب كله تمّ (10,667 مقطعًا)؛ تجري تمريرة ثانية للآثار الفائتة (T4.5c)؛ ثم التداخل والتغطية (T4.6) |
| 5 ربط الأحاديث | ⏳ |
| 6 الدلالات | ⏳ |
| 7 السؤال والجواب | ⏳ |

الملاحظات: [`docs/findings/findings-ar.html`](docs/findings/findings-ar.html) · المهام: [`docs/tickets/TRACKER.md`](docs/tickets/TRACKER.md)

**الفريق:** آية ومحمد (أصحاب المشروع، يعتمدان كل مهمة بعد اختبارها) · Claude (التخطيط والمراجعة) · agy (التنفيذ) · GLM عبر Ollama (الاستخراج بالجملة).

</div>

---

## English

A 4-layer Neo4j graph linking every Quran ayah to Ibn Kathir's tafsir, and every tafsir passage to its
evidence (other ayat, hadith), so any statement can be traced back to its source.

**Project page:** https://mohamed-soubhi.github.io/quran-graph/ (Arabic) ·
[English](https://mohamed-soubhi.github.io/quran-graph/en.html): overview, progress, Gantt timeline and findings.

A project by Aya & Mohamed, started 2026-10-29.

### Layers
| Layer | Nodes | Loaded |
|---|---|---|
| L0 Text | Surah, Ayah, Word, Lemma, Root | 114 · 6,236 · 77,429 · 4,832 · 1,642 |
| L1 Tafsir | Mufassir, TafsirBook, TafsirSegment | 1,911 segments, 6,236 `COVERS` |
| L2 Evidence | Span, Hadith, HadithBook, Grader, Narrator | 31,203 FOOTNOTE + 26,686 QURAN spans; HADITH spans in review |
| L3 Semantics | Topic, Concept, embeddings | Phase 6 |

Rules that never change: language models only extract and link (no tafsir writing, no hadith grading); hadith grades
come from the source unchanged; the tafsir text is never edited (structure is added as character offsets); every
relationship carries `source`, `method` and `confidence`. Full rules: [`AGENTS.md`](AGENTS.md).

### Status (2026-11-13)
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

### Sources
Tanzil v1.1 (Quran text) · Quranic Arabic Corpus v0.4 (morphology) · Ibn Kathir via spa5k/tafsir_api ·
fawazahmed0/hadith-api (10 collections, 36,512 hadith) · Sanadset (narrators, Phase 5).
Versions, licences and checksums: [`docs/sources.md`](docs/sources.md); every external link: [`docs/references.md`](docs/references.md).

### Run it
Windows, Python 3.12 venv in `.venv\`, Neo4j 5 + GDS in Docker, Ollama on `localhost:11434`. Copy `.env.example` to `.env` and fill it in.

```
python scripts/tasks.py up        # start Neo4j
python scripts/tasks.py schema    # constraints + indexes
python scripts/tasks.py parse     # raw sources -> data/interim JSONL
python scripts/tasks.py load      # L0 + L1 into Neo4j
python scripts/tasks.py spans --write   # FOOTNOTE + QURAN spans, written to Neo4j
python scripts/tasks.py test      # test suite
```

### Documents
- Plan: `docs/plan/plan-ar.docx` (source of truth), `docs/plan/plan-en.docx`; ideas for later: [`docs/plan/advanced-ideas.md`](docs/plan/advanced-ideas.md)
- Schema: [`docs/schema.md`](docs/schema.md) · decisions: [`docs/decisions.md`](docs/decisions.md)
- Tickets and reports: [`docs/tickets/`](docs/tickets/) · test queries: [`docs/notes/test-queries.html`](docs/notes/test-queries.html)

### Team
Aya & Mohamed (owners; approve every ticket after running its tests) · Claude (plans, schema, gold set, reviews) ·
agy (implements one ticket per session) · GLM via Ollama (bulk extraction).
