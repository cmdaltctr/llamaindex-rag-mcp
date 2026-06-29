## Purpose

Define the type-aware ingestion dispatch contract — Magika content-type detection integrated into the ingestion pipeline, CodeSplitter for code files, binary skip, and content_type metadata in ChromaDB.

## Requirements

### Requirement: Content-type-aware chunking dispatch

During ingestion, the system SHALL detect each file's content type (via Magika or suffix fallback) and dispatch to the appropriate chunking strategy. Code files SHALL use `CodeSplitter` (tree-sitter-aware boundaries). Document files SHALL use the existing `SentenceSplitter` or `MarkdownNodeParser`. Config files SHALL be chunked as whole files. Binary files SHALL be skipped.

#### Scenario: Code file uses CodeSplitter

- **WHEN** Magika detects a file as `code/typescript` (or any `code/*` group)
- **THEN** the ingestion pipeline SHALL use LlamaIndex's `CodeSplitter` with the appropriate tree-sitter language grammar
- **THEN** chunks SHALL respect function/class boundaries

#### Scenario: Markdown file uses existing parser

- **WHEN** Magika detects a file as `text/markdown`
- **THEN** the ingestion pipeline SHALL continue using the existing `MarkdownNodeParser + SentenceSplitter` combination
- **THEN** behaviour SHALL be identical to v1.7.0

#### Scenario: Config file chunked whole

- **WHEN** Magika detects a file as `config/yaml`, `config/json`, or `config/toml`
- **THEN** the entire file content SHALL be a single chunk

#### Scenario: Binary file skipped

- **WHEN** Magika detects a file as `executable/*`, `image/*`, or `archive/*` (any non-text type)
- **THEN** the file SHALL be skipped entirely — no reading, no chunking, no embedding
- **THEN** the skip SHALL be logged at INFO level with the filename and detected type

#### Scenario: Fallback when Magika unavailable

- **WHEN** Magika is not installed and suffix-based detection is used
- **THEN** the dispatch SHALL still function correctly using the suffix-to-group mapping
- **THEN** unknown extensions SHALL default to `SentenceSplitter`

### Requirement: content_type metadata in ChromaDB

Every document chunk stored in ChromaDB SHALL include a `content_type` metadata field reflecting the Magika-detected type (e.g., `code/typescript`, `document/pdf`, `config/yaml`). This metadata SHALL be filterable via the existing `metadata_filter` parameter in `search_documents`.

#### Scenario: content_type stored on code chunk

- **WHEN** a TypeScript file is ingested
- **THEN** each resulting chunk in ChromaDB SHALL have `metadata["content_type"] = "code/typescript"`

#### Scenario: content_type stored on document chunk

- **WHEN** a PDF file is ingested
- **THEN** each resulting chunk in ChromaDB SHALL have `metadata["content_type"] = "document/pdf"`

#### Scenario: Search filtered by content_type

- **WHEN** `search_documents(query="auth", metadata_filter={"content_type": "code/typescript"})` is called
- **THEN** only chunks with `content_type="code/typescript"` SHALL be returned

### Requirement: CodeSplitter language mapping

The system SHALL maintain a mapping from Magika content-type labels to tree-sitter language identifiers for `CodeSplitter`. The mapping SHALL be defined in `config.py`.

#### Scenario: Known language mapping

- **WHEN** Magika detects `code/typescript`
- **THEN** the system SHALL use `CodeSplitter(language="typescript", ...)`

#### Scenario: Unknown code language

- **WHEN** Magika detects a code file but no tree-sitter language mapping exists
- **THEN** the system SHALL fall back to `SentenceSplitter`
- **THEN** a debug-level log SHALL indicate the unmapped language
