# Specification: metadata-extraction

## Purpose

Define metadata extraction modes and fallback behaviour for enriching indexed document chunks with categories, keywords, and summaries.
## Requirements
### Requirement: Ollama LLM-based categorisation with hybrid category lookup

When `METADATA__EXTRACTION_MODE` is `"local"`, the system SHALL make bounded HTTP requests to classify the document using the provider selected by `METADATA_LLM_PROVIDER`. When `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=ollama`, the system SHALL use Ollama's `/api/generate` endpoint with the model specified by `METADATA__OLLAMA_CLASSIFY_MODEL`. When `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp`, the system SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at `LLAMACPP_CHAT_URL` with the model specified by `LLAMACPP_CHAT_MODEL`. When `METADATA_LLM_PROVIDER=cloud` with `CLOUD_BACKEND=openrouter`, the system SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at `https://openrouter.ai/api/v1` with the model specified by `OPENROUTER_LLM_MODEL` and `OPENROUTER_API_KEY` for authentication. Before sending the prompt, the system SHALL query ChromaDB for all unique category values currently in use across all metadata scan pages and SHALL include them in the prompt as "existing categories" alongside the seed categories from keyword mode. The prompt SHALL instruct the model to prefer an existing category when applicable, but to propose a new concise category label (1-3 words, lowercase) when no existing category fits. The prompt SHALL instruct the model to return a JSON object with keys `category`, `keywords`, and `summary`. On transient HTTP failure or invalid JSON response, the system SHALL retry within configured limits. After retries are exhausted, the system SHALL fall back to `{"category": "uncategorised", "keywords": [], "summary": ""}` and log a WARNING.

The deprecated `METADATA__EXTRACTION_MODE=ollama` value SHALL be silently mapped to `local` with no warning, as it is a pure rename.

#### Scenario: Successful classification reuses existing category

- **WHEN** `METADATA__EXTRACTION_MODE=local`
- **AND** ChromaDB contains existing categories `["ai", "biology", "philosophy"]`
- **AND** the document is about machine learning
- **THEN** the prompt SHALL include "ai" as an existing category option
- **THEN** the backend SHALL return `{"category": "ai", ...}` (reusing the exact existing label)

#### Scenario: Category exists beyond first metadata page

- **WHEN** `METADATA__EXTRACTION_MODE=local`
- **AND** a category value exists only after the first metadata scan page
- **THEN** the existing category lookup SHALL still discover that category
- **THEN** the classification prompt SHALL include that category as an existing option

#### Scenario: First run with no existing categories

- **WHEN** `METADATA__EXTRACTION_MODE=local`
- **AND** ChromaDB has no existing category values (empty collection)
- **THEN** the prompt SHALL include the seed categories from keyword mode as the initial taxonomy
- **THEN** classification SHALL proceed normally against the seed categories

#### Scenario: Transient backend failure succeeds on retry

- **WHEN** `METADATA__EXTRACTION_MODE=local`
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

- **WHEN** `METADATA__EXTRACTION_MODE=ollama`
- **THEN** the system SHALL treat it as `local`
- **THEN** no warning SHALL be logged (pure rename, not a semantic change)

### Requirement: LlamaIndex MetadataExtractor integration

When `METADATA__EXTRACTION_MODE` is `"llamaindex"`, the system SHALL use LlamaIndex's `IngestionPipeline` with a set of metadata extractor transformations (`TitleExtractor`, `KeywordExtractor`, `SummaryExtractor`) to enrich document chunks. The LLM SHALL be selected by `METADATA_LLM_PROVIDER`: when `ollama`, the system SHALL use `Ollama` from `llama-index-llms-ollama` with `METADATA__OLLAMA_CLASSIFY_MODEL`; when `llamacpp`, the system SHALL use `OpenAILike` from `llama-index-llms-openai-like` with `LLAMACPP_CHAT_URL` and `LLAMACPP_CHAT_MODEL`; when `openrouter`, the system SHALL use `OpenAILike` with `api_base=https://openrouter.ai/api/v1`, `api_key=OPENROUTER_API_KEY`, and `model=OPENROUTER_LLM_MODEL`. If the required LLM package is not installed or the LLM calls fail, the system SHALL fall back to keyword mode and log a WARNING. The extraction SHALL run per-chunk (per node), and the aggregated metadata across all chunks SHALL be returned as a merged dict.

The metadata timeouts SHALL be resolvable per provider. The system has two shared timeouts — `CLASSIFY_TIMEOUT` (per-attempt, direct-chat classification path) and `PIPELINE_TIMEOUT` (the llamaindex multi-extractor pipeline). For each, the system SHALL support a provider-specific override keyed on the active backend: `LLAMACPP_CLASSIFY_TIMEOUT_OVERRIDE` / `OLLAMA_CLASSIFY_TIMEOUT_OVERRIDE` / `OPENROUTER_CLASSIFY_TIMEOUT_OVERRIDE` for the classify budget, and `LLAMACPP_PIPELINE_TIMEOUT_OVERRIDE` / `OLLAMA_PIPELINE_TIMEOUT_OVERRIDE` / `OPENROUTER_PIPELINE_TIMEOUT_OVERRIDE` for the pipeline budget. When a provider-specific override is set, the system SHALL use it; when unset, the system SHALL fall back to the matching shared timeout. The llamaindex pipeline SHALL resolve and use the per-provider pipeline timeout; the direct-chat classification path SHALL resolve and use the per-provider classify timeout. The resolved value SHALL reach the LLM client under the keyword the client honours (`timeout` for `OpenAILike`, `request_timeout` for `Ollama`).

#### Scenario: Successful LlamaIndex extraction with ollama provider

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=ollama`
- **AND** `llama-index-llms-ollama` is installed and Ollama is reachable
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the system SHALL use `IngestionPipeline` with at least `TitleExtractor` and `KeywordExtractor`

#### Scenario: Successful LlamaIndex extraction with llamacpp provider

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp`
- **AND** `llama-index-llms-openai-like` is installed and llama-server is reachable
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the LLM SHALL be `OpenAILike` configured with `LLAMACPP_CHAT_URL` and `LLAMACPP_CHAT_MODEL`

#### Scenario: Successful LlamaIndex extraction with openrouter provider

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=cloud` with `CLOUD_BACKEND=openrouter`
- **AND** `llama-index-llms-openai-like` is installed and `OPENROUTER_API_KEY` is set
- **THEN** `extract_metadata()` SHALL return a dict containing `category`, `keywords`, `summary`, and optionally `document_title`
- **THEN** the LLM SHALL be `OpenAILike` configured with `api_base=https://openrouter.ai/api/v1` and `model=OPENROUTER_LLM_MODEL`

#### Scenario: LlamaIndex LLM package not installed

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** the required LLM package is not installed (ImportError)
- **THEN** the system SHALL log a WARNING
- **THEN** `extract_metadata()` SHALL fall back to the next available mode (local → keyword)

#### Scenario: LlamaIndex extraction fails mid-pipeline

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** the LLM call raises an exception (timeout, runtime error, etc.)
- **THEN** the system SHALL fall back to the next available mode (local → keyword)
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL signal that this file's metadata was degraded

#### Scenario: Respects chunk limit for extraction

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** the document has more than 10 chunks
- **THEN** the extraction pipeline SHALL process at most 10 chunks (first 10 by default)
- **THEN** the remaining chunks SHALL be skipped for metadata extraction but still indexed

#### Scenario: Provider-specific pipeline timeout override is honoured

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex` and the active backend is `llamacpp`
- **AND** `LLAMACPP_PIPELINE_TIMEOUT_OVERRIDE` is set to `300.0`
- **THEN** the pipeline LLM client SHALL be constructed with a `300.0` second timeout
- **THEN** the shared `PIPELINE_TIMEOUT` value SHALL NOT be used for the llama.cpp provider

#### Scenario: Provider-specific classify timeout override is honoured

- **WHEN** the direct-chat classification path runs with the `llamacpp` backend
- **AND** `LLAMACPP_CLASSIFY_TIMEOUT_OVERRIDE` is set to `45.0`
- **THEN** the per-attempt HTTP timeout SHALL be `45.0` seconds
- **THEN** the shared `CLASSIFY_TIMEOUT` value SHALL NOT be used for the llama.cpp provider

#### Scenario: Each timeout falls back to its shared default when unset

- **WHEN** the active backend is `openrouter`
- **AND** neither `OPENROUTER_CLASSIFY_TIMEOUT_OVERRIDE` nor `OPENROUTER_PIPELINE_TIMEOUT_OVERRIDE` is set
- **THEN** the resolved classify timeout SHALL equal the shared `CLASSIFY_TIMEOUT`
- **THEN** the resolved pipeline timeout SHALL equal the shared `PIPELINE_TIMEOUT`

### Requirement: Richer metadata output format

All metadata extraction modes (except `disabled`) SHALL return a dict that follows a consistent schema: `category` (string) is always present; `keywords` (list of strings, max 10) and `summary` (string, max 300 chars) are present when the extraction mode supports them. The `category` field SHALL always be present for backward compatibility.

#### Scenario: Keyword mode output format

- **WHEN** `METADATA__EXTRACTION_MODE=keyword`
- **THEN** `extract_metadata()` SHALL return `{"category": "<category>"}` (keywords and summary omitted)

#### Scenario: Local mode output format

- **WHEN** `METADATA__EXTRACTION_MODE=local`
- **THEN** `extract_metadata()` SHALL return `{"category": "<category>", "keywords": [...], "summary": "..."}`

#### Scenario: Disabled mode output format

- **WHEN** `METADATA__EXTRACTION_MODE=disabled`
- **THEN** `extract_metadata()` SHALL return `{}` (empty dict)

### Requirement: Hybrid category taxonomy for ollama mode

Before each classification call in `local` mode, the system SHALL query ChromaDB for all unique category values currently stored across all collections and SHALL merge them with the seed categories from keyword mode (deduplicating, lowercasing). The merged list SHALL be included in the prompt as the "existing categories" the model should prefer. This follows the TnT-LLM pattern (Microsoft, KDD 2024): sample the corpus → build a taxonomy → lock and classify into it — adapted for continuous ingestion where the taxonomy grows organically.

#### Scenario: ChromaDB lookup succeeds

- **WHEN** `METADATA__EXTRACTION_MODE=local`
- **AND** ChromaDB contains 3 collections with varying categories
- **THEN** the system SHALL query all collections for unique `category` metadata values
- **THEN** the result SHALL be deduplicated and normalised (lowercase)
- **THEN** seed categories from keyword mode SHALL be merged in

#### Scenario: ChromaDB lookup fails

- **WHEN** `METADATA__EXTRACTION_MODE=local`
- **AND** the ChromaDB query raises an exception (e.g., database locked)
- **THEN** the system SHALL log a WARNING
- **THEN** the prompt SHALL use only the seed categories from keyword mode
- **THEN** classification SHALL proceed normally (no crash)

#### Scenario: Category normalisation produces duplicates

- **WHEN** the query returns `["AI", "ai", "Artificial_Intelligence", "biology"]`
- **AND** these are merged with seed categories `["ai", "philosophy"]`
- **THEN** the deduplicated set SHALL be `["ai", "artificial_intelligence", "biology", "philosophy"]`

### Requirement: Serving-layer JSON enforcement for LLM classification

When `METADATA__EXTRACTION_MODE` is `"local"`, the classification request SHALL instruct the backend to
constrain generation to valid JSON, in addition to the existing prompt-level instruction. The system
SHALL use each backend's native mechanism:

- `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=ollama` — the request to `/api/generate` SHALL set the JSON output format flag.
- `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp` — the request to `/v1/chat/completions` SHALL set the OpenAI-compatible
  JSON-object response format.
- `METADATA_LLM_PROVIDER=cloud` with `CLOUD_BACKEND=openrouter` — the request SHALL set a JSON Schema response format describing the
  three-key classification object (`category` as a string, `keywords` as an array of strings, `summary` as
  a string), with all three required. Because structured-output support on OpenRouter is determined per
  serving endpoint rather than per model, the request SHALL additionally instruct provider routing to
  select only endpoints that honour the supplied parameters.

Enforcement SHALL be additive and SHALL NOT replace existing response handling: the system SHALL continue
to strip a surrounding markdown code fence and SHALL continue to fall back to
`{"category": "uncategorised", "keywords": [], "summary": ""}` when a response cannot be parsed. The
metadata dict returned to callers SHALL be unchanged in shape.

No new configuration setting SHALL be introduced; enforcement SHALL be unconditional for these backends.

#### Scenario: Ollama request constrains output format

- **WHEN** `METADATA__EXTRACTION_MODE=local` and `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=ollama`
- **THEN** the request body sent to `/api/generate` SHALL include the JSON output format flag
- **THEN** the request body SHALL still include the classification prompt and the existing category list

#### Scenario: llama.cpp request constrains output format

- **WHEN** `METADATA__EXTRACTION_MODE=local` and `METADATA_LLM_PROVIDER=local` with `LOCAL_BACKEND=llamacpp`
- **THEN** the request body sent to `/v1/chat/completions` SHALL include a JSON-object response format

#### Scenario: OpenRouter request carries the classification schema

- **WHEN** `METADATA__EXTRACTION_MODE=local` and `METADATA_LLM_PROVIDER=cloud` with `CLOUD_BACKEND=openrouter`
- **THEN** the request body SHALL include a JSON Schema response format requiring `category`, `keywords`
  and `summary`
- **THEN** the request body SHALL instruct provider routing to require parameter support

#### Scenario: Fence stripping still applies when enforcement is ignored

- **WHEN** a backend ignores the enforcement flag and returns JSON wrapped in a markdown code fence
- **THEN** the system SHALL strip the fence and parse the JSON as before
- **THEN** the returned metadata SHALL NOT be `uncategorised`

#### Scenario: Returned metadata shape is unchanged

- **WHEN** classification succeeds under enforcement
- **THEN** the returned dict SHALL contain exactly the keys `category`, `keywords` and `summary`

### Requirement: Graceful downgrade when a backend rejects structured output

A backend MAY reject a request whose structured-output parameters it cannot satisfy. When the OpenRouter
backend receives an HTTP 400, 404 or 422 response, the system SHALL treat it as a parameter fault rather
than a transient fault: it SHALL remove the response-format and provider-routing parameters from the
request, SHALL log at INFO that structured outputs were rejected, and SHALL retry immediately without
backoff on the prompt-only path. The downgrade SHALL be attempted at most once per classification call.

The downgraded retry SHALL consume one attempt from the configured retry budget rather than exceeding it.
Where that budget leaves no attempt remaining — notably when it is configured to a single attempt — no
downgraded request SHALL be sent. A single-attempt budget is an explicit instruction to issue one request
per classification, and the downgrade SHALL NOT override it; the system SHALL fall back to
`uncategorised` exactly as it would for any other exhausted budget.

Statuses that indicate a transient or unrelated fault SHALL NOT trigger a downgrade. In particular, HTTP
429 SHALL follow the existing retry-with-backoff path, and HTTP 401 or 403 SHALL NOT be downgraded because
dropping structured outputs cannot resolve an authentication failure.

The overall retry budget SHALL be unchanged; when it is exhausted the system SHALL fall back to
`{"category": "uncategorised", "keywords": [], "summary": ""}` and log a WARNING, as today.

#### Scenario: No schema-capable endpoint available

- **WHEN** the OpenRouter request is rejected with HTTP 404 because provider routing found no endpoint
  supporting the supplied parameters
- **THEN** the system SHALL retry without the response-format and provider-routing parameters
- **THEN** the retry SHALL be issued without backoff delay
- **THEN** a successful retry SHALL return normal metadata rather than `uncategorised`

#### Scenario: Schema rejected as invalid by the upstream provider

- **WHEN** the OpenRouter request is rejected with HTTP 400 or 422
- **THEN** the system SHALL retry once without the structured-output parameters

#### Scenario: Rate limiting does not trigger downgrade

- **WHEN** the OpenRouter request is rejected with HTTP 429
- **THEN** the request SHALL be retried with the structured-output parameters still present
- **THEN** the retry SHALL observe the existing exponential backoff

#### Scenario: Authentication failure does not trigger downgrade

- **WHEN** the OpenRouter request is rejected with HTTP 401 or 403
- **THEN** the structured-output parameters SHALL remain on the request
- **THEN** the system SHALL follow the existing retry-and-fallback path

#### Scenario: Downgrade is attempted at most once

- **WHEN** a downgraded request is itself rejected with HTTP 400
- **THEN** the system SHALL NOT attempt a further downgrade
- **THEN** it SHALL follow the existing retry-and-fallback path

#### Scenario: Downgrade cannot exceed a single-attempt retry budget

- **WHEN** the retry budget is configured to a single attempt
- **AND** the OpenRouter request is rejected with HTTP 400
- **THEN** no downgraded request SHALL be sent
- **THEN** exactly one request SHALL have been issued for that classification
- **THEN** the system SHALL return `{"category": "uncategorised", "keywords": [], "summary": ""}`

#### Scenario: Downgrade path exhausts the retry budget

- **WHEN** every attempt fails, including the downgraded one
- **THEN** the system SHALL return `{"category": "uncategorised", "keywords": [], "summary": ""}`
- **THEN** the system SHALL log a WARNING

### Requirement: Metadata degradation is reported, not only logged

When metadata extraction falls back from the configured LLM-backed mode to a lower tier (`llamaindex` → `local` → `keyword`) because the LLM package is missing, the backend is unreachable, a call times out, or a response cannot be parsed, the system SHALL signal that a degradation occurred in a way the ingestion caller can observe, in addition to the existing WARNING log. The signal SHALL identify that the file's metadata was produced by a fallback rather than the configured mode. Successful extraction in the configured mode SHALL NOT raise the signal.

The signal SHALL NOT change the metadata dict shape returned to chunk writers: `category`, `keywords`, and `summary` remain as today. The degradation is reported through a side channel consumed by the ingestion pipeline (see the `async-ingestion` capability), not by mutating the per-chunk metadata.

#### Scenario: Timeout fallback is signalled

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex` and the LLM call times out
- **THEN** the system SHALL fall back to keyword metadata
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL signal that this file's metadata was degraded

#### Scenario: Successful extraction raises no degradation signal

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex` and extraction succeeds in the configured mode
- **THEN** no degradation signal SHALL be raised for that file

#### Scenario: Degradation signal does not alter metadata shape

- **WHEN** a file's metadata is produced by a fallback tier
- **THEN** the metadata dict written to chunks SHALL still contain the standard `category` field
- **THEN** the degradation SHALL be reported separately from the metadata dict

