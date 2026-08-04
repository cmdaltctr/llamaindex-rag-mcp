## MODIFIED Requirements

### Requirement: Inference backend selection

The system SHALL support three embedding providers selected via the `EMBED_PROVIDER` environment variable: `ollama` (default), `llamacpp`, and `openrouter`. The system SHALL validate the provider value at settings-resolution time and fall back to `ollama` with a warning on unknown values. The system SHALL maintain a provider registry in `core/providers/` that maps each provider name to its module, class, required env vars, and optional dependency group, following the shared registry contract (lazy `"module:attr"` import strings resolved on first `get()`). Provider objects SHALL be constructed exclusively in `compose.py` (the composition root), which resolves the registry entry against the validated `Settings` and instantiates the provider; `config.py` SHALL NOT construct provider objects.

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

#### Scenario: Registry relocated to core/providers

- **WHEN** the provider registry is inspected after the refactor
- **THEN** it MUST live under `core/providers/` (embeddings and LLM sub-registries)
- **AND** `config.py` MUST NOT contain the registry or any provider construction logic
- **AND** provider behaviour (classes used, env vars read, fallback rules) MUST be identical to the pre-refactor registry
