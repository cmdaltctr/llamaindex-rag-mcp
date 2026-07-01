## MODIFIED Requirements

### Requirement: Ollama LLM-based categorisation with hybrid category lookup

When `METADATA_EXTRACTION_MODE` is `"ollama"`, the system SHALL make bounded local HTTP requests to classify the document using the selected inference backend. When `INFERENCE_BACKEND=ollama`, the system SHALL use Ollama's `/api/generate` endpoint with the model specified by `OLLAMA_CLASSIFY_MODEL`. When `INFERENCE_BACKEND=llamacpp`, the system SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at `LLAMACPP_CHAT_URL` with the model specified by `LLAMACPP_CHAT_MODEL`. Before sending the prompt, the system SHALL query ChromaDB for all unique category values currently in use across all metadata scan pages and SHALL include them in the prompt as "existing categories" alongside the seed categories from keyword mode. The prompt SHALL instruct the model to prefer an existing category when applicable, but to propose a new concise category label (1-3 words, lowercase) when no existing category fits. The prompt SHALL instruct the model to return a JSON object with keys `category`, `keywords`, and `summary`. On transient HTTP failure or invalid JSON response, the system SHALL retry within configured limits. After retries are exhausted, the system SHALL fall back to `{"category": "uncategorised", "keywords": [], "summary": ""}` and log a WARNING.

#### Scenario: Successful classification reuses existing category
- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** ChromaDB contains existing categories `["ai", "biology", "philosophy"]`
- **AND** the document is about machine learning
- **THEN** the prompt SHALL include "ai" as an existing category option
- **THEN** the backend SHALL return `{"category": "ai", ...}` (reusing the exact existing label)

#### Scenario: Category exists beyond first metadata page
- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** a category value exists only after the first metadata scan page
- **THEN** the existing category lookup SHALL still discover that category
- **THEN** the classification prompt SHALL include that category as an existing option

#### Scenario: First run with no existing categories
- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
- **AND** ChromaDB has no existing category values (empty collection)
- **THEN** the prompt SHALL include the seed categories from keyword mode as the initial taxonomy
- **THEN** classification SHALL proceed normally against the seed categories

#### Scenario: Transient backend failure succeeds on retry
- **WHEN** `METADATA_EXTRACTION_MODE=ollama`
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

### Requirement: LlamaIndex MetadataExtractor integration

When `METADATA_EXTRACTION_MODE` is `"llamaindex"`, the system SHALL use LlamaIndex's `IngestionPipeline` with a set of metadata extractor transformations (`TitleExtractor`, `KeywordExtractor`, `SummaryExtractor`) to enrich document chunks. When `INFERENCE_BACKEND=ollama`, the system SHALL configure the LLM using `Ollama` from `llama-index-llms-ollama` with the model specified by `OLLAMA_CLASSIFY_MODEL`. When `INFERENCE_BACKEND=llamacpp`, the system SHALL configure the LLM using `OpenAILike` from `llama-index-llms-openai-like` with `LLAMACPP_CHAT_URL` and `LLAMACPP_CHAT_MODEL`. If the required LLM package is not installed or the LLM calls fail, the system SHALL fall back to keyword mode and log a WARNING. The extraction SHALL run per-chunk (per node), and the aggregated metadata across all chunks SHALL be returned as a merged dict.

#### Scenario: Successful LlamaIndex extraction with ollama backend

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `INFERENCE_BACKEND=ollama`
- **AND** `llama-index-llms-ollama` is installed and Ollama is reachable
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the system SHALL use `IngestionPipeline` with at least `TitleExtractor` and `KeywordExtractor`

#### Scenario: Successful LlamaIndex extraction with llamacpp backend

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `INFERENCE_BACKEND=llamacpp`
- **AND** `llama-index-llms-openai-like` is installed and llama-server is reachable
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the LLM SHALL be `OpenAILike` configured with `LLAMACPP_CHAT_URL` and `LLAMACPP_CHAT_MODEL`

#### Scenario: LlamaIndex LLM package not installed

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** the required LLM package (`llama-index-llms-ollama` or `llama-index-llms-openai-like`) is not installed (ImportError)
- **THEN** the system SHALL log a WARNING
- **THEN** `extract_metadata()` SHALL fall back to the next available mode (ollama → keyword, or llamacpp chat → keyword)

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
