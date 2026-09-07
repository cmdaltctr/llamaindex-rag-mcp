# Experiment 22 Results: Raw-Query Qwen3-Embedding-4B Retrieval Baseline

**ID**: `22-raw-query-qwen4b-baseline-2026-09-07`  
**Date completed**: 2026-09-07  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  
**Status**: COMPLETE — measurement run. No pass/fail gates; task 1.6 derives the frozen regression and latency gates from these numbers.  
**Raw data**: [`output/eval_results.summary.json`](./output/eval_results.summary.json)

---

## Executive summary

This experiment recorded the retrieval baseline for the raw query path under the embedding model this change targets: `qwen/qwen3-embedding-4b` served via OpenRouter (EMBED_PROVIDER=cloud), stored in LanceDB. Two arms ran over the identical FreshStack LangChain corpus and qrels as Experiment 9a (10,024 parent documents, 223 queries): dense-only and hybrid (BM25 + dense with RRF fusion), both without reranking.

**Bottom line**: hybrid leads on every headline quality metric except Recall@1, where dense-only keeps a small edge (12.9% vs 12.1%). On the primary metric, Recall@5, hybrid scores 25.6% against dense-only's 22.7% (+2.9 pp). Hybrid is also quicker at the tail (P95 1,984 ms vs 5,488 ms), though both arms include the OpenRouter network round-trip in every latency figure.

These numbers are the frozen reference for every Stage 5 candidate (query instruction, model-token-aware chunking, OCR routing). They are NOT comparable with Experiment 9a's local `qwen3-embedding:0.6b` cells: different model, embedding width (2560 vs 1024), vector store, and ingestion granularity. The shared qrels anchor corpus identity only.

## Corpus and setup

| Parameter | Value |
| --- | --- |
| Corpus source | FreshStack LangChain, October 2024 (9a re-export, `prepare_freshstack.py`, seed 20260530) |
| Parent documents indexed | 10,024 (10,009 FreshStack + 15 continuity) |
| Chunks stored | 32,631 (omrg production ingestion, default chunking) |
| Query set | 203 FreshStack test queries + 20 continuity queries = 223 total |
| Query categories | 200 identifier-heavy, 3 semantic, 20 continuity |
| Query path | raw (no instruction template) |
| Embedding model | `qwen/qwen3-embedding-4b` via OpenRouter (cloud) |
| Embedding width | 2560 |
| Vector store | LanceDB (one row per chunk, parent-level relevance) |
| Fusion | RRF, k = 60 (production default `hybrid_rrf_k`) |
| Reranking | disabled (`RETRIEVAL__RERANK_ENABLED=false`, packaged default) |
| Fetch depth | top_k = 50 |
| Qrels sha256 | `ccd3bc5732d69a37…` (identical to 9a) |
| Index build time | ~8.4 h (cloud embeddings) |

## Cell metrics

### All queries (n = 223)

| Cell | R@1 | R@3 | R@5 | R@10 | R@50 | Coverage@20 | α-nDCG@10 | Hit@10 | MRR@10 | Mean latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dense-only | **12.9%** | 19.0% | 22.7% | 29.6% | 48.5% | 72.5% | 41.2% | 75.8% | 55.7% | 1,591 ms | 5,488 ms |
| hybrid (BM25 + dense, RRF) | 12.1% | **19.3%** | **25.6%** | **32.7%** | **51.5%** | **75.4%** | **43.5%** | **81.6%** | **57.9%** | **1,023 ms** | **1,984 ms** |

*Cell = retrieval arm tested; R@K = recall at cutoff K, the percentage of each query's ground-truth relevant parent documents found in the top K results; Coverage@20 = mean fraction of a query's nuggets (sub-questions) covered by the top-20 results; α-nDCG@10 = alpha-normalised Discounted Cumulative Gain at 10, which rewards covering multiple relevant nuggets at high ranks (1.0 = perfect ranking); Hit@10 = percentage of queries with at least one relevant document in the top 10; MRR@10 = Mean Reciprocal Rank at 10, the average of 1/rank for the first relevant result (1.0 = always rank 1); Mean/P95 latency = average and 95th-percentile query time, both including the OpenRouter network round-trip; RRF = Reciprocal Rank Fusion, the algorithm that merges dense and BM25 rank lists; BM25 = Best Matching 25, a keyword-frequency retrieval algorithm. Bold marks the better arm per metric.*

### Identifier-heavy queries (n = 200)

| Cell | R@1 | R@3 | R@5 | R@10 | R@50 | Coverage@20 | α-nDCG@10 | Hit@10 | MRR@10 | Mean latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dense-only | 5.8% | 12.7% | 16.7% | 24.4% | 44.6% | 71.3% | 36.9% | 75.5% | 53.4% | 1,679 ms | 6,275 ms |
| hybrid (BM25 + dense, RRF) | **6.5%** | **14.5%** | **20.0%** | **27.9%** | **48.0%** | **74.9%** | **40.6%** | **82.0%** | **56.9%** | **1,025 ms** | **1,900 ms** |

*Metric definitions as in the all-queries table.*

### Semantic queries (n = 3)

| Cell | R@1 | R@3 | R@5 | R@10 | R@50 | Coverage@20 | α-nDCG@10 | Hit@10 | MRR@10 | Mean latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dense-only | 0.0% | 3.9% | 5.9% | 7.8% | 27.1% | 33.3% | 18.6% | 33.3% | 16.7% | 976 ms | 1,151 ms |
| hybrid (BM25 + dense, RRF) | 0.0% | 2.0% | 3.9% | 7.8% | 31.8% | 44.4% | 14.5% | 33.3% | 16.7% | 812 ms | 900 ms |

*Metric definitions as in the all-queries table.*

*Note: only 3 semantic queries — too few for statistical conclusions.*

### Continuity queries (n = 20)

| Cell | R@1 | R@3 | R@5 | R@10 | R@50 | Coverage@20 | α-nDCG@10 | Hit@10 | MRR@10 | Mean latency | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| dense-only | **85.0%** | **85.0%** | 85.0% | 85.0% | 90.0% | **90.0%** | **87.5%** | 85.0% | **85.0%** | **799 ms** | **1,147 ms** |
| hybrid (BM25 + dense, RRF) | 70.0% | 70.0% | 85.0% | 85.0% | 90.0% | 85.0% | 77.0% | 85.0% | 73.5% | 1,039 ms | 1,984 ms |

*Metric definitions as in the all-queries table.*

## Arm comparison (all queries)

| Metric | Dense-only | Hybrid | Δ (hybrid − dense) |
| --- | ---: | ---: | ---: |
| Recall@1 | 12.9% | 12.1% | -0.7 pp |
| Recall@5 | 22.7% | 25.6% | +2.9 pp |
| Recall@10 | 29.6% | 32.7% | +3.2 pp |
| Recall@50 | 48.5% | 51.5% | +3.1 pp |
| Coverage@20 | 72.5% | 75.4% | +3.0 pp |
| α-nDCG@10 | 41.2% | 43.5% | +2.3 pp |
| Hit@10 | 75.8% | 81.6% | +5.8 pp |
| MRR@10 | 55.7% | 57.9% | +2.1 pp |
| Mean latency | 1,591 ms | 1,023 ms | -567 ms |
| P95 latency | 5,488 ms | 1,984 ms | -3,504 ms |

## Representative identifier-heavy queries

### Largest hybrid rescues

| Query | Title | Dense rank | Hybrid rank |
| --- | --- | ---: | ---: |
| `77759618` | TypeError: expected string or buffer - Langchain, OpenAI … | — | 4 |
| `78199269` | ConversationalRetrievalChain raising KeyError | — | 4 |
| `76313568` | TypeError: issubclass() arg 1 must be a class when import… | — | 6 |

### Largest dense-only advantages

| Query | Title | Dense rank | Hybrid rank |
| --- | --- | ---: | ---: |
| `76388280` | How does LangChain help to overcome the limited context s… | 31 | — |
| `77365175` | How to Improve Source Document Relevance in a Langchain C… | 36 | — |

*Rank = position of the first relevant parent in that arm's top-50 results; “—” = no relevant parent retrieved in the top 50. Selected from the 200 identifier-heavy queries by first-relevant-rank difference between arms.*

## Observations

1. Hybrid leads dense-only on every headline quality metric except Recall@1 (12.9% vs 12.1%, -0.7 pp).
2. The hybrid advantage widens with cutoff depth on the recall family: R@5 +2.9 pp, R@10 +3.2 pp, R@50 +3.1 pp.
3. Latency: hybrid mean 1,023 ms vs dense 1,591 ms; P95 1,984 ms vs 5,488 ms. Every query in both arms is embedded through OpenRouter, so both carry the network round-trip.
4. The semantic category holds 3 queries — no statistical conclusions.
5. Continuity queries (n = 20) score near ceiling for both arms (Recall@1 85.0% dense vs 70.0% hybrid), matching the 9a pattern.

## Interpretation

### Why hybrid gains concentrate below the top rank

The corpus is dominated by identifier-heavy queries (200 of 223). For these, BM25 supplies exact-token evidence that dense similarity ranks mid-list, and RRF fusion promotes such parents into the 5–50 window. This reproduces, under the 4B cloud model, the first-stage hybrid advantage 9a measured with the local 0.6B model.

### Why dense-only keeps Recall@1

RRF (k = 60) mixes two rank lists, so a strong dense top-1 parent can be demoted when BM25 ordering disagrees. Dense-only converts 12.9% of queries at rank 1 against hybrid's 12.1% — the known cost of fusion at the very top. The Stage 5 instruction-template candidates may shift this balance.

### Latency is cloud-inclusive

Every timed query embeds through OpenRouter, so the mean and P95 figures bundle network round-trips with local retrieval. The dense arm's P95 tail reflects network variance rather than algorithmic cost; BM25 runs locally. Task 1.6 should treat absolute latency as cloud-inclusive upper bounds and freeze gates on the relative gap.

### Not comparable with Experiment 9a

Model (4B cloud vs 0.6B local), embedding width (2560 vs 1024), vector store (LanceDB vs ChromaDB), and ingestion granularity (32,631 production chunks vs 9a's parent-per-vector helper) all differ. The qrels sha anchors corpus identity only; metric values are this change's standalone baseline.

## Next steps

1. Task 1.6: freeze the regression and latency gates from the `hybrid__raw` (production shape) numbers in this report.
2. Stage 5 candidates — query instruction template, model-token-aware chunking, OCR routing — measure against the frozen gates on this corpus and qrels.
3. Watch Recall@1 under fusion when evaluating instruction templates.

## Reproduction

```bash
# Index build (complete; index preserved outside git)
uv run python build_index.py

# Evaluation cells (checkpoint/resume; isolated cache per arm)
uv run python run_eval.py --cell dense_only__raw
uv run python run_eval.py --cell hybrid__raw

# Aggregates + this report
uv run python summarise_eval.py
```

The preserved index and corpus live outside the repository — see [`DATA_LOCATIONS.md`](./DATA_LOCATIONS.md). Point `STORE_URI` at the preserved index to rerun cells without rebuilding.

## Artefacts

| File | Description |
| --- | --- |
| `protocol.md` | Pre-run plan and measurement intent |
| `plan.json` | Machine-readable plan and preflight assertions |
| `build_index.py` | LanceDB index builder (production ingestion) |
| `run_eval.py` | Per-cell evaluation runner with checkpoint/resume |
| `summarise_eval.py` | Aggregator; regenerates this report |
| `DATA_LOCATIONS.md` | Preserved index and corpus locations |
| `output/eval_results.summary.json` | Machine-readable aggregates and runtime manifest |
| `output/cells/*.json` | Per-query checkpoints (raw retrieved parents) |
| `output/build_done.json` | Index build record |

---

*Raw metrics: `output/eval_results.summary.json`*  
*Per-query checkpoints: `output/cells/*.json`*  
*Preserved index and corpus: [`DATA_LOCATIONS.md`](./DATA_LOCATIONS.md)*