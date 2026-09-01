## ADDED Requirements

### Requirement: The ingestible extension set is profile-scoped

The set of file extensions ingestion collects SHALL be resolved from the
active profile rather than from one global constant, so a profile configured
for code can admit source files while a profile configured for documents does
not. The resolved set SHALL be part of the operation's effective settings, not
read from a module-level singleton.

Without this, `codebase.yaml`'s `chunking.strategy_fallback: code` is
unreachable: source extensions are never collected, so the AST-aware path
cannot run for a source file no matter how the profile is configured.

#### Scenario: The codebase profile admits source files

- **GIVEN** a directory containing `.py`, `.ts` and `.go` files
- **WHEN** it is ingested into a collection bound to the `codebase` profile
- **THEN** those files SHALL be collected
- **AND** files with a tree-sitter mapping SHALL be chunked by the AST-aware
  code strategy

#### Scenario: The documents profile is unchanged

- **GIVEN** the same directory
- **WHEN** it is ingested into a collection bound to the `documents` profile
- **THEN** only the seven document extensions SHALL be collected
- **AND** the source files SHALL be reported with `status: "skipped"` and an
  explicit reason, exactly as before this change

#### Scenario: Binary files remain excluded under every profile

- **GIVEN** a file that content-type detection classifies as binary
- **WHEN** it is ingested under any profile
- **THEN** it SHALL be skipped regardless of the profile's extension set

#### Scenario: The extension set participates in change detection

- **GIVEN** a collection ingested under one profile's extension set
- **WHEN** the collection's bound profile changes such that the set differs
- **THEN** files newly admitted by the change SHALL be ingested on the next run
- **AND** files already indexed and still admitted SHALL NOT be reprocessed
  solely because the set changed

#### Scenario: Coverage exercises the real gate

- **GIVEN** a test verifying code chunking through `ingest_path_async`
- **WHEN** the test runs
- **THEN** it SHALL drive a real source file through the real extension gate
- **AND** it SHALL NOT patch `gather_supported_files` to bypass that gate
