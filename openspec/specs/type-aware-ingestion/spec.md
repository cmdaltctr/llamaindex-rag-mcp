# type-aware-ingestion Specification

## Purpose
Defines content-aware ingestion: code files are split by a verifiably
active AST-aware splitter, fallback behaviour is observable, Markdown
and sentence helper paths honour the same configured post-processing,
and the ingestible extension set is scoped per profile. What a file IS
decides how it is chunked.

## Requirements
### Requirement: Code files use a verifiably active AST-aware splitter

For content classified as supported source code, the system SHALL invoke LlamaIndex `CodeSplitter` using parameter names and units supported by the locked LlamaIndex version. Code splitting configuration SHALL use code-specific units rather than reusing document token settings under incompatible names.

The chunking configuration SHALL expose explicit code-oriented settings for line count, line overlap and maximum character ceiling (or the exact successor fields required by a future supported LlamaIndex API). Document `chunk_size` / `chunk_overlap` remain token-oriented settings for SentenceSplitter and SHALL NOT be passed to CodeSplitter as though they had the same semantics.

#### Scenario: Supported Python code uses AST path
- **GIVEN** a valid Python source fixture whose AST-aware boundaries differ from SentenceSplitter output
- **WHEN** type-aware ingestion chunks the file
- **THEN** the effective strategy MUST be `code`
- **AND** the emitted boundaries MUST satisfy the CodeSplitter structural fixture assertions
- **AND** no fallback SHALL have occurred

#### Scenario: Constructor/API regression
- **GIVEN** the installed LlamaIndex CodeSplitter API no longer accepts the arguments the project supplies
- **WHEN** the code chunker contract test runs
- **THEN** the test MUST fail
- **AND** a successful SentenceSplitter fallback MUST NOT make the CodeSplitter success test pass

### Requirement: Code chunking fallback is observable

When AST-aware code splitting fails and the production policy falls back to SentenceSplitter, the system SHALL surface the requested strategy, effective strategy and fallback reason in internal diagnostics/logging. Experiments that manipulate chunking strategy SHALL treat such fallback as an invalid cell rather than silently measuring the fallback implementation.

#### Scenario: Parser failure falls back in production
- **GIVEN** CodeSplitter raises for a supported source file
- **WHEN** normal ingestion runs
- **THEN** SentenceSplitter MAY be used according to the existing graceful-degradation policy
- **AND** diagnostics MUST identify `requested=code`, `effective=sentence`, and the failure reason

#### Scenario: Chunker experiment observes fallback
- **GIVEN** an experiment declares CodeSplitter as the treatment
- **WHEN** fallback occurs
- **THEN** experiment preflight or the measured cell MUST abort as invalid

### Requirement: Markdown/sentence helper paths honour the same configured post-processing

Any public/internal helper that implements the same Markdown chunking strategy SHALL forward the configured heading-prepend and minimum-chunk-fraction values consistently. Calling the standalone sentence/Markdown helper SHALL NOT silently revert those knobs to function defaults while the main ingestion path honours them.

#### Scenario: Same Markdown settings through two entry points
- **GIVEN** heading prepend and a non-zero minimum chunk fraction are configured
- **WHEN** the same fixture is chunked through the main ingestion path and the standalone sentence/Markdown strategy helper
- **THEN** both paths SHALL apply equivalent configured post-processing


### Requirement: The ingestible extension set is profile-scoped

The set of file extensions ingestion collects SHALL be resolved from the
active profile rather than from one global constant, so a profile configured
for code can admit source files while a profile configured for documents does
not. The resolved set SHALL be part of the operation's effective settings, not
read from a module-level singleton.

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
