# Spec Delta

## MODIFIED Requirements

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

A collection tag SHALL also be able to name a user profile from the workspace. Such a
collection SHALL resolve to the settings of the user profile's base profile,
reported under the user profile's id. `RAG_PROFILE` and `hybrid.yaml`
`default_profile` SHALL accept built-in profiles only. The web server SHALL
resolve user profiles from its own workspace. The stdio MCP server, the CLI
and the watcher SHALL resolve them from the default workspace database, opened
read-only, when that file exists. A process that finds no workspace database
SHALL refuse a collection tagged with a name that is not built-in, with an
error that names the profile, the path it read and the fix.

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
  available profiles (`documents`, `codebase`, and each ready user profile
  when a workspace is present)

#### Scenario: Collection tagged as hybrid rejected

- **WHEN** a collection's metadata tag is literally `hybrid`
- **THEN** the resolver MUST reject it with an error directing the user to
  tag the collection with `documents` or `codebase`

#### Scenario: Collection tagged with a user profile

- **WHEN** collection `notes` is tagged `my-notes`, a user profile with base
  profile `codebase`
- **THEN** resolving `notes` MUST return the `codebase` settings with the
  profile name `my-notes`

#### Scenario: Collection tagged with a deleted user profile

- **WHEN** a collection is tagged with a user profile that was deleted
- **THEN** resolution MUST fail with an error that says the profile was
  deleted and tells the user to choose another profile

#### Scenario: User profile found in the default workspace

- **WHEN** the CLI, the watcher or the stdio MCP server resolves a collection
  tagged `my-notes`, and the default workspace database holds `my-notes` with
  base profile `documents`
- **THEN** resolution MUST return the `documents` settings with the profile
  name `my-notes`
- **AND** the workspace database MUST stay unchanged

#### Scenario: No workspace database

- **WHEN** the default workspace database does not exist and the CLI, the
  watcher or the stdio MCP server handles a collection tagged `my-notes`
- **THEN** it MUST fail with an error that names `my-notes` and the path it
  read, says that user profiles live in the web workspace, and tells the user
  to start `omrg web` once or to change the collection to `documents` or
  `codebase`

### Requirement: Non-destructive profile changes

Changing a collection's profile SHALL be an O(1) collection-metadata update
that never re-chunks, re-embeds, or deletes existing data. Query-time levers
(reranker, `top_k`, hybrid) SHALL apply immediately after the change;
ingest-time levers (taxonomy mode, chunking fallback) SHALL apply only to
future ingests. For a user profile, its Search and Answer pipelines SHALL
apply immediately after the change, and its Ingest pipeline SHALL apply only
to future ingests.

#### Scenario: Safety contract surfaced

- **WHEN** a profile change is requested on a non-empty collection
- **THEN** the system MUST present the safety contract before mutating:
  existing chunks unchanged, query-time levers apply immediately, taxonomy
  caveat stated, and the re-ingest `--force` path named for genuine
  re-chunking

#### Scenario: Safety contract for a user profile

- **WHEN** a change to a user profile is requested
- **THEN** the safety contract MUST also name the profile's three pipelines
  with their current revision numbers
- **AND** it MUST state that search and answers follow the Search and
  Answer pipelines at once, and that sources indexed by a different Ingest
  graph are processed again on their next ingestion

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
