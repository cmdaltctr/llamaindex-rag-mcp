# Experiment 8a: Query Embedding Cache Full-Size Evaluation

**ID**: `8a-query-embedding-cache-fullsize-2026-05-29`  
**Status**: READY TO RUN  
**Relation**: Follow-up to Experiment 8 and ADR-016 Decision 4.

## Why this experiment exists

Experiment 8 verified the query-embedding cache on both filtered and
unfiltered retrieval branches, but with two limitations:

1. trace sizes were reduced to 40 calls rather than the planned 250/200;
2. the cache-off cells did not actually bypass the production LRU cache.

Experiment 8a corrects both by using full-size traces and a real cache-disable
monkey patch.

## Hypotheses

1. Warm repeated-query traces achieve ≥ 30% mean latency reduction with cache on.
2. Cold unique-query traces remain within ±5% with cache on.
3. Agent-loop traces, which intentionally repeat verification questions, show
   stronger speedups than the generic warm trace.
4. Filtered and unfiltered branches both benefit from the same cache.
5. Production-shape rerank-on traces still show a measurable but smaller
   speedup, because reranker latency dilutes the embedding-cache win.

## Corpus

The corpus is copied into this experiment from Exp 3:

- 4 PDFs
- 2 Markdown READMEs

No symlinks are used.

## Workloads

| Trace | Calls | Shape | Purpose |
| --- | ---: | --- | --- |
| warm | 250 | 50 distinct × 5 repeats | standard repeat-query cache benchmark |
| cold | 200 | all unique | negative control / no cache hits |
| agent-loop | 250 | 25 distinct × 10 repeats | agent verification-loop simulation |

The runner generates `workload-*.txt` files if they are absent.

## Cell matrix

| Cell | Cache | Trace | Rerank | Branches |
| --- | --- | --- | --- | --- |
| 1 | off | warm | off | alternating filtered/unfiltered |
| 2 | on | warm | off | alternating filtered/unfiltered |
| 3 | off | cold | off | alternating filtered/unfiltered |
| 4 | on | cold | off | alternating filtered/unfiltered |
| 5 | off | agent-loop | off | alternating filtered/unfiltered |
| 6 | on | agent-loop | off | alternating filtered/unfiltered |
| 7 | off | warm | on | unfiltered production-like |
| 8 | on | warm | on | unfiltered production-like |

## Cache disable mechanism

`rag_mcp.retrieval._embed_query` is temporarily replaced with a direct call to
`Settings.embed_model.get_query_embedding(query)`. The production
`_cached_query_embedding` helper is still cleared between cells so cache-on
cells start cleanly.

## Success criteria

- Warm mean speedup ≥ 30%.
- Agent-loop mean speedup ≥ 50%.
- Cold cache-on mean within ±5% of cold cache-off.
- Warm cache-on embed calls = number of distinct warm queries (50).
- Cold cache-on embed calls = total cold queries (200).
- Agent-loop cache-on embed calls = number of distinct agent-loop queries (25).
- Filtered and unfiltered branch cache-hit rates are both ≥ 80% on warm and
  agent-loop traces.
