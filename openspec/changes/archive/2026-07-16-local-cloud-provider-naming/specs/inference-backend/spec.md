## MODIFIED Requirements

### Requirement: Inference backend selection

The system SHALL support two embedding provider categories selected via the `EMBED_PROVIDER` environment variable: `local` (default) and `cloud`. The system SHALL validate the provider value at import time and fall back to `local` with a warning on unknown values. The system SHALL use `LOCAL_BACKEND` (default: `llamacpp`) to select the local implementation when `EMBED_PROVIDER=local`, and `CLOUD_BACKEND` (default: `openrouter`) to select the cloud implementation when `EMBED_PROVIDER=cloud`. The system SHALL maintain nested provider registry dicts in `config.py` (`LOCAL_EMBED_PROVIDERS`, `CLOUD_EMBED_PROVIDERS`, `LOCAL_LLM_PROVIDERS`, `CLOUD_LLM_PROVIDERS`) that map each sub-provider name to its module, class, required env vars, and optional dependency group. A single `_build_provider()` function SHALL resolve the category → sub-provider → registry entry, dynamically import the class, and instantiate it.

The old flat provider names (`ollama`, `llamacpp`, `openrouter`) SHALL no longer be accepted as `EMBED_PROVIDER` or `METADATA_LLM_PROVIDER` values.

#### Scenario: Default provider is local with llamacpp backend

- **WHEN** `EMBED_PROVIDER` is not set
- **AND** `LOCAL_BACKEND` is not set
- **THEN** the system SHALL use `local` as the embedding provider category
- **AND** the system SHALL use `llamacpp` as the local backend
- **THEN** `Settings.embed_model` SHALL be an `OpenAIEmbedding` instance targeting `LLAMACPP_EMBED_URL`

#### Scenario: Local with ollama backend

- **WHEN** `EMBED_PROVIDER=local`
- **AND** `LOCAL_BACKEND=ollama`
- **THEN** the system SHALL use `OllamaEmbedding` with `OLLAMA_BASE_URL` and `EMBED_MODEL`

#### Scenario: Local with llamacpp backend

- **WHEN** `EMBED_PROVIDER=local`
- **AND** `LOCAL_BACKEND=llamacpp`
- **AND** `llama-index-embeddings-openai` is installed
- **THEN** the system SHALL use `OpenAIEmbedding` with `LLAMACPP_EMBED_URL` and `LLAMACPP_EMBED_MODEL`

#### Scenario: Cloud with openrouter backend

- **WHEN** `EMBED_PROVIDER=cloud`
- **AND** `CLOUD_BACKEND=openrouter`
- **AND** `OPENROUTER_API_KEY` and `OPENROUTER_EMBED_MODEL` are set
- **AND** `llama-index-embeddings-openai` is installed
- **THEN** the system SHALL use `OpenAIEmbedding` with `api_base=https://openrouter.ai/api/v1`

#### Scenario: Local with llamacpp but optional deps not installed

- **WHEN** `EMBED_PROVIDER=local`
- **AND** `LOCAL_BACKEND=llamacpp`
- **AND** `llama-index-embeddings-openai` is not installed
- **THEN** the system SHALL raise an `ImportError` instructing the user to run `uv sync --extra llamacpp`

#### Scenario: Unknown provider category

- **WHEN** `EMBED_PROVIDER` is set to a value other than `local` or `cloud`
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to `local`

#### Scenario: Unknown local backend

- **WHEN** `EMBED_PROVIDER=local`
- **AND** `LOCAL_BACKEND` is set to a value other than `llamacpp` or `ollama`
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to `llamacpp`

### Requirement: llamacpp embedding configuration

When `EMBED_PROVIDER=local` and `LOCAL_BACKEND=llamacpp`, the system SHALL read `LLAMACPP_EMBED_URL` (default `http://localhost:8080/v1`), `LLAMACPP_EMBED_MODEL` (the GGUF filename), and reuse `EMBED_BATCH_SIZE` for batch size. The `OpenAIEmbedding` instance SHALL be configured with `api_key="no-key"` since `llama-server` does not require authentication.

#### Scenario: Embedding server reachable
- **WHEN** `EMBED_PROVIDER=local`
- **AND** `LOCAL_BACKEND=llamacpp`
- **AND** `LLAMACPP_EMBED_URL=http://localhost:8080/v1`
- **AND** `LLAMACPP_EMBED_MODEL=Qwen3-Embedding-0.6B-Q8_0.gguf`
- **THEN** `Settings.embed_model` SHALL be an `OpenAIEmbedding` instance
- **THEN** embedding requests SHALL be sent to `http://localhost:8080/v1/embeddings`

#### Scenario: Custom embed URL
- **WHEN** `LLAMACPP_EMBED_URL=http://192.168.1.100:8080/v1`
- **THEN** embedding requests SHALL target that URL

### Requirement: llamacpp chat configuration for metadata extraction

When `METADATA_LLM_PROVIDER=local`, `LOCAL_BACKEND=llamacpp`, and `METADATA_EXTRACTION_MODE` is `local` or `llamaindex`, the system SHALL use `LLAMACPP_CHAT_URL` (default `http://localhost:8081/v1`) and `LLAMACPP_CHAT_MODEL` for LLM calls. The `local` metadata mode SHALL use `httpx` to call `/v1/chat/completions` with the OpenAI chat format. The `llamaindex` metadata mode SHALL use `OpenAILike` LLM from `llama-index-llms-openai-like`.

#### Scenario: local metadata mode with llamacpp backend
- **WHEN** `METADATA_LLM_PROVIDER=local`
- **AND** `LOCAL_BACKEND=llamacpp`
- **AND** `METADATA_EXTRACTION_MODE=local`
- **THEN** the system SHALL POST to `{LLAMACPP_CHAT_URL}/chat/completions`
- **THEN** the request body SHALL follow OpenAI chat format with `model`, `messages`, and `stream: false`
- **THEN** the response SHALL be parsed from `choices[0].message.content`

#### Scenario: llamaindex metadata mode with llamacpp backend
- **WHEN** `METADATA_LLM_PROVIDER=local`
- **AND** `LOCAL_BACKEND=llamacpp`
- **AND** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `llama-index-llms-openai-like` is installed
- **THEN** the LLM SHALL be `OpenAILike` with `api_base=LLAMACPP_CHAT_URL` and `model=LLAMACPP_CHAT_MODEL`
- **THEN** the extraction pipeline SHALL use this LLM for `TitleExtractor`, `KeywordExtractor`, and `SummaryExtractor`

#### Scenario: llamaindex mode with llamacpp but openai-like not installed
- **WHEN** `METADATA_LLM_PROVIDER=local`
- **AND** `LOCAL_BACKEND=llamacpp`
- **AND** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `llama-index-llms-openai-like` is not installed
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to the `local` metadata mode (which uses raw `httpx`)

### Requirement: Split embedding and metadata LLM provider selection

The system SHALL use two independent env vars for provider category selection: `EMBED_PROVIDER` (controls embedding model) and `METADATA_LLM_PROVIDER` (controls metadata extraction LLM). Both accept `local` or `cloud`. When `METADATA_LLM_PROVIDER` is not set, it SHALL default to `local` (safe, free) to avoid surprising cloud API costs when a user sets `EMBED_PROVIDER=cloud` without explicitly opting into cloud LLM for metadata. The `LOCAL_BACKEND` and `CLOUD_BACKEND` env vars SHALL apply to both embeddings and metadata LLM — a single sub-provider selection controls both.

#### Scenario: Both providers set independently

- **WHEN** `EMBED_PROVIDER=cloud`
- **AND** `METADATA_LLM_PROVIDER=local`
- **AND** `LOCAL_BACKEND=llamacpp`
- **THEN** embeddings SHALL use the cloud provider (OpenRouter)
- **AND** metadata extraction LLM SHALL use the local provider (llama.cpp)

#### Scenario: Only embed provider set, metadata LLM defaults to local

- **WHEN** `EMBED_PROVIDER=cloud`
- **AND** `METADATA_LLM_PROVIDER` is not set
- **THEN** metadata extraction LLM SHALL default to `local`
- **THEN** no paid cloud LLM calls SHALL be made without explicit opt-in

#### Scenario: Mix local embeddings with cloud LLM

- **WHEN** `EMBED_PROVIDER=local`
- **AND** `METADATA_LLM_PROVIDER=cloud`
- **AND** `CLOUD_BACKEND=openrouter`
- **THEN** embeddings SHALL use the local provider
- **AND** metadata extraction LLM SHALL use the cloud provider (OpenRouter)
