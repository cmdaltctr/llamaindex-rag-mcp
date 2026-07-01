# Specification: inference-backend

## Purpose

Define how the RAG MCP server selects between inference backends (Ollama and llama.cpp) for embeddings and metadata extraction LLM calls.
## Requirements
### Requirement: Inference backend selection

The system SHALL support three embedding providers selected via the `EMBED_PROVIDER` environment variable: `ollama` (default), `llamacpp`, and `openrouter`. The system SHALL validate the provider value at import time and fall back to `ollama` with a warning on unknown values. The system SHALL maintain a provider registry dict in `config.py` that maps each provider name to its module, class, required env vars, and optional dependency group. A single `_build_provider()` function SHALL resolve the registry entry, dynamically import the class, and instantiate it.

The deprecated `INFERENCE_BACKEND` env var SHALL still be accepted: when `EMBED_PROVIDER` is not set but `INFERENCE_BACKEND` is, the system SHALL map the value and log a deprecation warning.

#### Scenario: Default provider is ollama

- **WHEN** `EMBED_PROVIDER` is not set and `INFERENCE_BACKEND` is not set
- **THEN** the system SHALL use `ollama` as the embedding provider
- **THEN** existing behaviour SHALL be preserved with no changes

#### Scenario: Explicit ollama provider

- **WHEN** `EMBED_PROVIDER=ollama`
- **THEN** the system SHALL use `OllamaEmbedding` with `OLLAMA_BASE_URL` and `EMBED_MODEL`

#### Scenario: llamacpp provider selected

- **WHEN** `EMBED_PROVIDER=llamacpp`
- **AND** `llama-index-embeddings-openai` is installed
- **THEN** the system SHALL use `OpenAIEmbedding` with `LLAMACPP_EMBED_URL` and `LLAMACPP_EMBED_MODEL`

#### Scenario: openrouter provider selected

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY` and `OPENROUTER_EMBED_MODEL` are set
- **AND** `llama-index-embeddings-openai` is installed
- **THEN** the system SHALL use `OpenAIEmbedding` with `api_base=https://openrouter.ai/api/v1`

#### Scenario: llamacpp provider but optional deps not installed

- **WHEN** `EMBED_PROVIDER=llamacpp`
- **AND** `llama-index-embeddings-openai` is not installed
- **THEN** the system SHALL raise an `ImportError` instructing the user to run `uv sync --extra llamacpp`

#### Scenario: Unknown provider value

- **WHEN** `EMBED_PROVIDER` is set to a value other than `ollama`, `llamacpp`, or `openrouter`
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to `ollama`

#### Scenario: Legacy INFERENCE_BACKEND mapping

- **WHEN** `INFERENCE_BACKEND=llamacpp` is set
- **AND** `EMBED_PROVIDER` is not set
- **THEN** the system SHALL set `EMBED_PROVIDER=llamacpp`
- **THEN** the system SHALL log a deprecation WARNING advising migration to `EMBED_PROVIDER`

### Requirement: llamacpp embedding configuration

When `INFERENCE_BACKEND=llamacpp`, the system SHALL read `LLAMACPP_EMBED_URL` (default `http://localhost:8080/v1`), `LLAMACPP_EMBED_MODEL` (the GGUF filename), and reuse `EMBED_BATCH_SIZE` for batch size. The `OpenAIEmbedding` instance SHALL be configured with `api_key="no-key"` since `llama-server` does not require authentication.

#### Scenario: Embedding server reachable
- **WHEN** `INFERENCE_BACKEND=llamacpp`
- **AND** `LLAMACPP_EMBED_URL=http://localhost:8080/v1`
- **AND** `LLAMACPP_EMBED_MODEL=Qwen3-Embedding-0.6B-Q8_0.gguf`
- **THEN** `Settings.embed_model` SHALL be an `OpenAIEmbedding` instance
- **THEN** embedding requests SHALL be sent to `http://localhost:8080/v1/embeddings`

#### Scenario: Custom embed URL
- **WHEN** `LLAMACPP_EMBED_URL=http://192.168.1.100:8080/v1`
- **THEN** embedding requests SHALL target that URL

### Requirement: llamacpp chat configuration for metadata extraction

When `INFERENCE_BACKEND=llamacpp` and `METADATA_EXTRACTION_MODE` is `ollama` or `llamaindex`, the system SHALL use `LLAMACPP_CHAT_URL` (default `http://localhost:8081/v1`) and `LLAMACPP_CHAT_MODEL` for LLM calls. The `ollama` metadata mode SHALL use `httpx` to call `/v1/chat/completions` with the OpenAI chat format. The `llamaindex` metadata mode SHALL use `OpenAILike` LLM from `llama-index-llms-openai-like`.

#### Scenario: ollama metadata mode with llamacpp backend
- **WHEN** `INFERENCE_BACKEND=llamacpp`
- **AND** `METADATA_EXTRACTION_MODE=ollama`
- **THEN** the system SHALL POST to `{LLAMACPP_CHAT_URL}/chat/completions`
- **THEN** the request body SHALL follow OpenAI chat format with `model`, `messages`, and `stream: false`
- **THEN** the response SHALL be parsed from `choices[0].message.content`

#### Scenario: llamaindex metadata mode with llamacpp backend
- **WHEN** `INFERENCE_BACKEND=llamacpp`
- **AND** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `llama-index-llms-openai-like` is installed
- **THEN** the LLM SHALL be `OpenAILike` with `api_base=LLAMACPP_CHAT_URL` and `model=LLAMACPP_CHAT_MODEL`
- **THEN** the extraction pipeline SHALL use this LLM for `TitleExtractor`, `KeywordExtractor`, and `SummaryExtractor`

#### Scenario: llamaindex mode with llamacpp but openai-like not installed
- **WHEN** `INFERENCE_BACKEND=llamacpp`
- **AND** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `llama-index-llms-openai-like` is not installed
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to the `ollama` metadata mode (which uses raw `httpx`)

### Requirement: Split embedding and metadata LLM provider selection

The system SHALL use two independent env vars for provider selection: `EMBED_PROVIDER` (controls embedding model) and `METADATA_LLM_PROVIDER` (controls metadata extraction LLM). When `METADATA_LLM_PROVIDER` is not set, it SHALL default to `ollama` (safe, local, free) to avoid surprising cloud API costs when a user sets `EMBED_PROVIDER` to a cloud provider without explicitly opting into cloud LLM for metadata. The system SHALL support backward compatibility by mapping the deprecated `INFERENCE_BACKEND` env var to `EMBED_PROVIDER` with a deprecation warning.

#### Scenario: Both providers set independently

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `METADATA_LLM_PROVIDER=ollama`
- **THEN** embeddings SHALL use OpenRouter
- **AND** metadata extraction LLM SHALL use Ollama

#### Scenario: Only embed provider set, metadata LLM defaults to ollama

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `METADATA_LLM_PROVIDER` is not set
- **THEN** metadata extraction LLM SHALL default to `ollama`
- **THEN** no paid cloud LLM calls SHALL be made without explicit opt-in

#### Scenario: Legacy INFERENCE_BACKEND still works

- **WHEN** `INFERENCE_BACKEND=llamacpp` is set
- **AND** `EMBED_PROVIDER` is not set
- **THEN** the system SHALL map `EMBED_PROVIDER=llamacpp`
- **THEN** the system SHALL log a deprecation WARNING advising migration to `EMBED_PROVIDER`

#### Scenario: Both EMBED_PROVIDER and INFERENCE_BACKEND set

- **WHEN** `EMBED_PROVIDER=ollama` is set
- **AND** `INFERENCE_BACKEND=llamacpp` is also set
- **THEN** `EMBED_PROVIDER` SHALL take precedence
- **THEN** the system SHALL log a WARNING advising removal of `INFERENCE_BACKEND`

