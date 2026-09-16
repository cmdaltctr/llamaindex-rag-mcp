# type-aware-ingestion Delta

## ADDED Requirements

### Requirement: The base install uses a validated pinned Magika CLI result

The base dependency set SHALL include the official `magika==1.0.3` package.
A standard `uv sync` and `uv run` environment SHALL detect content through
the existing injected `MAGIKA_BINARY` CLI transport. The parser SHALL accept
only JSONL records with `result.status == "ok"`. It SHALL read
`result.value.output` and require non-empty string `group` and `label` fields
plus boolean `is_text`. It SHALL ignore blank JSONL lines.

A non-`ok` status, non-JSON row, malformed successful envelope, or invalid
required field MUST fail the whole detector scan. The parser MUST NOT maintain
an error-status allowlist. Production SHALL use the existing warned suffix
fallback for those failures, unavailable binary, non-zero exit, or timeout.
It MUST NOT fabricate an `unknown` label or report partial success. Production
MUST NOT add another walker to discover an expected full path set.

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

At the integration boundary, the system SHALL set `group` to `binary` only
when `is_text is False` and `group` is not `document`, `code`, or `text`.
It SHALL preserve the detected label and `is_text`. The existing
`content_type.startswith("binary")` check remains the only pre-reader binary
skip. A document group with `is_text=false` SHALL remain readable, subject to
the existing extension gate.

The system SHALL map only `text/markdown` to `document/markdown` and
`text/txt` to `document/text`. It MUST NOT use the source suffix to replace a
content prediction, change `_SUFFIX_MAP`, add broad aliases, relabel stored
rows, or backfill identity. Markdown routing remains governed by its existing
suffix-or-reader-format rule.

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

A smoke script SHALL accept explicit operator paths and `--json`. It SHALL
reuse existing `scan_with_suffix` from `core.codebase.codebase_map` and the
corrected `integrations.magika` scanner, passing injected settings to both.
It MAY reuse `FileEntry` or settings data when needed. It SHALL not copy the suffix table or add a directory walker.
Existing suffix traversal exclusions and limits SHALL remain. It SHALL compare
the two scanner path sets and effective OMRG-normalised labels. It SHALL
report `groups[].files` records containing `path`, `suffix_label`,
`magika_label`, and `would_change`, with `total_files` and
`would_change_count`. It MUST detect missing, extra, or duplicate paths and
MUST match paths rather than output order.

The script MAY import the `codebase_map` module for `scan_with_suffix`. It
MUST NOT import or call `build_codebase_map`, Engine, or ingestion, embedding,
store, or composition-root APIs. The guards MUST detect forbidden direct,
transitive, and dynamic imports and forbidden `build_codebase_map` or Engine
symbols. The script MUST fail clearly for empty input, invalid records,
unavailable or timed-out detection, path-set differences, or residual labels.
It SHALL exit zero only for a complete, non-empty all-match result. The smoke
script does not authorise re-ingestion.

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
