# Sources

Input to Phase 1. Status: **researched 2026-10-29, nothing downloaded yet.**
Downloads go to `data/raw/<source>/` with a SHA-256 per file in `data/raw/CHECKSUMS.txt`.

## Selected sources

| Category | Source | URL | Format | Licence | Stable IDs | Diacritics | Notes |
|---|---|---|---|---|---|---|---|
| Quran text | Tanzil v1.1 (2021-02-12) — Uthmani **and** Simple-Clean | https://tanzil.net/download/ | txt with aya numbers / XML | Verbatim copies only, no changes; credit + link to tanzil.net | surah\|ayah | Uthmani: full; Simple-Clean: none | Store both verbatim. Normalized forms are derived data, never written back as "Quran text". |
| Tafsir | Ibn Kathir (Arabic), via spa5k/tafsir_api, slug `ar-tafsir-ibn-kathir` | https://github.com/spa5k/tafsir_api | JSON per ayah: `{surah, ayah, text}` | Repo MIT; upstream QUL tafsir/22 says "no copyright information"; the work itself is pre-modern (public domain) | surah/ayah | Full | Quran quotes are wrapped in `﴿…﴾`. **Grouped ayat duplicate the text** (73:2 = 73:3, 20,860 chars); 73:1 is empty. Download via raw.githubusercontent.com (jsDelivr refuses: repo > 50 MB). |
| Tafsir (alt / cross-check) | QUL (Tarteel) tafsir 22 | https://qul.tarteel.ai/resources/tafsir/22 | JSON / SQLite | No copyright information | ayah ranges | Full | Original upstream; may give explicit ayah ranges per passage → prefer for grouping. Check in T1.x. |
| Hadith | fawazahmed0/hadith-api, Arabic editions `ara-<collection>` | https://github.com/fawazahmed0/hadith-api | JSON per collection; `hadithnumber`, `arabicnumber`, `text`, `grades[]` | Unlicense (public domain) | collection + number | Full | Collections: bukhari, muslim, abudawud, tirmidhi, nasai, ibnmajah, malik, nawawi, qudsi, dehlawi. `text` = isnad + matn in one string. `grades[]` = list of `{name, grade}` (e.g. Al-Albani, Shuaib Al Arnaut) — used as-is. **Missing: Musnad Ahmad** (heavily cited by Ibn Kathir). |
| Morphology / roots | Quranic Arabic Corpus v0.4 | https://corpus.quran.com/download/ | Plain text, one morpheme per line | GNU licence; verbatim, no changes; credit the source; email needed to download | surah:ayah:word:segment | Buckwalter | For L0 `Word` and `Root`. Manual download (email form). |
| Narrators / isnad | Sanadset 650K (Mendeley, DOI) | https://data.mendeley.com/datasets/5xth87zwb5 | Text/CSV | CC BY 4.0 | to check | to check | 650k records from 926 books; narrator chains extracted. Needed from Phase 5 on, not for Phase 3. |

## Candidates not selected (yet)
| Source | Why not now |
|---|---|
| AhmedBaset/hadith-json (17 collections) | No licence file in repo. Could fill the Musnad Ahmad gap if a licence is confirmed. |
| quranlab/hadith (Hugging Face) | Mixed per-source licences (ODbL for Ahmad/Darimi matn). **Best candidate for Musnad Ahmad** — evaluate in Phase 5. |
| Quranpedia dumps (book 136) | Attribution + version required on republish; fine as a fallback. |
| MIDS (Sahih Muslim isnad, Mendeley) | Muslim only; Sanadset is broader. |
| risan/quran-json | CC BY-SA; Tanzil is the primary source. |

## Checklist (per plan section 5)
| Source | Licence allows use? | Stable IDs? | Diacritized? | Grade + grade source? |
|---|---|---|---|---|
| Tanzil | ☑ (verbatim) | ☑ | ☑ both variants | n/a |
| Ibn Kathir (spa5k/QUL) | ☑ for research; edition copyright unknown | ☑ (needs de-dup of groups) | ☑ | n/a |
| fawazahmed0 hadith | ☑ | ☑ | ☑ | ☑ multiple graders, named |
| Quranic Corpus | ☑ (verbatim, credit) | ☑ | Buckwalter | n/a |
| Sanadset | ☑ CC BY 4.0 | ☐ to check | ☐ to check | ☐ to check |

## Risks / decisions for Phase 2
1. **Grouped tafsir passages** → one `TafsirSegment` must link to an ayah *range*. Proposal: segment_id = `ibn-kathir:<surah>:<first_ayah>-<last_ayah>:<n>`, with `(:TafsirSegment)-[:COVERS]->(:Ayah)` for every ayah in the range. Phase 3 gate "no ayah without tafsir" is then checked via COVERS.
2. **Musnad Ahmad gap** → Phase 5 recall on Ibn Kathir hadith will be capped until a licensed Ahmad source is added.
3. **Text normalization**: Tanzil Uthmani vs the tafsir's quoted text (`﴿…﴾`) use different orthography → 4a matching must use the normalized forms + Simple-Clean.
4. **Licence wording**: "no changes" (Tanzil, Corpus) is satisfied because raw files stay verbatim in `data/raw/`; spans/normalization are separate derived data.
