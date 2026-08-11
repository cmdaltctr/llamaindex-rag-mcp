## MODIFIED Requirements

### Requirement: Inference backend selection

The system SHALL select the embedding provider via the `EMBED_PROVIDER` environment variable. The accepted values SHALL be `local` (the default), `cloud`, `ollama`, `llamacpp`, and `openrouter`. The system SHALL validate the provider value at settings-resolution time and raise a startup error naming the offending value and the accepted set on an unrecognised value — this mirrors the existing `VECTOR_STORE` unknown-value contract (`vectordb-abstraction`, ADR-034); an unrecognised provider is a misconfiguration, not a condition to silently paper over. The system SHALL maintain a provider registry in `core/providers/` that maps each provider name to its module, class, required env vars, and optional dependency group, following the shared registry contract (lazy `"module:attr"` import strings resolved on first `get()`). Provider objects SHALL be constructed exclusively in `compose.py` (the composition root), which resolves the registry entry against the validated `Settings` and instantiates the provider; `config.py` SHALL NOT construct provider objects.

The provider-selection validation SHALL run before any validation that consumes a resolved provider (such as the `EMBED_MODEL`-required check), so that an unrecognised `EMBED_PROVIDER` reports the provider error rather than a downstream consequence of it.

The deprecated `INFERENCE_BACKEND` env var SHALL still be accepted: when `EMBED_PROVIDER` is not set but `INFERENCE_BACKEND` is, the system SHALL map the value and log a deprecation warning.

#### Scenario: Default provider is local

- **WHEN** `EMBED_PROVIDER` is not set and `INFERENCE_BACKEND` is not set
- **THEN** the system SHALL use `local` as the embedding provider
- **THEN** the concrete backend SHALL be resolved from `LOCAL_BACKEND`

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

- **WHEN** `EMBED_PROVIDER` is set to a value other than `local`, `cloud`, `ollama`, `llamacpp`, or `openrouter`
- **THEN** the system SHALL raise a startup error naming the offending value and the accepted values
- **THEN** the system SHALL NOT fall back to `local` or any other default

#### Scenario: Unknown provider value reports the provider error, not a downstream one

- **WHEN** `EMBED_PROVIDER` is set to an unrecognised value
- **AND** `EMBED_MODEL` is unset, so the `EMBED_MODEL`-required validation would also fail
- **THEN** the raised error SHALL name `EMBED_PROVIDER` as the offending setting
- **THEN** the error SHALL NOT report a missing `EMBED_MODEL` as the primary cause

#### Scenario: Legacy INFERENCE_BACKEND mapping

- **WHEN** `INFERENCE_BACKEND=llamacpp` is set
- **AND** `EMBED_PROVIDER` is not set
- **THEN** the system SHALL set `EMBED_PROVIDER=llamacpp`
- **THEN** the system SHALL log a deprecation WARNING advising migration to `EMBED_PROVIDER`

#### Scenario: Registry relocated to core/providers

- **WHEN** the provider registry is inspected after the refactor
- **THEN** it MUST live under `core/providers/` (embeddings and LLM sub-registries)
- **AND** `config.py` MUST NOT contain the registry or any provider construction logic
- **AND** provider behaviour (classes used, env vars read, fallback rules) MUST be identical to the pre-refactor registry, except that unknown-value handling now fails startup instead of falling back (see "Scenario: Unknown provider value")

### Requirement: Split embedding and metadata LLM provider selection

The system SHALL use two independent env vars for provider selection: `EMBED_PROVIDER` (controls embedding model) and `METADATA_LLM_PROVIDER` (controls metadata extraction LLM). `METADATA_LLM_PROVIDER` SHALL accept `local` and `cloud`, and SHALL default to `local` (safe, local, free) to avoid surprising cloud API costs when a user sets `EMBED_PROVIDER` to a cloud provider without explicitly opting into a cloud LLM for metadata. An unrecognised `METADATA_LLM_PROVIDER` value SHALL raise a startup error naming the offending value and the accepted set, rather than falling back. The system SHALL support backward compatibility by mapping the deprecated `INFERENCE_BACKEND` env var to `EMBED_PROVIDER` with a deprecation warning.

#### Scenario: Both providers set independently

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `METADATA_LLM_PROVIDER=local`
- **THEN** embeddings SHALL use OpenRouter
- **AND** metadata extraction LLM SHALL use the local backend selected by `LOCAL_BACKEND`

#### Scenario: Only embed provider set, metadata LLM defaults to local

- **WHEN** `EMBED_PROVIDER=openrouter`
- **AND** `METADATA_LLM_PROVIDER` is not set
- **THEN** metadata extraction LLM SHALL default to `local`
- **THEN** no paid cloud LLM calls SHALL be made without explicit opt-in

#### Scenario: Unknown metadata LLM provider value

- **WHEN** `METADATA_LLM_PROVIDER` is set to a value other than `local` or `cloud`
- **THEN** the system SHALL raise a startup error naming the offending value and the accepted values
- **THEN** the system SHALL NOT fall back to `local`

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
