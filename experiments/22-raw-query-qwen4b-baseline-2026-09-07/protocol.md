# Experiment 22 — Raw-query Qwen3-Embedding-4B retrieval baseline

- **Status:** PLANNED
- **Date:** 2026-09-07
- **Operator:** Dr Muhammad Aizat Bin Md Hawari with AI agent
- **OpenSpec stage:** Stage 1 baseline. No gates are evaluated here; task 1.6
  derives the frozen gates FROM these numbers.

## Purpose

Record the retrieval baseline for the raw query path under the embedding
model this change targets: `qwen/qwen3-embedding-4b` served via OpenRouter
(EMBED_PROVIDER=cloud). Every Stage 5 candidate (query instruction, chunker,
OCR routing) compares against the numbers recorded here.

This is a **measurement** run, not a pass/fail experiment. The deliverable is
the metric table plus the runtime manifest.

## Why cloud inference

Local Qwen3-Embedding-4B is impractical on this machine (32 GB M1 Pro; 9a
needed 5.4 h for the same corpus on the 0.6b local model). The OpenSpec
proposal (§4) and design D4.4 explicitly allow OpenRouter for inference while
token counting stays local via HF `tokenizers`.

Known consequence, accepted before the run: cloud inference cannot pin a
model digest the way TDR-016 pinned the local Ollama digest. The manifest
records model slug, provider, and measurement date instead. Local
`qwen3-embedding:0.6b` numbers (9a) are NOT comparable: different model,
different dims (1024 vs 2560).

## Variables

- **Manipulated:** none. Single configuration, two retrieval arms.
- **Cells:**
  1. `dense_only__raw` — dense branch only, raw query, rerank off.
  2. `hybrid__raw` — dense + BM25 + RRF (production shape), raw query,
     rerank off (packaged default `RETRIEVAL__RERANK_ENABLED=false`).
- **Controlled:** corpus and qrels identical to 9a (same seed 20260530,
  same selection) so the baseline is anchored to established ground truth;
  top_k=50 fetch; k values 1/3/5/10/20/50; OpenRouter model slug fixed.

## Corpus and ground truth

FreshStack `langchain` slice re-exported by the SAME `prepare_freshstack.py`
as 9a (symlinked), seed 20260530: ~10,025 parent docs, 223 queries with
nugget-level qrels and category labels (identifier-heavy / semantic /
continuity). Ground truth written BEFORE any measurement (re-export is
deterministic; identical to the committed 9a qrels modulo re-export).

## Metrics

Per cell, overall and per category:

- Evidence Recall@1 / @3 / @5 (task 1.5 requirement), plus recall@10/@20/@50.
- Nugget coverage@20 and alpha-nDCG@10 (9a vocabulary, for continuity).
- MRR@10, hit@5, hit@10.
- Latency mean and p95 (includes network round-trip to OpenRouter; recorded
  as such in the manifest).

## Procedure

1. Re-export corpus + qrels (`prepare_freshstack.py`, defaults, seed 20260530).
2. Build LanceDB index (ADR-049 policy: LanceDB is the default backend;
   vector store is not a manipulated factor) at
   `output/lancedb/` — one vector per parent doc, OpenRouter embeddings,
   batched with retry + atomic checkpoint (`.tmp` → rename).
3. Run eval with checkpoint/resume; clear the query-embedding cache between
   arms; record per-query ranks.
4. Summarise to `output/eval_results.summary.json` + `results.md`.
5. Record runtime manifest: model slug, provider, dims, corpus manifest
   hash, index identity, date, latency caveat.

## Cost

Corpus ≈ 10k docs; at $0.02/M tokens the full index build plus 2 × 223
query embeddings is estimated well under $1.

## Cleanup

Index stays under `output/` (gitignored). Raw JSON and Markdown summaries
are committed. No production store is touched.
