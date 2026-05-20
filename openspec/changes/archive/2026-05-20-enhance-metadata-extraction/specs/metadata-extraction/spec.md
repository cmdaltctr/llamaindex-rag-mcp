# Delta Specification: metadata-extraction

## MODIFIED Requirements

### Requirement: Ollama LLM-based categorisation with hybrid category lookup

When `METADATA_EXTRACTION_MODE` is `"ollama"`, the system SHALL make a single HTTP POST request to the local Ollama `/api/generate` endpoint to classify the document. The request SHALL use the model specified by `OLLAMA_CLASSIFY_MODEL` env var (default `"qwen3:0.6b"`). Before sending the prompt, the system SHALL query ChromaDB for all unique category values currently in use and SHALL include them in the prompt as "existing categories" alongside the seed categories from keyword mode. The prompt SHALL instruct the model to prefer an existing category when applicable, but to propose a new concise category label (1-3 words, lowercase) when no existing category fits. The prompt SHALL instruct the model to return a JSON object with keys `category`, `keywords`, and `summary`. On failure (Ollama unreachable, model not pulled, or invalid JSON response), the system SHALL fall back to `{"category": "uncategorised", "keywords": [], "summary": ""}` and log a WARNING.

#### Scenario: Successful classification reuses existing category

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** ChromaDB contains existing categories `["ai", "biology", "philosophy"]`
- **AND** the document is about machine learning
- **THEN** the prompt SHALL include "ai" as an existing category option
- **THEN** Ollama SHALL return `{"category": "ai", ...}` (reusing the exact existing label)

#### Scenario: Classification proposes a new category

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** ChromaDB contains existing categories `["ai", "biology"]`
- **AND** the document is about music theory (matches no existing category)
- **THEN** Ollama MAY return `{"category": "music", ...}` as a new proposed category
- **THEN** the system SHALL normalise the new category (lowercase, max 3 words, underscores for spaces)
- **THEN** the new category SHALL be stored and available for future classification prompts

#### Scenario: First run with no existing categories

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** ChromaDB has no existing category values (empty collection)
- **THEN** the prompt SHALL include the seed categories from keyword mode as the initial taxonomy
- **THEN** classification SHALL proceed normally against the seed categories

#### Scenario: Successful Ollama classification with rich output

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** Ollama returns valid JSON `{"category": "AI", "keywords": ["transformer", "attention"], "summary": "This document discusses..."}`
- **THEN** `extract_metadata()` SHALL return `{"category": "AI", "keywords": ["transformer", "attention"], "summary": "This document discusses..."}`

#### Scenario: Ollama returns JSON but missing optional fields

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** Ollama returns valid JSON `{"category": "Biology"}` (no keywords or summary keys)
- **THEN** `extract_metadata()` SHALL return `{"category": "Biology", "keywords": [], "summary": ""}`

#### Scenario: Ollama returns invalid JSON

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** Ollama returns a plain text string `"AI"` (not valid JSON)
- **THEN** `extract_metadata()` SHALL return `{"category": "AI", "keywords": [], "summary": ""}`
- **THEN** the system SHALL log a WARNING

#### Scenario: Ollama unreachable

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** Ollama is not running or the model is not pulled
- **THEN** `extract_metadata()` SHALL return `{"category": "uncategorised", "keywords": [], "summary": ""}`
- **THEN** the system SHALL log a WARNING with the error details

#### Scenario: Category output normalised

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** Ollama returns a category with mixed case or spaces, e.g. `"Artificial Intelligence"`
- **THEN** the system SHALL normalise to `"artificial_intelligence"` (lowercase, underscores)
- **THEN** the system SHALL reject categories longer than 3 words → `"uncategorised"`

#### Scenario: Keywords truncated to maximum length

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** the model returns more than 10 keywords
- **THEN** the returned list SHALL be truncated to 10
- **THEN** the summary SHALL be truncated to 300 characters

### Requirement: LlamaIndex MetadataExtractor integration

When `METADATA_EXTRACTION_MODE` is `"llamaindex"`, the system SHALL use LlamaIndex's `IngestionPipeline` with a set of metadata extractor transformations (`TitleExtractor`, `KeywordExtractor`, `SummaryExtractor`) to enrich document chunks. The system SHALL configure `Settings.llm` lazily on first use using the model specified by `OLLAMA_CLASSIFY_MODEL`. If `llama-index-llms-ollama` is not installed or the LLM calls fail, the system SHALL fall back to keyword mode and log a WARNING. The extraction SHALL run per-chunk (per node), and the aggregated metadata across all chunks SHALL be returned as a merged dict.

#### Scenario: Successful LlamaIndex extraction

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `llama-index-llms-ollama` is installed and Ollama is reachable
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the system SHALL use `IngestionPipeline` with at least `TitleExtractor` and `KeywordExtractor`

#### Scenario: LlamaIndex LLM package not installed

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `llama-index-llms-ollama` is not installed (ImportError)
- **THEN** the system SHALL log a WARNING: "llama-index-llms-ollama not installed — falling back to keyword mode"
- **THEN** `extract_metadata()` SHALL return results from keyword mode

#### Scenario: LlamaIndex extraction fails mid-pipeline

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** the LLM call succeeds but returns empty or unparseable output
- **THEN** the system SHALL fall back to keyword mode
- **THEN** the system SHALL log a WARNING

#### Scenario: Respects chunk limit for extraction

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** the document has more than 10 chunks
- **THEN** the extraction pipeline SHALL process at most 10 chunks (first 10 by default)
- **THEN** the remaining chunks SHALL be skipped for metadata extraction but still indexed

## ADDED Requirements

### Requirement: Richer metadata output format

All metadata extraction modes (except `disabled`) SHALL return a dict that follows a consistent schema: `category` (string) is always present; `keywords` (list of strings, max 10) and `summary` (string, max 300 chars) are present when the extraction mode supports them. The `category` field SHALL always be present for backward compatibility.

#### Scenario: Keyword mode output format

- **WHEN** `METADATA_EXTRACTION_MODE=keyword`
- **THEN** `extract_metadata()` SHALL return `{"category": "<category>"}` (keywords and summary omitted)

#### Scenario: Ollama mode output format

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **THEN** `extract_metadata()` SHALL return `{"category": "<category>", "keywords": [...], "summary": "..."}`

#### Scenario: Disabled mode output format

- **WHEN** `METADATA_EXTRACTION_MODE=disabled`
- **THEN** `extract_metadata()` SHALL return `{}` (empty dict)

### Requirement: Hybrid category taxonomy for ollama mode

Before each Ollama classification call, the system SHALL query ChromaDB for all unique category values currently stored across all collections and SHALL merge them with the seed categories from keyword mode (deduplicating, lowercasing). The merged list SHALL be included in the Ollama prompt as the "existing categories" the model should prefer. This follows the TnT-LLM pattern (Microsoft, KDD 2024): sample the corpus → build a taxonomy → lock and classify into it — adapted for continuous ingestion where the taxonomy grows organically.

#### Scenario: ChromaDB lookup succeeds

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** ChromaDB contains 3 collections with varying categories
- **THEN** the system SHALL query all collections for unique `category` metadata values
- **THEN** the result SHALL be deduplicated and normalised (lowercase)
- **THEN** seed categories from keyword mode SHALL be merged in

#### Scenario: ChromaDB lookup fails

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** the ChromaDB query raises an exception (e.g., database locked)
- **THEN** the system SHALL log a WARNING
- **THEN** the prompt SHALL use only the seed categories from keyword mode
- **THEN** classification SHALL proceed normally (no crash)

#### Scenario: Category normalisation produces duplicates

- **WHEN** the query returns `["AI", "ai", "Artificial_Intelligence", "biology"]`
- **AND** these are merged with seed categories `["ai", "philosophy"]`
- **THEN** the deduplicated set SHALL be `["ai", "artificial_intelligence", "biology", "philosophy"]`
