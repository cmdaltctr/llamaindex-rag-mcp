## ADDED Requirements

### Requirement: Named profile bundles

The system SHALL provide three version-controlled YAML profile bundles under
`config/profiles/`: `documents.yaml` (document grounding), `codebase.yaml`
(codebase context), and `hybrid.yaml` (per-collection policy). Bundles SHALL
be validated against the same Pydantic settings models as global
configuration and SHALL contain no credentials.

#### Scenario: Documents profile values

- **WHEN** the `documents` profile is loaded
- **THEN** it MUST resolve to: markdown chunking fallback, reranker enabled,
  `top_k=10`, dense-only retrieval (no hybrid), category taxonomy

#### Scenario: Codebase profile values

- **WHEN** the `codebase` profile is loaded
- **THEN** it MUST resolve to: code chunking fallback, reranker disabled,
  `top_k=20`, hybrid retrieval (dense + BM25 + RRF), file_type taxonomy

#### Scenario: Invalid bundle rejected

- **WHEN** a profile bundle fails schema validation
- **THEN** the system MUST fail at resolution time with a clear validation
  error naming the offending key

---

### Requirement: Profile selection and collection binding

The system SHALL select the server-wide default profile via the
`RAG_PROFILE` environment variable (`documents`, `codebase`, or `hybrid`;
default `documents`). A collection SHALL be able to declare its profile via
ChromaDB collection metadata (`metadata={"profile": "<name>"}`). A
collection with no profile tag SHALL inherit the server-wide default.

When `RAG_PROFILE=hybrid`, the `hybrid` profile is a mode selector, not an
operational profile with concrete retrieval settings. The `hybrid.yaml`
bundle SHALL declare a `default_profile` key (valid values: `documents` or
`codebase`; default `documents`). An untagged collection under
`RAG_PROFILE=hybrid` SHALL resolve to the `default_profile` named in
`hybrid.yaml`, not to `hybrid` itself. A collection whose metadata tag is
literally `hybrid` SHALL be rejected with a clear error directing the user
to tag the collection with `documents` or `codebase` instead.

#### Scenario: Existing collections unaffected

- **WHEN** the server starts against pre-refactor collections with no
  profile metadata
- **THEN** they MUST resolve to the server-wide default profile with no data
  migration

#### Scenario: Hybrid mode per-collection resolution

- **WHEN** `RAG_PROFILE=hybrid` and two collections carry different profile
  tags
- **THEN** operations against each collection MUST resolve that collection's
  profile in the same running process

#### Scenario: Hybrid mode untagged collection falls back to default_profile

- **WHEN** `RAG_PROFILE=hybrid` and a collection has no profile tag
- **AND** `hybrid.yaml` declares `default_profile: documents`
- **THEN** the collection MUST resolve to the `documents` profile
- **AND** MUST NOT attempt to resolve `hybrid` as an operational profile

#### Scenario: Invalid collection profile tag rejected

- **WHEN** `ProfileResolver.resolve()` encounters a collection whose
  metadata tag names a non-existent profile
- **THEN** it MUST raise a clear error naming the invalid tag and listing
  available profiles (`documents`, `codebase`)

#### Scenario: Collection tagged as hybrid rejected

- **WHEN** a collection's metadata tag is literally `hybrid`
- **THEN** the resolver MUST reject it with an error directing the user to
  tag the collection with `documents` or `codebase`

---

### Requirement: Two-tier settings resolution

The system SHALL resolve settings in two tiers. Tier 1 components (embedder,
chunking and reader registries, vector store handle, reranker model) SHALL
be constructed once at startup in `compose.py` and shared across
collections. Tier 2 levers (reranker on/off, `top_k`, hybrid/RRF, chunking
fallback for ambiguous types, metadata taxonomy mode) SHALL be resolved per
operation by a `ProfileResolver` and passed as parameters to `search()` and
`ingest_path_async()`. Core operations SHALL NOT read global state for
Tier 2 levers.

#### Scenario: Per-query reranker decision

- **WHEN** a query targets a `documents`-profile collection and then a
  `codebase`-profile collection in the same process
- **THEN** the reranker model MUST be loaded at most once (Tier 1)
- **AND** the decision to apply it MUST differ per query according to each
  collection's resolved profile (Tier 2)

#### Scenario: Resolver falls back to server default

- **WHEN** `ProfileResolver.resolve()` is called for a collection with no
  profile tag
- **THEN** it MUST return the server-wide default profile's effective
  settings

---

### Requirement: Content-type dispatch precedence over profiles

For known file types, content-type dispatch SHALL always win over the
profile's chunking strategy. The profile's `active_strategy` SHALL apply
only as the fallback for ambiguous file types.

#### Scenario: Known types ignore profile strategy

- **WHEN** a `.py` file is ingested into a `documents`-profile collection
- **THEN** it MUST be chunked with the code strategy (content-type dispatch),
  not the profile's markdown fallback

#### Scenario: Ambiguous types use profile fallback

- **WHEN** a `.txt` file (classified as ambiguous — could be code or prose)
  is ingested into a `codebase`-profile collection
- **THEN** the chunking decision MUST use the codebase profile's fallback
  strategy

---

### Requirement: Non-destructive profile changes

Changing a collection's profile SHALL be an O(1) collection-metadata update
that never re-chunks, re-embeds, or deletes existing data. Query-time levers
(reranker, `top_k`, hybrid) SHALL apply immediately after the change;
ingest-time levers (taxonomy mode, chunking fallback) SHALL apply only to
future ingests.

#### Scenario: Safety contract surfaced

- **WHEN** a profile change is requested on a non-empty collection
- **THEN** the system MUST present the safety contract before mutating:
  existing chunks unchanged, query-time levers apply immediately, taxonomy
  caveat stated, and the re-ingest `--force` path named for genuine
  re-chunking

#### Scenario: CLI transport prompts

- **WHEN** the profile change is requested via the CLI
- **THEN** the CLI MUST print the contract and prompt `Continue? [y/N]`,
  aborting on `N`

#### Scenario: MCP transport previews then confirms

- **WHEN** the profile change is requested via an MCP tool
- **THEN** the tool MUST return a preview object (`{"status": "preview",
  "contract": ..., "confirm_required": true}`) without mutating
- **AND** MUST apply the change only when re-invoked with `confirm=True`

#### Scenario: Profile change touches no vectors

- **WHEN** a profile change is confirmed
- **THEN** only the collection's metadata dict MUST be updated
- **AND** chunk count, embeddings, and document content MUST be byte-identical
  before and after

---

### Requirement: Documents-profile reranker default revalidation

The phase SHALL NOT ship until the `documents` profile's
`reranker_enabled: true` flip is revalidated against Experiment 10's
findings. This flip is a deliberate behaviour change restoring ADR-018
intent (the current code default is `false` post-Experiment 10), and
AGENTS.md invariant #5 SHALL be corrected to state the true code default
and the profile-level restoration.

#### Scenario: Revalidation recorded

- **WHEN** the phase is accepted
- **THEN** the change notes MUST record the Experiment 10 revalidation
  outcome (flip confirmed or documents profile amended to `false`)

#### Scenario: AGENTS.md corrected

- **WHEN** the phase is accepted
- **THEN** AGENTS.md invariant #5 MUST no longer claim `RERANK_ENABLED=true`
  is the code default
