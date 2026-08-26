## ADDED Requirements

### Requirement: Dense retrieval exposes canonical higher-is-better scores

Every `VectorStore` implementation SHALL convert its native vector-distance or vector-score output at the adapter boundary into a canonical dense retrieval score consumed by core retrieval. Core retrieval SHALL NOT assume ChromaDB L2 distance semantics or apply a hard-coded native-distance transform to every backend.

The store-neutral dense result SHALL expose at least `id`, `document`, `metadata`, `score`, and `score_kind`. `score_kind` SHALL identify the semantic contract of the score rather than the backend implementation name.

#### Scenario: Chroma and Lance use the same core path
- **GIVEN** identical precomputed embeddings and documents are loaded into ChromaDB and LanceDB
- **WHEN** the same query vector is issued
- **THEN** both adapters SHALL return higher-is-better canonical scores
- **AND** core retrieval SHALL not branch on the selected vector-store name to interpret those scores

#### Scenario: Unsupported native score semantics
- **GIVEN** a future vector-store backend cannot map its native ranking output to the required canonical score contract
- **WHEN** the backend is constructed or queried
- **THEN** it MUST fail clearly rather than returning a misleading `score`

### Requirement: Canonical dense score behaviour is contract-tested across stores

The repository SHALL maintain deterministic cross-store fixtures with known vector geometry. Each registered production vector store SHALL be tested for expected neighbour ordering, monotonicity, documented range and threshold behaviour.

The current `dense_similarity_v1` contract SHALL NOT require exact numeric equality between backends unless their native L2 distance scaling is independently proven identical. Cross-store parity is defined by the documented bounded range, higher-is-better direction, exact-match maximum, and monotonic ordering invariants.

#### Scenario: Known nearest neighbour
- **GIVEN** a fixture with one exact vector match and progressively more distant vectors
- **WHEN** each registered vector-store backend is queried
- **THEN** the exact match MUST rank first
- **AND** canonical scores MUST decrease monotonically with fixture distance according to the declared score contract

### Requirement: Score kinds are not compared across incompatible scales

The retrieval pipeline SHALL treat dense canonical scores, Reciprocal Rank Fusion scores and reranker scores as distinct score kinds. A threshold calibrated for one score kind MUST NOT be applied directly to another score kind without an explicit calibrated transform for that transition.

#### Scenario: RRF score is not a dense similarity
- **GIVEN** hybrid retrieval is enabled without reranking
- **WHEN** RRF produces a fused score
- **THEN** the fused score MUST NOT be compared directly with the dense `similarity_threshold`

#### Scenario: Successful reranker produces final thresholdable score
- **GIVEN** reranking succeeds
- **WHEN** final filtering runs
- **THEN** the threshold logic SHALL use the reranker score kind and its explicitly calibrated threshold transform

#### Scenario: Reranker fails
- **GIVEN** reranking was requested but inference failed
- **WHEN** final filtering runs
- **THEN** the pipeline SHALL revert to the appropriate pre-rerank score-kind threshold rule
- **AND** diagnostics SHALL state the fallback reason

### Requirement: Positive similarity threshold in non-reranked hybrid mode has explicit semantics

When hybrid retrieval runs without a successful reranker and `similarity_threshold > 0`, the threshold SHALL be evaluated against dense semantic evidence before fusion. RRF itself SHALL remain rank fusion only. A sparse-only result lacking qualifying dense evidence MUST NOT be represented as satisfying the caller's positive minimum dense similarity.

#### Scenario: Sparse-only candidate with positive dense threshold
- **GIVEN** a chunk appears in BM25 results but has no dense candidate meeting the requested similarity threshold
- **WHEN** hybrid retrieval runs without reranking
- **THEN** that chunk MUST NOT be returned as satisfying the positive dense similarity threshold

#### Scenario: Zero threshold preserves sparse recovery
- **GIVEN** `similarity_threshold=0.0`
- **WHEN** hybrid retrieval runs without reranking
- **THEN** sparse-only candidates MAY participate in RRF normally

### Requirement: Diagnostics expose the score kind used for filtering

Experiment/debug diagnostics SHALL expose enough information to determine which score kind was used for final filtering and whether any calibrated transform was applied.

#### Scenario: Experiment manifest
- **WHEN** an experiment records a retrieval cell
- **THEN** it SHALL record the final threshold value, the score kind to which it applied, and the reason for any threshold transform
