# Experiment 8: Query Embedding Cache Hit-Rate and Latency

**ID**: `query-embedding-cache-2026-05-27`
**Date**: 2026-05-27
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent (for automation)
**Status**: PLANNED
**Related OpenSpec change**: `rag-retrieval-quality-improvements` (Tier 2)

---

## What this experiment is for

The Tier 2 OpenSpec change adds an in-process LRU cache around the query
embedding step. The intent is to short-circuit the Ollama call when the
same query is asked again in the same process — a pattern that shows up
constantly in agentic workloads where an agent re-asks similar sub-questions
or runs identical retrieval as a verification step.

This experiment confirms two things:

1. **The cache works on the unfiltered path too.** The naive risk is that an
   `lru_cache` decorator only catches the metadata-filtered branch and
   silently misses the default (unfiltered) branch, because LlamaIndex's
   `VectorStoreIndex.as_retriever()` chain embeds the query *inside*
   LlamaIndex. Tier 2 task 4.2 refactors `search()` to embed once at the
   top and thread the vector into both branches. This experiment is the
   end-to-end check that the refactor actually removes the duplicate
   embed call.
2. **The cache is worth it.** On a warm trace (same queries repeated), mean
   search latency should drop by ≥ 30 %. On a cold trace (every query
   unique), the cache should be a no-op — neither faster nor measurably
   slower.

---

## Hypothesis

With the LRU query-embedding cache enabled:

- **Warm trace**: mean search latency drops by ≥ 30 % vs cache-disabled,
  and the Ollama embed-call count equals the number of *distinct* queries.
- **Cold trace**: mean search latency stays within ±5 % of cache-disabled,
  and the Ollama embed-call count equals the number of queries (every
  query is a miss).

Both branches (filtered and unfiltered) hit Ollama exactly once for the
same query within the cache window.

---

## Background

The current `retrieval.search()` has two branches:

- **Metadata-filtered** branch — explicitly calls
  `Settings.embed_model.get_query_embedding(query)` and passes the vector
  to ChromaDB.
- **Unfiltered** branch — uses
  `VectorStoreIndex.from_vector_store(...).as_retriever(...).retrieve(query)`,
  where LlamaIndex internally re-embeds the query.

A naive `@lru_cache` on `Settings.embed_model.get_query_embedding` would
only catch the filtered branch. The unfiltered branch (the default) would
silently miss the cache. Tier 2 task 4.2 fixes this by replacing the
unfiltered branch's LlamaIndex retriever chain with a direct
`collection.query(query_embeddings=[vec], n_results=fetch_k)` call, where
`vec` is the cached embedding.

Once the refactor is in, both branches share a single embed call at the
top of `search()`, wrapped in `functools.lru_cache(maxsize=128)` keyed on
`(query, embed_model_name)`.

The expected order-of-magnitude speedup: a `qwen3-embedding:0.6b` query
embedding takes ~100 ms (Exp 2 measured ~104 ms average). Skipping it on
a cache hit recovers most of that for trivial cost (`O(1)` dict lookup).
On a workload where 80 % of queries are repeats, mean latency should
drop by 60–80 %.

---

## Variables

| Type        | Variable                          | Values                                          |
| ----------- | --------------------------------- | ----------------------------------------------- |
| Independent | Cache enabled / disabled          | Cache off / Cache on                            |
| Independent | Workload trace                    | Warm trace / Cold trace                         |
| Dependent   | Mean search latency (ms)          | —                                               |
| Dependent   | P95 search latency (ms)           | —                                               |
| Dependent   | Ollama embed-call count           | Counted via instrumentation wrapper             |
| Dependent   | Cache hit / miss / eviction count | From `lru_cache.cache_info()`                   |
| Controlled  | Embedding model                   | `qwen3-embedding:0.6b`                          |
| Controlled  | Reranker                          | **Disabled** — isolate the embed-call cost      |
| Controlled  | Corpus                            | Reuse Exp 2 corpus (6 documents, 207 chunks)    |
| Controlled  | `top_k`                           | 5                                               |
| Controlled  | Similarity threshold              | 0.0                                             |
| Controlled  | Cache `maxsize`                   | 128                                             |
| Controlled  | Hardware                          | Apple Silicon Mac, 16 GB                        |

> **Why reranker disabled?** The cache short-circuits the embed step. The
> reranker dominates the latency budget when enabled and would mask a 30 %
> embed-cache speedup. We measure the cache effect on the embed step
> directly, not on end-to-end production latency.

---

## Environment & Prerequisites

| Requirement   | Version / Value                                                    |
| ------------- | ------------------------------------------------------------------ |
| Python        | 3.12                                                               |
| Ollama models | `qwen3-embedding:0.6b`                                             |
| Hardware      | Apple Silicon Mac, 16 GB                                           |
| Code branch   | Post-Tier-2 with `search()` refactored per task 4.1–4.3            |

```bash
ollama list   # qwen3-embedding:0.6b
uv sync
```

---

## Step 1: Reuse the Exp 2 corpus

```bash
ln -s ../2-embedding-model-comparison-2026-05-19/corpus \
      experiments/8-query-embedding-cache-2026-05-27/corpus
```

The Exp 2 corpus has 6 documents → ~207 chunks. Plenty for the cache
experiment because we are not measuring retrieval quality, only embed-call
count and latency.

---

## Step 2: Build the workload traces

The cache experiment needs two synthetic workload traces. Both are simple
text files with one query per line; the runner reads them and fires queries
in order.

### Warm trace (`workload-warm.txt`)

50 distinct queries × 5 repeats each = 250 calls, **interleaved** so each
query reappears spaced through the trace (not all repeats back-to-back).

```
What is RAG?
How does the transformer work?
What is the attention mechanism?
... (47 more)
What is RAG?              ← repeat 2
How does the transformer work?
...
```

Generate it programmatically: take 50 queries from
`experiments/2-embedding-model-comparison-2026-05-19/ground-truth.json`
(or write 50 fresh ones — they don't need ground-truth labels here, just
to be representative). Shuffle them, then concatenate 5 shuffled copies.

> **Why 50 distinct queries × 5 repeats?** This gives 250 total calls with
> a steady 80 % cache hit rate after the first wave. The numbers are big
> enough for stable percentile measurements and small enough to fit
> comfortably under the `maxsize=128` LRU.

### Cold trace (`workload-cold.txt`)

200 unique queries, **no repeats**. The cache should never hit. This is
the negative control: we want to confirm the cache adds no measurable
overhead when it is not earning anything.

Generate by mutating each warm-trace query slightly (add a unique suffix,
change wording, append a paragraph reference, etc.) so every query is
distinct.

You can use any LLM to generate 200 paraphrases of a topic seed list —
the queries do not need to be perfect, only distinct.

---

## Step 3: Run all four cells

The runner does a 2 × 2 grid: `{cache off, cache on} × {warm, cold}`:

```bash
cd experiments/8-query-embedding-cache-2026-05-27
uv run python run_eval.py \
  --corpus ./corpus \
  --warm-trace workload-warm.txt \
  --cold-trace workload-cold.txt
```

The script:

1. Ingests the corpus into a fresh ChromaDB.
2. Wraps `Settings.embed_model.get_query_embedding` with a counting helper
   that records every call.
3. For each of the 4 cells:
   - Disables or enables the LRU cache (sets `LRUCACHE_ENABLED` env or
     toggles directly on the helper).
   - Replays the trace, recording per-query latency.
   - Reads `cache_info()` and the embed-call counter.
   - Resets the counter and clears the cache between cells.
4. Prints a comparison table.
5. Saves raw data to `eval_results.json`.

> **Implementation note**: if Tier 2 ships the cache as always-on with no
> disable flag, the runner needs to monkey-patch the cache to a `maxsize=0`
> or replace the cached function with a passthrough for the "cache off"
> cells. Document the technique used.

---

## Step 4: Interpret the results

```
┌──────────────────┬──────────┬─────────┬──────────┬────────────┬───────────┐
│ Cell             │ Mean ms  │ P95 ms  │ Embed    │ Cache hit  │ Cache     │
│                  │          │         │ calls    │ rate       │ size end  │
├──────────────────┼──────────┼─────────┼──────────┼────────────┼───────────┤
│ Cache off, warm  │  108.2   │  142.7  │   250    │     —      │     —     │
│ Cache on,  warm  │   24.1   │  140.5  │    50    │   80.0%    │    50     │
│ Cache off, cold  │  104.5   │  136.0  │   200    │     —      │     —     │
│ Cache on,  cold  │  105.3   │  138.2  │   200    │    0.0%    │   128     │
└──────────────────┴──────────┴─────────┴──────────┴────────────┴───────────┘
```

Key questions:

1. **Warm-trace speedup**: cache-on mean ≤ 0.7 × cache-off mean? (≥ 30 %
   reduction.)
2. **Cold-trace neutrality**: cache-on mean within ±5 % of cache-off mean?
3. **Embed-call count**: warm cache-on equals the number of distinct
   queries (50)? Cold cache-on equals the number of queries (200)?
4. **No silent miss on the unfiltered path**: did the warm trace's repeat
   queries hit the cache? If `cache hit rate` is 0 % on the warm trace,
   the unfiltered path is still bypassing the cache and Tier 2 task 4.2's
   refactor is incomplete.
5. **LRU eviction**: cold trace reaches `cache size end = 128` (the
   maxsize)? This confirms eviction works.

---

## Success Criteria

| Check                                    | Pass condition                                                       |
| ---------------------------------------- | -------------------------------------------------------------------- |
| Warm-trace speedup                       | `cache on, warm` mean ≤ 0.7 × `cache off, warm` mean (≥ 30 % reduction) |
| Cold-trace neutrality                    | `cache on, cold` mean within ±5 % of `cache off, cold` mean          |
| Embed-call count, warm cache-on          | Equals number of distinct queries in the warm trace (50)             |
| Embed-call count, cold cache-on          | Equals number of queries in the cold trace (200)                     |
| Both retrieval paths cached              | Filtered and unfiltered paths each show ≥ 80 % cache hit rate on the warm trace |
| LRU eviction works                       | Cache size at end of cold trace equals `maxsize=128`                 |

---

## What to do if the experiment fails

**Warm-trace speedup < 30 %:**

1. Confirm `Settings.embed_model.get_query_embedding` is genuinely being
   skipped on hits — instrument with print statements.
2. Confirm the cache is actually running; check `cache_info()`.
3. If the cache is running but the speedup is small, the embed call is
   not the dominant cost on this workload (maybe ChromaDB is). Document
   and adjust expectations. Cache still earns its keep on slower embed
   models like `qwen3-embedding:8b`.

**Warm cache-on hit rate is 0 % on the unfiltered path:**

1. Tier 2 task 4.2 has not removed the LlamaIndex internal embed call.
2. Re-read `retrieval.search()` and confirm the unfiltered branch uses
   `collection.query(query_embeddings=[vec], n_results=fetch_k)` directly,
   not `index.as_retriever(...).retrieve(query)`.
3. Loop back to Tier 2 task 4.2 until the unfiltered path is on the
   refactored code path.

**Cold-trace neutrality fails (cache adds > 5 % overhead):**

1. The `lru_cache` overhead should be sub-microsecond. If it is bigger,
   something else changed at the same time.
2. Re-run the cold trace 3× and average — small samples lie.
3. If the regression is real and not noise, profile the hot path with
   `cProfile` and look for unintended copies or hashing of large objects.

---

## Cleanup

```bash
rm -rf ./chroma_db_test
rm -f workload-warm.txt workload-cold.txt   # If you don't want to keep them
```

---

## References

- `openspec/changes/rag-retrieval-quality-improvements/design.md` — Decision 4
- `openspec/changes/rag-retrieval-quality-improvements/tasks.md` — tasks 4.1–4.9
- Python `functools.lru_cache`:
  https://docs.python.org/3/library/functools.html#functools.lru_cache
- ChromaDB `collection.query` API:
  https://docs.trychroma.com/reference/Collection#query
- LlamaIndex `VectorStoreIndex.as_retriever`:
  https://docs.llamaindex.ai/en/stable/api_reference/indices/vector_store/

---

## Artefacts

| File                | Description                                                                |
| ------------------- | -------------------------------------------------------------------------- |
| `protocol.md`       | This file — hypothesis, method, reproduction steps                         |
| `run_eval.py`       | 2 × 2 cell runner (cache on/off × warm/cold)                               |
| `workload-warm.txt` | 50 distinct queries × 5 repeats, interleaved                               |
| `workload-cold.txt` | 200 unique queries, no repeats                                             |
| `eval_results.json` | Per-cell mean / P95 / embed-call count / cache-info dump                   |
| `results.md`        | Comparison table, decision                                                 |
| `corpus/`           | Symlink to `experiments/2-embedding-model-comparison-2026-05-19/corpus/`   |
