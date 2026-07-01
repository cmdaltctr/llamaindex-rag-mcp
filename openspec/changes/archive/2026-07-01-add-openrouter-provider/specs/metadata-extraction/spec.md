## MODIFIED Requirements

### Requirement: Ollama LLM-based categorisation with hybrid category lookup

When `METADATA_EXTRACTION_MODE` is `"local"`, the system SHALL make bounded HTTP requests to classify the document using the provider selected by `METADATA_LLM_PROVIDER`. When `METADATA_LLM_PROVIDER=ollama`, the system SHALL use Ollama's `/api/generate` endpoint with the model specified by `OLLAMA_CLASSIFY_MODEL`. When `METADATA_LLM_PROVIDER=llamacpp`, the system SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at `LLAMACPP_CHAT_URL` with the model specified by `LLAMACPP_CHAT_MODEL`. When `METADATA_LLM_PROVIDER=openrouter`, the system SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at `https://openrouter.ai/api/v1` with the model specified by `OPENROUTER_LLM_MODEL` and `OPENROUTER_API_KEY` for authentication. Before sending the prompt, the system SHALL query ChromaDB for all unique category values currently in use across all metadata scan pages and SHALL include them in the prompt as "existing categories" alongside the seed categories from keyword mode. The prompt SHALL instruct the model to prefer an existing category when applicable, but to propose a new concise category label (1-3 words, lowercase) when no existing category fits. The prompt SHALL instruct the model to return a JSON object with keys `category`, `keywords`, and `summary`. On transient HTTP failure or invalid JSON response, the system SHALL retry within configured limits. After retries are exhausted, the system SHALL fall back to `{"category": "uncategorised", "keywords": [], "summary": ""}` and log a WARNING.

The deprecated `METADATA_EXTRACTION_MODE=ollama` value SHALL be silently mapped to `local` with no warning, as it is a pure rename.

#### Scenario: Successful classification reuses existing category

- **WHEN** `METADATA_EXTRACTION_MODE=local`
- **AND** ChromaDB contains existing categories `["ai", "biology", "philosophy"]`
- **AND** the document is about machine learning
- **THEN** the prompt SHALL include "ai" as an existing category option
- **THEN** the backend SHALL return `{"category": "ai", ...}` (reusing the exact existing label)

#### Scenario: Category exists beyond first metadata page

- **WHEN** `METADATA_EXTRACTION_MODE=local`
- **AND** a category value exists only after the first metadata scan page
- **THEN** the existing category lookup SHALL still discover that category
- **THEN** the classification prompt SHALL include that category as an existing option

#### Scenario: First run with no existing categories

- **WHEN** `METADATA_EXTRACTION_MODE=local`
- **AND** ChromaDB has no existing category values (empty collection)
- **THEN** the prompt SHALL include the seed categories from keyword mode as the initial taxonomy
- **THEN** classification SHALL proceed normally against the seed categories

#### Scenario: Transient backend failure succeeds on retry

- **WHEN** `METADATA_EXTRACTION_MODE=local`
- **AND** the first backend request fails with a transient timeout or 5xx response
- **AND** a later retry succeeds within the configured retry limit
- **THEN** `extract_metadata_async` SHALL return the successful metadata response
- **THEN** it SHALL NOT fall back to `uncategorised`

#### Scenario: JSON wrapped in markdown code fence

- **WHEN** the backend returns valid JSON wrapped in a markdown code fence
- **THEN** the metadata parser SHALL strip the code fence
- **THEN** it SHALL parse and normalise the JSON object

#### Scenario: Retries exhausted

- **WHEN** every classification attempt fails
- **THEN** the system SHALL return `{"category": "uncategorised", "keywords": [], "summary": ""}`
- **THEN** the system SHALL log a WARNING with enough detail to diagnose the failure

#### Scenario: Legacy ollama mode name silently mapped

- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **THEN** the system SHALL treat it as `local`
- **THEN** no warning SHALL be logged (pure rename, not a semantic change)

### Requirement: LlamaIndex MetadataExtractor integration

When `METADATA_EXTRACTION_MODE` is `"llamaindex"`, the system SHALL use LlamaIndex's `IngestionPipeline` with a set of metadata extractor transformations (`TitleExtractor`, `KeywordExtractor`, `SummaryExtractor`) to enrich document chunks. The LLM SHALL be selected by `METADATA_LLM_PROVIDER`: when `ollama`, the system SHALL use `Ollama` from `llama-index-llms-ollama` with `OLLAMA_CLASSIFY_MODEL`; when `llamacpp`, the system SHALL use `OpenAILike` from `llama-index-llms-openai-like` with `LLAMACPP_CHAT_URL` and `LLAMACPP_CHAT_MODEL`; when `openrouter`, the system SHALL use `OpenAILike` with `api_base=https://openrouter.ai/api/v1`, `api_key=OPENROUTER_API_KEY`, and `model=OPENROUTER_LLM_MODEL`. If the required LLM package is not installed or the LLM calls fail, the system SHALL fall back to keyword mode and log a WARNING. The extraction SHALL run per-chunk (per node), and the aggregated metadata across all chunks SHALL be returned as a merged dict.

#### Scenario: Successful LlamaIndex extraction with ollama provider

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=ollama`
- **AND** `llama-index-llms-ollama` is installed and Ollama is reachable
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the system SHALL use `IngestionPipeline` with at least `TitleExtractor` and `KeywordExtractor`

#### Scenario: Successful LlamaIndex extraction with llamacpp provider

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=llamacpp`
- **AND** `llama-index-llms-openai-like` is installed and llama-server is reachable
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the LLM SHALL be `OpenAILike` configured with `LLAMACPP_CHAT_URL` and `LLAMACPP_CHAT_MODEL`

#### Scenario: Successful LlamaIndex extraction with openrouter provider

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=openrouter`
- **AND** `llama-index-llms-openai-like` is installed and `OPENROUTER_API_KEY` is set
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the LLM SHALL be `OpenAILike` configured with `api_base=https://openrouter.ai/api/v1` and `model=OPENROUTER_LLM_MODEL`

#### Scenario: LlamaIndex LLM package not installed

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** the required LLM package is not installed (ImportError)
- **THEN** the system SHALL log a WARNING
- **THEN** `extract_metadata()` SHALL fall back to the next available mode (local → keyword)

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

### Requirement: Richer metadata output format

All metadata extraction modes (except `disabled`) SHALL return a dict that follows a consistent schema: `category` (string) is always present; `keywords` (list of strings, max 10) and `summary` (string, max 300 chars) are present when the extraction mode supports them. The `category` field SHALL always be present for backward compatibility.

#### Scenario: Keyword mode output format

- **WHEN** `METADATA_EXTRACTION_MODE=keyword`
- **THEN** `extract_metadata()` SHALL return `{"category": "<category>"}` (keywords and summary omitted)

#### Scenario: Local mode output format

- **WHEN** `METADATA_EXTRACTION_MODE=local`
- **THEN** `extract_metadata()` SHALL return `{"category": "<category>", "keywords": [...], "summary": "..."}`

#### Scenario: Disabled mode output format

- **WHEN** `METADATA_EXTRACTION_MODE=disabled`
- **THEN** `extract_metadata()` SHALL return `{}` (empty dict)

### Requirement: Hybrid category taxonomy for ollama mode

Before each classification call in `local` mode, the system SHALL query ChromaDB for all unique category values currently stored across all collections and SHALL merge them with the seed categories from keyword mode (deduplicating, lowercasing). The merged list SHALL be included in the prompt as the "existing categories" the model should prefer. This follows the TnT-LLM pattern (Microsoft, KDD 2024): sample the corpus → build a taxonomy → lock and classify into it — adapted for continuous ingestion where the taxonomy grows organically.

#### Scenario: ChromaDB lookup succeeds

- **WHEN** `METADATA_EXTRACTION_MODE=local`
- **AND** ChromaDB contains 3 collections with varying categories
- **THEN** the system SHALL query all collections for unique `category` metadata values
- **THEN** the result SHALL be deduplicated and normalised (lowercase)
- **THEN** seed categories from keyword mode SHALL be merged in

#### Scenario: ChromaDB lookup fails

- **WHEN** `METADATA_EXTRACTION_MODE=local`
- **AND** the ChromaDB query raises an exception (e.g., database locked)
- **THEN** the system SHALL log a WARNING
- **THEN** the prompt SHALL use only the seed categories from keyword mode
- **THEN** classification SHALL proceed normally (no crash)

#### Scenario: Category normalisation produces duplicates

- **WHEN** the query returns `["AI", "ai", "Artificial_Intelligence", "biology"]`
- **AND** these are merged with seed categories `["ai", "philosophy"]`
- **THEN** the deduplicated set SHALL be `["ai", "artificial_intelligence", "biology", "philosophy"]`
