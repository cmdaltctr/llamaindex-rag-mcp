## Context

The current retrieval pipeline is a single-stage dense vector search backed by ChromaDB and Ollama embeddings, optionally followed by an ONNX cross-encoder reranker. Two failure modes are well documented:

1. The reranker pool starts from dense retrieval only, so any chunk that dense retrieval ranks below the fetch cut-off can never be reranked. The Colosseum experiment is a concrete instance.
2. Rare or exact-match terms (product codes, legal citations, gene names, identifiers) are systematically harder for dense embeddings than for keyword matching.

Hybrid retrieval addresses both by running a sparse keyword retriever in parallel and fusing rankings with Reciprocal Rank Fusion (RRF). The reranker continues to operate on the fused pool exactly as it does on the dense-only pool today, so the calibrated ÷30 threshold scaling factor remains valid.

## Goals / Non-Goals

**Goals:**

- Provide an opt-in `hybrid=True` retrieval mode that fuses dense and sparse rankings.
- Use Reciprocal Rank Fusion (Cormack, Clarke & Buettcher, 2009) with the standard `k=60` constant.
- Preserve all current behaviour when `hybrid=False` (the default).
- Keep the existing reranker pipeline and its calibrated threshold scaling unchanged.
- Stay local-only and CPU-friendly. No new cloud services. No PyTorch.
- Provide a regression-test corpus that includes the Colosseum-style rare-term query.

**Non-Goals:**

- No replacement of the reranker model.
- No HyDE-style query expansion.
- No semantic chunking.
- No change to the embedding model or vector dimension.
- No required ChromaDB collection rebuild for users who keep `hybrid=False`.

## Decisions

### Decision 1: Reciprocal Rank Fusion with k=60

Use RRF as the fusion function:

```
score_fused(d) = Σ_r 1 / (k + rank_r(d))    where k = 60
```

RRF is the de facto fusion baseline in IR literature, requires no learned weights, and is robust across mismatched score scales between dense and sparse retrievers. `k=60` is the value used by Cormack et al. and reproduced widely in production systems.

Alternatives considered: weighted convex combination (`α * dense + (1-α) * sparse`). Rejected because it requires per-corpus weight tuning and produces brittle results when score distributions shift.

### Decision 2: Sparse backend defaults to BM25 for v1, with capability detection available behind an env var

The `HYBRID_SPARSE_BACKEND` env var SHALL accept `auto`, `native`, or `bm25`. **The default for v1 SHALL be `bm25`**, not `auto`. The native ChromaDB sparse-vector / BM25 / SPLADE API has been a moving target across recent minor versions; defaulting to the in-memory BM25 path keeps the rollout surface small and avoids version-pinning issues. Promotion of the default to `auto` (or `native`) belongs in a follow-up change after the calibration experiment confirms the native path works on the project's pinned `chromadb`.

When `HYBRID_SPARSE_BACKEND=auto`, the system SHALL run the capability detection routine and select `native` or `bm25`. When `HYBRID_SPARSE_BACKEND=native` is set explicitly and the installed ChromaDB does not support sparse vectors, the system SHALL log a WARNING and fall back to `bm25` rather than crashing.

The BM25 fallback path SHALL build its index over the full set of chunks in the active collection on first hybrid query, then cache the index in process. (The earlier "lazy build over a chunk subset" idea was circular: you cannot pre-filter the chunk subset without already having a sparse ranking.) Cache invalidation is covered in Decision 6.

Both paths SHALL return the same `(rank, doc_id, text, metadata)` shape downstream.

Alternative considered: requiring a specific ChromaDB version. Rejected because it would force users to upgrade for an opt-in feature.

Alternative considered: defaulting to `auto`. Rejected for v1 because capability detection on a moving target API yields mystery failures during rollout; we want users opting into the native path deliberately, after the experiment proves it.

### Decision 3: Hybrid is opt-in, then evaluated

`HYBRID_ENABLED=false` by default. The MCP `search_documents` tool exposes `hybrid: bool` with default `False`. Make the change behind a feature flag so users can A/B against their existing collections, then run the new experiment under `experiments/hybrid-retrieval-<date>/` to set the recommended default.

### Decision 4: Reranker integration is unchanged

The reranker receives a fused candidate list of size determined by Tier 2's `RERANK_FETCH_MULTIPLIER` / `RERANK_MAX_FETCH` settings, applied identically to dense-only retrieval. The reranker still uses the calibrated ÷30 threshold scaling because its scoring function is unchanged.

### Decision 5: No automatic re-ingestion required

If the native sparse path is selected, only newly ingested chunks gain sparse vectors; existing chunks remain dense-only. Hybrid retrieval gracefully handles partial coverage by treating dense-only chunks as having an unknown sparse rank (RRF naturally handles missing ranks by excluding them from one term of the sum). A CLI command SHALL be added or extended to support a deliberate re-ingest for users who want full hybrid coverage immediately.

### Decision 6: BM25 cache invalidation tied to the ingestion write lock

The BM25 fallback index SHALL be cached in process and SHALL invalidate whenever ingestion writes new chunks to the active collection. The simplest implementation hooks into the existing `_write_lock` path inside `_embed_and_write_async` (see `ingestion.py`): bump a per-collection generation counter on every successful write, and have the sparse retriever compare against the counter on each query. If the counter has advanced since the cached index was built, the sparse retriever SHALL rebuild the index lazily on the next hybrid query.

A "lazy rebuild on stale generation" approach is preferred over "eager rebuild during ingest" because rebuilds can be expensive on large collections and ingestion is already on the critical path. Lazy rebuilds amortise the cost across queries and let the system stay responsive during ingest.

Concrete behaviour the implementer SHALL preserve:

- Generation counter is per-collection, in-process state.
- Counter increments under `_write_lock` so concurrent ingest writes serialise correctly.
- Sparse retriever caches `(collection_name, generation, bm25_index)`. On query, if the current generation does not match the cached generation, the cached index is discarded and rebuilt.
- Deletion paths (`remove_document`, `remove_by_metadata`, `remove_collection`) SHALL also bump the generation counter.

Alternative considered: re-read the collection on every hybrid query. Rejected because it makes hybrid quadratic-ish on collection size for repeat queries.

Alternative considered: persistent on-disk BM25 index. Rejected as overkill for a local MCP server and as scope creep relative to the v1 deliverable.

### Decision 7: Mixed-coverage collections trigger a one-shot WARNING

When the native sparse path is active and `_get_chroma_collection(...)` reports that some chunks lack sparse vectors, the system SHALL emit a one-shot WARNING log on the first hybrid query against that collection within the process lifetime. The warning SHALL name the collection and explain that flipping `hybrid=True` may produce different results than dense-only retrieval until the user re-ingests for full coverage.

The warning is one-shot per `(collection, process)` pair so the operator sees it without spamming the log on every query. The warning SHALL include a remediation hint: re-ingest the collection (or specific files) to gain full hybrid coverage.

This decision is non-blocking for retrieval — RRF still handles missing ranks correctly per Decision 1; the warning just makes the operationally surprising behaviour visible. The BM25 fallback path is unaffected because that path always indexes every chunk it sees.

Alternative considered: refuse to run hybrid on partially-covered collections until re-ingested. Rejected as too aggressive for an opt-in feature; users may deliberately want partial hybrid as a stepping stone.

Alternative considered: silently proceed. Rejected because score changes look like a bug to operators who do not know about the underlying coverage gap.

### Decision 8: Hybrid is exposed in both MCP and CLI

The `hybrid: bool` parameter SHALL be added to:

- The MCP `search_documents` tool, defaulting to `False`.
- The CLI `search` subcommand as `--hybrid / --no-hybrid` flag, defaulting to `False`.

This mirrors the existing parity pattern used for `--rerank`, `--top-k`, `--threshold`, and `--collection` on the same CLI subcommand. Skipping CLI parity would create a quiet asymmetry where MCP clients have a feature CLI users cannot reach.

Alternative considered: MCP-only for v1. Rejected because the CLI surface already has slots for every other retrieval flag and adding one is trivial.

## Risks / Trade-offs

- **Risk: in-memory BM25 index consumes memory proportional to collection size.** → Accepted for v1 (single-user local server). The cache is invalidated on every ingest write per Decision 6, so memory is bounded by the active collection's chunk count. Document the limit; revisit if users hit it.
- **Risk: BM25 cache becomes stale after ingestion.** → Mitigated by Decision 6: generation counter under `_write_lock`, lazy rebuild on next query when generation changes.
- **Risk: capability detection misidentifies ChromaDB version features.** → Mitigated by Decision 2: v1 default is `bm25`, not `auto`. Users opt into the native path explicitly via `HYBRID_SPARSE_BACKEND=native` once the experiment confirms it works on the pinned `chromadb`.
- **Risk: hybrid retrieval changes default search results.** → Mitigated by keeping `hybrid=False` as the default until the calibration experiment confirms gains; the default flip is a deliberate follow-up change.
- **Risk: mixed-coverage collections silently produce different scores.** → Mitigated by Decision 7: one-shot WARNING per `(collection, process)` pair with a remediation hint.
- **Risk: latency increases due to running two retrievers.** → Mitigated by running them concurrently and bounding pool sizes via Tier 2's `RERANK_FETCH_MULTIPLIER` / `RERANK_MAX_FETCH`.
- **Risk: stop-word and tokeniser choice for BM25 affects quality.** → Mitigated by defaulting to a standard English tokeniser; expose an env-var override later if the experiment surfaces a gap.
- **Risk: AGENTS.md ÷30 calibration rule is mistakenly assumed to need recalibration.** → Documented explicitly in this design and in the modified `reranking` spec: hybrid does not change reranker scoring and therefore does not require re-running the calibration experiment.
- **Risk: CLI users miss the feature if it lands MCP-only.** → Mitigated by Decision 8: `--hybrid` flag mirrored onto the existing `cli search` subcommand.

## Migration Plan

1. Ship the change behind `HYBRID_ENABLED=false` and `HYBRID_SPARSE_BACKEND=bm25` defaults.
2. Run the new experiment in `experiments/hybrid-retrieval-<date>/` against a corpus that includes the Colosseum-style rare-term query.
3. Document the recommended setting in `AGENTS.md`.
4. As a separate follow-up change, optionally flip `HYBRID_ENABLED` to `true` and/or promote `HYBRID_SPARSE_BACKEND` to `auto` once the experiment supports it.

Rollback is a code rollback; persisted ChromaDB collections remain valid because dense vectors are unchanged.

## Open Questions

- Which ChromaDB version is the threshold for native sparse vectors? Resolve by inspecting the project's pinned `chromadb` and the upstream changelog at implementation time. Non-blocking for v1 because the default is `bm25`.

## Resolved Questions

- **Default sparse backend?** — `bm25` for v1 (Decision 2). Promotion to `auto` is a follow-up.
- **BM25 cache invalidation strategy?** — generation counter tied to `_write_lock`, lazy rebuild on next query (Decision 6).
- **Mixed-coverage behaviour?** — proceed and emit a one-shot WARNING per collection (Decision 7).
- **Should the BM25 fallback persist its index to disk between runs?** — no, rebuild per process (covered in Decision 6).
- **Should hybrid retrieval be exposed in the CLI in addition to MCP?** — yes, mirrored (Decision 8).
