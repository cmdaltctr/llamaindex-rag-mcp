## 1. Configuration and capability detection

- [x] 1.1 Add `HYBRID_ENABLED` (default `false`), `HYBRID_RRF_K` (default `60`), and `HYBRID_SPARSE_BACKEND` (default **`bm25`** for v1 per design Decision 2) to `config.py`
- [x] 1.2 Update `.env.example` with the new variables and an inline comment explaining that promotion of `HYBRID_SPARSE_BACKEND` to `auto` is a follow-up change
- [x] 1.3 Implement capability detection routine (`_detect_native_sparse_capability`) — only invoked when `HYBRID_SPARSE_BACKEND=auto`
- [x] 1.4 Implement explicit `native` override fallback: if `HYBRID_SPARSE_BACKEND=native` and the installed ChromaDB does not support sparse vectors, log a WARNING and fall back to `bm25` rather than crashing
- [x] 1.5 Inspect the project's pinned `chromadb` version and record whether the native path is currently available (informational, captured in the experiment notes)

## 2. Sparse retriever (BM25 path — primary for v1)

- [x] 2.1 Add `rank_bm25` as an optional dependency under a `hybrid` extra in `pyproject.toml`
- [x] 2.2 Create `src/rag_mcp/sparse_retriever.py` with a `BM25SparseRetriever` class that lazily builds a BM25 index over the chunks of a given collection
- [x] 2.3 Implement a default English tokeniser (lowercase + simple word-boundary split + standard stop-word list); structure the code so an env-var-driven custom tokeniser can be plugged in later
- [x] 2.4 Provide a `query(query_text, top_n)` method returning `[(rank, doc_id, text, metadata), ...]`
- [x] 2.5 Add unit tests for tokenisation, rank ordering, and an empty-collection edge case
- [x] 2.6 Document the in-memory BM25 footprint behaviour in the module docstring

## 3. BM25 cache invalidation (Decision 6)

- [x] 3.1 Add a per-collection generation counter dict (process-local, guarded by `_write_lock`) to `ingestion.py`
- [x] 3.2 Increment the counter inside `_embed_and_write_async` after every successful write
- [x] 3.3 Increment the counter inside `remove_document`, `remove_by_metadata`, and `remove_collection`
- [x] 3.4 Have `BM25SparseRetriever` cache `(collection_name, generation, bm25_index)` and rebuild lazily when the live generation has advanced past the cached one
- [x] 3.5 Add a test asserting two consecutive hybrid queries with no ingest between them reuse the same BM25 index instance
- [x] 3.6 Add a test asserting a hybrid query, an ingest, and another hybrid query rebuild the BM25 index and include the newly ingested chunks
- [x] 3.7 Add a test asserting a `remove_document` between two hybrid queries triggers a rebuild and excludes the deleted chunks
- [x] 3.8 Add a test asserting `remove_collection` invalidates the cache for that collection

## 4. Sparse retriever (native ChromaDB path — deferred follow-up)

The v1 change deliberately ships the BM25 sparse backend as the default and supported path. Native ChromaDB sparse storage/query support is deferred to a separate follow-up change once the pinned ChromaDB runtime exposes a stable local API.

- [x] 4.1 Defer native sparse collection configuration to a future native-sparse change; v1 keeps `HYBRID_SPARSE_BACKEND=bm25` as the default and falls back safely when `native` is unavailable
- [x] 4.2 Defer native sparse writes during ingestion to the same follow-up; no v1 collection migration is required for BM25 hybrid retrieval
- [x] 4.3 Defer a real native sparse query helper to the same follow-up; selected native mode currently warns and falls back to the BM25 sparse retriever rather than silently degrading to dense-only
- [x] 4.4 Detect mixed-coverage collections (some chunks have sparse vectors, some do not) and emit a one-shot WARNING per `(collection, process)` pair on first hybrid query against such a collection — see task 6.x for matching tests
- [x] 4.5 Ensure the warning is suppressed entirely when the BM25 path is active

## 5. RRF fusion

- [x] 5.1 Implement `reciprocal_rank_fusion(rankings: list[list[doc_id]], k: int) -> dict[doc_id, float]`
- [x] 5.2 Implement an `rrf_with_metadata` helper that returns a sorted list of dicts containing the fused score and the chunk text/metadata
- [x] 5.3 Add a unit test covering the worked example from the spec (`1/(60+3) + 1/(60+5)`)
- [x] 5.4 Add a unit test covering chunks present in only one ranking
- [x] 5.5 Add a unit test covering an empty sparse ranking (BM25 index empty, dense ranking present) — fused output equals the dense ranking with no errors raised

## 6. Hybrid retrieval entry point and CLI / MCP exposure (Decision 8)

- [x] 6.1 Add `hybrid: bool = False` to `retrieval.search()` signature
- [x] 6.2 When `hybrid=True`, run dense and sparse retrievers concurrently (`asyncio.gather` or thread offload) and fuse via RRF
- [x] 6.3 Pass the fused candidate list (sized per Tier 2's `RERANK_FETCH_MULTIPLIER` / `RERANK_MAX_FETCH`) to the existing reranker when `rerank=True`
- [x] 6.4 Preserve existing dense-only behaviour exactly when `hybrid=False`
- [x] 6.5 Add `hybrid: bool = False` parameter to the MCP `search_documents` tool and pass through
- [x] 6.6 Add `--hybrid / --no-hybrid` flag to the CLI `search` subcommand in `cli.py`, defaulting to `False`, mirroring the existing `--rerank` pattern
- [x] 6.7 Add a CLI test asserting `rag-mcp search "X" --hybrid` runs in hybrid mode and `rag-mcp search "X"` without the flag does not

## 7. Mixed-coverage warning (Decision 7)

- [x] 7.1 Implement the one-shot warning state (`_warned_collections: set[str]` keyed on collection name, process-local)
- [x] 7.2 Emit the WARNING the first time a hybrid query against a partially-covered collection runs, naming the collection and including a remediation hint to re-ingest
- [x] 7.3 Add a test asserting the first hybrid query on a mixed-coverage collection emits the warning
- [x] 7.4 Add a test asserting subsequent hybrid queries on the same collection in the same process do not re-emit the warning
- [x] 7.5 Add a test asserting BM25-path queries do not emit the warning at all

## 8. Tests

- [x] 8.1 Add a fixture corpus reproducing the documented rare-term failure case (Colosseum-style)
- [x] 8.2 Add a regression test that fails on dense-only retrieval and passes with `hybrid=True`
- [x] 8.3 Add an end-to-end test combining `hybrid=True, rerank=True` and verifying the reranker receives the fused candidate list
- [x] 8.4 Add a test verifying `hybrid=False` default is byte-identical to current behaviour
- [x] 8.5 Add a test verifying capability detection paths with mocked ChromaDB versions (auto → bm25 when unsupported, auto → native when supported, explicit native fallback to bm25)

## 9. Experiment

- [x] 9.1 Confirm `experiments/9-hybrid-retrieval-2026-05-27/protocol.md` is up to date with the v1 default `HYBRID_SPARSE_BACKEND=bm25`, the named Colosseum regression case, and the rare-term + semantic + mixed query partitions
- [x] 9.2 Build the corpus per the protocol — `corpus/exp1-fixtures/` (Colosseum continuity), `corpus/rare-term-pack/` (5–10 docs with exact-match identifiers), `corpus/semantic-pack/` (5 docs with paraphrase-only queries)
- [x] 9.3 Pre-write 18–25 ground-truth queries in `experiments/9-hybrid-retrieval-2026-05-27/ground-truth.json` partitioned across the three categories with the Colosseum and one BM25-only query as named cases
- [x] 9.4 Implement `experiments/9-hybrid-retrieval-2026-05-27/run_eval.py` running the cell grid (mode × reranker), saving raw per-query results and fusion source ranks
- [x] 9.5 Remove any `TypeError` fallback in `run_eval.py`; Experiment 9 MUST fail loudly if `retrieval.search()` does not expose a `hybrid` parameter, rather than silently evaluating hybrid cells through the dense-only signature
- [x] 9.6 Add an explicit startup assertion in `run_eval.py` that `retrieval.search()` includes `hybrid` in its signature before any ingestion or query cell runs
- [x] 9.7 Fix the experiment ingestion path to call the actual ingestion API (`ingest_path_async` via `asyncio.run(...)`, or add/restore a sync `ingest_path` wrapper) so Experiment 9 runs against the current codebase
- [x] 9.8 Ensure hybrid result rows expose dense/sparse/fused rank diagnostics for the expected gold chunk and persist them in `eval_results.json`
- [x] 9.9 Run **Experiment 9/9a** end-to-end and evaluate pass criteria. Experiment 9 verified the small-regression corpus but saturated; Experiment 9a reran on FreshStack LangChain with 10,025 parent documents and confirmed that hybrid BM25/RRF improves first-stage retrieval without reranking, but hybrid + rerank does not meet the default-promotion quality gates.
- [x] 9.10 Record the failed default-promotion outcome and follow-up path. The implicated issue is not BM25/RRF fusion itself: Experiment 9a shows BM25 contribution on improved identifier-heavy queries. The production reranker path erases the first-stage hybrid gains, so reranker policy/model/pool-size investigation is deferred to a separate follow-up change and Experiment 10 rather than blocking opt-in hybrid v1.
- [x] 9.11 Write `results.md` only after the full mode × reranker grid has run and pass criteria have been evaluated
- [x] 9.12 Record the recommendation for the future `HYBRID_ENABLED` and `HYBRID_SPARSE_BACKEND` default flips in `results.md` — to be acted on as a separate small follow-up change

## 10. Documentation

- [x] 10.1 Update `AGENTS.md` to describe the hybrid retrieval feature, the env vars, the v1 default of `bm25`, and explicitly state that the ÷30 reranker scaling factor remains valid
- [x] 10.2 Document the BM25 cache invalidation behaviour in `AGENTS.md`'s "Non-Obvious Rules" section
- [x] 10.3 Update the README or relevant docs with a usage example for both MCP and CLI surfaces
- [x] 10.4 Note the in-memory BM25 fallback's memory characteristics

## 11. ADR — record the architectural decisions

After implementation passes validation, write **ADR-017: Hybrid Retrieval with Reciprocal Rank Fusion** under `docs/adr/017-hybrid-retrieval-rrf.md` following the existing ADR convention. Use ADR-014 as the structural template — one ADR per OpenSpec change, with sub-decisions as numbered bullets inside the Decision section.

- [x] 11.1 Capture the eight sub-decisions from `design.md` as numbered bullets in the Decision section:
  1. Reciprocal Rank Fusion with `k=60` (Cormack, Clarke & Buettcher 2009) as the fusion function; chosen over weighted convex combination because RRF needs no per-corpus tuning
  2. Sparse backend defaults to `bm25` for v1 (not `auto`); `HYBRID_SPARSE_BACKEND` accepts `auto`, `native`, `bm25`; explicit `native` falls back to `bm25` with a WARNING when ChromaDB doesn't support sparse vectors
  3. Hybrid is opt-in via `HYBRID_ENABLED=false` and a per-call `hybrid: bool = False` parameter; the default flip is a deliberate follow-up change after the calibration experiment
  4. Reranker integration is unchanged — fused candidate list feeds the existing cross-encoder; ADR-005's ÷30 threshold scaling remains valid because reranker scoring is unchanged
  5. No automatic re-ingestion required; partial coverage handled naturally by RRF's missing-rank semantics
  6. BM25 cache invalidation tied to a per-collection generation counter incremented under the existing `_write_lock` in `_embed_and_write_async`, `remove_document`, `remove_by_metadata`, and `remove_collection`; sparse retriever caches `(collection_name, generation, bm25_index)` and rebuilds lazily on stale generation
  7. Mixed-coverage collections trigger a one-shot WARNING per `(collection, process)` pair on the native path; suppressed on the BM25 path which always indexes everything
  8. Hybrid exposed via both MCP `search_documents` and CLI `search --hybrid / --no-hybrid`, mirroring the existing `--rerank` parity
- [x] 11.2 In Consequences, note: positive (rare-term failure mode from `experiments/reranker-threshold-calibration-2026-05-12/` is now recoverable, RRF needs no per-corpus tuning, ÷30 calibration preserved, CLI / MCP parity); negative (in-memory BM25 footprint scales with collection size, optional `rank_bm25` dependency, two retrievers running concurrently increase latency); neutral (deliberate `bm25` v1 default means the native path stays opt-in until the experiment validates it).
- [x] 11.3 Record the experiment recommendation for the future flip of `HYBRID_ENABLED` and `HYBRID_SPARSE_BACKEND` defaults — note that the flip is intentionally a separate small change.
- [x] 11.4 In Alternatives Considered, record: weighted convex combination `α·dense + (1-α)·sparse` (rejected — needs per-corpus tuning, brittle to score-distribution shift); requiring a specific ChromaDB version (rejected — forces an upgrade for an opt-in feature); `auto` as the v1 default (rejected — moving-target API yields mystery failures); refuse hybrid on partially-covered collections until re-ingested (rejected — too aggressive); silently proceed on partial coverage (rejected — score changes look like a bug); persistent on-disk BM25 index (rejected — overkill for v1); MCP-only exposure (rejected — CLI surface already has slots for the flag).
- [x] 11.5 Cross-reference ADR-005 (reranker — fed by the fused candidate list, its ÷30 calibration explicitly preserved), ADR-014 (async path — hybrid retrieval composes with `asyncio.gather`-based concurrency), and ADR-016 (Tier 2 — `RERANK_FETCH_MULTIPLIER` / `RERANK_MAX_FETCH` size the rerank pool fed from the fused list). Reference the OpenSpec change directory and the new `experiments/hybrid-retrieval-<date>/` directory.
- [x] 11.6 Update `docs/adr/ADR_README.md` index table with the new ADR row.
- [x] 11.7 Set status to `Accepted` once the change is archived; the future default-flip change will get its own short ADR or amend ADR-017 with a status note.

## 12. Validation

- [x] 12.1 Run `openspec validate rag-hybrid-retrieval --strict`
- [x] 12.2 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm coverage thresholds remain intact
- [x] 12.3 Confirm Experiment 9/9a has been run end-to-end and `results.md` records the default recommendation. The pass criteria for flipping `HYBRID_ENABLED=true` were not met; v1 remains opt-in with `HYBRID_ENABLED=false` and `HYBRID_SPARSE_BACKEND=bm25`, and reranker policy is deferred to a follow-up Experiment 10.
- [x] 12.4 Verify backward compatibility on an existing on-disk ChromaDB collection (`hybrid=False` path returns identical results to pre-change)
- [x] 12.5 Confirm ADR-017 is published, indexed, and cross-referenced before archiving the OpenSpec change

## 13. Merge-blocking / should fix before claiming complete

These review items MUST remain unchecked until addressed. The change MUST NOT be claimed complete, merged, archived, or used to set ADR-017 to `Accepted` while any item in this section remains open.

- [x] 13.1 Replace the native sparse placeholder behaviour with an explicit safe path: if native sparse retrieval is selected but cannot issue a real sparse query, it MUST either fall back to the BM25 sparse retriever with a WARNING or fail loudly before evaluating hybrid cells. It MUST NOT silently return an empty sparse ranking that makes native hybrid behave like dense-only.
- [x] 13.2 Update mixed-coverage detection to use bounded/paged metadata scanning (for example `iter_collection_metadatas` / `CHROMA_SCAN_PAGE_SIZE`) instead of a single `collection.get(..., limit=collection.count())` call. Add or update a test so large collections cannot regress to unbounded metadata loads.
- [x] 13.3 Decide and pin the public hybrid result shape. If hybrid diagnostics (`id`, `fused_score`, `dense_rank`, `sparse_rank`, `fused_rank`) are public, document them in the MCP/CLI/README or relevant guide and add tests that assert the shape. If they are internal-only, strip them before returning public results and provide a separate path for Experiment 9 diagnostics.
- [x] 13.4 Add a deterministic rare-term regression test reproducing the Colosseum-style failure mode: dense-only retrieval misses the gold chunk because it is below the dense cut-off, while `hybrid=True` recovers it through BM25/RRF.
- [x] 13.5 Keep the experiment/archive-dependent items unchecked until their prerequisites are actually complete: Experiment 9/9a end-to-end run and `results.md` (9.9–9.12, 12.3) are complete, and the default recommendation is recorded as keep hybrid opt-in. ADR-017 `Accepted` status remains tied to archiving (11.7).
