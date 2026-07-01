## ADDED Requirements

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

The system SHALL support `EMBED_PROVIDER=openrouter` for cloud embeddings via OpenRouter's OpenAI-compatible API. The system SHALL use `OpenAIEmbedding` from `llama-index-embeddings-openai` with `api_base` set to `https://openrouter.ai/api/v1`, `api_key` set from `OPENROUTER_API_KEY`, and `model` set from `OPENROUTER_EMBED_MODEL`. The system SHALL require `llama-index-embeddings-openai` to be installed (same package as llamacpp backend).

#### Scenario: OpenRouter embeddings configured

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY=sk-or-v1-...`
- **AND** `OPENROUTER_EMBED_MODEL=nvidia/nv-embed-v1`
- **AND** `llama-index-embeddings-openai` is installed
- **THEN** `Settings.embed_model` SHALL be an `OpenAIEmbedding` instance
- **THEN** embedding requests SHALL be sent to `https://openrouter.ai/api/v1/embeddings`
- **THEN** the `api_key` SHALL be set to the value of `OPENROUTER_API_KEY`

#### Scenario: OpenRouter embeddings but optional deps not installed

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `llama-index-embeddings-openai` is not installed
- **THEN** the system SHALL raise an `ImportError` instructing the user to run `uv sync --extra openrouter`

#### Scenario: OpenRouter API key not set

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY` is not set
- **THEN** the system SHALL raise a `ValueError` with a message naming `OPENROUTER_API_KEY` as required

### Requirement: OpenRouter LLM provider for metadata extraction

The system SHALL support `METADATA_LLM_PROVIDER=openrouter` for metadata extraction LLM calls. When `METADATA_LLM_PROVIDER=openrouter` and `METADATA_EXTRACTION_MODE` is `local` or `llamaindex`, the system SHALL use `OpenAILike` from `llama-index-llms-openai-like` with `api_base` set to `https://openrouter.ai/api/v1`, `api_key` set from `OPENROUTER_API_KEY`, and `model` set from `OPENROUTER_LLM_MODEL`.

#### Scenario: local metadata mode with OpenRouter LLM

- **WHEN** `METADATA_EXTRACTION_MODE=local`
- **AND** `METADATA_LLM_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY` and `OPENROUTER_LLM_MODEL` are set
- **THEN** the system SHALL POST to `https://openrouter.ai/api/v1/chat/completions`
- **THEN** the request body SHALL follow OpenAI chat format with `model`, `messages`, and `stream: false`

#### Scenario: llamaindex metadata mode with OpenRouter LLM

- **WHEN** `METADATA_EXTRACTION_MODE=llamaindex`
- **AND** `METADATA_LLM_PROVIDER=openrouter`
- **AND** `llama-index-llms-openai-like` is installed
- **THEN** the LLM SHALL be `OpenAILike` with `api_base=https://openrouter.ai/api/v1` and `model=OPENROUTER_LLM_MODEL`
