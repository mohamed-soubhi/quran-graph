# Advanced plan ideas (to discuss later)

Ideas raised during the work that are **not yet in the plan**. Each one is discussed with Aya & Mohamed before it
becomes a ticket. Nothing here changes the current phase order.

## 1. Interfaces: MCP server, web interface, LLM chat (raised 2026-10-31, Phase 2)

**Idea:** make the graph easy to use from LLM tools, a browser and a chat.

**Proposed design:** one read-only **query layer** in Python, with three front ends that all use it, so every interface
gives the same answers with the same sources:

```
                              ┌─ MCP server    → Claude Desktop / Claude Code / any MCP client
Neo4j graph ── query layer ───┼─ Web interface → browse ayah → tafsir → evidence
 (read-only)    (Python)      └─ LLM chat (GraphRAG) → questions in Arabic, answers with sources
```

### MCP server — read-only tools
| Tool | Returns |
|---|---|
| `get_ayah("2:255")` | text, words, roots, lemmas |
| `get_tafsir("2:255")` | the whole Ibn Kathir passage + the ayah range it covers |
| `trace_evidence("2:255")` | Quran quotes and hadith in that tafsir, each with its source link and its grade from the source dataset |
| `search("آية الكرسي")` | full-text search on normalized text |
| `hadith_cited_in("muslim:7207")` | every tafsir passage citing that hadith |
| read-only Cypher (maybe) | advanced queries |

### Web interface
An ayah with its tafsir. Quran quotes, hadith and footnotes are highlighted from the spans, and each one links to its source.
It also works as a **review tool** for the Phase 4 spans, instead of reading JSON.

### LLM chat (= plan Phase 7, GraphRAG)
The chat model calls the same MCP tools. Hard rules apply: answers quote only the retrieved subgraph, always show
the path ayah → tafsir → source, and say "not found" instead of guessing.

### Proposed timing (to decide)
- Minimal MCP server (`get_ayah`, `get_tafsir`, `search`) **right after Phase 3**, for early exploration and Phase 4 review.
- Web interface + LLM chat in **Phase 7**, as in the plan (the plan says Streamlit or a Telegram bot).

### Open questions
- The LLM interface is *for* whom or what? (Aya & Mohamed's message was cut off: "a llm interface for …")
- Which chat model answers: local GLM or Claude (plan Phase 7: "local or Claude depending on quality")?
- Who uses the web interface: only the two of you (review), or public users (then hosting, licences and attribution
  of Tanzil, Quranic Corpus and the tafsir edition must be checked)?
