# Phase 4 annotation rules (gold set T4.3 — confirmed by Aya & Mohamed 2026-11-03)

These rules decide where each span starts and ends. The gold set and the 4a/4b extractors must follow the same rules,
otherwise the gate measures disagreement about rules instead of extraction quality.

| Type | Rule |
|---|---|
| QURAN | Everything from ﴿ to ﴾, both brackets included; footnotes inside are nested spans. Unbracketed text is a QURAN span only when it is presented as a quote (a reading «"وَإن كُلٌّ لَمَا"», a surah named by its first ayah inside a hadith) — Quranic phrases woven into prose stay COMMENTARY. |
| Links | EXPLAINS = an ayah the passage covers; CITES = any other ayah. A written reference «[سورة: آية]» after the quote is stored as `ref_text`. Multi-ayah quotes link to every ayah. |
| HADITH | A narration with an isnad (حدثنا / أخبرنا / سمعت), an explicit takhrij (رواه / أخرجه / أخرجاه + collector), or the Prophet's ﷺ words or acts quoted directly («قال رسول الله ﷺ», «وفي الحديث»). |
| HADITH start | At the attribution cue («قال الإمام أحمد:», «وقال ابن جرير:», «وثبت في صحيح مسلم»); a leading connective like «ولهذا» stays outside. |
| HADITH end | After the last word of the matn, or of the takhrij that belongs to it («… أخرجاه»); closing quote marks included, the sentence-final full stop not. A footnote right after the end is a separate top-level span. A takhrij sentence about another collection («وقد رواه مسلم عن … به») is its own HADITH span (T0.5 fixture). |
| HADITH kind | `marfu` = reaches the Prophet ﷺ; `athar` = stops at a Companion or Successor. Both kinds count toward the 4b targets (Aya & Mohamed, 2026-11-03). |
| Not HADITH | A tafsir opinion with only a short route and no transmission verb or takhrij («قال علي بن أبي طلحة عن ابن عباس: …», «قال مجاهد: …») → COMMENTARY. A dream or story report, even with an isnad, is not a hadith → COMMENTARY (W44, Ibn Asakir). |
| OTHER | Poetry: one span per poem, first word to the last «...». |
| COMMENTARY | Everything not covered by the spans above (filled in by 4c). |

Gold windows are whole paragraphs that never start or end inside `[[…]]` or `﴿…﴾`; a hadith that runs past the
window edge is cut out by moving the window edge (W50).
Tooling: `scripts/gold/` (sample → draft → manual anchors → build → review page in `data/interim/gold/`).
