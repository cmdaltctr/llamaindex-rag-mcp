# hybrid-retrieval Specification

## Purpose
Defines opt-in hybrid retrieval: dense vector search fused with a
sparse backend through Reciprocal Rank Fusion (k=60), with a BM25
fallback index that is scoped per store and collection and invalidated
on every mutation. Mixed-coverage collections warn once, and the mode
is reachable from both MCP and CLI.

## Requirements
### Requirement: Hybrid retrieval mode is opt-in
The system SHALL provide an opt-in hybrid retrieval mode that fuses dense vector search with sparse keyword retrieval. When `hybrid=True` is requested via the MCP tool or `retrieval.search()`, the system SHALL run both retrievers and fuse their rankings. When `hybrid=False` (the default), the system SHALL behave exactly as the existing dense-only pipeline.

#### Scenario: Default behaviour is unchanged
- **GIVEN** documents have been indexed
- **WHEN** `search_documents(query="X")` is called without `hybrid`
- **THEN** the system SHALL run the existing dense-only retrieval path
- **THEN** results SHALL be identical in shape and content to pre-change behaviour for the same inputs

#### Scenario: Hybrid retrieval enabled returns fused results
- **GIVEN** documents have been indexed
- **WHEN** `search_documents(query="X", hybrid=True)` is called
- **THEN** the system SHALL run both dense and sparse retrievers
- **THEN** the system SHALL fuse rankings using Reciprocal Rank Fusion before any reranking step

### Requirement: Reciprocal Rank Fusion with k=60
The system SHALL fuse dense and sparse rankings using the Reciprocal Rank Fusion formula `score(d) = Σ_r 1 / (k + rank_r(d))` with `k = 60` as the default constant. The constant SHALL be configurable via the `RETRIEVAL__HYBRID_RRF_K` env var.

#### Scenario: RRF score combines both retrievers
- **GIVEN** a chunk ranked 3rd by dense retrieval and 5th by sparse retrieval
- **WHEN** RRF fusion runs with `k=60`
- **THEN** the chunk's fused score SHALL equal `1/(60+3) + 1/(60+5)`

#### Scenario: Chunk ranked by only one retriever
- **GIVEN** a chunk ranked 2nd by dense retrieval and absent from the sparse top results
- **WHEN** RRF fusion runs
- **THEN** the chunk's fused score SHALL include only the dense reciprocal-rank term

#### Scenario: Configurable k via env
- **GIVEN** `RETRIEVAL__HYBRID_RRF_K=80` is set
- **WHEN** hybrid retrieval runs
- **THEN** RRF SHALL use `k = 80` instead of the default

### Requirement: Sparse backend defaults to BM25 for v1
At startup, the system SHALL select the sparse retrieval backend based on the `RETRIEVAL__HYBRID_SPARSE_BACKEND` env var, which SHALL accept `auto`, `native`, or `bm25`. **The default for v1 SHALL be `bm25`.** When `RETRIEVAL__HYBRID_SPARSE_BACKEND=auto`, the system SHALL run capability detection against the **selected vector store** (through its registry capability metadata and a native full-text-search probe) and select `native` or `bm25` accordingly — not against any specific vendor runtime version. When `RETRIEVAL__HYBRID_SPARSE_BACKEND=native` is set explicitly but the selected store cannot issue native sparse queries, the system SHALL log a WARNING and fall back to `bm25` rather than crashing.

#### Scenario: v1 default is bm25
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND` is unset
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL use the BM25 fallback path
- **THEN** no capability detection SHALL be invoked

#### Scenario: Auto-detected native path
- **GIVEN** the selected vector store supports native sparse queries
- **AND** `RETRIEVAL__HYBRID_SPARSE_BACKEND=auto`
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL issue native sparse rankings through the selected store
- **THEN** no in-memory BM25 index SHALL be constructed

#### Scenario: Auto detection falls back when native is unsupported
- **GIVEN** the selected vector store does not support native sparse queries
- **AND** `RETRIEVAL__HYBRID_SPARSE_BACKEND=auto`
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL build or reuse an in-memory BM25 index over the active collection
- **THEN** sparse rankings SHALL come from the BM25 index

#### Scenario: Explicit native override falls back gracefully
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND=native` is set
- **AND** the selected vector store does not support native sparse queries
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to the BM25 path without crashing

#### Scenario: Manual BM25 override
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND=bm25` is set
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL use the BM25 fallback regardless of native capability detection

### Requirement: BM25 fallback index is scoped by store and collection and invalidates on every mutation

The in-memory BM25 index SHALL be cached by a process-local store identity token plus collection name. Two distinct vector-store instances containing the same collection name MUST NOT share cached rows or term statistics.

Cache validity SHALL be decided by the collection's **durable data version**
where the store exposes one, so that a mutation performed by another process
invalidates the cache. Where the store exposes no durable version, the
process-local generation counter SHALL be used and the reduced guarantee
(same-process mutations only) SHALL be logged once per collection.

The store SHALL continue to own its collection generation counter and SHALL increment it exactly once for every successful mutation that can change sparse-visible rows. The sparse retriever SHALL compare the current tagged validity token against the cached one on every hybrid query and lazily rebuild only the affected store/collection namespace when it changes.

A BM25 rebuild SHALL read the validity token before fetching rows and again
before publishing the cache. It SHALL publish only when both durable tokens are
equal, or when both tagged local-fallback tokens are equal. If they differ, the
unstable build SHALL be discarded and retried within a bounded policy rather
than cached.

The default sparse backend remains BM25. Experiment 19 pre-registered the
comparison against native FTS and recorded native failing the latency gate at
138.7× BM25's warm p50; this change fixes BM25's invalidation rather than
switching away from it.

#### Scenario: Repeat queries reuse one store-scoped cache
- **GIVEN** one store instance contains collection `documents`
- **AND** the BM25 fallback path is active
- **WHEN** two hybrid queries run with no intervening mutation
- **THEN** the BM25 index SHALL be built once for that store/collection namespace
- **AND** the second query SHALL reuse it

#### Scenario: Same collection name in another store is isolated
- **GIVEN** store A and store B both contain a collection named `documents`
- **AND** their contents differ
- **AND** their generation values happen to be equal
- **WHEN** BM25 is queried against A and then B in the same process
- **THEN** B MUST build/use an index from B's rows
- **AND** no row originating only from A may appear due to cache reuse

#### Scenario: Mutation advances generation exactly once
- **GIVEN** a store/collection generation value `g`
- **WHEN** a successful write, precomputed upsert, filtered delete, or collection delete mutates sparse-visible state
- **THEN** the store generation SHALL become `g+1`
- **AND** orchestration code SHALL NOT apply a second generation bump for the same mutation

#### Scenario: Repeat queries reuse the BM25 cache
- **GIVEN** a collection with chunks indexed
- **AND** the BM25 fallback path is active
- **WHEN** two hybrid queries are issued in succession with no mutation between them
- **THEN** the BM25 index SHALL be built once for that store/collection namespace
- **THEN** the second query SHALL reuse the cached index

#### Scenario: Ingest invalidates the cache
- **GIVEN** a hybrid query has just built and cached the BM25 index
- **WHEN** new chunks are ingested into the same collection
- **AND** another hybrid query runs against that collection
- **THEN** the BM25 index SHALL be rebuilt before the query is served
- **THEN** the rebuilt index SHALL include the newly ingested chunks

#### Scenario: Deletion invalidates the cache
- **GIVEN** a hybrid query has just built and cached the BM25 index
- **WHEN** chunks are deleted from the same collection (via document removal, metadata-filtered removal, or collection removal)
- **AND** another hybrid query runs against that collection
- **THEN** the BM25 index SHALL be rebuilt before the query is served
- **THEN** the rebuilt index SHALL not contain the deleted chunks

#### Scenario: A write from another process invalidates the cache

- **GIVEN** a server process has built and cached a BM25 index for a collection
- **AND** a separate process, such as the watch daemon, ingests a new document
  into that same collection
- **WHEN** the server process serves the next hybrid query
- **THEN** the BM25 index SHALL be rebuilt before the query is served
- **THEN** the rebuilt index SHALL include the newly ingested chunks

#### Scenario: Mutation during a BM25 build is not cached

- **GIVEN** a BM25 rebuild has read its starting validity token
- **WHEN** another process mutates or recreates the collection before the
  rebuild is published
- **THEN** the ending validity token MUST differ
- **AND** the partial or stale build MUST NOT be installed in the cache
- **AND** retry behaviour MUST be bounded

#### Scenario: Durable capability transition invalidates fallback cache

- **GIVEN** a BM25 cache built while a pre-existing Lance table had no epoch
  and used a tagged local-generation token
- **WHEN** a writer installs an epoch and completes a mutation
- **THEN** the next hybrid query MUST compare a tagged durable token
- **AND** MUST rebuild rather than treating its numeric members as equal to the
  old fallback token

#### Scenario: A store without a durable version states its limit

- **GIVEN** a store exposing no durable data version
- **WHEN** the BM25 cache is used for one of its collections
- **THEN** the process-local generation counter SHALL be used
- **AND** a warning naming the reduced guarantee SHALL be logged once per
  collection per process

### Requirement: Mixed-coverage collections trigger a one-shot warning
When the native sparse path is active and the system detects that some chunks in the active collection lack sparse coverage (on LanceDB, lack full-text-search index coverage; on a sparse-vector store, lack sparse vectors), the system SHALL emit a one-shot WARNING log on the first hybrid query against that collection within the process lifetime. The warning SHALL identify the collection and SHALL include a remediation hint advising re-ingestion or index creation for full hybrid coverage. Subsequent hybrid queries against the same collection within the same process SHALL NOT re-emit the warning. The BM25 path is unaffected because it always indexes every chunk it sees.

#### Scenario: First hybrid query on a partially-covered collection
- **GIVEN** the native sparse path is active
- **AND** a collection contains a mix of covered and uncovered chunks
- **WHEN** the first hybrid query against that collection runs in the process
- **THEN** the system SHALL emit a WARNING-level log naming the collection
- **THEN** the warning SHALL include a remediation hint to re-ingest or create the index

#### Scenario: Subsequent queries on the same collection do not re-warn
- **GIVEN** a previous hybrid query has already emitted the mixed-coverage warning
- **WHEN** another hybrid query runs against the same collection in the same process
- **THEN** the system SHALL NOT emit the mixed-coverage warning again

#### Scenario: BM25 path skips the warning entirely
- **GIVEN** the BM25 fallback path is active
- **WHEN** a hybrid query runs against any collection
- **THEN** the system SHALL NOT emit the mixed-coverage warning

### Requirement: Hybrid is exposed via both MCP and CLI
The `hybrid: bool` parameter SHALL be exposed via the MCP `search_documents` tool and via the CLI `search` subcommand as a `--hybrid / --no-hybrid` flag. Both surfaces SHALL default to `False`. Both surfaces SHALL pass the parameter through to `retrieval.search()` unchanged.

#### Scenario: MCP tool exposes hybrid
- **WHEN** an MCP client calls `search_documents(query="X", hybrid=True)`
- **THEN** retrieval SHALL run in hybrid mode
- **WHEN** an MCP client calls `search_documents(query="X")` without `hybrid`
- **THEN** retrieval SHALL run in dense-only mode

#### Scenario: CLI exposes --hybrid flag
- **WHEN** the operator runs `rag-mcp search "X" --hybrid`
- **THEN** retrieval SHALL run in hybrid mode
- **WHEN** the operator runs `rag-mcp search "X"` without `--hybrid`
- **THEN** retrieval SHALL run in dense-only mode

### Requirement: Hybrid retrieval recovers rare-term failure cases
The system SHALL produce correct results for rare-term queries that pure dense retrieval misses, including the regression case captured in the reranker calibration experiment.

#### Scenario: Rare-term regression test
- **GIVEN** a fixture corpus containing the documented rare-term failure case
- **WHEN** the rare-term query is run with `hybrid=True`
- **THEN** the correct chunk SHALL appear in the top results
- **THEN** the same query with `hybrid=False` SHALL still pass any thresholds it currently passes (no regression in the dense-only default)

### Requirement: Hybrid experiment fails loudly when hybrid retrieval is unavailable
Experiment 9 SHALL fail before running ingestion or query evaluation if the active `retrieval.search()` implementation does not expose a `hybrid` parameter. The experiment SHALL NOT silently fall back to dense-only retrieval for hybrid cells.

#### Scenario: Missing hybrid parameter aborts experiment
- **GIVEN** `retrieval.search()` does not accept a `hybrid` parameter
- **WHEN** Experiment 9 starts
- **THEN** the experiment SHALL raise a clear error before running any cell
- **THEN** no `hybrid_bm25` cell SHALL be evaluated using the dense-only path

### Requirement: Hybrid retrieval composes with the existing reranker
The fused candidate list produced by hybrid retrieval SHALL be passed to the existing cross-encoder reranker when `rerank=True`. The reranker SHALL receive the configured fetch pool size derived from Tier 2 settings (`RETRIEVAL__RERANK_FETCH_MULTIPLIER`, `RETRIEVAL__RERANK_MAX_FETCH`).

#### Scenario: Hybrid + rerank end-to-end
- **WHEN** `search_documents(query="X", hybrid=True, rerank=True, top_k=5)` is called
- **THEN** retrieval SHALL run dense and sparse retrievers, fuse them via RRF
- **THEN** the top fused candidates up to the configured rerank pool size SHALL be passed to the reranker
- **THEN** the reranker SHALL return the top 5 reranked results

### Requirement: Existing collections are usable without re-ingestion
The system SHALL accept existing collections without forcing a re-ingestion. When the native sparse path is selected and chunks lack sparse coverage (an unindexed row on an FTS backend, or a missing sparse vector on a sparse-vector backend), those chunks SHALL still participate in the dense ranking and SHALL be excluded from the sparse ranking only. RRF SHALL handle the missing-rank case naturally.

#### Scenario: Mixed coverage collection
- **GIVEN** a collection where some chunks have sparse coverage and others do not
- **WHEN** hybrid retrieval runs
- **THEN** all chunks SHALL participate in dense ranking
- **THEN** only covered chunks SHALL participate in sparse ranking
- **THEN** the system SHALL NOT raise on chunks lacking sparse coverage

### Requirement: Native sparse placeholder must not silently degrade to dense-only
If the native sparse backend is selected but the implementation cannot issue a real native sparse query, the system SHALL either fall back to the BM25 sparse retriever with a WARNING or fail loudly before any native-hybrid evaluation is reported. The system SHALL NOT represent native hybrid as successful when the sparse side is an empty placeholder.

#### Scenario: Native selected without implemented sparse query
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND=native` is selected
- **AND** no real native sparse query implementation is available
- **WHEN** hybrid retrieval is requested
- **THEN** the system SHALL warn and use the BM25 sparse path, or raise a clear unsupported-backend error before evaluation
- **THEN** native hybrid SHALL NOT silently return dense-only results through an empty sparse ranking

### Requirement: Hybrid result diagnostics are explicit
The system SHALL make the public result-shape decision for hybrid diagnostics explicit. If diagnostic fields such as `id`, `fused_score`, `dense_rank`, `sparse_rank`, and `fused_rank` are returned to MCP/CLI callers, they SHALL be documented and tested as public fields. If they are internal diagnostics, they SHALL be stripped from public `search_documents` / CLI results and exposed only through experiment/debug-specific paths.

#### Scenario: Public hybrid result shape is pinned
- **GIVEN** a hybrid search returns fused results
- **WHEN** results are returned through MCP or CLI
- **THEN** all included fields SHALL be documented as public output or excluded from the public response
- **THEN** tests SHALL fail if internal diagnostic fields leak unintentionally

### Requirement: Hybrid configuration via environment
The system SHALL expose the following environment variables for hybrid retrieval:

| Variable | Default | Description |
|----------|---------|-------------|
| `RETRIEVAL__HYBRID_ENABLED` | `false` | Default value of `hybrid` parameter when not specified by the caller |
| `RETRIEVAL__HYBRID_RRF_K` | `60` | RRF constant `k` |
| `RETRIEVAL__HYBRID_SPARSE_BACKEND` | `bm25` | One of `auto`, `native`, `bm25` (v1 default is `bm25`; promotion to `auto` belongs in a follow-up change) |

#### Scenario: Default values
- **WHEN** none of the hybrid env vars are set
- **THEN** `RETRIEVAL__HYBRID_ENABLED` SHALL be `false`
- **THEN** `RETRIEVAL__HYBRID_RRF_K` SHALL be `60`
- **THEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND` SHALL be `bm25`

### Requirement: Hybrid metadata filters constrain every retrieval branch

When `metadata_filter` is supplied to hybrid retrieval, the same logical filter SHALL constrain dense and sparse candidate eligibility before RRF. Fusion SHALL NOT re-introduce a row that fails the caller's filter merely because it ranked highly in BM25/native sparse retrieval.

#### Scenario: BM25 ranks a forbidden row highly
- **GIVEN** a metadata filter selects category `allowed`
- **AND** a category `forbidden` row is the strongest BM25 keyword match
- **WHEN** hybrid retrieval runs
- **THEN** the forbidden row MUST NOT be present in the sparse ranking passed to RRF
- **AND** the final result set MUST contain only filter-matching rows

#### Scenario: Dense and hybrid enforce equivalent filters
- **GIVEN** a supported metadata filter and a fixed collection
- **WHEN** dense-only and hybrid searches run with that filter
- **THEN** every returned row from both modes MUST satisfy the filter

### Requirement: Reciprocal Rank Fusion scores are rank-fusion scores, not dense similarities

The system SHALL continue to compute RRF using `score(d) = sum(1/(k+rank))`, but SHALL classify the result as an RRF/fusion score. Dense `similarity_threshold` SHALL NOT be applied directly to the RRF numeric value. Threshold semantics are governed by the `retrieval-score-semantics` capability.

#### Scenario: High RRF rank with ordinary dense threshold
- **GIVEN** `rrf_k=60`
- **AND** a document ranks first in both dense and sparse lists
- **WHEN** its RRF score is computed
- **THEN** the score SHALL be `2/61`
- **AND** a dense threshold such as `0.3` SHALL NOT be compared directly against `2/61`

### Requirement: Hybrid diagnostics expose effective sparse backend and cache namespace

When diagnostics are requested, the system SHALL expose the effective sparse backend used after capability/fallback resolution and enough cache/store identity to distinguish one store/collection namespace from another without exposing secrets or filesystem-sensitive data unnecessarily.

#### Scenario: Native request falls back to BM25
- **GIVEN** native sparse is requested but the runtime falls back to BM25
- **WHEN** diagnostics are requested
- **THEN** the effective backend SHALL be reported as `bm25`
- **AND** an experiment that declared native as the manipulated backend SHALL be able to abort before reporting native results

### Requirement: Concrete sparse backends resolve through one contract
The `bm25` and `native` sparse backend names SHALL resolve through one sparse-query contract. The `auto` value SHALL remain a capability-selection policy and SHALL resolve to a concrete registered backend before query execution.

#### Scenario: BM25 is selected
- **WHEN** the effective sparse backend is `bm25`
- **THEN** hybrid retrieval SHALL execute the registered BM25 implementation

#### Scenario: Native is selected and supported
- **WHEN** the effective sparse backend is `native`
- **AND** the selected vector store supports native sparse queries
- **THEN** hybrid retrieval SHALL execute a real registered native sparse implementation
- **AND** SHALL NOT report an empty placeholder ranking as successful

#### Scenario: Auto resolves to native when supported
- **WHEN** the effective sparse backend is `auto`
- **AND** the selected vector store supports native sparse queries
- **THEN** resolution SHALL select the registered `native` backend before query execution

#### Scenario: Auto resolves to BM25 when native is unsupported
- **WHEN** the effective sparse backend is `auto`
- **AND** the selected vector store does not support native sparse queries
- **THEN** resolution SHALL select the registered `bm25` backend without emitting the explicit-native fallback warning

#### Scenario: Unknown concrete backend is configured
- **WHEN** sparse backend resolution produces an unregistered concrete name
- **THEN** startup SHALL fail and list the registered sparse backend names

### Requirement: Native fallback remains explicit
The system SHALL retain BM25 fallback when native sparse capability is absent or fails safely, and SHALL emit a visible warning before returning results.

#### Scenario: Explicit native is unsupported
- **WHEN** `native` is selected but the selected vector store cannot issue native sparse queries
- **THEN** the system SHALL warn and execute BM25
- **AND** SHALL NOT identify the resulting sparse ranking as native

#### Scenario: Native fails safely at query time
- **WHEN** the selected native backend raises a supported runtime error during a sparse query
- **THEN** the hybrid pipeline SHALL fall back to BM25 for that query
- **AND** SHALL emit the visible fallback warning before returning results
- **AND** SHALL NOT label the resulting sparse ranking as native

#### Scenario: Existing collection has mixed sparse coverage
- **WHEN** native retrieval runs against a collection with partial sparse coverage
- **THEN** every chunk SHALL remain eligible for dense ranking
- **AND** the existing one-shot remediation warning SHALL remain in effect

### Requirement: Native FTS lifecycle is specified and durable
The native sparse implementation on LanceDB SHALL define its full-text-search index lifecycle explicitly: additive initial creation on the stored `text` column, refresh after writes and source replacements, delete and stale-node handling, freshness diagnostics distinct from indexed/unindexed coverage, and failure diagnostics that route to BM25 fallback. After a write, replacement, or deletion, the index SHALL be treated as stale until refresh completes. A native query SHALL NOT return stale index results as successful: it SHALL establish freshness or warn and fall back to BM25. The process-local store generation counter SHALL NOT be used as durable FTS-index maintenance; it SHALL remain a cache-invalidation mechanism for the in-memory BM25 index.

#### Scenario: FTS index is created additively
- **WHEN** native sparse is first used on a collection without an FTS index
- **THEN** index creation SHALL be additive and explicitly triggered
- **AND** the collection SHALL remain queryable throughout

#### Scenario: Mutations make freshness explicit
- **WHEN** chunks are written, a source is replaced, or rows are deleted after an FTS index exists
- **THEN** the FTS index SHALL be considered stale until refresh completes
- **AND** a native query SHALL either establish a fresh state that covers new rows and excludes stale or deleted rows, or warn and fall back to BM25
- **AND** diagnostics SHALL report the resulting fresh, stale, or fallback state

#### Scenario: Partial FTS coverage is distinguishable
- **WHEN** a collection contains both indexed and unindexed rows
- **THEN** diagnostics SHALL distinguish indexed from unindexed coverage
- **AND** unindexed rows SHALL remain eligible in dense rankings

