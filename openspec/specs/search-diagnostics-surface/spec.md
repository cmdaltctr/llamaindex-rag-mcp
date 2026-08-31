## Purpose

Defines opt-in access to existing retrieval diagnostics through MCP and CLI
search while preserving lean default responses and thin transport boundaries.
## Requirements
### Requirement: MCP search exposes diagnostics as an optional passthrough

The MCP `search_documents` operation SHALL accept an optional `diagnostics`
boolean. Its default SHALL be `false`. The operation SHALL pass this value to
core retrieval's diagnostics control without changing its meaning.

When diagnostics are enabled, successful results SHALL preserve every
diagnostic field supplied by core retrieval. The MCP transport SHALL NOT
compute, rename, or add diagnostic fields.

#### Scenario: MCP caller enables diagnostics

- **WHEN** a client calls `search_documents` with `diagnostics: true`
- **THEN** the MCP transport passes `true` to core retrieval's diagnostics
  control
- **AND** each successful result preserves the diagnostic fields supplied by
  core retrieval

#### Scenario: MCP caller omits diagnostics

- **WHEN** a client calls `search_documents` without `diagnostics`
- **THEN** the MCP transport passes `false` to core retrieval's diagnostics
  control
- **AND** successful results omit core retrieval's opt-in diagnostic fields

#### Scenario: MCP caller disables diagnostics explicitly

- **WHEN** a client calls `search_documents` with `diagnostics: false`
- **THEN** the response matches the default non-diagnostic result shape

### Requirement: CLI search exposes diagnostics as an optional passthrough

The `rag-mcp search` command SHALL accept a `--diagnostics` flag. Its default
SHALL be disabled. The command SHALL pass the resulting boolean to core
retrieval's diagnostics control without changing its meaning.

#### Scenario: CLI JSON output includes requested diagnostics

- **WHEN** a user runs `rag-mcp search <query> --diagnostics --json`
- **THEN** the CLI passes `true` to core retrieval's diagnostics control
- **AND** the JSON result preserves applicable core-produced fields such as
  `dense_rank`, `sparse_rank`, `fused_rank`, `rerank_reason`,
  `threshold_score_kind`, and `sparse_backend`

#### Scenario: CLI JSON output stays lean by default

- **WHEN** a user runs `rag-mcp search <query> --json` without `--diagnostics`
- **THEN** the CLI passes `false` to core retrieval's diagnostics control
- **AND** the JSON result omits core retrieval's opt-in diagnostic fields

#### Scenario: Human-readable output receives diagnostic results

- **WHEN** a user runs `rag-mcp search <query> --diagnostics` without `--json`
- **THEN** the existing human-readable result table renders successfully
- **AND** additional diagnostic fields do not add or change table columns

### Requirement: Diagnostics passthrough preserves existing transport contracts

Adding the diagnostics controls SHALL NOT move retrieval logic into a
transport. Core retrieval SHALL remain the sole producer and remover of
diagnostic fields.

The MCP handler SHALL preserve its existing never-raise error envelope. Its
read-only and non-destructive tool annotations SHALL remain unchanged.

#### Scenario: Retrieval fails after MCP diagnostics are requested

- **WHEN** core retrieval fails during an MCP search with diagnostics enabled
- **THEN** the MCP handler returns its existing status-error envelope
- **AND** the handler does not raise the underlying exception to the MCP runtime

#### Scenario: MCP tool metadata is inspected

- **WHEN** a client inspects the `search_documents` tool annotations after this
  change
- **THEN** the tool remains marked read-only and non-destructive

#### Scenario: Core diagnostic fields evolve

- **WHEN** core retrieval changes its diagnostic field set in a later change
- **THEN** the MCP and CLI transports continue to pass the core result through
  without defining a separate diagnostic schema

### Requirement: Diagnostics report per-stage retrieval timing

When diagnostics are enabled, core retrieval SHALL report the wall-clock
duration of each retrieval stage that ran for the query. The measurements
SHALL cover query embedding, dense search, sparse search, rank fusion, and
reranking.

Durations SHALL be reported in seconds as a single `timings` mapping of stage
name to duration, attached to each returned result so the field set survives
fusion and reranking exactly as the existing per-row diagnostics do.

A stage that did not run SHALL be absent from the mapping. Absence means the
stage did not execute; it MUST NOT be reported as a zero duration, because
zero is a legitimate measurement for a stage that ran and was fast. This
follows the reporting rule the ingest norm band already uses: report what ran,
not what did not.

A stage that executes more than once during one query SHALL report the sum of
its executions. The reported value is the total time the query spent in that
stage, so no execution is discarded. The mapping SHALL NOT report the duration
of only the most recent execution.

Because the mapping is attached to result rows, a query that returns no rows
SHALL report no timings. This is a known boundary of row-attached diagnostics,
not a defect.

Timing SHALL be measurement only. Enabling diagnostics SHALL NOT change which
candidates are retrieved, their scores, their order, or the final result
count.

#### Scenario: Hybrid query reports both retrieval branches

- **WHEN** a caller runs a hybrid search with diagnostics enabled
- **THEN** each result carries a `timings` mapping
- **AND** the mapping contains a duration for query embedding, dense search,
  sparse search, and fusion
- **AND** every reported duration is a non-negative number of seconds

#### Scenario: Dense-only query omits the sparse stage

- **WHEN** a caller runs a non-hybrid search with diagnostics enabled
- **THEN** the `timings` mapping contains no sparse-search entry
- **AND** it contains no fusion entry
- **AND** the absent entries are omitted rather than reported as zero

#### Scenario: Non-reranked query omits the rerank stage

- **WHEN** a search resolves to no reranking and diagnostics are enabled
- **THEN** the `timings` mapping contains no rerank entry

#### Scenario: Reranked query reports the rerank stage

- **WHEN** a search runs the reranker and diagnostics are enabled
- **THEN** the `timings` mapping contains a rerank duration

#### Scenario: A cached query embedding is not re-fetched

- **GIVEN** an identical query was embedded earlier in the process
- **WHEN** the query is searched again with diagnostics enabled
- **THEN** the embedding provider MUST NOT be called a second time
- **AND** an embedding duration MUST still be reported, because the stage ran
  and served from cache

#### Scenario: Retrieval stages repeat after a failed rerank

- **GIVEN** a hybrid search whose reranker fails and whose similarity
  threshold triggers a re-query
- **WHEN** the search completes with diagnostics enabled
- **THEN** the dense, sparse and fusion durations MUST each be the sum of both
  executions
- **AND** the rerank duration MUST be reported, because the reranker ran

#### Scenario: A query returning no results reports no timings

- **WHEN** a search with diagnostics enabled returns an empty result list
- **THEN** no timing mapping is returned, because the mapping travels on
  result rows

#### Scenario: Diagnostics disabled omits timing entirely

- **WHEN** a caller runs a search without enabling diagnostics
- **THEN** no result carries a `timings` field
- **AND** the result shape is unchanged from the pre-timing default shape

#### Scenario: Timing does not alter retrieval outcomes

- **GIVEN** a fixed collection and a fixed query
- **WHEN** the query runs once with diagnostics enabled and once without
- **THEN** both runs return the same result identities in the same order
- **AND** both runs return the same scores

#### Scenario: Transports surface timing without a transport change

- **WHEN** a caller enables diagnostics through MCP or the CLI
- **THEN** the `timings` field reaches the caller through the existing
  passthrough
- **AND** no transport defines, renames, or computes any timing field

