# Experiment: Reranker Threshold Calibration

**ID**: `reranker-threshold-calibration-2026-05-12`
**Date**: 2026-05-12
**Operator**: Dr Muhammad Aizat Bin Md Hawari
**Status**: PASS

---

## Hypothesis / Purpose

Does the cross-encoder reranker improve retrieval accuracy over vector-only search, and
how should the similarity threshold be scaled when reranking is active (given that
reranker sigmoid scores are much lower than cosine similarity scores)?

## Background

The RAG pipeline supports an optional cross-encoder reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`,
ONNX Runtime). Before this experiment, it was unclear whether the reranker provided
meaningful quality improvements over plain vector cosine similarity, and the interaction
between reranker scores and the `similarity_threshold` parameter was untested.

## Variables

| Type                         | Variable                          | Values                                                    |
| ---------------------------- | --------------------------------- | --------------------------------------------------------- |
| Independent (what we change) | Pipeline configuration            | Vector only, Vector + Reranker, Vector + Threshold, Full Pipeline |
| Dependent (what we measure)  | Source accuracy, Answer accuracy, Avg score, Avg latency | —                                    |
| Controlled (held constant)   | Embedding model                   | `nomic-embed-text` (768-dim)                              |
| Controlled (held constant)   | Corpus                            | 5 fixture documents (European capitals TXT/MD, programming languages TXT) |
| Controlled (held constant)   | Chunk size                        | Default                                                   |
| Controlled (held constant)   | Similarity threshold (raw)        | 0.3 (where applicable)                                    |

## Environment & Prerequisites

| Requirement   | Version / Value                                              |
| ------------- | ------------------------------------------------------------ |
| Python        | 3.12                                                         |
| OS            | macOS ARM64                                                  |
| Ollama models | `nomic-embed-text`                                           |
| Reranker      | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX, ~23 MB)      |
| Key config    | Default chunk size, similarity_threshold=0.3 where applicable |

```bash
# Verify prerequisites
ollama list   # nomic-embed-text must be present
uv sync
```

## Corpus

5 documents from `tests/fixtures/`:

| File          | Type | Domain                | Notes                          |
| ------------- | ---- | --------------------- | ------------------------------ |
| `sample.txt`  | TXT  | Geography (capitals)  | France, Germany                |
| `sample.md`   | MD   | Geography (capitals)  | Italy (mentions Colosseum)     |
| `python.txt`  | TXT  | Programming languages | Python description             |
| (+ 2 others)  | TXT  | Mixed                 | Additional fixture documents   |

5 chunks total from these documents.

## Method (How to Reproduce)

```bash
# From project root
cd experiments/reranker-threshold-calibration-2026-05-12

# Run the experiment (requires Ollama running with nomic-embed-text)
uv run python run_experiments.py
```

The script:
1. Ingests the 5 fixture documents into a temporary ChromaDB
2. Runs 8 structured queries (4 geography, 4 programming) under 4 configurations:
   - **Vector only** — cosine similarity, no reranking, no threshold
   - **Vector + Reranker** — cosine similarity → cross-encoder re-score
   - **Vector + Threshold** — cosine similarity, filter at 0.3
   - **Full Pipeline** — cosine similarity → rerank → threshold at 0.3
3. Measures source accuracy (top-1 from correct document?) and answer accuracy (top-1 contains expected substring?)
4. Saves raw results to `experiment_results.json`

## Success Criteria

| Check                                | Pass condition                                                |
| ------------------------------------ | ------------------------------------------------------------- |
| Reranker improves accuracy           | Vector + Reranker scores higher than Vector only              |
| Full Pipeline matches Reranker alone | After threshold fix, Full Pipeline = 100% accuracy            |
| Threshold scaling factor identified  | A concrete ÷N factor is determined from score distributions   |

## Artefacts

| File                      | Description                                              |
| ------------------------- | -------------------------------------------------------- |
| `protocol.md`             | This file — hypothesis, method, reproduction steps       |
| `results.md`              | Findings, score tables, key insights, recommendations    |
| `run_experiments.py`      | Automation script (8 queries × 4 configurations)         |
| `experiment_results.json` | Raw per-query results (scores, sources, latency)         |
