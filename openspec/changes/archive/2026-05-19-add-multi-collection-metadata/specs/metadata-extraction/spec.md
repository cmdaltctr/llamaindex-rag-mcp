# Delta Specification: metadata-extraction

## ADDED Requirements

### Requirement: Configurable extraction mode

The system SHALL support a `METADATA_EXTRACTION_MODE` environment variable with four values: `"disabled"`, `"keyword"`, `"ollama"`, and `"llamaindex"`. The mode SHALL control how document metadata is extracted during ingestion.

#### Scenario: Mode set to disabled
- **WHEN** `METADATA_EXTRACTION_MODE=disabled`
- **THEN** `extract_metadata()` SHALL return an empty dict
- **THEN** no metadata SHALL be attached to document chunks

#### Scenario: Mode set to keyword (default)
- **WHEN** `METADATA_EXTRACTION_MODE` is not set (falls back to `"keyword"`)
- **THEN** `extract_metadata()` SHALL use regex keyword matching
- **THEN** the mode SHALL require zero external dependencies

### Requirement: Keyword-based categorisation

When `METADATA_EXTRACTION_MODE` is `"keyword"`, the system SHALL use a set of regex pattern→category rules to classify document content. Each rule SHALL consist of a regex pattern and a target category. The category with the most keyword matches SHALL be assigned. If no keywords match, the category SHALL be `"uncategorised"`.

#### Scenario: Single category match
- **WHEN** document text contains `"transformer"`, `"attention"`, and `"embedding"` keywords
- **AND** the keyword rules map these to `"AI"`
- **THEN** `extract_metadata()` SHALL return `{"category": "AI"}`

#### Scenario: Multiple category matches
- **WHEN** document text contains keywords matching both `"AI"` (3 hits) and `"Philosophy"` (1 hit)
- **THEN** `extract_metadata()` SHALL return `{"category": "AI"}` (highest score)

#### Scenario: No keyword matches
- **WHEN** document text contains no keywords from any rule
- **THEN** `extract_metadata()` SHALL return `{"category": "uncategorised"}`

### Requirement: User-overridable keyword rules

The system SHALL provide a default set of keyword→category rules. Users SHALL be able to override these rules by setting `METADATA_KEYWORD_RULES` in `.env` to a JSON string of `[{"pattern": "regex", "category": "name"}, ...]`.

#### Scenario: Custom keyword rules
- **WHEN** `METADATA_KEYWORD_RULES='[{"pattern": "f1|grand.prix", "category": "Motorsport"}]'` is set
- **AND** document text contains `"Formula 1"` and `"Grand Prix"`
- **THEN** `extract_metadata()` SHALL return `{"category": "Motorsport"}`

#### Scenario: Invalid JSON silently falls back
- **WHEN** `METADATA_KEYWORD_RULES` contains invalid JSON
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to default keyword rules

### Requirement: Ollama LLM-based categorisation

When `METADATA_EXTRACTION_MODE` is `"ollama"`, the system SHALL make a single HTTP POST request to the local Ollama API to classify the document. The request SHALL use the model specified by `OLLAMA_CLASSIFY_MODEL` env var (default `"qwen3:0.6b"`). On failure, the system SHALL fall back to `"uncategorised"` and log a WARNING.

#### Scenario: Successful Ollama classification
- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** Ollama returns `"AI"` for the document
- **THEN** `extract_metadata()` SHALL return `{"category": "AI"}`

#### Scenario: Ollama unreachable
- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** Ollama is not running or the model is not pulled
- **THEN** `extract_metadata()` SHALL return `{"category": "uncategorised"}`
- **THEN** the system SHALL log a WARNING with the error details

### Requirement: LlamaIndex MetadataExtractor integration (stub)

When `METADATA_EXTRACTION_MODE` is `"llamaindex"`, the system SHALL attempt to use LlamaIndex's built-in `MetadataExtractor` pipeline. In v1, this mode SHALL log an INFO message indicating the feature is not yet implemented and fall back to the `"keyword"` mode.

#### Scenario: Llamaindex mode not yet implemented
- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **THEN** the system SHALL log an INFO message: "MetadataExtractor not yet implemented — falling back to keyword mode"
- **THEN** `extract_metadata()` SHALL return results from the keyword mode

### Requirement: Metadata attachment during ingestion

During ingestion, after a file is read and chunked, the system SHALL call `extract_metadata()` once per file and attach the resulting dict to every chunk's `.metadata` field. The metadata SHALL be stored as ChromaDB metadata alongside each vector.

#### Scenario: Metadata attached to all chunks
- **WHEN** a 5-page PDF is ingested and categorised as `"AI"`
- **THEN** all chunks from that document SHALL have `metadata = {"category": "AI", ...}` in ChromaDB

#### Scenario: No metadata when disabled
- **WHEN** `METADATA_EXTRACTION_MODE=disabled`
- **THEN** chunks SHALL have no `"category"` field in their ChromaDB metadata

### Requirement: Search filtering by metadata

The search functions SHALL accept an optional `metadata_filter: dict | None` parameter. When provided, the filter SHALL be passed to ChromaDB's `where` clause. Only chunks matching the filter SHALL be returned.

#### Scenario: Filter by category
- **WHEN** `search_documents("transformer", metadata_filter={"category": "AI"})` is called
- **THEN** only chunks with `category = "AI"` SHALL be returned

#### Scenario: No filter returns all
- **WHEN** `search_documents("transformer")` is called without `metadata_filter`
- **THEN** chunks from all categories SHALL be returned (no category filtering)
