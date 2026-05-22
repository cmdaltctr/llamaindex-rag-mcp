# Experiment: <Descriptive Title>

**ID**: `<dirname>`
**Date**: YYYY-MM-DD
**Operator**: <who ran it — human name (refer to @LICENSE name) with "AI agent (for automation)">
**Status**: PLANNED | PASS | FAIL | INCONCLUSIVE

---

## Hypothesis / Purpose

What question are we answering? One or two sentences.

## Background

Why does this matter? Link to prior experiments, ADRs, or issues that motivated this.

## Variables

| Type                         | Variable                 | Values                       |
| ---------------------------- | ------------------------ | ---------------------------- |
| Independent (what we change) | e.g. embedding model     | nomic, qwen3:0.6b, qwen3:8b |
| Dependent (what we measure)  | e.g. Hit@1, MRR, latency | —                            |
| Controlled (held constant)   | e.g. reranker, chunk size | disabled, 512               |

## Environment & Prerequisites

| Requirement   | Version / Value                        |
| ------------- | -------------------------------------- |
| Python        | 3.12                                   |
| Ollama models | `qwen3-embedding:0.6b`, `qwen3:0.6b`  |
| Hardware      | Apple Silicon Mac, 16 GB               |
| Key config    | CHUNK_SIZE=512, EMBED_BATCH_SIZE=100   |

```bash
# Verify prerequisites
ollama list
uv sync
```

## Corpus

Describe or list the test data. If in a `corpus/` subdirectory, list files and their domains.

| File | Type | Domain | Notes |
| ---- | ---- | ------ | ----- |
|      |      |        |       |

## Method (How to Reproduce)

Step-by-step commands. Someone should be able to copy-paste these and get the same results.

```bash
# Step 1: Ingest (use isolated ChromaDB)
CHROMA_PERSIST_DIR=./chroma_db_test uv run rag-mcp ingest ./corpus

# Step 2: Run evaluation
uv run python run_eval.py

# Step 3: Cleanup
rm -rf ./chroma_db_test
```

## Success Criteria

| Check     | Pass condition   |
| --------- | ---------------- |
|           |                  |

## Results

Link to `results.md` or inline if short. Include the summary table and key findings.

## Conclusion / Decision

What did we learn? What action was taken as a result?
(e.g., "Switched default model to qwen3:0.6b based on 100% Hit@1 with 13× faster embedding.")

## Artefacts

| File                | Description                        |
| ------------------- | ---------------------------------- |
| `protocol.md`       | This file (or the experiment doc)  |
| `run_eval.py`       | Automation script                  |
| `results.md`        | Full results with per-query detail |
| `eval_results.json` | Raw machine-readable data          |
| `corpus/`           | Test documents                     |
| `ground-truth.json` | Pre-written queries and expected answers |
