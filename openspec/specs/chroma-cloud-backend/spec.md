# chroma-cloud-backend Specification

## Purpose
Define explicit, secure selection between local embedded ChromaDB and hosted
Chroma Cloud while preserving one vector-store behaviour contract.
## Requirements
### Requirement: Chroma deployment mode SHALL be explicit

The system SHALL expose `CHROMA_MODE` with accepted values `local` and
`cloud`. The default SHALL remain `local`. Mode selection SHALL NOT depend on
whether an API key happens to be present.

#### Scenario: Default local mode

- **WHEN** `CHROMA_MODE` is unset
- **THEN** the system SHALL use the existing local persistent Chroma client
- **AND** no cloud credentials or network connection SHALL be required

#### Scenario: Explicit cloud mode

- **WHEN** `CHROMA_MODE=cloud`
- **THEN** the system SHALL use Chroma Cloud for every collection operation
- **AND** it SHALL NOT read or write the local Chroma persist directory

#### Scenario: Unknown mode

- **WHEN** `CHROMA_MODE` contains any value other than `local` or `cloud`
- **THEN** settings validation SHALL fail with a message listing the accepted values

### Requirement: Embedding compute and vector storage SHALL be independent

The embedding-provider axis and Chroma deployment-mode axis SHALL be resolved
independently. The system SHALL support full local, cloud compute with local
storage, full cloud, and local compute with cloud storage. It SHALL NOT add a
third selector named `hybrid`.

#### Scenario: Cloud embeddings with local Chroma

- **WHEN** the embedding provider is cloud and `CHROMA_MODE=local`
- **THEN** embeddings SHALL be produced by the selected cloud provider and stored in local Chroma

#### Scenario: Full cloud

- **WHEN** the embedding provider is cloud and `CHROMA_MODE=cloud`
- **THEN** embeddings SHALL be produced by the selected cloud provider and stored in Chroma Cloud

#### Scenario: Local embeddings with Chroma Cloud

- **WHEN** the embedding provider is local and `CHROMA_MODE=cloud`
- **THEN** llama.cpp SHALL produce embeddings and Chroma Cloud SHALL store them

### Requirement: Cloud mode SHALL validate credentials and connection

Cloud mode SHALL require `CHROMA_CLOUD_API_KEY`. Tenant and database values
MAY be omitted together so the cloud client resolves them from the API key.
If either `CHROMA_CLOUD_TENANT` or `CHROMA_CLOUD_DATABASE` is supplied, both
SHALL be supplied. Cloud client construction and a lightweight connection
check SHALL complete during runtime setup.

#### Scenario: Missing API key

- **WHEN** `CHROMA_MODE=cloud` and `CHROMA_CLOUD_API_KEY` is empty
- **THEN** startup SHALL fail before ingestion or retrieval begins
- **AND** the error SHALL name the missing variable without exposing a secret

#### Scenario: Tenant and database supplied together

- **WHEN** cloud mode supplies an API key, tenant, and database
- **THEN** all three values SHALL be passed to the cloud client

#### Scenario: Partial tenant/database pair

- **WHEN** exactly one of tenant or database is supplied
- **THEN** settings validation SHALL fail and name both required variables

#### Scenario: Authentication or network failure

- **WHEN** the cloud connection check fails
- **THEN** startup SHALL fail with an actionable cloud connection error
- **AND** the system SHALL NOT silently create or use a local index

### Requirement: Cloud credentials SHALL remain secret

Cloud API keys SHALL be sourced from environment settings only. They SHALL
NOT appear in YAML defaults, profiles, logs, runtime summaries, exceptions,
experiment result files, or object representations produced by project code.

#### Scenario: Runtime summary in cloud mode

- **WHEN** the runtime summary is rendered in cloud mode
- **THEN** it MAY include mode, tenant, and database identifiers
- **AND** it SHALL NOT include the API key or an API-key prefix

#### Scenario: Connection failure message

- **WHEN** cloud authentication fails
- **THEN** the returned message SHALL omit the submitted key

### Requirement: Cloud collections SHALL preserve local Chroma semantics

Cloud and local modes SHALL expose the same collection lifecycle, upsert,
query, metadata filtering, deletion, and dimension locking through the
existing vector-store contract. Process-local generation counters SHALL
remain valid within a one-writer-per-collection execution boundary.

#### Scenario: Identical operation contract

- **WHEN** the same operation is invoked against local and cloud modes
- **THEN** both modes SHALL return the same project-level result shape

#### Scenario: Embedding model changes

- **WHEN** a collection was indexed with one embedding dimension and a later
  write uses another dimension
- **THEN** the store SHALL reject the mismatched write
- **AND** documentation SHALL require a fresh collection or re-ingestion when
  the embedding model changes

### Requirement: Collection identity SHALL prevent incompatible embedding reuse

Every newly indexed collection SHALL store its effective embedding provider,
embedding model, and immutable index identity in collection metadata. Existing
metadata such as profile tags SHALL be merged, not overwritten. Before a write
or query, the active provider/model SHALL match the stored identity. A match on
vector dimension alone SHALL NOT be accepted as model compatibility.

#### Scenario: Same dimension from different models

- **WHEN** an existing collection was indexed by model A and model B produces
  vectors with the same dimension
- **THEN** the operation SHALL fail before query or write because model identity differs

#### Scenario: Existing collection metadata is preserved

- **WHEN** embedding identity is added to a collection with profile metadata
- **THEN** the profile metadata SHALL remain present with its original values

#### Scenario: Compatible reuse

- **WHEN** provider, model, corpus/config identity, and dimension all match
- **THEN** the existing collection MAY be reused without re-embedding

#### Scenario: Experiment cells reuse an immutable index

- **WHEN** separate processes run evaluation cells against one cloud database
- **THEN** the coordinator SHALL build one collection per immutable index identity
- **AND** retrieval-only cells and repetitions SHALL reuse it read-only
- **AND** at most one process SHALL mutate the collection during the run

#### Scenario: Deterministic experiment collection name

- **WHEN** an experiment creates an index
- **THEN** its collection name SHALL derive from experiment ID, corpus/config
  identity, embedding provider/model, parser, and chunking configuration
- **AND** it SHALL satisfy Chroma's collection-name rules
- **AND** cell ID and repetition SHALL remain in checkpoint/result metadata,
  not the collection name, unless they change the indexed content

#### Scenario: Same-collection multi-process mutation

- **WHEN** more than one process must mutate the same cloud collection while
  BM25 caching is active
- **THEN** documentation SHALL state that this change does not guarantee
  cross-process sparse-cache invalidation
- **AND** the workload SHALL use one writer or disable reuse of the sparse cache

### Requirement: Chroma modes SHALL require explicit backend selection and the optional extra

Local and cloud Chroma operation SHALL be available only when
`VECTOR_STORE=chroma` is explicitly selected and both optional packages are
installed. Chroma settings SHALL never alter an unselected LanceDB route.

#### Scenario: Chroma Cloud selected correctly

- **GIVEN** explicit `VECTOR_STORE=chroma`
- **AND** `CHROMA_MODE=cloud`
- **AND** both Chroma optional packages and valid credentials are present
- **WHEN** runtime setup completes
- **THEN** the Chroma Cloud client MUST serve every collection operation

#### Scenario: Chroma settings with LanceDB selected

- **GIVEN** `VECTOR_STORE=lancedb`
- **AND** `CHROMA_MODE=cloud` or any non-empty Chroma cloud credential is explicitly set
- **WHEN** settings are validated
- **THEN** backend mismatch MUST be reported before credential completeness
- **AND** the error MUST name the incompatible setting names without exposing values

#### Scenario: Chroma backend without the complete extra

- **GIVEN** explicit `VECTOR_STORE=chroma`
- **AND** either optional Chroma package is absent
- **WHEN** composition begins
- **THEN** startup MUST fail with backend-specific installation guidance
- **AND** it MUST NOT fall back to LanceDB

### Requirement: Chroma SHALL remain quarantined until authoritative patch evidence converges

Chroma packages SHALL remain optional and LanceDB SHALL remain the base default
until a separately reviewed official release has accepted fix and advisory
evidence. Upstream assertion alone SHALL not end quarantine.

#### Scenario: No accepted patched release exists

- **WHEN** dependency policy is evaluated
- **THEN** Chroma packages MUST remain confined to the optional extra
- **AND** LanceDB MUST remain the base default

#### Scenario: Candidate patched release appears

- **GIVEN** an official maintainer PyPI release exists
- **AND** a fixing commit or release note is linked
- **AND** the project's named authoritative advisory excludes that version
- **AND** renewed security review accepts the candidate, preferably with an isolated regression test
- **WHEN** all evidence agrees
- **THEN** the project MAY open a separate OpenSpec reassessment
- **AND** no automatic base-dependency or default reversal may occur

#### Scenario: Authorities disagree

- **WHEN** upstream, the authoritative advisory or renewed review disagree about the candidate
- **THEN** quarantine MUST remain in force

