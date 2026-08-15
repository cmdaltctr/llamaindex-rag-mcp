## MODIFIED Requirements

### Requirement: OpenRouter embedding provider

The system SHALL support `EMBED_PROVIDER=openrouter` for cloud embeddings via OpenRouter's OpenAI-compatible API. The system SHALL use `OpenAILikeEmbedding` from `llama-index-embeddings-openai-like` with `api_base` set to `https://openrouter.ai/api/v1`, `api_key` set from `OPENROUTER_API_KEY`, and `model_name` set from `OPENROUTER_EMBED_MODEL`. `OpenAILikeEmbedding` SHALL forward the model identifier unchanged, because OpenRouter serves embeddings under provider-prefixed, non-OpenAI IDs (for example `qwen/qwen3-embedding-4b`) that `OpenAIEmbedding`'s fixed model enum rejects at construction. The system SHALL require `llama-index-embeddings-openai-like` to be installed (same package as llamacpp backend).

#### Scenario: OpenRouter embeddings configured

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `OPENROUTER_API_KEY=sk-or-v1-...`
- **AND** `OPENROUTER_EMBED_MODEL=nvidia/nv-embed-v1`
- **AND** `llama-index-embeddings-openai-like` is installed
- **THEN** `Settings.embed_model` SHALL be an `OpenAILikeEmbedding` instance
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
