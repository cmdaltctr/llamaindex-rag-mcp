## MODIFIED Requirements

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
