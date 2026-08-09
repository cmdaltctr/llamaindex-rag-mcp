## MODIFIED Requirements

### Requirement: LlamaIndex MetadataExtractor integration

When `METADATA_EXTRACTION_MODE` is `"llamaindex"`, the system SHALL use LlamaIndex's `IngestionPipeline` with a set of metadata extractor transformations (`TitleExtractor`, `KeywordExtractor`, `SummaryExtractor`) to enrich document chunks. The LLM SHALL be selected by `METADATA_LLM_PROVIDER`: when `ollama`, the system SHALL use `Ollama` from `llama-index-llms-ollama` with `OLLAMA_CLASSIFY_MODEL`; when `llamacpp`, the system SHALL use `OpenAILike` from `llama-index-llms-openai-like` with `LLAMACPP_CHAT_URL` and `LLAMACPP_CHAT_MODEL`; when `openrouter`, the system SHALL use `OpenAILike` with `api_base=https://openrouter.ai/api/v1`, `api_key=OPENROUTER_API_KEY`, and `model=OPENROUTER_LLM_MODEL`. If the required LLM package is not installed or the LLM calls fail, the system SHALL fall back to keyword mode and log a WARNING. The extraction SHALL run per-chunk (per node), and the aggregated metadata across all chunks SHALL be returned as a merged dict.

The metadata timeouts SHALL be resolvable per provider. The system has two shared timeouts — `CLASSIFY_TIMEOUT` (per-attempt, direct-chat classification path) and `PIPELINE_TIMEOUT` (the llamaindex multi-extractor pipeline). For each, the system SHALL support a provider-specific override keyed on the active backend: `LLAMACPP_CLASSIFY_TIMEOUT_OVERRIDE` / `OLLAMA_CLASSIFY_TIMEOUT_OVERRIDE` / `OPENROUTER_CLASSIFY_TIMEOUT_OVERRIDE` for the classify budget, and `LLAMACPP_PIPELINE_TIMEOUT_OVERRIDE` / `OLLAMA_PIPELINE_TIMEOUT_OVERRIDE` / `OPENROUTER_PIPELINE_TIMEOUT_OVERRIDE` for the pipeline budget. When a provider-specific override is set, the system SHALL use it; when unset, the system SHALL fall back to the matching shared timeout. The llamaindex pipeline SHALL resolve and use the per-provider pipeline timeout; the direct-chat classification path SHALL resolve and use the per-provider classify timeout. The resolved value SHALL reach the LLM client under the keyword the client honours (`timeout` for `OpenAILike`, `request_timeout` for `Ollama`).

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
- **AND** the LLM call raises an exception (timeout, runtime error, etc.)
- **THEN** the system SHALL fall back to the next available mode (local → keyword)
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL signal that this file's metadata was degraded

#### Scenario: Respects chunk limit for extraction

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** the document has more than 10 chunks
- **THEN** the extraction pipeline SHALL process at most 10 chunks (first 10 by default)
- **THEN** the remaining chunks SHALL be skipped for metadata extraction but still indexed

#### Scenario: Provider-specific pipeline timeout override is honoured

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex` and the active backend is `llamacpp`
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

## ADDED Requirements

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
