## 1. Configuration and capability detection

- [ ] 1.1 Add `HYBRID_ENABLED` (default `false`), `HYBRID_RRF_K` (default `60`), and `HYBRID_SPARSE_BACKEND` (default **`bm25`** for v1 per design Decision 2) to `config.py`
- [ ] 1.2 Update `.env.example` with the new variables and an inline comment explaining that promotion of `HYBRID_SPARSE_BACKEND` to `auto` is a follow-up change
- [ ] 1.3 Implement capability detection routine (`_detect_native_sparse_capability`) — only invoked when `HYBRID_SPARSE_BACKEND=auto`
- [ ] 1.4 Implement explicit `native` override fallback: if `HYBRID_SPARSE_BACKEND=native` and the installed ChromaDB does not support sparse vectors, log a WARNING and fall back to `bm25` rather than crashing
- [ ] 1.5 Inspect the project's pinned `chromadb` version and record whether the native path is currently available (informational, captured in the experiment notes)

## 2. Sparse retriever (BM25 path — primary for v1)

- [ ] 2.1 Add `rank_bm25` as an optional dependency under a `hybrid` extra in `pyproject.toml`
- [ ] 2.2 Create `src/rag_mcp/sparse_retriever.py` with a `BM25SparseRetriever` class that lazily builds a BM25 index over the chunks of a given collection
- [ ] 2.3 Implement a default English tokeniser (lowercase + simple word-boundary split + standard stop-word list); structure the code so an env-var-driven custom tokeniser can be plugged in later
- [ ] 2.4 Provide a `query(query_text, top_n)` method returning `[(rank, doc_id, text, metadata), ...]`
- [ ] 2.5 Add unit tests for tokenisation, rank ordering, and an empty-collection edge case
- [ ] 2.6 Document the in-memory BM25 footprint behaviour in the module docstring

## 3. BM25 cache invalidation (Decision 6)

- [ ] 3.1 Add a per-collection generation counter dict (process-local, guarded by `_write_lock`) to `ingestion.py`
- [ ] 3.2 Increment the counter inside `_embed_and_write_async` after every successful write
- [ ] 3.3 Increment the counter inside `remove_document`, `remove_by_metadata`, and `remove_collection`
- [ ] 3.4 Have `BM25SparseRetriever` cache `(collection_name, generation, bm25_index)` and rebuild lazily when the live generation has advanced past the cached one
- [ ] 3.5 Add a test asserting two consecutive hybrid queries with no ingest between them reuse the same BM25 index instance
- [ ] 3.6 Add a test asserting a hybrid query, an ingest, and another hybrid query rebuild the BM25 index and include the newly ingested chunks
- [ ] 3.7 Add a test asserting a `remove_document` between two hybrid queries triggers a rebuild and excludes the deleted chunks
- [ ] 3.8 Add a test asserting `remove_collection` invalidates the cache for that collection

## 4. Sparse retriever (native ChromaDB path — opt-in)

- [ ] 4.1 If native sparse vectors are available and selected, extend `_get_chroma_collection` to configure sparse vector storage
- [ ] 4.2 Extend ingestion to write sparse representations alongside dense vectors when the native path is active
- [ ] 4.3 Add a retrieval helper that issues the sparse-vector query and returns the same `(rank, doc_id, text, metadata)` shape as the BM25 path
- [ ] 4.4 Detect mixed-coverage collections (some chunks have sparse vectors, some do not) and emit a one-shot WARNING per `(collection, process)` pair on first hybrid query against such a collection — see task 6.x for matching tests
- [ ] 4.5 Ensure the warning is suppressed entirely when the BM25 path is active

## 5. RRF fusion

- [ ] 5.1 Implement `reciprocal_rank_fusion(rankings: list[list[doc_id]], k: int) -> dict[doc_id, float]`
- [ ] 5.2 Implement an `rrf_with_metadata` helper that returns a sorted list of dicts containing the fused score and the chunk text/metadata
- [ ] 5.3 Add a unit test covering the worked example from the spec (`1/(60+3) + 1/(60+5)`)
- [ ] 5.4 Add a unit test covering chunks present in only one ranking
- [ ] 5.5 Add a unit test covering an empty sparse ranking (BM25 index empty, dense ranking present) — fused output equals the dense ranking with no errors raised

## 6. Hybrid retrieval entry point and CLI / MCP exposure (Decision 8)

- [ ] 6.1 Add `hybrid: bool = False` to `retrieval.search()` signature
- [ ] 6.2 When `hybrid=True`, run dense and sparse retrievers concurrently (`asyncio.gather` or thread offload) and fuse via RRF
- [ ] 6.3 Pass the fused candidate list (sized per Tier 2's `RERANK_FETCH_MULTIPLIER` / `RERANK_MAX_FETCH`) to the existing reranker when `rerank=True`
- [ ] 6.4 Preserve existing dense-only behaviour exactly when `hybrid=False`
- [ ] 6.5 Add `hybrid: bool = False` parameter to the MCP `search_documents` tool and pass through
- [ ] 6.6 Add `--hybrid / --no-hybrid` flag to the CLI `search` subcommand in `cli.py`, defaulting to `False`, mirroring the existing `--rerank` pattern
- [ ] 6.7 Add a CLI test asserting `rag-mcp search "X" --hybrid` runs in hybrid mode and `rag-mcp search "X"` without the flag does not

## 7. Mixed-coverage warning (Decision 7)

- [ ] 7.1 Implement the one-shot warning state (`_warned_collections: set[str]` keyed on collection name, process-local)
- [ ] 7.2 Emit the WARNING the first time a hybrid query against a partially-covered collection runs, naming the collection and including a remediation hint to re-ingest
- [ ] 7.3 Add a test asserting the first hybrid query on a mixed-coverage collection emits the warning
- [ ] 7.4 Add a test asserting subsequent hybrid queries on the same collection in the same process do not re-emit the warning
- [ ] 7.5 Add a test asserting BM25-path queries do not emit the warning at all

## 8. Tests

- [ ] 8.1 Add a fixture corpus reproducing the documented rare-term failure case (Colosseum-style)
- [ ] 8.2 Add a regression test that fails on dense-only retrieval and passes with `hybrid=True`
- [ ] 8.3 Add an end-to-end test combining `hybrid=True, rerank=True` and verifying the reranker receives the fused candidate list
- [ ] 8.4 Add a test verifying `hybrid=False` default is byte-identical to current behaviour
- [ ] 8.5 Add a test verifying capability detection paths with mocked ChromaDB versions (auto → bm25 when unsupported, auto → native when supported, explicit native fallback to bm25)

## 9. Experiment

- [ ] 9.1 Confirm `experiments/9-hybrid-retrieval-2026-05-27/protocol.md` is up to date with the v1 default `HYBRID_SPARSE_BACKEND=bm25`, the named Colosseum regression case, and the rare-term + semantic + mixed query partitions
- [ ] 9.2 Build the corpus per the protocol — `corpus/exp1-fixtures/` (Colosseum continuity), `corpus/rare-term-pack/` (5–10 docs with exact-match identifiers), `corpus/semantic-pack/` (5 docs with paraphrase-only queries)
- [ ] 9.3 Pre-write 18–25 ground-truth queries in `experiments/9-hybrid-retrieval-2026-05-27/ground-truth.json` partitioned across the three categories with the Colosseum and one BM25-only query as named cases
- [ ] 9.4 Implement `experiments/9-hybrid-retrieval-2026-05-27/run_eval.py` running the cell grid (mode × reranker), saving raw per-query results and fusion source ranks
- [ ] 9.5 Run **Experiment 9** end-to-end and confirm: Colosseum hits top-1 under at least one hybrid cell; rare-term Hit@1 lifts ≥ 10 pp vs dense-only at the same reranker setting; semantic Hit@1 stays within −2 pp of dense-only; hybrid + rerank P95 ≤ 1.5 × dense-only + rerank P95
- [ ] 9.6 If Experiment 9 fails its pass criteria: revisit the implicated tasks (Colosseum miss → tasks 2.3 tokeniser / 5.x RRF math; rare-term shortfall → task 6.3 reranker pool; semantic regression → review BM25 tokeniser stop-words; latency breach → tasks 3.x BM25 cache and 6.2 concurrent dispatch), re-run the experiment, loop until criteria pass
- [ ] 9.7 Record the recommendation for the future `HYBRID_ENABLED` and `HYBRID_SPARSE_BACKEND` default flips in `results.md` — to be acted on as a separate small follow-up change

## 10. Documentation

- [ ] 10.1 Update `AGENTS.md` to describe the hybrid retrieval feature, the env vars, the v1 default of `bm25`, and explicitly state that the ÷30 reranker scaling factor remains valid
- [ ] 10.2 Document the BM25 cache invalidation behaviour in `AGENTS.md`'s "Non-Obvious Rules" section
- [ ] 10.3 Update the README or relevant docs with a usage example for both MCP and CLI surfaces
- [ ] 10.4 Note the in-memory BM25 fallback's memory characteristics

## 11. ADR — record the architectural decisions

After implementation passes validation, write **ADR-017: Hybrid Retrieval with Reciprocal Rank Fusion** under `docs/adr/017-hybrid-retrieval-rrf.md` following the existing ADR convention. Use ADR-014 as the structural template — one ADR per OpenSpec change, with sub-decisions as numbered bullets inside the Decision section.

- [ ] 11.1 Capture the eight sub-decisions from `design.md` as numbered bullets in the Decision section:
  1. Reciprocal Rank Fusion with `k=60` (Cormack, Clarke & Buettcher 2009) as the fusion function; chosen over weighted convex combination because RRF needs no per-corpus tuning
  2. Sparse backend defaults to `bm25` for v1 (not `auto`); `HYBRID_SPARSE_BACKEND` accepts `auto`, `native`, `bm25`; explicit `native` falls back to `bm25` with a WARNING when ChromaDB doesn't support sparse vectors
  3. Hybrid is opt-in via `HYBRID_ENABLED=false` and a per-call `hybrid: bool = False` parameter; the default flip is a deliberate follow-up change after the calibration experiment
  4. Reranker integration is unchanged — fused candidate list feeds the existing cross-encoder; ADR-005's ÷30 threshold scaling remains valid because reranker scoring is unchanged
  5. No automatic re-ingestion required; partial coverage handled naturally by RRF's missing-rank semantics
  6. BM25 cache invalidation tied to a per-collection generation counter incremented under the existing `_write_lock` in `_embed_and_write_async`, `remove_document`, `remove_by_metadata`, and `remove_collection`; sparse retriever caches `(collection_name, generation, bm25_index)` and rebuilds lazily on stale generation
  7. Mixed-coverage collections trigger a one-shot WARNING per `(collection, process)` pair on the native path; suppressed on the BM25 path which always indexes everything
  8. Hybrid exposed via both MCP `search_documents` and CLI `search --hybrid / --no-hybrid`, mirroring the existing `--rerank` parity
- [ ] 11.2 In Consequences, note: positive (rare-term failure mode from `experiments/reranker-threshold-calibration-2026-05-12/` is now recoverable, RRF needs no per-corpus tuning, ÷30 calibration preserved, CLI / MCP parity); negative (in-memory BM25 footprint scales with collection size, optional `rank_bm25` dependency, two retrievers running concurrently increase latency); neutral (deliberate `bm25` v1 default means the native path stays opt-in until the experiment validates it).
- [ ] 11.3 Record the experiment recommendation for the future flip of `HYBRID_ENABLED` and `HYBRID_SPARSE_BACKEND` defaults — note that the flip is intentionally a separate small change.
- [ ] 11.4 In Alternatives Considered, record: weighted convex combination `α·dense + (1-α)·sparse` (rejected — needs per-corpus tuning, brittle to score-distribution shift); requiring a specific ChromaDB version (rejected — forces an upgrade for an opt-in feature); `auto` as the v1 default (rejected — moving-target API yields mystery failures); refuse hybrid on partially-covered collections until re-ingested (rejected — too aggressive); silently proceed on partial coverage (rejected — score changes look like a bug); persistent on-disk BM25 index (rejected — overkill for v1); MCP-only exposure (rejected — CLI surface already has slots for the flag).
- [ ] 11.5 Cross-reference ADR-005 (reranker — fed by the fused candidate list, its ÷30 calibration explicitly preserved), ADR-014 (async path — hybrid retrieval composes with `asyncio.gather`-based concurrency), and ADR-016 (Tier 2 — `RERANK_FETCH_MULTIPLIER` / `RERANK_MAX_FETCH` size the rerank pool fed from the fused list). Reference the OpenSpec change directory and the new `experiments/hybrid-retrieval-<date>/` directory.
- [ ] 11.6 Update `docs/adr/ADR_README.md` index table with the new ADR row.
- [ ] 11.7 Set status to `Accepted` once the change is archived; the future default-flip change will get its own short ADR or amend ADR-017 with a status note.

## 12. Validation

- [ ] 12.1 Run `openspec validate rag-hybrid-retrieval --strict`
- [ ] 12.2 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm coverage thresholds remain intact
- [ ] 12.3 Confirm Experiment 9 (`experiments/9-hybrid-retrieval-2026-05-27/`) has been run end-to-end, all pass criteria are met, and `results.md` records the recommendation for the future `HYBRID_ENABLED` / `HYBRID_SPARSE_BACKEND` default flip
- [ ] 12.4 Verify backward compatibility on an existing on-disk ChromaDB collection (`hybrid=False` path returns identical results to pre-change)
- [ ] 12.5 Confirm ADR-017 is published, indexed, and cross-referenced before archiving the OpenSpec change
