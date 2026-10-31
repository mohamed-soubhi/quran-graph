# References

Every external link consulted for this project, with what it was used for. Add new entries when a
ticket or decision relies on an outside source. Accessed dates are when the link was last checked.

## Quran text
| Reference | Used for | Accessed |
|---|---|---|
| [Tanzil — download & licence](https://tanzil.net/download/) | Selected Quran text source; licence: verbatim copies only, credit + link to tanzil.net; v1.1 (2021-02-12) | 2026-10-29 |
| [Tanzil download endpoint (Uthmani, txt-2)](https://tanzil.net/pub/download/index.php?quranType=uthmani&outType=txt-2&agree=true) | T1.1 direct download; verified 200, 6236 ayah lines + 28-line `#` copyright block; `quranType=simple-clean` for the clean text | 2026-10-31 |
| [Tanzil — Quran text types](https://tanzil.net/docs/Quran_Text_Types) | Uthmani vs Simple / Simple-Clean variants | 2026-10-29 |
| [Tanzil — text updates](https://tanzil.net/docs/text_updates) | Version history | 2026-10-29 |
| [tanzil-downloader (npm, unofficial)](https://npmjs.com/package/tanzil-downloader) | Lists available types/formats (txt, txt-2, xml, sql); not used | 2026-10-29 |
| [risan/quran-json](https://github.com/risan/quran-json) | Candidate, CC BY-SA 4.0; not selected | 2026-10-29 |
| [fawazahmed0/quran-api](https://github.com/fawazahmed0/quran-api) | Candidate, Unlicense; not selected | 2026-10-29 |

## Tafsir
| Reference | Used for | Accessed |
|---|---|---|
| [spa5k/tafsir_api](https://github.com/spa5k/tafsir_api) | Selected Ibn Kathir source, slug `ar-tafsir-ibn-kathir`; repo MIT | 2026-10-29 |
| [spa5k editions.json](https://github.com/spa5k/tafsir_api/blob/main/tafsir/editions.json) | Edition list; Arabic Ibn Kathir upstream = QUL tafsir 22 | 2026-10-29 |
| [Sample: Ibn Kathir 1:2](https://cdn.jsdelivr.net/gh/spa5k/tafsir_api@main/tafsir/ar-tafsir-ibn-kathir/1/2.json) | Confirmed format `{surah, ayah, text}`, full diacritics, `﴿…﴾` quote markers | 2026-10-29 |
| [Sample: Ibn Kathir 2:255](https://raw.githubusercontent.com/spa5k/tafsir_api/main/tafsir/ar-tafsir-ibn-kathir/2/255.json) | T0.5 fixture (paragraph 0); found `[[…]]` editor footnotes (93) and shadda/vowel order issue | 2026-10-29 |
| [Unicode NFC normalization (UAX #15)](https://unicode.org/reports/tr15/) | Canonical reordering of Arabic marks (shadda vs fatha) before matching | 2026-10-29 |
| [Sample: Ibn Kathir 73:2](https://raw.githubusercontent.com/spa5k/tafsir_api/main/tafsir/ar-tafsir-ibn-kathir/73/2.json) | Found grouped-ayah duplication (73:2 = 73:3) → segment range decision | 2026-10-29 |
| [QUL tafsir 22 (Ibn Kathir, Arabic)](https://qul.tarteel.ai/resources/tafsir/22) | Upstream; JSON/SQLite; "one passage often covers several ayahs" | 2026-10-29 |
| [QUL tafsir 22 — licence](https://qul.tarteel.ai/resources/tafsir/22/licence) | "We don't have copyright information for this resource." | 2026-10-29 |
| [quranlab/quran-tafsir (HF)](https://huggingface.co/datasets/quranlab/quran-tafsir) | Pointed to spa5k as the Arabic Ibn Kathir source | 2026-10-29 |
| [Quranpedia dumps](https://quranpedia.net/dumps?lang=en) | Fallback (book 136); attribution + version required | 2026-10-29 |
| [docs.islamic.app tafsirs API](https://docs.islamic.app/api-reference/tafsirs) | Commercial API; not used | 2026-10-29 |
| [M-AI-C/en-tafsir-ibn-kathir (HF)](https://huggingface.co/datasets/M-AI-C/en-tafsir-ibn-kathir/tree/main) | English abridged; licence unclear; not used | 2026-10-29 |
| [malekverse/quran-dataset](https://github.com/malekverse/quran-dataset) | Seen in search; not evaluated | 2026-10-29 |

## Hadith
| Reference | Used for | Accessed |
|---|---|---|
| [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api) | Selected hadith source; Unlicense; 10 Arabic collections with named grades | 2026-10-29 |
| [hadith-api editions.json](https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions.json) | Edition list (`ara-<collection>`, `ara-<collection>1`) | 2026-10-29 |
| [Sample: ara-bukhari 1](https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/ara-bukhari/1.json) | Confirmed fields: hadithnumber, arabicnumber, text (isnad + matn) | 2026-10-29 |
| [Sample: ara-abudawud 1](https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/ara-abudawud/1.json) | Confirmed `grades[] = {name, grade}` | 2026-10-29 |
| [quranlab/hadith (HF)](https://huggingface.co/datasets/quranlab/hadith) | Best candidate for Musnad Ahmad (ODbL for Ahmad/Darimi matn); Phase 5 | 2026-10-29 |
| [AhmedBaset/hadith-json](https://github.com/AhmedBaset/hadith-json/releases) | 17 collections; no licence file; not selected | 2026-10-29 |
| [Ikhan/sahih-bukhari-english](https://github.com/Ikhan/sahih-bukhari-english) | Bukhari only; not selected | 2026-10-29 |
| [meeAtif/hadith_datasets (HF)](https://huggingface.co/datasets/meeAtif/hadith_datasets/tree/main) | Licence not stated; not selected | 2026-10-29 |
| [ArabicNLPWorld/canonical-islamic-corpus (HF)](https://huggingface.co/datasets/ArabicNLPWorld/canonical-islamic-corpus) | CC BY-SA 4.0, mixed corpus; not selected | 2026-10-29 |
| [sunnah.com llms.txt](https://sunnah.com/llms.txt) | Seen in search; not evaluated | 2026-10-29 |

## Narrators / isnad
| Reference | Used for | Accessed |
|---|---|---|
| [Sanadset 650K (Mendeley)](https://data.mendeley.com/datasets/5xth87zwb5) | Selected for Phase 5; CC BY 4.0 | 2026-10-29 |
| [Sanadset 650K paper (PMC)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9440281/) | Dataset description: 650,986 records, 926 books | 2026-10-29 |
| [MIDS — Sahih Muslim isnad (Mendeley)](https://data.mendeley.com/datasets/gzprcr93zn) | Muslim-only alternative | 2026-10-29 |
| [muhaddithat/isnad-datasets](https://github.com/muhaddithat/isnad-datasets) | Small, no licence; not selected | 2026-10-29 |
| [emadjumaah/hadith-kg (HF)](https://huggingface.co/datasets/emadjumaah/hadith-kg) | Hadith knowledge-graph design reference | 2026-10-29 |
| [emadjumaah/hadith](https://github.com/emadjumaah/hadith) | Related platform; licence NOASSERTION | 2026-10-29 |
| [Hadith narrators 24K (Kaggle mirror)](https://baselight.app/u/kaggle/dataset/fahd09_hadith_narrators) | Scraped from muslimscholars.info; terms unclear | 2026-10-29 |

## Morphology / roots
| Reference | Used for | Accessed |
|---|---|---|
| [Quranic Arabic Corpus — download](https://corpus.quran.com/download/) | Selected; v0.4; GNU licence, verbatim, credit required; email form | 2026-10-29 |
| [Quranic Arabic Corpus — release notes](https://corpus.quran.com/releasenotes.jsp) | Version history, root/lemma consistency | 2026-10-29 |
| [QAMAR paper (AbjadNLP 2026)](https://preview.aclanthology.org/credits/2026.abjadnlp-1.38) | Alternative verified morphology resource; to watch | 2026-10-29 |
| [mustafa0x/quran-morphology](https://github.com/mustafa0x/quran-morphology) | Corpus-derived; no licence; not selected | 2026-10-29 |

## Tools
| Reference | Used for | Accessed |
|---|---|---|
| [Ollama](https://ollama.com) | GLM (`glm-5.3:cloud`, `glm-5.3-flash:cloud`), embeddings (`bge-m3`) | 2026-10-29 |
| [Ollama API docs](https://github.com/ollama/ollama/blob/main/docs/api.md) | `/api/generate`, `/api/chat` (`format` = JSON schema), `/api/embed` | 2026-10-29 |
| [bge-m3 on Ollama](https://ollama.com/library/bge-m3) | Multilingual embedding model, 1024 dims, used for Arabic | 2026-10-29 |
| [Neo4j Graph Data Science](https://neo4j.com/docs/graph-data-science/current/) | GDS plugin for Phase 0 / 6 | 2026-10-29 |
| [Neo4j Docker Hub](https://hub.docker.com/_/neo4j) | Official Neo4j Docker image (`neo4j:5`) configuration and plugin documentation | 2026-10-29 |
| [Neo4j GDS Ninja repository](https://graphdatascience.ninja/versions.json) | Upstream plugin repository used by Neo4j container to install GDS 2.13.14 | 2026-10-29 |
| [Neo4j Python Driver](https://neo4j.com/docs/python-manual/current/) | Python driver API reference for client connectivity and Cypher execution (T0.3) | 2026-10-29 |
