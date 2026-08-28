## ADDED Requirements

### Requirement: Inference backend selection

The system SHALL support two inference backends for embeddings and metadata extraction LLM calls: `ollama` (default) and `llamacpp`. The backend SHALL be selected via the `INFERENCE_BACKEND` environment variable. When set to `ollama`, the system SHALL use `OllamaEmbedding` and Ollama's `/api/generate` endpoint. When set to `llamacpp`, the system SHALL use `OpenAIEmbedding` pointing to a `llama-server` instance and the OpenAI-compatible `/v1/chat/completions` endpoint. The system SHALL validate the backend value at import time and fall back to `ollama` with a warning on unknown values.

#### Scenario: Default backend is ollama
- **WHEN** `INFERENCE_BACKEND` is not set
- **THEN** the system SHALL use Ollama for embeddings and metadata extraction
- **THEN** existing behaviour SHALL be preserved with no changes

#### Scenario: Explicit ollama backend
- **WHEN** `INFERENCE_BACKEND=ollama`
- **THEN** the system SHALL use `OllamaEmbedding` with `OLLAMA_BASE_URL` and `EMBED_MODEL`
- **THEN** metadata extraction SHALL use Ollama's `/api/generate` endpoint

#### Scenario: llamacpp backend selected
- **WHEN** `INFERENCE_BACKEND=llamacpp`
- **AND** `llama-index-embeddings-openai` is installed
- **THEN** the system SHALL use `OpenAIEmbedding` with `LLAMACPP_EMBED_URL` and `LLAMACPP_EMBED_MODEL`
- **THEN** metadata extraction SHALL use the OpenAI-compatible `/v1/chat/completions` endpoint at `LLAMACPP_CHAT_URL`

#### Scenario: llamacpp backend but optional deps not installed
- **WHEN** `INFERENCE_BACKEND=llamacpp`
- **AND** `llama-index-embeddings-openai` is not installed
- **THEN** the system SHALL raise a `ValueError` with a message instructing the user to run `uv sync --extra llamacpp`

#### Scenario: Unknown backend value
- **WHEN** `INFERENCE_BACKEND` is set to a value other than `ollama` or `llamacpp`
- **THEN** the system SHALL log a WARNING
- **THEN** the system SHALL fall back to `ollama`

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
