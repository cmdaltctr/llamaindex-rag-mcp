# type-aware-ingestion Delta

## ADDED Requirements

### Requirement: The base install performs content-based detection

The base dependency set SHALL include the pinned official Magika package
so `detect_file_types` classifies by file content in a standard
`uv sync` + `uv run` environment, without an operator-installed external
binary. The suffix fallback SHALL remain the degradation for environments
where the binary is genuinely unavailable.

#### Scenario: A standard install detects by content
- **GIVEN** a base install (`uv sync`, no extras, no system magika)
- **WHEN** `detect_file_types` runs on a corpus
- **THEN** classification SHALL come from the Magika model, not the suffix map

#### Scenario: A mislabelled code file routes to the AST splitter
- **GIVEN** a Python source file whose extension is `.txt`
- **WHEN** it is ingested in a standard install
- **THEN** its content type SHALL be `code/python` and it SHALL chunk through the AST-aware splitter

#### Scenario: Binary content with a document extension is skipped
- **GIVEN** a zip archive renamed to `.pdf`
- **WHEN** it is ingested in a standard install
- **THEN** it SHALL be skipped as binary before any reader runs

#### Scenario: Label equivalence is verified without ingestion
- **WHEN** the label-equivalence smoke tool runs over a target corpus
- **THEN** it SHALL compare suffix-map labels against Magika labels using detection only
- **AND** it SHALL NOT call any ingest, embedding, or store operation
- **AND** it SHALL report every file whose label would change, so index-identity shifts are known before any re-ingest
