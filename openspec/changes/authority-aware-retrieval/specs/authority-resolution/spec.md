# Spec Delta

## Purpose

Gives retrieval a second axis beside relevance: which of several legitimate, indexed texts controls a question, which merely qualify it, which are superseded or not yet in force, and where the corpus holds a conflict that no evidence resolves. Relations between sources are typed, directed and evidence-bearing; the resolver annotates candidates and never silently discards evidence.

## ADDED Requirements

### Requirement: Authority stage is opt-in and inert when disabled
The system SHALL expose an `authority` settings block on `EffectiveSettings` with `enabled` defaulting to `false`, resolved like every other block. When the stage does not run, the system SHALL NOT import `core/authority/`, and the output of `search()`, `Engine.search`, MCP `search_documents`, the HTTP search route, `Engine.ingest` and answer evidence SHALL equal the output captured before this capability existed.

#### Scenario: Disabled by default
- **WHEN** no `AUTHORITY__ENABLED` environment variable, no `omrs.jsonc` value and no profile `authority.enabled` value is set
- **THEN** `EffectiveSettings.authority.enabled` is `false` and `search()` returns rows without `authority_status`, `authority_reason` or `authority_conflicts` keys

#### Scenario: Every surface matches the golden output when off
- **WHEN** the golden fixtures captured on v4 HEAD run with authority off through `search()`, `Engine.search`, MCP `search_documents`, the HTTP search route and `Engine.ingest`
- **THEN** each output equals its golden file

#### Scenario: Enabled through the documents profile
- **WHEN** the `documents` profile bundle sets `authority.enabled: true` and the collection is bound to that profile
- **THEN** the resolved `EffectiveSettings.authority.enabled` is `true` for that collection and `false` for a collection bound to the `codebase` profile

#### Scenario: Environment wins over profile
- **WHEN** the profile bundle sets `authority.enabled: true` and the environment sets `AUTHORITY__ENABLED=false`
- **THEN** the resolved value is `false`

### Requirement: User-profile graphs reach the resolver through a graph operation
The operation catalogue SHALL offer an `authority.resolve` operation with evidence in and evidence out, an `enabled` parameter tied to the `authority.enabled` lever, an `as_of` parameter, and a bypass that passes evidence through unchanged. It SHALL use the same resolver as the built-in path. The canonical search and answer templates SHALL include the step only when asked.

#### Scenario: Graph step annotates like the built-in path
- **WHEN** a user-profile Search graph includes an enabled `authority.resolve` step and the built-in path runs with `authority.enabled=true` over the same fixtures
- **THEN** both return the same rows with the same `authority_status`, `authority_reason` and `authority_conflicts` values

#### Scenario: Disabled step is a pass-through
- **WHEN** the `authority.resolve` step is disabled
- **THEN** its output evidence equals its input evidence

#### Scenario: Default templates are unchanged
- **WHEN** the canonical templates are built without the authority option
- **THEN** no template contains an `authority.resolve` node

### Requirement: Relation vocabulary is closed, directed and evidence-bearing
An edge SHALL be directed `source_id → target_id` with `relation` one of exactly `corroborates`, `explains`, `specialises`, `restricts`, `amends`, `supersedes`, `conflicts_with`. It SHALL carry `scope` (`document` or a clause or section reference), optional `effective_from` and `effective_until` ISO dates, `evidence_chunk_id`, `evidence_text`, `relation_origin` (`explicit_text` or `model`), `confidence` in `[0.0, 1.0]` and `target_present`. An `explicit_text` edge SHALL have `confidence=1.0`.

#### Scenario: Unknown relation rejected
- **WHEN** code attempts to construct an edge with `relation="replaces"`
- **THEN** construction raises `ValueError` naming the accepted vocabulary

#### Scenario: Explicit-text edge carries its evidence
- **WHEN** the deterministic extractor matches "This policy supersedes the Employee Handbook 2024" in a chunk of source B whose collection contains a source A titled "Employee Handbook 2024"
- **THEN** an edge `B → A`, `relation=supersedes`, `scope=document`, `relation_origin=explicit_text`, `confidence=1.0`, `evidence_chunk_id` equal to the matching chunk's `chunk_id` and `evidence_text` containing the matched sentence is stored

### Requirement: Relations live in a local sidecar per collection
The system SHALL store edges and pending references in files under `<store root>/_authority/<collection>/`, where the store root is the local LanceDB folder or the local Chroma persist folder. The files SHALL NOT be part of the vector rows and SHALL be written atomically. When the store has no local folder, the system SHALL NOT run the stage and SHALL say so.

#### Scenario: Sidecar does not change the collection list
- **WHEN** a sidecar folder exists for collection `docs` on a LanceDB or local Chroma store
- **THEN** `list_collections()` returns the same names as without the folder

#### Scenario: Chroma Cloud is not supported
- **WHEN** `omrs authority rebuild docs` runs with `CHROMA_MODE=cloud`
- **THEN** the command exits non-zero with a message that the relation sidecar needs a local store folder

#### Scenario: Search on an unsupported store stays unchanged
- **WHEN** `authority.enabled` is `true`, the store is Chroma Cloud, and `search()` runs with diagnostics
- **THEN** rows carry no authority keys and each row carries `authority_skipped` naming the reason

### Requirement: Linking runs after ingestion and does not depend on order
The system SHALL extract relations in a pass that runs after `Engine.ingest` and through `omrs authority rebuild`. The pass SHALL extract from new or changed sources, remove the outgoing edges of deleted sources, mark their incoming edges `target_present=false`, and re-resolve stored pending references against the current sources. Ingestion itself SHALL NOT extract relations.

#### Scenario: Superseding source ingested first
- **WHEN** source B, which states that it supersedes A, is ingested before A, and A is ingested in a later call
- **THEN** after the second ingest the store holds the edge `B → A supersedes`

#### Scenario: Failed replacement keeps previous edges
- **WHEN** source B is re-ingested with new content and the replacement fails verification
- **THEN** the store keeps B's previous `source_version` and the sidecar keeps B's previous edges

#### Scenario: Deletion leaves an auditable dangling edge
- **WHEN** source A is deleted, source B holds an edge `B → A`, and the next link pass runs
- **THEN** the edge remains with `target_present=false` and the resolver ignores it

#### Scenario: Rebuild links an existing collection
- **WHEN** `authority.enabled` becomes `true` for a collection indexed earlier and `omrs authority rebuild` runs
- **THEN** the sidecar holds the edges of every source, although no file was re-ingested

### Requirement: Deterministic extraction runs first and needs no model
The extractor SHALL detect at least explicit supersession and replacement statements, amendment and repeal statements naming a target document or clause, effective-date clauses, and clause or section references to another source. It SHALL resolve the target by title or canonical path. An unresolved target SHALL be kept as a pending reference with a diagnostic, not as an edge. This tier SHALL need no network access and no model download.

#### Scenario: Effective-date clause populates the window
- **WHEN** a chunk reads "Effective from 1 January 2026, clause 12 of the Employment Contract is replaced by the following"
- **THEN** the emitted edge has `relation=amends`, `scope="clause 12"`, `effective_from="2026-01-01"` and targets the source whose title matches "Employment Contract"

#### Scenario: Unresolvable target waits as a pending reference
- **WHEN** a chunk reads "This notice supersedes Circular 7/2019" and no indexed source matches that title
- **THEN** no edge is stored, a pending reference is stored, and the extractor records an `unresolved_target` diagnostic for the chunk

### Requirement: Model-assisted extraction is opt-in and quarantined
`authority.model_tier` SHALL accept `off` (default), `onnx_decision` and `nli`. Other than `off`, a local model MAY type candidate pairs, and those edges SHALL carry `relation_origin=model` and the model probability as `confidence`. Pairs SHALL come from document-graph similarity edges and shared clause references, at most `max_candidate_pairs_per_source` per source. Model edges SHALL NOT enter the document graph.

#### Scenario: Explicit text outranks a model guess
- **WHEN** the sidecar holds `B → A supersedes (explicit_text)` and `B → A specialises (model, 0.81)`
- **THEN** the resolver applies `supersedes` and reports the explicit edge in `authority_reason`

#### Scenario: Model tier off emits no model edges
- **WHEN** `authority.model_tier` is `off`
- **THEN** the link pass loads no model and the sidecar contains no edge with `relation_origin=model`

#### Scenario: Typed pairs respect the cap
- **WHEN** the model tier runs on a collection with N sources and a cap of C
- **THEN** the number of typed pairs is at most C × N

### Requirement: Authority statuses have exact meanings
The resolver SHALL give each row exactly one `authority_status`: `controlling` (governs its scope at `as_of`), `qualified` (valid but narrowed by another candidate), `superseded` (replaced within scope by an in-force edge), `historical` (older amending text that no longer controls), `not_yet_in_force` (newer text whose `effective_from` is after `as_of`), `unresolved_conflict`, or `unknown` (no relation applies).

#### Scenario: Superseded row stays in the result
- **WHEN** candidates include a chunk from A and a chunk from B, and the sidecar holds an in-force `B → A supersedes` with `scope=document`
- **THEN** both rows are returned; A's row is `superseded` and B's row is `controlling`; `authority_reason` on both names the edge

#### Scenario: Partial amendment supersedes only the named scope
- **WHEN** candidates include chunks of contract A whose `header_path` anchors name clauses 3 and 7, and the sidecar holds an in-force `B → A amends` with `scope="clause 3"`
- **THEN** A's clause 3 row is `superseded`, A's clause 7 row is `controlling`, and B's row is `controlling`

#### Scenario: Unanchored row of a partially amended source
- **WHEN** a candidate row of contract A has no `header_path` anchor and an in-force `B → A amends` has `scope="clause 3"`
- **THEN** that row is `qualified`, not `superseded`

#### Scenario: Newer file is not treated as supersession
- **WHEN** candidates include A and B, B has a later `source_version` and modification time, and the sidecar holds no edge between them
- **THEN** both rows are `unknown` and neither is `superseded`

### Requirement: Resolver annotates candidates and drops none
When the stage runs, the resolver SHALL run after fusion (or dense retrieval when hybrid is off) and before reranking. It SHALL add `authority_status`, `authority_reason` and `authority_conflicts` to every row and SHALL return every input row. `search()` SHALL keep returning a list of rows.

#### Scenario: Every row carries all three keys
- **WHEN** the resolver runs over five rows of which only two have edges
- **THEN** five rows are returned, the three without edges are `unknown` with an empty `authority_conflicts` list, and `search()` returns a list

### Requirement: Resolution follows a fixed ordering before declaring conflict
For each pair of candidate sources, the resolver SHALL take the edges of the best origin and apply the first relation in this order: `corroborates`, `explains`, `specialises` and `restricts`, `amends` and `supersedes`, `conflicts_with`. `explains` adds the source to the target's `qualified_by`. The resolver SHALL NOT infer supersession from filenames, ingestion order, `source_version` or modification time.

#### Scenario: Specific rule does not obsolete the general rule
- **WHEN** candidates include a general leave policy A and an addendum B with `B → A specialises`
- **THEN** A is `qualified` with B in `qualified_by`, B is `controlling`, neither is `superseded`, and both have an empty `authority_conflicts` list

#### Scenario: Reconciliation outranks supersession for the same pair
- **WHEN** the sidecar holds `B → A explains` and `B → A supersedes`, both `explicit_text`
- **THEN** A and B are both `controlling` and A's `qualified_by` lists B

### Requirement: Applicability is decided before conflict
A pair of rows SHALL apply to the question only when both rows are in the query's first-stage candidates, their scopes overlap (document scope, or a clause scope that matches both rows' `header_path` anchors), and neither row is already `superseded`, `historical` or `not_yet_in_force` for that scope. The resolver SHALL NOT make its own relevance judgement.

#### Scenario: Different clauses do not conflict
- **WHEN** the sidecar holds `A ↔ B conflicts_with` with `scope="clause 4"`, and the candidates are A's clause 4 row and B's clause 9 row
- **THEN** neither row is `unresolved_conflict`

### Requirement: Unresolved conflicts are reported on each row
When two applicable rows state incompatible rules on the same scope and no ordered relation resolves them, the resolver SHALL mark both rows `unresolved_conflict` and SHALL add to each row's `authority_conflicts` the other row's `source_id`, `chunk_id` and the reason no relation applied.

#### Scenario: Conflict reported to the caller
- **WHEN** A states a 30-day notice period, B states 60 days for the same clause, and the sidecar holds `A ↔ B conflicts_with`
- **THEN** both rows are `unresolved_conflict`, A's `authority_conflicts` names B's row, and B's names A's row

### Requirement: Point-in-time queries honour effective windows
`search()`, `Engine.search`, `search_documents`, the HTTP search route and the CLI SHALL accept an optional ISO-8601 `as_of`. An edge is in force when `effective_from` is absent or on or before `as_of`, and `effective_until` is absent or after it. Without `as_of`, the resolver SHALL use the current date from an injected clock. An unparsable `as_of` SHALL give a validation error, never an exception from an MCP handler.

#### Scenario: Historical question retrieves the rule in force
- **WHEN** `B → A supersedes` has `effective_from="2025-01-01"` and the query passes `as_of="2024-03-15"`
- **THEN** A is `controlling` and B is `not_yet_in_force`

#### Scenario: Default date comes from the clock
- **WHEN** the injected clock returns 2026-06-01, `B → A supersedes` has `effective_from="2026-01-01"`, and no `as_of` is passed
- **THEN** A is `superseded` and B is `controlling`

#### Scenario: Superseded is not deleted
- **WHEN** a source is `superseded` for the current date
- **THEN** it remains indexed and retrievable and is returned with `authority_status="superseded"`

### Requirement: Amendment chains resolve to the latest edge in force
When several in-force `amends` or `supersedes` edges share one target and scope, the edge with the latest `effective_from` on or before `as_of` SHALL control. The sources of earlier edges SHALL be `historical`. Two such edges with the same `effective_from` and no edge between their sources SHALL make both sources `unresolved_conflict`.

#### Scenario: Three amendments to one clause
- **WHEN** B, C and D each amend clause 5 of A with `effective_from` 2020-01-01, 2022-01-01 and 2025-01-01, and the query passes `as_of="2023-06-01"`
- **THEN** A's clause 5 row is `superseded`, C is `controlling`, B is `historical`, and D is `not_yet_in_force`

### Requirement: Later pipeline stages keep the annotations
The system SHALL re-apply the resolver to rows produced by the rerank-failure fallback re-query. Statuses SHALL be computed before reranking, thresholding and truncation and SHALL NOT be recomputed after them; a surviving row SHALL keep the reference to a partner row that was cut. Context assembly SHALL NOT merge rows whose authority keys differ.

#### Scenario: Fallback re-query keeps annotations
- **WHEN** a hybrid rerank fails and the pipeline re-runs the first stage with the dense threshold
- **THEN** every returned row carries the three authority keys

#### Scenario: Cut partner stays referenced
- **WHEN** A and B are `unresolved_conflict` and truncation removes B's row
- **THEN** A's row is still `unresolved_conflict` and its `authority_conflicts` still names B's row

#### Scenario: Assembly does not merge across statuses
- **WHEN** two adjacent chunks of one source version are `superseded` and `controlling`
- **THEN** assembly returns them as separate rows

### Requirement: Relevance and authority stay separate
The resolver SHALL NOT change `score`, `score_kind`, or candidate order, and the reranker SHALL receive the annotated rows unchanged in count. The reranker SHALL NOT read the authority keys. Callers that want authority to influence ordering SHALL do so downstream of retrieval.

#### Scenario: Scores untouched
- **WHEN** the resolver runs over fused rows
- **THEN** every row's `score` and `score_kind` equal the values before the resolver ran, and the row count and order are unchanged

### Requirement: Authority decisions are explainable
`authority_reason` SHALL hold the edge id, relation, `relation_origin`, an `evidence_text` excerpt of at most 300 characters, the counterpart `source_id`, and `qualified_by` (the `source_id`s that qualify or explain the row). With diagnostics, rows SHALL also carry `timing_report["authority_seconds"]` and the count of edges consulted.

#### Scenario: Reason cites the text
- **WHEN** a row is `superseded` because of an `explicit_text` edge
- **THEN** its `authority_reason` contains the relation, the origin `explicit_text` and the sentence that stated the supersession

### Requirement: Experiment 43 pre-registers the authority metrics
Before any default flip, the change SHALL run Experiment 43 on a synthetic corpus (five case types plus amendment chains), then on a UK statute and its amending instruments. It SHALL report the five authority metrics against frozen gates, beside a baseline, a newest-document-wins cell, the deterministic tier, the model tier, and the resolver without reconciliation.

#### Scenario: Gate failure blocks promotion
- **WHEN** Experiment 43 reports stale authority rate above its pre-registered gate
- **THEN** the `documents` profile keeps `authority.enabled: false` and the report records the failure as the reason

### Requirement: The web workspace shows authority annotations
The Knowledge Base search SHALL accept an optional `as_of` date and send it with the search request. A result row that carries `authority_status` SHALL show the status as a badge with its reason and the names of any conflicting rows. A row without authority keys SHALL look exactly as it does today.

#### Scenario: Status badge on an annotated row
- **WHEN** a search returns a row with `authority_status` `superseded`
- **THEN** the result list shows a "Superseded" badge and the `authority_reason` text for that row

#### Scenario: Plain rows are unchanged
- **WHEN** a search returns rows without authority keys
- **THEN** the result list renders them exactly as before this change

#### Scenario: Empty date sends no point in time
- **WHEN** the user leaves the "As of" field empty
- **THEN** the search request sends `as_of` as `null`, as it does for other omitted controls
