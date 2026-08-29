# Experiment 19 results: native FTS vs BM25 sparse backend

**Status:** FAIL (gates) — decision: KEEP bm25 DEFAULT
**Ran:** 2026-08-29 · corpus: Exp 9 packs · store chunks: 53

## Quality (sparse-only, warm)

| Metric | BM25 | Native |
| --- | --- | --- |
| Recall@5 | 0.850 | 0.800 |
| Recall@10 | 0.850 | 0.850 |
| MRR@10 | 0.792 | 0.774 |

Per category (sparse-only Recall@10):

| Category | BM25 | Native |
| --- | --- | --- |
| mixed | 1.000 | 1.000 |
| rare-term | 0.889 | 0.889 |
| semantic | 0.667 | 0.667 |

## Quality (hybrid fused, warm)

| Metric | BM25 | Native |
| --- | --- | --- |
| Recall@10 | 0.950 | 0.950 |
| MRR@10 | 0.950 | 0.950 |

## Latency (sparse query, seconds)

| Phase | BM25 | Native |
| --- | --- | --- |
| Cold first query | 0.3223 | 0.0297 |
| Warm p50 | 0.0 | 0.0057 |
| Warm p95 | 0.0001 | 0.0178 |

Native/BM25 warm p50 ratio: **138.7×**

## Determinism and memory

| Metric | BM25 | Native |
| --- | --- | --- |
| Ordering mismatches (warm 2 vs 3) | 0 | 0 |
| tracemalloc cold peak (MB) | 2.39 | 2.36 |
| Peak RSS (MB) | 283.84 | 262.88 |

Peak RSS delta (native vs bm25): **-7.4%**

## Gates

- ✅ G1_quality_floor_-2pp
- ✅ G2_determinism_zero_mismatches
- ❌ G3_latency_within_10x
- ✅ G4_memory_within_10pct

Quality delta (native − bm25, sparse Recall@10): **+0.00 pp**

## Recommendation

The default stays `bm25`. Native FTS is a registered,
capability-resolved alternative with lifecycle and fallback
guarantees; these results are the standing evidence for the
default decision. Revisit only with a larger, more
representative corpus or changed pass gates (protocol
pre-registration).
