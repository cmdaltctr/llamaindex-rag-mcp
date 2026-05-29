# Experiment 8a Results: Query Embedding Cache Full-Size Evaluation

**ID**: `8a-query-embedding-cache-fullsize-2026-05-29`  
**Date run**: 2026-05-29  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent support  
**Status**: **PASS**  
**Raw data**: external artifact; see [`artifacts.md`](./artifacts.md). Summary data is tracked in [`eval_results.summary.json`](./eval_results.summary.json).

---

## Hypothesis

The query embedding cache should make repeated searches much faster.

In plain terms: before the system can search ChromaDB, it must turn the user
query into an embedding vector. That embedding call goes through Ollama and is
relatively expensive. If the exact same query is asked again in the same
process, we should reuse the previous embedding instead of asking Ollama again.

Experiment 8 already showed this worked, but it had two weaknesses:

1. the traces were small;
2. the cache-off cells did not truly disable the cache.

Experiment 8a fixes both problems.

---

## Variables

| Type | Variable | Values |
| --- | --- | --- |
| Independent | Cache | off, on |
| Independent | Trace | warm, cold, agent-loop |
| Independent | Reranker | off for cache isolation, on for production-shaped check |
| Dependent | Mean latency | Average search time per call |
| Dependent | P95 latency | Slow-tail search time |
| Dependent | Embed calls | Actual calls to `Settings.embed_model.get_query_embedding` |
| Dependent | Cache hit rate | Fraction of calls that avoided a new embedding |
| Controlled | Corpus | 4 PDFs + 2 Markdown README files copied from Exp 3 |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |
| Controlled | `top_k` | 5 |

---

## Method

The experiment used a copied local corpus. No symlinks were used.

Command used:

```bash
cd experiments/8a-query-embedding-cache-fullsize-2026-05-29
uv run python run_eval.py --corpus ./corpus --regenerate-traces
```

The runner generated three deterministic workload traces:

| Trace | Calls | Shape | Why it matters |
| --- | ---: | --- | --- |
| warm | 250 | 50 distinct queries × 5 repeats | Standard repeated-query benchmark |
| cold | 200 | 200 unique queries | Negative control: cache should not help or hurt |
| agent-loop | 250 | 25 distinct queries × 10 repeats | Simulates an agent repeatedly verifying similar retrieval steps |

Cache-off was implemented by monkey-patching `rag_mcp.retrieval._embed_query`
to call `Settings.embed_model.get_query_embedding()` directly. This means the
cache-off cells genuinely bypassed the production LRU cache.

---

## Results

### Main pass criteria

| Criterion | Result | Pass? |
| --- | ---: | :--: |
| Warm trace speedup ≥ 30% | **76.16%** | ✅ |
| Agent-loop speedup ≥ 50% | **86.71%** | ✅ |
| Cold trace overhead within ±5% | **-2.78%** | ✅ |
| Warm cache-on embed calls = 50 | **50** | ✅ |
| Cold cache-on embed calls = 200 | **200** | ✅ |
| Agent-loop cache-on embed calls = 25 | **25** | ✅ |
| Both branches hit cache | filtered/unfiltered ≥ 80% | ✅ |

Simple reading:

- Repeated queries become much faster.
- Unique queries do not pay a meaningful penalty.
- The cache works on both filtered and unfiltered search paths.

### Cell summary

| Trace | Cache | Rerank | Mean latency | P95 latency | Embed calls | Hit rate |
| --- | :--: | :--: | -----------: | ----------: | ----------: | -------: |
| warm | off | off | 75.49 ms | 87.50 ms | 250 | 0% |
| warm | on | off | **18.00 ms** | 79.59 ms | **50** | 80% |
| cold | off | off | 82.95 ms | 93.07 ms | 200 | 0% |
| cold | on | off | 80.64 ms | 87.96 ms | 200 | 0% |
| agent-loop | off | off | 80.35 ms | 86.86 ms | 250 | 0% |
| agent-loop | on | off | **10.68 ms** | 79.89 ms | **25** | 90% |
| warm | off | on | 1318.24 ms | 1367.78 ms | 250 | 0% |
| warm | on | on | **1214.01 ms** | 1308.74 ms | **50** | 80% |

### Why P95 does not drop as much as the mean

The first time each distinct query appears, the cache misses and Ollama still
has to create an embedding. Those first misses dominate P95 latency.

The mean drops sharply because most repeated calls become cheap cache hits.

So the cache mostly improves the average case for repeated-query workflows,
while the slow tail still includes first-time queries.

### Why rerank-on speedup is smaller

With reranking enabled, the cross-encoder reranker dominates total latency.

The cache still removes embedding work, but embedding is only a small part of a
rerank-on query. That is why the production-shaped warm trace improved by
**7.91%**, not by 70%+.

This is still useful: a free 8% improvement in production-shaped repeated
queries, while keeping much larger gains for rerank-off or lightweight search
paths.

---

## Conclusion

### Decision

The query embedding cache is validated.

Keep the ADR-016 implementation:

```text
process-local lru_cache(maxsize=128)
keyed by (query, embed_model_name)
shared by filtered and unfiltered retrieval branches
```

### Practical meaning

- If an agent repeats the same search question, we avoid repeated Ollama
  embedding calls.
- Agent-loop style workloads benefit the most: **86.71% mean latency reduction**.
- Cold one-off queries do not suffer: measured overhead was within noise.
- Both filtered and unfiltered retrieval branches share the same cache.
- The LRU bound works: the cold 200-query trace filled the cache to its max size
  of 128 rather than growing unbounded.

### What changed in the codebase?

No production code changed. This experiment confirms the existing ADR-016 cache
implementation under a larger and more faithful workload.

---

## Cleanup

This experiment uses a temporary ChromaDB directory created under the system
temp directory and deletes it at the end of the run. The generated workload
files can be kept for reproducibility or removed manually:

```bash
rm -f workload-warm.txt workload-cold.txt workload-agent-loop.txt
```
