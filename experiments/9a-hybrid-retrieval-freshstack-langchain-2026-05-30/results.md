# Experiment 9a Results: Hybrid Retrieval on FreshStack LangChain

**ID**: `9a-hybrid-retrieval-freshstack-langchain-2026-05-30`  
**Date completed**: 2026-05-31  
**Recommendation**: **KEEP `HYBRID_ENABLED=false` default** — hybrid remains opt-in

---

## Executive summary

This experiment tested whether BM25 + dense hybrid retrieval with RRF fusion
improves retrieval quality on a realistic technical documentation benchmark
(FreshStack LangChain, 10,025 parent documents, 223 queries).

**Bottom line**: Hybrid retrieval genuinely helps at the first-retrieval stage —
Coverage@20 improves by +4.6 percentage points over dense-only when no reranker
is applied. However, the existing reranker (`RERANK_MAX_FETCH=50`) acts as a
bottleneck that collapses both modes to near-identical coverage (~0.54),
eliminating the hybrid advantage entirely. Three primary quality gates failed;
four guardrail and diagnostic gates passed.

The recommendation is to keep `HYBRID_ENABLED=false` as the default and
investigate reranker pool sizing before reconsidering the default flip.

## Corpus and setup

| Parameter | Value |
| --- | --- |
| Corpus source | FreshStack LangChain, October 2024 |
| Corpus subset | qrels-plus-distractors (deterministic sample) |
| Parent documents indexed | 10,025 (exceeds 10,000 minimum) |
| Query set | 203 FreshStack test queries + 20 continuity queries = 223 total |
| Query categories | 200 identifier-heavy, 3 semantic, 40 continuity |
| Embedding model | `qwen3-embedding:0.6b` via Ollama |
| RRF constant | k = 60 |
| Rerank pool | `max_fetch=50`, `multiplier=10` |
| Sparse backend | BM25 (`rank_bm25` library) |
| ChromaDB indexes | Separate persist dirs per mode (no cache bleed) |
| Ingestion method | Experiment-specific direct Chroma helper (`build_indexes.py`) |

The corpus was sampled using the qrels-plus-distractors strategy: all documents
cited in FreshStack qrels, all Experiment 9 continuity documents, and a
deterministic random sample of non-relevant LangChain parents to reach 10,025
total. This avoids the ceiling effect from Experiment 9 (55 chunks) while
remaining feasible on local hardware.

## Cell metrics

All four cells (dense/hybrid × rerank on/off) were evaluated on the same
223 queries against the same corpus.

### All queries (n = 223)

| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dense-only, no rerank | 69.2% | 51.9% | 38.8% | 77.6% | 51.3% | 2,190 ms |
| dense-only, rerank | 53.9% | 35.3% | 26.2% | 60.1% | 34.6% | 52,279 ms |
| **hybrid, no rerank** | **73.8%** | **54.9%** | **42.6%** | **82.5%** | **57.8%** | 2,952 ms |
| hybrid, rerank | 54.0% | 35.4% | 26.2% | 59.6% | 34.6% | 31,804 ms |

*Cell = retrieval configuration tested (dense-only or hybrid BM25 + dense with RRF fusion, with or without cross-encoder reranking); Coverage@20 = percentage of queries where the top-20 retrieved documents collectively cover all relevant nuggets (sub-questions) for that query — measures whether the retriever finds enough relevant material across the 10,025-document corpus; Recall@50 = fraction of all ground-truth relevant documents found within the top-50 results; α-nDCG@10 = alpha-normalized Discounted Cumulative Gain at 10, a ranking-quality metric that rewards covering multiple relevant nuggets at high ranks (1.0 = perfect ranking, all nuggets covered at the top); Hit@10 = percentage of queries where at least one relevant document appears in the top-10 results; MRR@10 = Mean Reciprocal Rank at 10, the average of 1/rank for the first correct result (1.0 = always rank 1); P95 latency = 95th-percentile response time in milliseconds (95% of queries complete faster than this); RRF = Reciprocal Rank Fusion, the algorithm that merges dense and sparse rank lists (k = 60); BM25 = Best Matching 25, a classic keyword-frequency retrieval algorithm.*

### Identifier-heavy queries (n = 200)

| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dense-only, no rerank | 67.7% | 48.6% | 34.3% | 77.5% | 48.2% | 2,392 ms |
| dense-only, rerank | 50.4% | 29.6% | 20.5% | 58.0% | 29.8% | 34,574 ms |
| **hybrid, no rerank** | **72.1%** | **51.3%** | **38.6%** | **82.5%** | **55.7%** | 3,100 ms |
| hybrid, rerank | 50.2% | 29.7% | 20.4% | 57.0% | 29.7% | 32,072 ms |

*Cell = retrieval configuration tested; Coverage@20 = percentage of queries where top-20 results cover all relevant nuggets; Recall@50 = fraction of ground-truth relevant documents found in top-50; α-nDCG@10 = alpha-normalized Discounted Cumulative Gain at 10 (1.0 = perfect ranking across all nuggets); Hit@10 = percentage of queries with at least one relevant document in top-10; MRR@10 = Mean Reciprocal Rank at 10 (1.0 = always rank 1); P95 latency = 95th-percentile response time in milliseconds.*

### Semantic queries (n = 3)

| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dense-only, no rerank | 33.3% | 21.6% | 26.5% | 33.3% | 33.3% | 302 ms |
| dense-only, rerank | 50.0% | 17.4% | 13.8% | 33.3% | 16.7% | 63,395 ms |
| hybrid, no rerank | 44.4% | 27.1% | 20.0% | 33.3% | 16.7% | 513 ms |
| hybrid, rerank | 66.7% | 22.1% | 21.2% | 66.7% | 27.8% | 15,259 ms |

*Cell = retrieval configuration tested; Coverage@20 = percentage of queries where top-20 results cover all relevant nuggets; Recall@50 = fraction of ground-truth relevant documents found in top-50; α-nDCG@10 = alpha-normalized Discounted Cumulative Gain at 10 (1.0 = perfect ranking across all nuggets); Hit@10 = percentage of queries with at least one relevant document in top-10; MRR@10 = Mean Reciprocal Rank at 10 (1.0 = always rank 1); P95 latency = 95th-percentile response time in milliseconds.*

*Note: only 3 semantic queries — too few for statistical conclusions.*

### Continuity queries (n = 40)

| Cell | Coverage@20 | Recall@50 | α-nDCG@10 | Hit@10 | MRR@10 | P95 latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dense-only, no rerank | 90.0% | 90.0% | 85.0% | 85.0% | 85.0% | 171 ms |
| dense-only, rerank | 90.0% | 95.0% | 85.0% | 85.0% | 85.0% | 107,831 ms |
| hybrid, no rerank | 95.0% | 95.0% | 86.3% | 90.0% | 85.0% | 383 ms |
| hybrid, rerank | 90.0% | 95.0% | 85.0% | 85.0% | 85.0% | 19,975 ms |

*Cell = retrieval configuration tested; Coverage@20 = percentage of queries where top-20 results cover all relevant nuggets; Recall@50 = fraction of ground-truth relevant documents found in top-50; α-nDCG@10 = alpha-normalized Discounted Cumulative Gain at 10 (1.0 = perfect ranking across all nuggets); Hit@10 = percentage of queries with at least one relevant document in top-10; MRR@10 = Mean Reciprocal Rank at 10 (1.0 = always rank 1); P95 latency = 95th-percentile response time in milliseconds.*

## Pass gate analysis

### Corpus validity — ✅ PASS

10,025 parent documents indexed, exceeding the 10,000 minimum. The corpus
saturation problem from Experiment 9 is resolved.

### Production coverage lift (rerank cells) — ❌ FAIL

Hybrid+rerank Coverage@20 = 0.540 vs dense+rerank = 0.539. Lift = +0.001,
far below the required +0.05 threshold. The reranker erases hybrid's
first-stage advantage.

### Production recall lift (rerank cells) — ❌ FAIL

Hybrid+rerank Recall@50 = 0.354 vs dense+rerank = 0.353. Lift = +0.002,
far below the required +0.05 threshold.

### Identifier-heavy coverage lift (rerank cells) — ❌ FAIL

Hybrid+rerank Coverage@20 = 0.502 vs dense+rerank = 0.504. Lift = −0.002 —
hybrid actually performs marginally *worse* on identifier-heavy queries after
reranking, the exact opposite of the +0.08 threshold.

### Semantic guardrail — ✅ PASS

Non-identifier Coverage@20 regression = +0.167 (hybrid is better, not worse).
Well within the −0.02 guardrail.

### Latency P95 ratio — ✅ PASS

Hybrid+rerank P95 = 31,804 ms vs dense+rerank P95 = 52,279 ms.
Ratio = 0.61×, well under the 1.5× limit. Hybrid is actually *faster* because
BM25 candidates may be easier for the reranker to process.

### BM25 contribution — ✅ PASS

All 10 improved identifier-heavy queries had sparse_rank < dense_rank or no
dense rank at all, confirming BM25 is contributing genuine evidence, not noise.
Ratio = 10/10 = 100%, far exceeding the 25% threshold.

Notable examples where BM25 rescued documents that dense retrieval missed:

| Query | Document | Dense rank | Sparse rank | Fused rank |
| --- | --- | ---: | ---: | ---: |
| 77744941 | `cql_agent.ipynb` | 21 | 1 | **1** |
| 77797163 | `weaviate.ipynb` | — | 1 | 15 |
| 77683730 | `deprecation.py` | 96 | 2 | 9 |
| 77365175 | `conversational_retrieval_chain.ts` | 17 | 1 | 2 |
| 76199653 | `self-query-qdrant/README.md` | — | 63 | 143 |

*Query = FreshStack query identifier; Document = source file from the LangChain corpus where the relevant content lives; Dense rank = position of that document in the dense-only retrieval results ("—" means dense retrieval did not find it at all); Sparse rank = position in the BM25-only results; Fused rank = final position after RRF (Reciprocal Rank Fusion) merges both rank lists — lower is better.*

### Continuity non-regression — ✅ PASS

Dense Coverage@20 = 0.900, hybrid Coverage@20 = 0.900 on continuity queries.
No regression from Experiment 9 named cases.

## Interpretation

### Why hybrid helps at first retrieval but not after reranking

The critical finding is the gap between rerank-off and rerank-on cells:

- **Without reranker**: hybrid Coverage@20 = 0.738 vs dense = 0.692 (+4.6 pp)
- **With reranker**: hybrid Coverage@20 = 0.540 vs dense = 0.539 (+0.1 pp)

This pattern is consistent with a **reranker bottleneck**. The reranker sees
only `RERANK_MAX_FETCH=50` candidates. On a 10,025-document corpus, the dense
retriever's top-50 candidates are already well-optimised by embedding similarity.
BM25 + RRF fusion promotes different candidates (especially for exact-token
queries), but many of these BM25-promoted documents fall outside the top-50
reranker window. The reranker therefore discards hybrid's gains and returns
nearly identical results to dense-only.

The BM25 contribution gate confirms this: BM25 is genuinely finding documents
that dense misses (sparse rank 1–2 for several queries), but these documents
cannot survive the reranker's 50-candidate pool.

### Why the reranker hurts overall quality

The reranker actively degrades quality for both retrieval modes:

| Configuration | Coverage@20 | What happened |
| --- | ---: | --- |
| Hybrid, NO rerank | 73.8% | ✅ Hybrid found good docs |
| Hybrid, WITH rerank | 54.0% | ❌ Reranker killed 19.8pp of them |
| Dense, NO rerank | 69.2% | ✅ Dense found decent docs |
| Dense, WITH rerank | 53.9% | ❌ Reranker killed 15.3pp of them |

*Configuration = retrieval mode (hybrid or dense-only) with reranker on or off; Coverage@20 = percentage of queries where top-20 results cover all relevant nuggets across the 10,025-document corpus; pp = percentage points (difference between two percentage values).*

Both dense+rerank and hybrid+rerank score *worse* than their no-rerank
counterparts on Coverage@20 and Recall@50. This is expected behaviour for a
reranker with a small candidate pool on a large corpus — the reranker's
cross-encoder scoring is more precise but sees too few candidates to improve
over first-stage retrieval. Experiment 9 did not observe this because its
55-document corpus was smaller than the reranker pool.

### Implications for the default-flip decision

The experiment design required all gates to pass for a default-flip
recommendation. Three primary quality gates failed decisively (lift near zero,
not merely marginal). The correct recommendation is to keep hybrid opt-in.

However, the no-rerank results demonstrate that hybrid retrieval has genuine
value — the problem is the reranker interaction, not hybrid retrieval itself.
A follow-up experiment with a larger reranker pool could change the conclusion.

## Next steps

1. **Reranker pool sizing experiment**: Test `RERANK_MAX_FETCH` at 100, 200,
   and 500 to determine the pool size at which hybrid's first-stage advantage
   survives into the final result set.
2. **Two-stage reranker cascade**: Consider a fast coarse reranker (e.g.,
   cross-encoder on 200 candidates) followed by the precise reranker on a
   smaller pool.
3. **Cost-benefit analysis**: If larger reranker pools are computationally
   expensive, evaluate whether the quality lift justifies the latency cost.

---

*Raw metrics: `output/eval_results.summary.json`*  
*Per-query data: `output/eval_results.json` (gitignored, ~21 MB)*
