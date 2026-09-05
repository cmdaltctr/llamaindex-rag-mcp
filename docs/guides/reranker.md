# Reranker

The server includes an optional **cross-encoder reranker** that re-scores vector search results for significantly better retrieval precision. It uses `cross-encoder/ms-marco-MiniLM-L-6-v2` — a ~23 MB quantised ONNX model that runs locally via pure ONNX Runtime. The default install has no PyTorch; a torch-backed backend is available as an opt-in extra (see [Backends](#backends) below).

## How it works

Without the reranker:

```
query → embed → canonical dense similarity → return top_k
```

With the reranker:

```
query → embed → dense candidates → cross-encoder re-score → return top_k
```

The cross-encoder evaluates each (query, document) pair jointly, which is slower but can be more precise than dense retrieval alone. The vector search fetches a wider candidate pool so the reranker has meaningful rows to re-score.

## Threshold auto-scaling

Cross-encoder sigmoid scores occupy a different range from the canonical dense score. Valid reranker results can score as low as 0.015.

When `rerank=True` **and reranking actually succeeds**, the `similarity_threshold` is **automatically scaled down by 30×** so that a user-supplied value of 0.3 becomes 0.01. Supply the threshold in canonical dense-score terms; the system applies the calibrated reranker transform.

The scaling follows the rerank *outcome*, not the request. If reranking fails, dense-only search applies the unscaled threshold to `dense_similarity_v1`; hybrid search rebuilds the first-stage candidates with that dense threshold before RRF. RRF utilities are never compared directly with the dense threshold.

Calibrated from experiment data in `experiments/reranker-threshold-calibration-2026-05-12/`:

| Score range | Meaning |
|-------------|---------|
| 0.79–1.0 | Strong reranker match |
| ~0.015 | Weak but correct match |
| < 0.003 | Noise |

## Enabling

**Per-query** (recommended — call with `rerank=True`):

> "Search for quantum superposition, use reranking"

**Always on** (via `.env`):

```bash
RETRIEVAL__RERANK_ENABLED=true
RETRIEVAL__SIMILARITY_THRESHOLD=0.3   # optional default threshold
```

**CLI**:

```bash
omrg search "machine learning" --rerank --threshold 0.3
```

## First-run download

The first time you call `search_documents` with `rerank=True`, the ~23 MB quantised ONNX model downloads from HuggingFace Hub and caches in `~/.cache/huggingface/`. On macOS ARM64, the `model_qint8_arm64.onnx` variant is used automatically. Subsequent calls use the cached model — it's a singleton, loaded once and reused across all calls.

> **Note:** CoreML is disabled by default (ADR-029) — it doesn't support the dynamic sequence lengths that cross-encoder tokenisation produces. CPU-only inference is used instead. Override with `RERANK_ONNX_PROVIDER=coreml` to experiment.

## Backends

The reranker has two interchangeable inference backends. Both produce scores on the same `(0, 1)` scale via a shared sigmoid transform, so the calibrated threshold stays valid whichever backend runs (ADR-038).

| Backend | Settings value | Install | Torch loaded? |
|---------|---------------|---------|---------------|
| ONNX Runtime (default) | `RETRIEVAL__RERANK_BACKEND=onnx` | Base install | No |
| sentence-transformers | `RETRIEVAL__RERANK_BACKEND=torch` | `uv sync --extra torch` (~200 MB on macOS ARM) | Yes — only when this backend is selected |

The ONNX backend tokenises with the pure-Rust `tokenizers` package, which cannot pull `torch`. The torch backend imports `sentence_transformers` lazily inside its model-load method, so simply installing the extra does not change the default path.

**Sigmoid parity**: `CrossEncoder.predict()` applies `nn.Sigmoid()` by default for `num_labels=1` models. The torch backend overrides this with `nn.Identity()` and applies the shared `_sigmoid` once — otherwise the logits would be double-sigmoided, compressing scores to roughly `[0.5, 0.73]` and silently breaking the ÷30 threshold (ADR-038, design decision 3). The cross-backend contract test (`tests/test_reranker_backend_contract.py`) compares score *values*, not just ranking, to catch this.

**Fallback**: if `RETRIEVAL__RERANK_BACKEND=torch` is set but the extra is not installed, the server logs an error naming `uv sync --extra torch` and falls back to the ONNX backend. If the ONNX backend also fails, the search returns un-reranked results truncated to `top_k`.

## When to use

| Scenario | Recommendation |
|----------|---------------|
| Quick lookups, broad recall | `rerank=False` (default — faster) |
| Precision-critical answers | `rerank=True` |
| Filtering noise | `similarity_threshold=0.3` + `rerank=True` |
| Many similar results | `rerank=True` — breaks ties better |

## Fallback

If the reranker model fails to load (no internet for first download, corrupt cache, etc.) or inference raises, the server **gracefully falls back** to un-reranked vector search results. The server never crashes due to reranker issues. The next call retries loading automatically.

**Failure escalation** (ADR-029 decision #3): each failure logs a warning as before, but the server tracks consecutive failures with the same error signature process-wide. Below 3 consecutive same-signature failures it logs at WARNING; at or above that threshold it logs at ERROR, so a persistent outage (like the 5-week CoreML incident in ADR-029) stops looking identical to an occasional transient hiccup in the logs. Any successful load or inference resets the counter.

**Diagnostics**: when `include_diagnostics=True`, each result carries:
- `rerank_reason` — the policy decision or the reranker's own failure reason (e.g. `"inference failed: ..."` or `"model load failed: ..."`)
- `rerank_backend` — the backend that performed the re-scoring (`"onnx"` or `"torch"`), which may differ from the settings value when the torch extra is missing and the helper fell back to ONNX

So a broken reranker is distinguishable from a policy-driven skip without grepping logs, and the active backend is observable alongside it (ADR-029 deferred item 2).

## Sparse retrieval backends (hybrid search)

Hybrid search fuses two rankings: dense embedding similarity and a sparse keyword ranking. The sparse stage runs exactly one registered backend, chosen by `RETRIEVAL__HYBRID_SPARSE_BACKEND`:

| Backend | What it runs | Notes |
|---------|--------------|-------|
| `bm25` (default) | In-process BM25, cached per store and collection, invalidated on every mutation | Base install, backend-agnostic |
| `native` | LanceDB native full-text search over the stored `text` column | LanceDB only |

The registry (`core/retrieval/sparse_registry.py`) maps backend names to implementations; adding a backend is one new file plus one `register()` line. `auto` is deliberately not a backend: the composition root resolves it before query time through the selected store's capability metadata plus a real native-FTS probe (`omrg.core.vectordb.lance_fts:probe_native_fts`). On LanceDB `auto` resolves to `native`. Chroma declares no native capability, so `auto` resolves to `bm25` there. An unknown concrete name fails startup listing `auto` plus the registered names.

Scores are not comparable across backends. Native rows carry `score_kind` `native_fts_v1`, the engine's raw higher-is-better score. Only rank order feeds RRF, so the scale difference never affects fusion.

### Why the default stays `bm25`

Experiment 19 (`experiments/19-native-fts-vs-bm25-sparse-2026-08-29/`) is the standing calibration evidence:

| Metric | BM25 | Native |
|--------|------|--------|
| Sparse Recall@10 (warm) | 0.850 | 0.850 |
| Ordering mismatches | 0 | 0 |
| Peak RSS | baseline | −7.4% |
| Warm p50 latency | baseline | 138.7× slower |
| Cold first query | baseline | 10.8× faster |

At the 53-chunk corpus the experiment measured, native warm latency is far above BM25's for the same retrieval quality. The pre-registered decision keeps `bm25` as the default. Revisit only with a larger, more representative corpus or changed pass gates.

### Fallback and diagnostics

Selecting `native` on a store without the capability logs a WARNING at composition and falls back to `bm25`. At query time, a native failure (index creation, refresh, or query) emits a one-shot WARNING per collection and serves BM25 results through the same contract. With `include_diagnostics=True`, each result carries `sparse_backend`: the backend that actually ran. Fallback results are never labelled `native`.

### FTS lifecycle (LanceDB)

The native path owns one full-text-search index per collection. The contract lives in `core/vectordb/lance_fts.py` and is pinned by `tests/test_lancedb_native_fts_contract.py`:

- **Creation** is additive and triggered on the first native query, indexing existing rows synchronously. A collection without an index keeps working through every other operation.
- **Staleness** is a durable property: writes by any process show as `num_unindexed_rows > 0` in `list_indices()` statistics. The process-local generation counter is not used for this. BM25 cache validity uses the store's durable data version where one exists ([ADR-056](../adr/056-lineage-navigation-replaces-a-document-store.md)); the process-local counter is the fallback.
- **Refresh** (`table.optimize()`) runs before serving a native query when the statistics show lag. Engine queries are fresh-by-construction regardless: unindexed rows are scanned and deletions are tombstoned.
- **Mixed coverage** (`0 < indexed < total`) emits a one-shot WARNING naming the collection with a remediation hint. Coverage is reported separately from freshness via `native_sparse_coverage()`.

The BM25 path never emits these warnings; it indexes every chunk it sees.

### Migration

Existing collections need no re-ingestion: the first native query creates the FTS index additively and indexes existing rows synchronously. FTS indexes add per-collection disk footprint. To roll back, set `RETRIEVAL__HYBRID_SPARSE_BACKEND=bm25`; stored data and any FTS indexes are left untouched. An unused index is inert.
