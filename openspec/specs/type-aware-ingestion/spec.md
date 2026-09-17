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

### Requirement: The base install uses a validated pinned Magika CLI result

The base dependency set SHALL include the official `magika==1.0.3` package. A standard `uv sync` and `uv run` environment SHALL detect content through the existing injected `MAGIKA_BINARY` CLI transport. The parser SHALL accept only JSONL records with `result.status == "ok"`. It SHALL read `result.value.output` and require non-empty string `group` and `label` fields plus boolean `is_text`. It SHALL ignore blank JSONL lines.

A non-`ok` status, non-JSON row, malformed successful envelope, or invalid required field MUST fail the whole detector scan. The parser MUST NOT maintain an error-status allowlist. Production SHALL use the existing warned suffix fallback for those failures, unavailable binary, non-zero exit, or timeout. It MUST NOT fabricate an `unknown` label or report partial success. Production MUST NOT add another walker to discover an expected full path set.

#### Scenario: A standard install detects by content
- **GIVEN** a base install with `magika==1.0.3`, no system Magika, and valid JSONL results
- **WHEN** `detect_file_types` runs on a corpus with injected settings
- **THEN** classification SHALL come from `result.value.output`, not the suffix map

#### Scenario: An invalid CLI result falls back safely
- **GIVEN** a detector row with non-`ok` status, non-JSON content, malformed output, or an invalid required field
- **WHEN** `detect_file_types` processes the scan
- **THEN** the whole scan MUST use the warned suffix fallback
- **AND** it MUST NOT fabricate a label or report partial success

### Requirement: Content typing preserves readable false-text groups and normalises only confirmed aliases

At the integration boundary, the system SHALL set `group` to `binary` only when `is_text is False` and `group` is not `document`, `code`, or `text`. It SHALL preserve the detected label and `is_text`. The existing `content_type.startswith("binary")` check remains the only pre-reader binary skip. A document group with `is_text=false` SHALL remain readable, subject to the existing extension gate.

The system SHALL map only `text/markdown` to `document/markdown` and `text/txt` to `document/text`. It MUST NOT use the source suffix to replace a content prediction, change `_SUFFIX_MAP`, add broad aliases, relabel stored rows, or backfill identity. Markdown routing remains governed by its existing suffix-or-reader-format rule.

#### Scenario: Confirmed text aliases preserve the identity input
- **GIVEN** detected `text/markdown` or `text/txt` content and equal non-content identity inputs
- **WHEN** the integration boundary normalises the detected label
- **THEN** the identity content-type input SHALL be `document/markdown` or `document/text`
- **AND** `.md` parsing SHALL remain unchanged

#### Scenario: A mislabelled code file routes to the AST splitter
- **GIVEN** a substantial valid Python source fixture with a `.txt` extension, sufficient for the model to identify Python
- **WHEN** it is ingested with injected settings, fake stores, and mock readers
- **THEN** its content type SHALL be `code/python` and it SHALL use the existing AST-aware splitter path
- **AND** direct-file keys, including `.`, SHALL retain injected-settings behaviour with no global settings read
- **AND** no short-source `txt` result SHALL be repaired by padding, retrying, threshold change, or suffix override

#### Scenario: Binary content with a document extension is skipped
- **GIVEN** a ZIP archive renamed to `.pdf` and a valid Magika result with `is_text=false` and a group outside `document`, `code`, and `text`
- **WHEN** it is ingested in a standard install
- **THEN** the integration boundary SHALL classify it under `binary/*`
- **AND** it SHALL be skipped before any reader runs

#### Scenario: A binary transition removes the previously indexed rows
- **GIVEN** a source is indexed and searchable, and its bytes later change so Magika classifies it under `binary/*`
- **WHEN** it is re-ingested into the same collection
- **THEN** the rows of the previous version SHALL be removed through the writer's source identity
- **AND** the skip SHALL report success with the removed count in `chunks_removed`
- **AND** a removal failure SHALL report that file as failed instead of a successful skip

#### Scenario: Readable documents remain readable
- **GIVEN** a valid PDF or Office result with `group=document` and `is_text=false`
- **WHEN** it passes through the integration boundary
- **THEN** it SHALL remain a readable document, subject to the existing extension gate

### Requirement: The label-equivalence smoke is complete, detection-only, and fail-closed

A smoke script SHALL accept explicit operator paths and `--json`. It SHALL reuse existing `scan_with_suffix` from `core.codebase.codebase_map` and the corrected `integrations.magika` scanner, passing injected settings to both. It MAY reuse `FileEntry` or settings data when needed. It SHALL not copy the suffix table or add a directory walker. Existing suffix traversal exclusions and limits SHALL remain. It SHALL compare the two scanner path sets and effective OMRG-normalised labels. It SHALL report `groups[].files` records containing `path`, `suffix_label`, `magika_label`, and `would_change`, with `total_files` and `would_change_count`. It MUST detect missing, extra, or duplicate paths and MUST match paths rather than output order.

The script MAY import the `codebase_map` module for `scan_with_suffix`. It MUST NOT import or call `build_codebase_map`, Engine, or ingestion, embedding, store, or composition-root APIs. The guards MUST detect forbidden direct, transitive, and dynamic imports and forbidden `build_codebase_map` or Engine symbols. The script MUST fail clearly for empty input, invalid records, unavailable or timed-out detection, path-set differences, or residual labels. It SHALL exit zero only for a complete, non-empty all-match result. The smoke script does not authorise re-ingestion.

#### Scenario: Label equivalence is verified without ingestion
- **GIVEN** a frozen acceptance corpus of representative common PDF, Python, Markdown, and TXT paths
- **WHEN** the smoke tool runs after implementation
- **THEN** it SHALL exit zero only for a complete, non-empty all-match result
- **AND** a mismatch, fallback, detector error, empty input, or path-set difference MUST stop acceptance and execute option 2

#### Scenario: Predesignated diagnostic probes record limitations
- **GIVEN** deliberately misnamed and tiny-source paths designated before execution
- **WHEN** the same smoke tool runs on the diagnostics separately
- **THEN** each residual mismatch SHALL exit non-zero and be recorded as a limitation
- **AND** a file inside the frozen acceptance corpus MUST NOT be moved or excluded after output is known
