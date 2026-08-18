# ADR-047: Semantic Vector-Store Swappability

**Date:** 2026-08-18
**Status:** Proposed
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

ADR-034 introduced a `VectorStore` interface and ADR-046 proved that ChromaDB
and LanceDB can satisfy the same Python surface. Interface compatibility was
not yet semantic compatibility:

- core retrieval converted a generic `distance` with a Chroma-shaped formula,
  although the ABC did not define the backend metric or scale;
- hybrid RRF utilities were compared directly with a dense similarity
  threshold;
- caller metadata filters constrained dense retrieval but not BM25, allowing
  fusion to re-introduce forbidden rows;
- the process-wide BM25 cache used only the collection name, so equal
  generations in two stores could alias one sparse index;
- generation invalidation was split between stores and ingestion
  orchestration, producing backend asymmetry and double-bump paths; and
- provider registries made embedding providers look runtime-swappable even
  though LlamaIndex exposes one process-global `Settings.embed_model`.

Those defects can change experiment conclusions independently of retrieval
quality. Calibration must therefore wait for a deterministic semantic contract.

## Decision

1. **Adapters own native dense-score conversion.** `VectorStore.query_dense`
   returns `id`, `document`, `metadata`, a higher-is-better `score`, and
   `score_kind`. Core retrieval does not read or transform a generic native
   distance.

2. **`dense_similarity_v1` is a bounded monotonic L2 transform.** ChromaDB and
   LanceDB pin L2 at their adapter boundaries and convert native distance with
   `1 / (1 + distance)`. The contract guarantees values in `(0, 1]`, nearest-
   neighbour ordering, and compatible threshold direction. It does **not**
   claim cosine similarity or exact cross-store numeric equality, because the
   engines may expose differently scaled L2 distances. A Chroma collection
   explicitly configured with a non-L2 metric fails clearly rather than being
   mislabeled.

3. **Thresholds apply only to compatible score kinds.** Dense/no-rerank uses
   `dense_similarity_v1`. Hybrid/no-rerank evaluates the dense threshold before
   fusion and excludes sparse-only or low-dense candidates; `rrf_v1` remains a
   ranking utility and is never compared directly with the dense threshold.
   Successful reranking uses `reranker_sigmoid_v1` and the existing empirically
   calibrated divide-by-30 transform. Reranker failure returns to the correct
   dense pre-rerank rule. Diagnostics expose `score_kind` and
   `threshold_score_kind`.

4. **Metadata filters are branch-invariant.** BM25 evaluates the same
   Chroma-shaped equality, comparison, membership, and boolean filter forms as
   the dense store contract before sparse truncation and RRF. Correctness takes
   precedence over the cost of evaluating cached row metadata in memory.

5. **Sparse cache identity is store plus collection.** BM25 cache keys are
   `(store.cache_identity, collection_name)`. The default identity token is the
   store object itself: stable and opaque for the process lifetime, retained by
   the cache so object-id reuse cannot alias a later store.

6. **Stores own generation invalidation exactly once.** Every successful
   sparse-visible write, precomputed upsert, filtered delete, and collection
   delete advances that store instance's collection generation once. Ingestion
   orchestration never applies a second bump. Direct callers and pipeline
   callers therefore have identical cache-invalidation semantics.

7. **Embedding-provider swappability is deployment scoped.** The composition
   root assigns one LlamaIndex `Settings.embed_model` and declares
   `EMBEDDING_PROVIDER_SCOPE = "process"`. Different providers or models require
   separate server processes; per-collection profiles do not override the
   process-global provider. Concurrent per-collection provider selection needs
   a future explicit design with per-operation embedding context.

## Evidence Boundary

The acceptance evidence for this ADR will be the deterministic cross-store
contract suite in `tests/test_vectordb_contract.py`, the hybrid retrieval suite
in `tests/test_hybrid_retrieval.py`, and the Stage 2 audit regressions in
`tests/test_precalibration_audit_regressions.py`.

Example Experiments 2–4 under `experiments/example/` remain future empirical
evidence inputs. They have not run at Stage 2, so this ADR makes no experimental
PASS claim about exact score parity, filter performance, or cache performance.

## Consequences

### Positive

- Swapping ChromaDB and LanceDB preserves ranking direction, score provenance,
  filter eligibility, cache isolation, and mutation invalidation semantics.
- Dense, RRF, and reranker values cannot silently cross threshold domains.
- A direct store mutation can no longer leave BM25 stale merely because the
  caller bypassed ingestion orchestration.
- Deployment documentation no longer implies unsupported per-collection
  embedding-provider concurrency.

### Negative

- Positive dense thresholds in non-reranked hybrid search remove sparse-only
  recall by design; callers asking for a semantic minimum receive only rows
  with qualifying dense evidence.
- A hybrid reranker failure may repeat the first-stage query to reapply the
  dense threshold before fusion. Failure is expected to be rare, and the extra
  work is accepted for semantic correctness.
- BM25 retains a strong process-local reference to each queried store in its
  cache key. Long-lived processes that construct many throwaway stores should
  clear the cache or add an explicit lifecycle in a future change.
- Existing non-L2 Chroma collections must be re-ingested into an L2 collection
  or gain a separately specified score kind and transform.

### Neutral

- `dense_similarity_v1` preserves the historical `1 / (1 + d)` formula but
  relocates ownership from retrieval core to the backend adapters.
- The generation counter remains process-local; this decision does not create
  cross-process cache invalidation.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Keep generic `distance` in the ABC | A backend can satisfy the interface while silently changing metric and threshold meaning. |
| Convert all native outputs in core retrieval | Core would still need backend/metric knowledge and violate adapter ownership. |
| Treat RRF as a similarity score | RRF magnitude depends on rank positions and damping, not semantic similarity. |
| Post-filter only the final public hybrid rows | It can waste sparse candidate budget and leaves branch eligibility asymmetric before fusion. |
| Key BM25 by collection and generation only | Distinct stores commonly begin at the same generation and may reuse collection names. |
| Keep caller-owned generation bumps | Direct store callers remain unsafe and backend behaviour stays asymmetric. |
| Claim per-collection embedding-provider support | LlamaIndex's process-global embed model makes the claim false under concurrent use. |

## References

- OpenSpec change:
  `openspec/changes/harden-pipeline-correctness-before-calibration/`
- Implementation: `src/rag_mcp/core/vectordb/{base,score,chroma,lancedb}.py`,
  `src/rag_mcp/core/retrieval/{dense,filters,fusion,sparse,pipeline}.py`,
  `src/rag_mcp/core/ingestion/writer.py`, `src/rag_mcp/compose.py`
- Deterministic tests: `tests/test_vectordb_contract.py`,
  `tests/test_hybrid_retrieval.py`,
  `tests/test_precalibration_audit_regressions.py`
- Future evidence inputs: `experiments/example/experiment-2-*`,
  `experiments/example/experiment-3-*`, `experiments/example/experiment-4-*`
- Related decisions: ADR-015 (historical distance transform), ADR-017 (RRF),
  ADR-031 (reranker), ADR-034 (VectorStore ABC), ADR-045 (hosted Chroma),
  ADR-046 (LanceDB)
