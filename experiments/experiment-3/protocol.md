# Experiment 3: End-to-End Smoke Test with Real-World Documents

**Date**: 2026-05-20
**Purpose**: Validate the full ingest → retrieval pipeline with a diverse real-world corpus
(PDFs + Markdown) under the current production configuration, following the
`enhance-metadata-extraction` ADR (2026-05-20).
**Metric**: Does the pipeline ingest without errors? Does retrieval return the correct
document for each ground-truth query?

---

## Background

Experiments 1 and 2 used either synthetic fixtures or focused on a single variable
(reranker calibration, embedding model comparison). This experiment is a **smoke test**
against the current production configuration using 6 real-world documents spanning
academic papers (PDF) and technical READMEs (Markdown).

The goals are:

1. Confirm the ingest pipeline handles mixed file types (PDF + MD) without errors.
2. Verify that `llamaindex` metadata extraction mode attaches per-chunk enrichment
   (`title`, `keywords`, `summary`) correctly — the key output of the
   `enhance-metadata-extraction` ADR.
3. Confirm retrieval returns the correct document for pre-written ground-truth queries
   with the reranker enabled.
4. Establish a **regression baseline** for this corpus — if future changes break
   retrieval quality, we have a reference point.

---

## Current Configuration (from `.env`)

| Setting                    | Value                                    | Note                                      |
| -------------------------- | ---------------------------------------- | ----------------------------------------- |
| `EMBED_MODEL`              | `qwen3-embedding:0.6b`                   | 1024-dim; winner from experiment-2        |
| `METADATA_EXTRACTION_MODE` | `llamaindex`                             | Per-chunk: title + keywords + summary     |
| `OLLAMA_CLASSIFY_MODEL`    | `qwen3:0.6b`                             | LLM used by LlamaIndex extractors         |
| `RERANK_ENABLED`           | `true`                                   | Cross-encoder reranker active             |
| `CHUNK_SIZE`               | 512                                      |                                           |
| `CHUNK_OVERLAP`            | 64                                       |                                           |
| `INGEST_WORKERS`           | 8                                        | Higher than default (4)                   |
| `EMBED_CONCURRENCY`        | 4                                        | Higher than default (2)                   |
| `SIMILARITY_THRESHOLD`     | 0.0                                      | No filtering; reranker handles precision  |
| `CHROMA_PERSIST_DIR`       | `./chroma_db_test`                       | **Experiment override** — not production  |
| `COLLECTION_NAME`          | `documents`                              | Default                                   |

> **Why `llamaindex` mode gives richer metadata**: Unlike `keyword` mode (regex → `category`
> only) or `ollama` mode (`category` + `keywords` + `summary` per file), `llamaindex` mode
> runs LlamaIndex's `IngestionPipeline` with `TitleExtractor`, `KeywordExtractor`, and
> `SummaryExtractor` **per chunk**. Every chunk in ChromaDB will carry `document_title`,
> `excerpt_keywords`, and `section_summary` fields alongside the standard `file_name` and
> `file_type`. This makes filtered retrieval (e.g. `search by category`) more precise.

---

## Corpus

6 documents in `experiments/experiment-3/corpus/`:

| File                                                                                        | Type     | Domain             | Queries |
| ------------------------------------------------------------------------------------------- | -------- | ------------------ | ------- |
| `Kalai et al. - 2025 - Why Language Models Hallucinate.pdf`                                 | PDF      | AI/ML              | 2       |
| `Popat and Starkey - 2019 - Learning to code or coding to learn A systematic review.pdf`    | PDF      | Education          | 3       |
| `Van Der Weel and Van Der Meer - 2024 - Handwriting but not typewriting...pdf`              | PDF      | Neuroscience       | 3       |
| `paper-search-mcp-cf-README.md`                                                             | Markdown | Software/MCP       | 2       |
| `grep-ai-README.md`                                                                         | Markdown | Software/AI        | 2       |
| `Ghazali-Mustasfa.pdf`                                                                      | PDF      | Islamic philosophy | 3       |

The corpus is intentionally diverse — different domains, file types, and lengths — to
stress-test the pipeline's generality. The Ghazali and hallucination papers are
thematically distant from the software READMEs, which tests cross-domain non-confusion.

---

## Ground-Truth Queries

Pre-written in `questions.md` — 15 queries with expected answers across all 6 documents.
Queries were written before running the experiment to avoid confirmation bias.

---

## Step 1: Check Prerequisites

```bash
# Verify Ollama is running and both models are available
ollama list
# Expected: qwen3-embedding:0.6b and qwen3:0.6b both present

# Confirm EMBED_MODEL is set
grep EMBED_MODEL .env
```

---

## Step 2: Run Ingest into Test ChromaDB

```bash
# From project root — override CHROMA_PERSIST_DIR to avoid touching production
CHROMA_PERSIST_DIR=./chroma_db_test uv run rag-mcp ingest \
  experiments/experiment-3/corpus
```

Expected output:
- Progress bar showing 6 files processed
- No `ERROR` lines
- Chunk count logged at completion (expect 80–350 chunks; PDFs chunk heavily)
- `llamaindex` extractor log lines showing per-chunk enrichment

---

## Step 3: Verify Ingest via List Command

```bash
CHROMA_PERSIST_DIR=./chroma_db_test uv run rag-mcp list
```

Expected: All 6 source files appear with chunk counts.

---

## Step 4: Spot-Check Retrieval

Three representative queries — easy, hard, and cross-domain. Pass `--rerank`
explicitly because the CLI does not currently auto-honour `RERANK_ENABLED=true`
from `.env` (only the MCP server path does).

```bash
# Easy — keyword overlap with document
CHROMA_PERSIST_DIR=./chroma_db_test uv run rag-mcp search --rerank \
  "How does pretraining cause hallucinations?"

# Hard — paraphrased, no exact keywords
CHROMA_PERSIST_DIR=./chroma_db_test uv run rag-mcp search --rerank \
  "What brain activity differences exist between handwriting and typing?"

# Cross-domain — should not confuse documents
CHROMA_PERSIST_DIR=./chroma_db_test uv run rag-mcp search --rerank \
  "How does al-Ghazali view the role of human reason?"
```

---

## Success Criteria

### Ingest

| Check                        | Pass Condition                                                        |
| ---------------------------- | --------------------------------------------------------------------- |
| No errors during ingest      | Zero `ERROR` lines in output                                          |
| All 6 files indexed          | `list` command shows 6 distinct sources                               |
| Chunk count reasonable       | 80–350 total chunks                                                   |
| LlamaIndex metadata attached | Each chunk carries `document_title`, `keywords`, `summary` (lists flattened to comma-separated strings — ChromaDB requires scalar metadata) |

### Retrieval

| Check                        | Pass Condition                                                        |
| ---------------------------- | --------------------------------------------------------------------- |
| Correct source returned      | Top-1 result comes from the expected document for all 3 spot queries  |
| Reranker active              | Response includes reranker scores (not raw cosine only)               |
| No cross-domain confusion    | Ghazali query returns Ghazali chunks, not ML paper chunks             |

---

## Cleanup

```bash
# Safe to delete after experiment — this is not the production ChromaDB
rm -rf ./chroma_db_test
```

---

## Notes

- `chroma_db_test` is isolated from the production `chroma_db` — safe to delete freely.
- If ingest fails on a PDF, run `uv sync` to ensure `pypdf` is installed.
- If `qwen3:0.6b` is not available, the `llamaindex` extractor will fall back to
  `keyword` mode gracefully (per the ADR spec). Pull it with `ollama pull qwen3:0.6b`.
- For quantitative Hit@K / MRR metrics, adapt experiment-2's `run_eval.py` pattern.
- `RERANK_ENABLED=true` means the `÷30` threshold scaling is active (see experiment-1
  findings). With `SIMILARITY_THRESHOLD=0.0` this has no practical effect here.
