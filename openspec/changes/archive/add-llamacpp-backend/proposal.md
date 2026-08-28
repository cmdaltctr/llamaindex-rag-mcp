## Why

Ollama adds a wrapper layer over llama.cpp that introduces ~20-27% overhead and serialises concurrent requests, slowing batch ingestion. Researchers and power users who want maximum inference throughput prefer llama.cpp's `llama-server` directly — no middleman, OpenAI-compatible API, better concurrency via parallel slots. The project should support both backends so users can choose based on their needs: Ollama for convenience, llama.cpp for raw performance.

## What Changes

- Add `INFERENCE_BACKEND` env var (`ollama` | `llamacpp`), defaulting to `ollama` to preserve existing behaviour
- When `llamacpp` is selected, embeddings use `OpenAIEmbedding` pointing to `llama-server`'s `/v1/embeddings` endpoint instead of `OllamaEmbedding`
- When `llamacpp` is selected, metadata extraction's `ollama` mode routes to `/v1/chat/completions` (OpenAI format) instead of `/api/generate` (Ollama format)
- When `llamacpp` is selected, metadata extraction's `llamaindex` mode uses `OpenAILike` LLM instead of `Ollama` LLM
- Add `llama-index-embeddings-openai` and `llama-index-llms-openai-like` as optional dependencies under a `llamacpp` extra
- Update `.env.example` with new env vars and llama.cpp setup instructions
- No breaking changes — existing `ollama` users see zero difference

## Capabilities

### New Capabilities
- `inference-backend`: Pluggable inference backend selection (Ollama or llama.cpp) for embeddings and metadata extraction LLM calls

### Modified Capabilities
- `metadata-extraction`: Metadata extraction modes (`ollama`, `llamaindex`) now route through the selected inference backend instead of hardcoding Ollama

## Impact

- **`config.py`**: New env vars (`INFERENCE_BACKEND`, `LLAMACPP_EMBED_URL`, `LLAMACPP_EMBED_MODEL`, `LLAMACPP_CHAT_URL`, `LLAMACPP_CHAT_MODEL`); conditional embedding model instantiation
- **`metadata_extractor.py`**: `_extract_ollama_async` and `_extract_llamaindex_async` branch on backend; new `_extract_llamacpp_chat_async` function for OpenAI-compatible chat endpoint
- **`pyproject.toml`**: New `llamacpp` optional dependency group
- **`.env.example`**: Documentation for llama.cpp backend configuration
- **Dependencies**: `llama-index-embeddings-openai`, `llama-index-llms-openai-like` (optional, only needed when `INFERENCE_BACKEND=llamacpp`)
