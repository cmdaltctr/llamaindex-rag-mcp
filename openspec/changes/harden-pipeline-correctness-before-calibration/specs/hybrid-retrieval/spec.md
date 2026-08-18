## MODIFIED Requirements

### Requirement: BM25 fallback index is scoped by store and collection and invalidates on every mutation

The in-memory BM25 index SHALL be cached by a process-local store identity token plus collection name. Two distinct vector-store instances containing the same collection name MUST NOT share cached rows or term statistics. The store SHALL own its collection generation counter and SHALL increment it exactly once for every successful mutation that can change sparse-visible rows. The sparse retriever SHALL compare the current generation against the cached generation on every hybrid query and lazily rebuild only the affected store/collection namespace when the generation changes.

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
