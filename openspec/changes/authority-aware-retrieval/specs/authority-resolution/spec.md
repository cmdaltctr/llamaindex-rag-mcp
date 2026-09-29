# Spec Delta

## Purpose

Gives retrieval a second axis beside relevance: which of several legitimate, indexed texts controls a question, which merely qualify it, which are superseded, and where the corpus holds a conflict that no evidence resolves. Relations between sources are typed, directed and evidence-bearing; the resolver annotates candidates and never silently discards evidence.

## ADDED Requirements

### Requirement: Authority stage is opt-in and inert when disabled
The system SHALL expose an `authority` settings block on `EffectiveSettings` with `enabled` defaulting to `false`, resolved through the composition root and profile overlay like every other block. When `enabled` is `false`, the retrieval pipeline SHALL NOT import, construct or call any `core/authority/` component, and search results SHALL be byte-identical to the results produced before this capability existed.

#### Scenario: Disabled by default
- **WHEN** no `AUTHORITY__ENABLED` environment variable and no profile `authority.enabled` value is set
- **THEN** `EffectiveSettings.authority.enabled` is `false` and `search()` returns rows without `authority_status` or `authority_reason` keys and without a `conflicts` field

#### Scenario: Enabled through the documents profile
- **WHEN** the `documents` profile bundle sets `authority.enabled: true` and the collection is bound to that profile
- **THEN** the resolved `EffectiveSettings.authority.enabled` is `true` for that collection and `false` for a collection bound to the `codebase` profile

#### Scenario: Environment wins over profile
- **WHEN** the profile bundle sets `authority.enabled: true` and the environment sets `AUTHORITY__ENABLED=false`
- **THEN** the resolved value is `false`

### Requirement: Relation vocabulary is closed, directed and evidence-bearing
The system SHALL represent a relation between two sources as a directed edge `source_id → target_id` whose `relation` is one of exactly `corroborates`, `explains`, `specialises`, `restricts`, `amends`, `supersedes`, `conflicts_with`. Every edge SHALL carry `scope` (`document` or a clause/section reference), optional `effective_from` and `effective_until` ISO dates, `evidence_chunk_id`, `evidence_text`, `relation_origin` (one of `explicit_text`, `metadata`, `model`) and `confidence` in `[0.0, 1.0]`. An edge with `relation_origin=explicit_text` SHALL have `confidence=1.0`.

#### Scenario: Unknown relation rejected
- **WHEN** code attempts to construct an edge with `relation="replaces"`
- **THEN** construction raises `ValueError` naming the accepted vocabulary

#### Scenario: Explicit-text edge carries its evidence
- **WHEN** the deterministic extractor matches "This policy supersedes the Employee Handbook 2024" in a chunk of source B whose corpus contains a source A titled "Employee Handbook 2024"
- **THEN** an edge `B → A`, `relation=supersedes`, `scope=document`, `relation_origin=explicit_text`, `confidence=1.0`, `evidence_chunk_id` equal to the matching chunk's `chunk_id` and `evidence_text` containing the matched sentence is stored

### Requirement: Relations are stored per collection and rebuilt on source replacement
The system SHALL persist edges in a relation store scoped to the collection, keyed by `source_id`, independent of the vector rows and readable by both LanceDB and Chroma backed collections. When a source is replaced through the failure-safe replacement path, the system SHALL rebuild that source's outgoing edges from the new candidate and SHALL commit them only when the replacement commits. Deleting a source SHALL delete its outgoing edges and mark incoming edges from other sources as dangling without deleting them.

#### Scenario: Replacement rebuilds edges atomically
- **WHEN** source B is re-ingested with new content and the candidate write fails verification
- **THEN** the relation store still holds B's previous edges and no edge from the failed candidate

#### Scenario: Deletion leaves an auditable dangling edge
- **WHEN** source A is deleted and source B holds an edge `B → A`
- **THEN** the edge remains, its `target_present` flag is `false`, and the resolver ignores it

### Requirement: Deterministic extraction runs first and needs no model
When `authority.enabled` is `true`, ingestion SHALL run a rule-based extractor over each chunk after chunking and before write. The extractor SHALL detect at least: explicit supersession and replacement statements, explicit amendment and repeal statements naming a target document or clause, effective-date clauses, and clause or section references to another indexed source. It SHALL resolve the named target to a `source_id` by title or canonical path match and SHALL emit no edge when the target cannot be resolved to an indexed source. The deterministic tier SHALL NOT require network access or a model download.

#### Scenario: Effective-date clause populates the window
- **WHEN** a chunk reads "Effective from 1 January 2026, clause 12 of the Employment Contract is replaced by the following"
- **THEN** the emitted edge has `relation=amends`, `scope="clause 12"`, `effective_from="2026-01-01"` and targets the source whose title matches "Employment Contract"

#### Scenario: Unresolvable target emits nothing
- **WHEN** a chunk reads "This notice supersedes Circular 7/2019" and no indexed source matches that title
- **THEN** no edge is stored and the extractor records an `unresolved_target` diagnostic for the chunk

### Requirement: Model-assisted extraction is opt-in and quarantined
The system SHALL accept `authority.model_tier` with values `off` (default), `onnx_decision` and `nli`. When set to a value other than `off`, the extractor MAY type candidate pairs with a local model and SHALL emit those edges with `relation_origin=model` and the model's probability as `confidence`. Candidate pairs SHALL come from the existing document-graph similarity edges and from shared clause references, never from an all-pairs scan. Model-typed edges SHALL NOT be written into the document graph in `core/documents/`, and the resolver SHALL prefer an `explicit_text` edge over a `model` edge for the same ordered pair.

#### Scenario: Explicit text outranks a model guess
- **WHEN** the relation store holds `B → A supersedes (explicit_text)` and `B → A specialises (model, 0.81)`
- **THEN** the resolver applies `supersedes` and reports the explicit edge in `authority_reason`

#### Scenario: Model tier off emits no model edges
- **WHEN** `authority.model_tier` is `off`
- **THEN** ingestion loads no model and the relation store contains no edge with `relation_origin=model`

### Requirement: Resolver annotates candidates and drops none
When enabled, the retrieval pipeline SHALL call the resolver after fusion (or dense retrieval when hybrid is off) and before reranking. The resolver SHALL add `authority_status` and `authority_reason` to every row and SHALL return every input row. `authority_status` SHALL be one of `controlling`, `qualified`, `superseded`, `historical`, `unresolved_conflict`, `unknown`. Rows whose source has no edge to or from any other candidate's source SHALL be `unknown`.

#### Scenario: Superseded row stays in the result
- **WHEN** candidates include a chunk from A and a chunk from B, and the store holds `B → A supersedes` with `scope=document`
- **THEN** both rows are returned; A's row has `authority_status="superseded"` and B's row has `authority_status="controlling"`; `authority_reason` on both names the edge

#### Scenario: Partial amendment supersedes only the named scope
- **WHEN** candidates include chunks from clauses 3 and 7 of contract A, and the store holds `B → A amends` with `scope="clause 3"`
- **THEN** A's clause 3 row is `superseded`, A's clause 7 row is `controlling`, and B's row is `controlling`

### Requirement: Resolution follows a fixed ordering before declaring conflict
For each pair of candidate sources connected by one or more edges, the resolver SHALL apply relations in this order and stop at the first that applies: `corroborates` (both `controlling`), `explains` (both `controlling`, explained row gains `qualified_by`), `specialises` and `restricts` (both remain returned; the general row becomes `qualified`, the specific row `controlling`), `amends` and `supersedes` (target becomes `superseded` within scope and effective window), `conflicts_with` or no edge with contradictory dated rules (both become `unresolved_conflict`). The resolver SHALL NOT infer supersession from filenames, ingestion order, `source_version` or modification time.

#### Scenario: Specific rule does not obsolete the general rule
- **WHEN** candidates include a general leave policy A and an addendum B with `B → A specialises`
- **THEN** A is `qualified`, B is `controlling`, neither is `superseded`, and no `conflicts` entry is produced

#### Scenario: Newer file is not treated as supersession
- **WHEN** candidates include A and B, B has a later `source_version` and modification time, and the store holds no edge between them
- **THEN** both rows are `unknown` and neither is `superseded`

### Requirement: Unresolved conflicts are surfaced, not resolved by guess
When two candidate sources are both applicable to the query, state incompatible rules on the same scope, and no ordered relation resolves them, the resolver SHALL mark both rows `unresolved_conflict` and SHALL append an entry to a top-level `conflicts` list in the search result containing both `source_id`s, both `chunk_id`s and the reason no relation applied.

#### Scenario: Conflict reported to the caller
- **WHEN** A states a 30-day notice period, B states 60 days for the same clause, and the store holds `A ↔ B conflicts_with`
- **THEN** both rows are `unresolved_conflict` and the result's `conflicts` list holds one entry naming A and B

### Requirement: Point-in-time queries honour effective windows
`search()` and `search_documents` SHALL accept an optional `as_of` ISO-8601 date. When `as_of` is supplied and an edge `B → A supersedes|amends` has `effective_from` later than `as_of`, the resolver SHALL treat A as `controlling` and B as `historical` for that query. When `as_of` is absent, the resolver SHALL use the current date. An unparsable `as_of` SHALL produce a validation error in the MCP envelope, never an exception.

#### Scenario: Historical question retrieves the rule in force
- **WHEN** `B → A supersedes` has `effective_from="2025-01-01"` and the query passes `as_of="2024-03-15"`
- **THEN** A is `controlling`, B is `historical`

#### Scenario: Superseded is not deleted
- **WHEN** a source is `superseded` for the current date
- **THEN** it remains indexed and retrievable and is returned with `authority_status="superseded"`

### Requirement: Relevance and authority stay separate
The resolver SHALL NOT change `score`, `score_kind`, or candidate order, and the reranker SHALL receive the annotated rows unchanged in count. The reranker SHALL NOT read `authority_status`. Callers that want authority to influence ordering SHALL do so downstream of retrieval.

#### Scenario: Scores untouched
- **WHEN** the resolver runs over fused rows
- **THEN** every row's `score` and `score_kind` equal the values before the resolver ran, and the row count is unchanged

### Requirement: Authority decisions are explainable
`authority_reason` SHALL name the edge id, relation, `relation_origin` and, when present, the `evidence_text` excerpt that produced the status. With `diagnostics=true`, the result SHALL also include per-query resolver timing under `timing_report["authority_seconds"]` and the count of edges consulted.

#### Scenario: Reason cites the text
- **WHEN** a row is `superseded` because of an `explicit_text` edge
- **THEN** its `authority_reason` contains the relation, the origin `explicit_text` and the sentence that stated the supersession

### Requirement: Experiment 38 pre-registers the authority metrics
Before any default flip, the change SHALL run Experiment 38 with a synthetic corpus covering full supersession, general + specific, partial amendment, corroboration and unresolved conflict, then one real corpus of a UK statute and its amending instruments. It SHALL report stale authority rate, incorrect supersession rate, scope resolution accuracy, conflict detection recall and historical authority accuracy against a pre-registered gate for each, and SHALL report ablations for deterministic-only, model tier added, and resolver without the reconciliation step.

#### Scenario: Gate failure blocks promotion
- **WHEN** Experiment 38 reports stale authority rate above its pre-registered gate
- **THEN** the `documents` profile keeps `authority.enabled: false` and the report records the failure as the reason
