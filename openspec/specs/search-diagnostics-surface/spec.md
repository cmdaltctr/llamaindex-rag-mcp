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
