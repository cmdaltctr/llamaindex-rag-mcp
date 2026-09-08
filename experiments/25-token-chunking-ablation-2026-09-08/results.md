# Experiment 25 Results: Model-Token-Aware Markdown Chunking Ablation

**ID**: `25-token-chunking-ablation-2026-09-08`  
**Date evaluated**: 2026-09-09  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  
**Status**: COMPLETE — frozen-gate verdict: **PASS** (all four gates passed).  
**Raw data**: [`output/eval_results.summary.json`](./output/eval_results.summary.json)

---

## Executive summary

This experiment rebuilt the Experiment 22 corpus index with the merged model-token-aware Markdown chunker (ADR-063: `semantic-text-splitter` + pinned Qwen tokenizer) and evaluated the identical 223 raw queries under the identical hybrid retrieval configuration (BM25 + dense, RRF k=60, rerank disabled, top_k 50, `qwen/qwen3-embedding-4b` via OpenRouter). The baseline arm is Experiment 22's `hybrid__raw` checkpoint, loaded and re-aggregated with the same metric code — cross-checked equal to the published summary before gating.

The candidate index stores 22,281 chunks against the baseline's 32,631 (-31.7%) and its build spent 0.974906 × the baseline's embedded request tokens. Mean Recall@5 over all 223 queries is 23.6% against the baseline's 25.6% (-2.0 pp). Identifier-heavy Recall@10 (n=200) is 27.8% vs 27.9% (-0.1 pp). Candidate query P95 latency is 2,183 ms against the baseline's 1,984 ms.

**Overall verdict: PASS.** All four frozen validity gates passed.

**Recommendation (task 5.5): promote the chunker.** The measured benefit is cost and input-contract correctness, not quality: embedded request tokens −2.5%, largest chunk halved (2,087 → 1,120 payload tokens), retrieval neutral. Two costs travel with the promotion:

1. Mean query latency rose from 1,023 ms to 1,593 ms (fewer, fuller chunks cost more to score; P95 stays inside the frozen cap). If interactive agents find this too slow, the fix is a smaller `CHUNKING__MARKDOWN_CHUNK_SIZE`, not a return to character budgeting.
2. The R@5 point estimate sits 2.0 pp below baseline, inside the ±2.48 pp noise band. One non-inferiority result is evidence of a wash. A second measurement below baseline would be a trend; treat it as one.

## Frozen-gate verdict

Thresholds are read from the frozen [`plan.json`](./plan.json) (task 1.6, frozen 2026-09-08, before any candidate measurement). Comparisons use unrounded values; the table shows them at comparison-transparent precision.

| Gate | Metric | Scope | Value (unrounded) | Threshold | Verdict |
| --- | --- | --- | ---: | ---: | :-: |
| Quality | mean recall_at_5 | all 223 queries | 0.236226 | >= 0.231 | **PASS** |
| Regression | mean recall_at_10 | identifier-heavy queries (n=200) | 0.277500 | >= 0.2583 | **PASS** |
| Cost | total_embedded_tokens ratio (request-text basis) | full index build | 0.974906 | <= 1.15 | **PASS** |
| Latency | query_p95_latency_ms | all 223 candidate queries | 2,183.1 | <= 2850 | **PASS** |

*Cost gate basis: retrospective corrected accounting (`verify_accounting.py`, TDR-022 method, committed in 8902309) — request-text ratio is operative; the pre-adapter EMBED-basis ratio is recorded in the gate basis in the summary JSON. Latency basis: per-query wall time around `pipeline.search` exactly as Experiment 22 measured it (query embedding via OpenRouter included, no warm-up pass); p95 over the 223 candidate queries with the same order statistic.*

## Corpus and setup

| Parameter | Value |
| --- | --- |
| Corpus source | FreshStack LangChain, October 2024 (exp 22 preserved copy) |
| Parent documents indexed | 10,024 (10,009 FreshStack + 15 continuity) |
| Chunks stored (candidate) | 22,281 (model-token Markdown chunker) |
| Chunks stored (baseline) | 32,631 (exp 22 production chunking) |
| Chunker tokenizer | `Qwen/Qwen3-Embedding-4B` @ `5cf2132abc99…` |
| Query set | 203 FreshStack test queries + 20 continuity = 223 total |
| Query categories | 200 identifier-heavy, 3 semantic, 20 continuity |
| Query path | raw (no instruction template) |
| Embedding model | `qwen/qwen3-embedding-4b` via OpenRouter (cloud) |
| Embedding width | 2560 |
| Vector store | LanceDB (one row per chunk, parent-level relevance) |
| Fusion | RRF, k = 60 (production default `hybrid_rrf_k`) |
| Reranking | disabled |
| Fetch depth | top_k = 50 |
| Qrels sha256 | `ccd3bc5732d69a37…` (identical to exp 22) |

## Cell metrics

### All queries (n = 223)

| Cell | R@1 | R@3 | R@5 | R@10 | R@50 | Coverage@20 | α-nDCG@10 | Hit@10 | MRR@10 | Mean latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline (exp 22 hybrid__raw checkpoint) | 12.1% | 19.3% | 25.6% | 32.7% | 51.5% | 75.4% | 43.5% | 81.6% | 57.9% | 1,023 ms | 1,984 ms |
| model-token Markdown chunker (candidate) | 11.3% | 18.9% | 23.6% | 32.2% | 52.2% | 74.1% | 42.7% | 82.1% | 57.1% | 1,593 ms | 2,183 ms |

*Metric definitions as in Experiment 22's results: R@K = recall at cutoff K over deduplicated parent rankings; Coverage@20 = mean fraction of a query's nuggets covered by the top-20 results; α-nDCG@10 = alpha-normalised DCG at 10; Hit@10 = queries with at least one relevant document in the top 10; MRR@10 = mean reciprocal rank at 10; Mean/P95 latency include the OpenRouter network round-trip.*

### Identifier-heavy queries (n = 200)

| Cell | R@1 | R@3 | R@5 | R@10 | R@50 | Coverage@20 | α-nDCG@10 | Hit@10 | MRR@10 | Mean latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline (exp 22 hybrid__raw checkpoint) | 6.5% | 14.5% | 20.0% | 27.9% | 48.0% | 74.9% | 40.6% | 82.0% | 56.9% | 1,025 ms | 1,900 ms |
| model-token Markdown chunker (candidate) | 5.6% | 13.5% | 18.7% | 27.8% | 48.6% | 73.4% | 39.9% | 82.5% | 56.0% | 1,681 ms | 2,183 ms |

*Metric definitions as in the all-queries table.*

### Semantic queries (n = 3)

| Cell | R@1 | R@3 | R@5 | R@10 | R@50 | Coverage@20 | α-nDCG@10 | Hit@10 | MRR@10 | Mean latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline (exp 22 hybrid__raw checkpoint) | 0.0% | 2.0% | 3.9% | 7.8% | 31.8% | 44.4% | 14.5% | 33.3% | 16.7% | 812 ms | 900 ms |
| model-token Markdown chunker (candidate) | 0.0% | 3.9% | 10.6% | 12.5% | 39.3% | 83.3% | 21.8% | 66.7% | 23.3% | 1,320 ms | 2,579 ms |

*Metric definitions as in the all-queries table.*

*Note: only 3 semantic queries — too few for statistical conclusions.*

### Continuity queries (n = 20)

| Cell | R@1 | R@3 | R@5 | R@10 | R@50 | Coverage@20 | α-nDCG@10 | Hit@10 | MRR@10 | Mean latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline (exp 22 hybrid__raw checkpoint) | 70.0% | 70.0% | 85.0% | 85.0% | 90.0% | 85.0% | 77.0% | 85.0% | 73.5% | 1,039 ms | 1,984 ms |
| model-token Markdown chunker (candidate) | 70.0% | 75.0% | 75.0% | 80.0% | 90.0% | 80.0% | 74.7% | 80.0% | 73.1% | 757 ms | 900 ms |

*Metric definitions as in the all-queries table.*

## Monitored, not gated

| Metric | Baseline | Candidate | Δ |
| --- | ---: | ---: | ---: |
| Continuity R@10 (n=20) | 85.0% | 80.0% | -5.0 pp |

*Per the frozen plan, continuity R@10 is recorded and inspected, not gated: at n=20 the bootstrap 95% half-width is ±0.15, so a hard gate would be noise.*

## Arm comparison (all queries)

| Metric | Baseline | Candidate | Δ (candidate − baseline) |
| --- | ---: | ---: | ---: |
| Recall@1 | 12.1% | 11.3% | -0.8 pp |
| Recall@5 | 25.6% | 23.6% | -2.0 pp |
| Recall@10 | 32.7% | 32.2% | -0.5 pp |
| Recall@50 | 51.5% | 52.2% | +0.7 pp |
| Coverage@20 | 75.4% | 74.1% | -1.3 pp |
| α-nDCG@10 | 43.5% | 42.7% | -0.8 pp |
| Hit@10 | 81.6% | 82.1% | +0.4 pp |
| MRR@10 | 57.9% | 57.1% | -0.8 pp |
| Mean latency | 1,023 ms | 1,593 ms | +570 ms |
| P95 latency | 1,984 ms | 2,183 ms | +199 ms |

## Interpretation

1. Chunk count falls from 32,631 to 22,281 (-31.7%) while embedded request tokens fall to 0.9749 × baseline — the token-aware splitter produces fewer, more model-aligned chunks and spends less to index the same corpus.
2. Quality: candidate mean R@5 0.236226 against the frozen floor 0.231 — clears the floor by 0.005226 (paired difference -1.97 pp vs baseline, inside the ±2.48 pp bootstrap noise band the floor encodes).
3. Regression (identifier-heavy R@10): candidate 0.277500 against the frozen floor 0.2583 — clears by 0.019200 (paired difference -0.14 pp). This is the at-risk workload for heading-prefix tokens and identifier splitting.
4. Latency: candidate P95 2,183.1 ms against the 2,850 ms cap — passes with 0.7 s headroom. Both arms bundle the OpenRouter round-trip, so the tail is network-dominated.
5. All four gates pass: per the interpretation rules, the candidate is eligible for task 5.5's promotion judgement, which weighs lift and cost together (fewer chunks, less spend, quality held inside noise).

## Discussion

The gates asked one question: does the new chunker damage retrieval? The answer is no. That was the right safety question, but it was never the reason the chunker exists. ADR-063 chose token units because the embedding model, the API bill, and the context window all count in tokens. Characters are a proxy with a drifting exchange rate. Four characters per token holds for English prose. It collapses on code, JSON, error dumps, and heading paths, which is what this corpus is made of.

The measurement shows that failure mode was real, not theoretical. The baseline splitter produced chunks up to 2,087 tokens. The candidate tops out at 1,120. On token-dense Markdown the character estimate ran at nearly double the intended budget, and every oversize chunk was invisible from the character side.

Retrieval came out a wash for a structural reason. Both paths are heading-aware, so changing the size budget mostly changes which part of the right document surfaces, not whether the document surfaces at all. Sizing accuracy was never likely to move R@5 on this workload.

What sizing accuracy buys is an honest input contract. Spend is measured in the unit the provider bills. Chunks respect the cap the operator configured. This experiment demonstrated the same point from an unplanned direction: the TDR-022 accounting corrections existed because character-era tooling could not measure tokens, and that gap produced two wrong counters before a right one.

## Reproduction

```bash
# Candidate index (already built; build_index.py refuses paid rebuilds,
# see TDR-022)
uv run --no-sync python build_index.py --resume

# Evaluation cell (checkpoint/resume; single candidate arm)
uv run --no-sync python run_eval.py

# Aggregates + gates + this report
uv run --no-sync python summarise_eval.py
```

The baseline arm is Experiment 22's `hybrid__raw` checkpoint, loaded read-only. The preserved indexes live outside the repository (exp 22 `DATA_LOCATIONS.md`).

## Artefacts

| File | Description |
| --- | --- |
| `protocol.md` | Pre-run plan and measurement intent |
| `plan.json` | Frozen machine-readable plan and gates (never edited post-results) |
| `build_index.py` | Candidate index builder (paid rebuilds refused) |
| `run_eval.py` | Candidate evaluation runner with checkpoint/resume |
| `summarise_eval.py` + `report.py` | Aggregator, gate evaluation, this report |
| `token_accounting.py` | Deprecated pre-spend counter (defects documented in protocol) |
| `verify_accounting.py` | Retrospective corrected cost accounting |
| `output/eval_results.summary.json` | Aggregates, gates, runtime manifest |
| `output/cells/model_token_markdown.json` | Candidate per-query checkpoint |
| `output/build_done.json` | Index build record |
| `output/verify_accounting_*.json` | Cost-gate evidence (both sides) |

---

*Raw metrics: `output/eval_results.summary.json`*  
*Per-query checkpoint: `output/cells/model_token_markdown.json`*  
*Baseline checkpoint: `experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/cells/hybrid__raw.json`*