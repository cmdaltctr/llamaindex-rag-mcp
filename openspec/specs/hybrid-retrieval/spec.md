# hybrid-retrieval Specification

## Purpose
TBD - created by archiving change rag-hybrid-retrieval. Update Purpose after archive.
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
At startup, the system SHALL select the sparse retrieval backend based on the `RETRIEVAL__HYBRID_SPARSE_BACKEND` env var, which SHALL accept `auto`, `native`, or `bm25`. **The default for v1 SHALL be `bm25`.** When `RETRIEVAL__HYBRID_SPARSE_BACKEND=auto`, the system SHALL run capability detection against the installed ChromaDB version and select `native` or `bm25` accordingly. When `RETRIEVAL__HYBRID_SPARSE_BACKEND=native` is set explicitly but the installed ChromaDB does not support sparse vectors, the system SHALL log a WARNING and fall back to `bm25` rather than crashing.

#### Scenario: v1 default is bm25
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND` is unset
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL use the BM25 fallback path
- **THEN** no capability detection SHALL be invoked

#### Scenario: Auto-detected native path
- **GIVEN** the installed ChromaDB version supports sparse vectors
- **AND** `RETRIEVAL__HYBRID_SPARSE_BACKEND=auto`
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL query ChromaDB for sparse rankings
- **THEN** no in-memory BM25 index SHALL be constructed

#### Scenario: Auto detection falls back when native is unsupported
- **GIVEN** the installed ChromaDB version does not support sparse vectors
- **AND** `RETRIEVAL__HYBRID_SPARSE_BACKEND=auto`
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL build or reuse an in-memory BM25 index over the active collection
- **THEN** sparse rankings SHALL come from the BM25 index

#### Scenario: Explicit native override falls back gracefully
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND=native` is set
- **AND** the installed ChromaDB does not support sparse vectors
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to the BM25 path without crashing

#### Scenario: Manual BM25 override
- **GIVEN** `RETRIEVAL__HYBRID_SPARSE_BACKEND=bm25` is set
- **WHEN** hybrid retrieval runs
- **THEN** the system SHALL use the BM25 fallback regardless of native capability detection

### Requirement: BM25 fallback index invalidates on every ingest write
The in-memory BM25 index SHALL be cached per collection and SHALL invalidate whenever ingestion writes to or deletes from that collection. The implementation SHALL maintain a per-collection generation counter that increments under the existing `_write_lock` on every successful write or delete (in `_embed_and_write_async`, `remove_document`, `remove_by_metadata`, and `remove_collection`). The sparse retriever SHALL compare the current generation against its cached generation on every hybrid query and SHALL rebuild the index lazily on the next query when the generation has advanced.

#### Scenario: Repeat queries reuse the BM25 cache
- **GIVEN** a collection with chunks indexed
- **AND** the BM25 fallback path is active
- **WHEN** two hybrid queries are issued in succession with no ingest between them
- **THEN** the BM25 index SHALL be built once
- **THEN** the second query SHALL reuse the cached index

#### Scenario: Ingest invalidates the cache
- **GIVEN** a hybrid query has just built and cached the BM25 index
- **WHEN** new chunks are ingested into the same collection
- **AND** another hybrid query runs against that collection
- **THEN** the BM25 index SHALL be rebuilt before the query is served
- **THEN** the rebuilt index SHALL include the newly ingested chunks

#### Scenario: Deletion invalidates the cache
- **GIVEN** a hybrid query has just built and cached the BM25 index
- **WHEN** chunks are deleted from the same collection (via `remove_document`, `remove_by_metadata`, or `remove_collection`)
- **AND** another hybrid query runs against that collection
- **THEN** the BM25 index SHALL be rebuilt before the query is served
- **THEN** the rebuilt index SHALL not contain the deleted chunks

### Requirement: Mixed-coverage collections trigger a one-shot warning
When the native sparse path is active and the system detects that some chunks in the active collection lack sparse vectors, the system SHALL emit a one-shot WARNING log on the first hybrid query against that collection within the process lifetime. The warning SHALL identify the collection and SHALL include a remediation hint advising re-ingestion for full hybrid coverage. Subsequent hybrid queries against the same collection within the same process SHALL NOT re-emit the warning. The BM25 path is unaffected because it always indexes every chunk it sees.

#### Scenario: First hybrid query on a partially-covered collection
- **GIVEN** the native sparse path is active
- **AND** a collection contains a mix of chunks with and without sparse vectors
- **WHEN** the first hybrid query against that collection runs in the process
- **THEN** the system SHALL emit a WARNING-level log naming the collection
- **THEN** the warning SHALL include a remediation hint to re-ingest

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
The system SHALL accept existing ChromaDB collections without forcing a re-ingestion. When the native sparse-vector path is selected and chunks lack sparse vectors, those chunks SHALL still participate in the dense ranking and SHALL be excluded from the sparse ranking only. RRF SHALL handle the missing-rank case naturally.

#### Scenario: Mixed coverage collection
- **GIVEN** a collection where some chunks have sparse vectors and others do not
- **WHEN** hybrid retrieval runs
- **THEN** all chunks SHALL participate in dense ranking
- **THEN** only chunks with sparse vectors SHALL participate in sparse ranking
- **THEN** the system SHALL NOT raise on chunks lacking sparse vectors

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

