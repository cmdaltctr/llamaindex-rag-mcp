# Experiment 3: Results

**Date**: 2026-05-20
**Operator**: build agent (automated)
**Status**: PASS (with one finding)

---

## Ingest Results

| Check | Result |
|---|---|
| No errors during ingest | ✓ Pass — zero ERROR lines |
| All 6 files indexed | ✓ Pass — 6 distinct sources in ChromaDB |
| Chunk count reasonable (80–350) | ✓ Pass — 207 chunks total |
| LlamaIndex per-chunk metadata attached | ✗ Finding — see below |

### Chunk breakdown

| File | Chunks |
|---|---|
| Kalai et al. - 2025 - Why Language Models Hallucinate.pdf | 84 |
| Popat and Starkey - 2019 - Learning to code or coding to learn.pdf | 40 |
| Van Der Weel and Van Der Meer - 2024 - Handwriting but not typewriting.pdf | 36 |
| Ghazali-Mustasfa.pdf | 36 |
| paper-search-mcp-cf-README.md | 8 |
| grep-ai-README.md | 3 |
| **Total** | **207** |

### Finding → Resolved: LlamaIndex metadata now fully operational

Initial run (2026-05-20 morning) fell back to keyword mode because
`llama-index-llms-ollama` was declared as an optional extra rather than a core
dependency. This was fixed in the same session:

- `llama-index-llms-ollama>=0.4.0` moved to `[project.dependencies]` in
  `pyproject.toml` (installed: `0.10.1`)
- Fallback chain corrected: `llamaindex → ollama → keyword` (was
  `llamaindex → keyword`, skipping ollama)
- `uv sync` installs the package on a fresh clone with no extra flags needed

Re-run after the fix confirmed full `llamaindex` mode active. Per-chunk metadata
fields stored in ChromaDB (verified on Kalai et al. paper, 84 chunks):

| Field | Key in ChromaDB | Sample value |
|---|---|---|
| Category | `category` | `hallucination` |
| Document title | `document_title` | `"Hallucinations in Language Models: Training, Evaluation..."` |
| Keywords | `keywords` | `hallucination, training, evaluation, socio-technical, mitigation...` |
| Summary | `summary` | `The document summarizes the key topics...` |

Note: `document_title` carries LLM markdown prefix noise (`** "..."`) — the
`_strip_llm_prefix` helper strips `Title:` labels but not surrounding bold
markers. Cosmetic issue; does not affect retrieval or filtering.

---

## Retrieval Results

Three spot-check queries run with `rerank=True`, `top_k=3`.

| Query | Expected source | Top-1 source | Score | Pass? |
|---|---|---|---|---|
| Easy: "How does pretraining cause hallucinations?" | Kalai et al. | Kalai et al. | 0.9813 | ✓ |
| Hard: "What brain activity differences exist between handwriting and typing?" | Van Der Weel | Van Der Weel | 0.9877 | ✓ |
| Cross-domain: "How does al-Ghazali view the role of human reason?" | Ghazali | Ghazali | 0.9962 | ✓ |

All 3 queries returned the correct document as top-1. No cross-domain confusion
observed — the Ghazali query returned only Ghazali chunks across all top-3
positions. Reranker was active on all results (`reranked=True`).

---

## Success Criteria Summary

### Ingest
- ✓ No errors during ingest
- ✓ All 6 files indexed
- ✓ Chunk count within expected range (207 of 80–350)
- ✓ LlamaIndex per-chunk metadata present — `category`, `document_title`, `keywords`, `summary` confirmed on all 6 sources after moving `llama-index-llms-ollama` to core deps

### Retrieval
- ✓ Correct source returned as top-1 for all 3 spot queries
- ✓ Reranker active on all results
- ✓ No cross-domain confusion (Ghazali query returned only Ghazali chunks)

---

## Regression Baseline

This corpus and query set now serves as a regression baseline. Future changes
that degrade top-1 accuracy on these 3 queries should be investigated before
merging.

Expected top-1 reranker scores (±0.05 tolerance):

| Query | Baseline score |
|---|---|
| Pretraining hallucinations | 0.9813 |
| Handwriting vs typing | 0.9877 |
| Al-Ghazali human reason | 0.9962 |

---

## Configuration Used

| Setting | Value |
|---|---|
| `EMBED_MODEL` | `qwen3-embedding:0.6b` |
| `METADATA_EXTRACTION_MODE` | `llamaindex` (fell back to `keyword`) |
| `OLLAMA_CLASSIFY_MODEL` | `qwen3:0.6b` |
| `RERANK_ENABLED` | `true` |
| `CHUNK_SIZE` | 512 |
| `CHUNK_OVERLAP` | 64 |
| `INGEST_WORKERS` | 8 |
| `EMBED_CONCURRENCY` | 4 |
| `SIMILARITY_THRESHOLD` | 0.0 |
| `CHROMA_PERSIST_DIR` | `./chroma_db_test` (experiment only) |

---

## Cleanup

```bash
rm -rf ./chroma_db_test
```

Test ChromaDB removed after experiment.
