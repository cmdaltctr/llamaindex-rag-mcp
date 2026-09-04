# cloud-embed-providers Specification

## Purpose
Defines how cloud providers (OpenRouter embeddings and LLMs, resolved
through the shared provider registry) join the local-first deployment:
opt-in per ADR-024, configuration-driven, and degrading gracefully when
credentials or optional dependencies are absent. Local operation never
depends on a cloud provider being configured.

## Requirements
### Requirement: Config-based provider registry

The system SHALL maintain a provider registry dict in `config.py` that defines all embedding and LLM providers. Each registry entry SHALL specify: module path, class name, required env vars (mapped to constructor params), optional env vars, static constructor params, and the optional dependency group name. A single `_build_provider(registry, provider_name)` function SHALL resolve env vars, perform a dynamic import, instantiate the class, and return the instance. Adding a new provider SHALL require only a new dict entry — no if/elif changes in consuming modules.

#### Scenario: Registry lookup for known provider

- **WHEN** `EMBED_PROVIDER=ollama`
- **THEN** the system SHALL look up `"ollama"` in the embed provider registry
- **THEN** it SHALL dynamically import `llama_index.embeddings.ollama.OllamaEmbedding`
- **THEN** it SHALL resolve `EMBED_MODEL` and `OLLAMA_BASE_URL` from env vars and pass them as constructor params

#### Scenario: Registry lookup for unknown provider

- **WHEN** `EMBED_PROVIDER=nonexistent`
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to `ollama`

#### Scenario: Missing required env var for provider

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY` is not set
- **THEN** the system SHALL raise a `ValueError` naming the missing env var and the provider

### Requirement: OpenRouter embedding provider

The system SHALL support `EMBED_PROVIDER=openrouter` for cloud embeddings via OpenRouter's OpenAI-compatible API. The system SHALL use `OpenAILikeEmbedding` from `llama-index-embeddings-openai-like` with `api_base` set to `https://openrouter.ai/api/v1`, `api_key` set from `OPENROUTER_API_KEY`, and `model_name` set from `OPENROUTER_EMBED_MODEL`. `OpenAILikeEmbedding` SHALL forward the model identifier unchanged, because OpenRouter serves embeddings under provider-prefixed, non-OpenAI IDs (for example `qwen/qwen3-embedding-4b`) that `OpenAIEmbedding`'s fixed model enum rejects at construction. The system SHALL require `llama-index-embeddings-openai-like` to be installed (same package as llamacpp backend).

#### Scenario: OpenRouter embeddings configured

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY=sk-or-v1-...`
- **AND** `OPENROUTER_EMBED_MODEL=nvidia/nv-embed-v1`
- **AND** `llama-index-embeddings-openai-like` is installed
- **THEN** `compose.build_embed_model(settings)` SHALL return an `OpenAILikeEmbedding` instance
- **THEN** embedding requests SHALL be sent to `https://openrouter.ai/api/v1/embeddings`
- **THEN** the `api_key` SHALL be set to the value of `OPENROUTER_API_KEY`
- **THEN** the `model_name` SHALL equal `OPENROUTER_EMBED_MODEL` unchanged

#### Scenario: OpenRouter embeddings but optional deps not installed

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `llama-index-embeddings-openai-like` is not installed
- **THEN** the system SHALL raise an `ImportError` instructing the user to run `uv sync --extra openrouter`

#### Scenario: OpenRouter API key not set

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY` is not set
- **THEN** the system SHALL raise a `ValueError` with a message naming `OPENROUTER_API_KEY` as required

### Requirement: OpenRouter LLM provider for metadata extraction

The system SHALL support `METADATA_LLM_PROVIDER=openrouter` for metadata extraction LLM calls. When `METADATA_LLM_PROVIDER=openrouter` and `METADATA__EXTRACTION_MODE` is `local` or `llamaindex`, the system SHALL use `OpenAILike` from `llama-index-llms-openai-like` with `api_base` set to `https://openrouter.ai/api/v1`, `api_key` set from `OPENROUTER_API_KEY`, and `model` set from `OPENROUTER_LLM_MODEL`.

#### Scenario: local metadata mode with OpenRouter LLM

- **WHEN** `METADATA__EXTRACTION_MODE=local`
- **AND** `METADATA_LLM_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY` and `OPENROUTER_LLM_MODEL` are set
- **THEN** the system SHALL POST to `https://openrouter.ai/api/v1/chat/completions`
- **THEN** the request body SHALL follow OpenAI chat format with `model`, `messages`, and `stream: false`

#### Scenario: llamaindex metadata mode with OpenRouter LLM

- **WHEN** `METADATA__EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=openrouter`
- **AND** `llama-index-llms-openai-like` is installed
- **THEN** the LLM SHALL be `OpenAILike` with `api_base=https://openrouter.ai/api/v1` and `model=OPENROUTER_LLM_MODEL`

