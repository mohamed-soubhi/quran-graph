# Sources

Input to Phase 1. Status: **researched 2026-10-29, nothing downloaded yet.**
Downloads go to `data/raw/<source>/` with a SHA-256 per file in `data/raw/CHECKSUMS.txt`.
Full list of every link consulted: `docs/references.md`.

## Selected sources

| Category | Source | URL | Format | Licence | Stable IDs | Diacritics | Notes |
|---|---|---|---|---|---|---|---|
| Quran text | Tanzil v1.1 (2021-02-12) — Uthmani **and** Simple-Clean | https://tanzil.net/download/ | txt with aya numbers / XML | Verbatim copies only, no changes; credit + link to tanzil.net | surah\|ayah | Uthmani: full; Simple-Clean: none | Store both verbatim. Normalized forms are derived data, never written back as "Quran text". |
| Tafsir | Ibn Kathir (Arabic), via spa5k/tafsir_api, slug `ar-tafsir-ibn-kathir` | https://github.com/spa5k/tafsir_api | JSON per ayah: `{surah, ayah, text}` | Repo MIT; upstream QUL tafsir/22 says "no copyright information"; the work itself is pre-modern (public domain) | surah/ayah | Full | Quran quotes wrapped in `﴿…﴾`. Downloaded in T1.2 via raw.githubusercontent.com pinned to commit `eb82bb6294efe30ad5c135c03b1864afaa70e855` (2026-09-30). Measured stats (T1.2): 6,236 ayat, 48,211,904 total characters (incl. duplicates; **13,401,179 characters of distinct text** — the real tafsir size, Claude review), 0 empty texts, 4,325 texts identical to previous ayah, 1,911 distinct texts, 1,421 grouped passages (runs > 1). Top 5 largest groups: 74:11 (size 20), 74:38 (size 19), 44:17 (size 17), 55:62 (size 17), 68:17 (size 17). |
| Tafsir (alt / cross-check) | QUL (Tarteel) tafsir 22 | https://qul.tarteel.ai/resources/tafsir/22 | JSON / SQLite | No copyright information | ayah ranges | Full | Original upstream; may give explicit ayah ranges per passage → prefer for grouping. Check in T1.x. |
| Hadith | fawazahmed0/hadith-api, Arabic editions `ara-<collection>` | https://github.com/fawazahmed0/hadith-api | JSON per collection; `hadithnumber`, `arabicnumber`, `text`, `grades[]` | Unlicense (public domain) | collection + number | Full | Pinned to commit `df57907be35291c91ad6a6691180e22ca9920784` (branch `1`, 2026-06-03). Downloaded in T1.3: `editions.json` + 10 diacritized Arabic editions (36,512 total hadiths, 21,185 with ≥1 grade, 9 distinct graders). `text` = isnad + matn in one string. `grades[]` = list of `{name, grade}` — used as-is. **Missing: Musnad Ahmad** (heavily cited by Ibn Kathir). |
| Morphology / roots | Quranic Arabic Corpus v0.4 | https://corpus.quran.com/download/ | Plain text, one morpheme per line | GNU licence; verbatim, no changes; credit the source; email needed to download | surah:ayah:word:segment | Buckwalter | Downloaded in T1.4 (version 0.4 zip, verbatim in `data/raw/quranic-corpus/quranic-corpus-morphology-0.4.zip`, SHA-256 `fda26f87…`). Measured stats: 128,219 morpheme rows, 77,429 words, 6,236 ayat (identical to Tanzil simple-clean), 1,642 distinct roots. For L0 `Word` and `Root`. |
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

## Hadith collections measured (T1.3)
Pinned commit `df57907be35291c91ad6a6691180e22ca9920784` (branch `1`, 2026-06-03).
Stored in `data/raw/hadith/fawazahmed0/` with per-file SHA-256 in `MANIFEST.txt`.

| Collection | Edition | Total Hadiths | With ≥1 Grade | Graders | Top 5 Grade Values |
|---|---|---|---|---|---|
| abudawud | `ara-abudawud` | 5,274 | 5,274 | Al-Albani, Muhammad Muhyi Al-Din Abdul Hamid, Shuaib Al Arnaut, Zubair Ali Zai | Sahih (8,975), Daif (3,484), Hasan (1,526), Isnaad Hasan (714), Isnaad Sahih (604) |
| bukhari | `ara-bukhari` | 7,589 | 0 | — | — |
| dehlawi | `ara-dehlawi` | 40 | 0 | — | — |
| ibnmajah | `ara-ibnmajah` | 4,343 | 4,341 | Al-Albani, Muhammad Fouad Abd al-Baqi, Shuaib Al Arnaut, Zubair Ali Zai | Sahih (7,935), Daif (3,256), Hasan (1,272), Sahih Muslim (535), Hasan Sahih (491) |
| malik | `ara-malik` | 1,858 | 1,858 | Salim al-Hilali | Sahih (619), Mauquf Sahih (481), Maqtu Sahih (241), Mauquf Daif (189), Sahih Lighairihi (110) |
| muslim | `ara-muslim` | 7,563 | 0 | — | — |
| nasai | `ara-nasai` | 5,765 | 5,758 | Abu Ghuddah, Al-Albani, Zubair Ali Zai | Sahih (9,719), Hasan (1,523), Sahih - Agreed Upon (977), Daif (967), Isnaad Sahih (719) |
| nawawi | `ara-nawawi` | 42 | 0 | — | — |
| qudsi | `ara-qudsi` | 40 | 0 | — | — |
| tirmidhi | `ara-tirmidhi` | 3,998 | 3,954 | Ahmad Muhammad Shakir, Al-Albani, Bashar Awad Maarouf, Zubair Ali Zai | Sahih (5,661), Daif (2,162), Hasan Sahih (2,016), Hasan (1,289), Sahih - Agreed Upon (679) |
| **Total** | **10 collections** | **36,512** | **21,185** | **9 distinct graders** | — |

## Quranic Corpus morphology measured (T1.4)
Archive `data/raw/quranic-corpus/quranic-corpus-morphology-0.4.zip` (SHA-256 `fda26f87cc58b42fc992a3ad666a562805b636f34bcecb46326d048337ca7999`, 1,028,754 bytes).
Contains exactly one member `quranic-corpus-morphology-0.4.txt` (6,309,503 bytes uncompressed). Read in-place via Python `zipfile` (Hard Rule 5).

| Metric | Value |
|---|---|
| Archive members | 1 (`quranic-corpus-morphology-0.4.txt`) |
| Uncompressed text size | 6,309,503 bytes |
| License/comment lines | 54 (`#`) |
| Header line | 1 (`LOCATION\tFORM\tTAG\tFEATURES`) |
| Morpheme rows | 128,219 |
| Distinct words `(surah, ayah, word)` | 77,429 |
| Distinct ayat `(surah, ayah)` | 6,236 (100% 1:1 match with Tanzil 6,236 ayat) |
| Distinct roots (`ROOT:...`) | 1,642 |

### Top 10 Most Frequent Roots (Buckwalter)
| Root | Occurrences |
|---|---|
| `Alh` | 2,851 |
| `qwl` | 1,722 |
| `kwn` | 1,390 |
| `rbb` | 980 |
| `Amn` | 879 |
| `Elm` | 854 |
| `qwm` | 660 |
| `Aty` | 549 |
| `kfr` | 525 |
| `byn` | 523 |

### Top 10 Morpheme Tags
| Tag | Description / Count |
|---|---|
| `N` | Noun (25,136) |
| `PRON` | Personal pronoun (24,685) |
| `V` | Verb (19,356) |
| `P` | Preposition (13,006) |
| `CONJ` | Conjunction (9,450) |
| `DET` | Determiner (8,377) |
| `PN` | Proper noun (3,911) |
| `REL` | Relative pronoun (3,575) |
| `REM` | Resumption particle (2,925) |
| `NEG` | Negative particle (2,688) |

## Risks / decisions for Phase 2
1. **Grouped tafsir passages** → one `TafsirSegment` links to an ayah *range*. **Decided 2026-10-29** (see `docs/decisions.md`): segment_id = `ibn-kathir:<surah>:<first_ayah>-<last_ayah>:<n>`, with `(:TafsirSegment)-[:COVERS]->(:Ayah)` for every ayah in the range. Phase 3 gate "no ayah without tafsir" is checked via COVERS.
2. **Musnad Ahmad gap** → Phase 5 recall on Ibn Kathir hadith will be capped until a licensed Ahmad source is added.
3. **Text normalization**: Tanzil Uthmani vs the tafsir's quoted text (`﴿…﴾`) use different orthography → 4a matching must use the normalized forms + Simple-Clean.
4. **Licence wording**: "no changes" (Tanzil, Corpus) is satisfied because raw files stay verbatim in `data/raw/`; spans/normalization are separate derived data.
