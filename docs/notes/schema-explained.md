# Schema explained: Lemma (Q4) and tafsir per ayah (Q2)

For Aya & Mohamed, 2026-10-31. All numbers below are counted from our own data in `data/raw/`.

---

## Q4 — What is a Lemma, and why add it?

An Arabic word in the Quran has three levels:

| Level | What it is | Example |
|---|---|---|
| **Word** | the word exactly as written in the ayah, with its prefixes and suffixes | «بِسْمِ» in 1:1, «ٱلسَّمَٰوَٰتِ» in 10:101 |
| **Lemma** | the dictionary entry of that word (the word you would look up) | «ٱسْم» (name), «سَمَآء» (sky) |
| **Root** | the 3 (sometimes 4) base letters shared by a whole family of lemmas | «س م و» |

So: **Word → Lemma → Root**. The plan has only Word and Root. The problem is that one root holds
words with **very different meanings**:

### Example 1 — root «س م و»: 6 lemmas, 381 words in the Quran
| Lemma | Meaning | Words | Example |
|---|---|---|---|
| سَمَآء | sky, heaven | 310 | 10:101 «ٱلسَّمَٰوَٰتِ» |
| ٱسْم | name | 39 | 11:41 «بِسْمِ» |
| مُّسَمًّى | named, appointed (term) | 21 | 11:3 «أَجَلٍ مُّسَمًّى» |
| سَمَّىٰ | to name (verb) | 8 | 12:40 «سَمَّيْتُمُوهَآ» |
| سَمِيّ | namesake, equal | 2 | 19:65 «سَمِيًّا» |
| تَسْمِيَة | naming | 1 | 53:27 «تَسْمِيَةَ» |

Without Lemma, the query "show every place the Quran says **name** (اسم)" returns all 381 words of the root,
and 310 of them mean **sky**. With Lemma it returns exactly the 39 "name" words.

### Example 2 — root «ع ل م»: 14 lemmas, 854 words
عَلِمَ (to know, 382) · عِلْم (knowledge, 105) · عَلِيم (All-Knowing, 163) · عَٰلَمِين (the worlds, 73) · عَلَّمَ (to teach, 41) …
«العالمين» (worlds) and «عليم» (All-Knowing) share a root but are different words for tafsir and topics.

### Example 3 — same spelling, different lemma (the "sense number")
| Lemma | Meaning | Words | Example |
|---|---|---|---|
| عَاد | transgressing | 6 | 2:173 «غَيْرَ بَاغٍ وَلَا عَادٍ» |
| عَاد #2 | the people of ʿĀd | 24 | 7:65 «وَإِلَىٰ عَادٍ أَخَاهُمْ» |

Same letters, same root, completely different meaning. The corpus marks the second one with a number;
we keep it in `Lemma.sense` (15 such lemmas).

### Example 4 — one written word, two lemmas
«مِمَّا» (2:3) is two words joined: «مِن» (from) + «مَا» (what). 486 words in the Quran are like this.

### What it looks like in the graph
```
(:Word {text:"بِسْمِ", word_id:"1:1:1"})-[:HAS_LEMMA]->(:Lemma {text:"ٱسْم"})-[:LEMMA_OF_ROOT]->(:Root {text:"سمو"})
(:Word {text:"ٱلسَّمَٰوَٰتِ"})-[:HAS_LEMMA]->(:Lemma {text:"سَمَآء"})-[:LEMMA_OF_ROOT]->(:Root {text:"سمو"})
```
Both words still reach the same root, so root-level questions keep working. Lemma only adds a more precise level.

### Cost
4,832 extra nodes (small next to 77,429 words). It comes from the same corpus file, no extra download, no LLM.

**Recommendation: add Lemma.** If you say no, Word links straight to Root as in the plan, and "meaning-level"
search (Phase 6 topics, GraphRAG questions like "where does the Quran mention names") loses precision.

---

## Q2 — Store the tafsir duplicated for each ayah?

Your answer: *the tafsir should be whole and related to the ayah; some ayat share one tafsir as a group;
duplicate it for each ayah.*

The goal — **every ayah shows its whole tafsir** — is agreed. The question is only *how it is stored*.
This was decided once already (2026-10-29, approved): store the shared text **once** and link it to every
ayah of the group. Before changing that, here is what each option means.

### The data
- 5,746 of 6,236 ayat (92 %) share their tafsir passage with at least one other ayah.
- The largest group: 74:11–74:30, **20 ayat** with one passage.
- Total text: **13.4 M characters** stored once vs **48.2 M** if duplicated per ayah (3.6×).

### Option A — one passage, linked to each ayah (decided 2026-10-29)
```
(:Ayah 74:11)─┐
(:Ayah 74:12)─┼──COVERS──(:TafsirSegment "ibn-kathir:74:11-30:1"  text = whole passage)
   …          │
(:Ayah 74:30)─┘
```
Asking for 74:15 returns the **whole** passage, exactly like duplication would.

### Option B — a copy for each ayah (your answer)
```
(:Ayah 74:11)──(:TafsirSegment "ibn-kathir:74:11"  text = whole passage)
(:Ayah 74:12)──(:TafsirSegment "ibn-kathir:74:12"  text = same passage again)
   … 20 copies
```

### What changes with B
| Topic | A (stored once) | B (copy per ayah) |
|---|---|---|
| What the user sees for one ayah | whole passage | whole passage — **same** |
| Hadith counts (Phase 5–6) | Muslim 2865 cited in **13** places | counted once per copy — a hadith in the 20-ayah group counts **20 times**; "most-cited hadith" (plan's Phase 6 gate) becomes wrong |
| Span annotation + GLM (Phase 4) | 13.4 M chars to annotate | 48.2 M chars — **3.6× the GLM time**, or extra code to copy results between copies |
| Human review of spans | each passage reviewed once | the same error appears up to 20 times |
| "Is this tafsir about several ayat?" | visible (range in the ID) | lost unless stored separately |

### Recommendation
**Keep A.** It gives exactly what you asked for (each ayah → its whole tafsir) without counting the same
evidence many times. If you still prefer B, it can be done safely by marking copies
(`is_copy_of`) and counting only originals — but that adds rules every later phase must remember.

### About paragraphs (my earlier suggestion)
You chose **whole passages**, not paragraphs — agreed, the segment is the whole passage.
Embeddings (Phase 6) cannot take passages over ~8,000 tokens, so Phase 6 will cut *temporary chunks only for the
embedding index*; the stored tafsir text stays whole.

---

**Please answer:** Q4 add Lemma (yes / no) · Q2 option A or B.
