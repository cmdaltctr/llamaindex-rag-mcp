## 1. Dependencies

- [x] 1.1 Add `llamacpp` optional dependency group to `pyproject.toml` with `llama-index-embeddings-openai` and `llama-index-llms-openai-like`
- [x] 1.2 Run `uv sync --extra llamacpp` to verify deps install cleanly

## 2. Config: inference backend selection

- [x] 2.1 Add `INFERENCE_BACKEND` env var to `config.py` with validation (default `ollama`, warn on unknown)
- [x] 2.2 Add `LLAMACPP_EMBED_URL`, `LLAMACPP_EMBED_MODEL`, `LLAMACPP_CHAT_URL`, `LLAMACPP_CHAT_MODEL` env vars to `config.py`
- [x] 2.3 Conditionally instantiate `OpenAIEmbedding` (llamacpp) or `OllamaEmbedding` (ollama) in `config.py` based on `INFERENCE_BACKEND`
- [x] 2.4 Raise `ValueError` with install hint when `INFERENCE_BACKEND=llamacpp` but `llama-index-embeddings-openai` not installed

## 3. Metadata extraction: llamacpp chat path

- [x] 3.1 Add `_extract_llamacpp_chat_async()` to `metadata_extractor.py` — uses `httpx` to POST to `/v1/chat/completions` with OpenAI chat format, parses `choices[0].message.content`
- [x] 3.2 Modify `_extract_ollama_async()` dispatch — when `INFERENCE_BACKEND=llamacpp`, call `_extract_llamacpp_chat_async()` instead
- [x] 3.3 Modify `_extract_llamaindex_async()` — when `INFERENCE_BACKEND=llamacpp`, use `OpenAILike` LLM instead of `Ollama` LLM, with fallback to `_extract_llamacpp_chat_async()` on ImportError

## 4. Documentation

- [x] 4.1 Update `.env.example` with `INFERENCE_BACKEND`, `LLAMACPP_*` vars, and llama.cpp setup instructions (model download + server commands)
- [x] 4.2 Create ADR documenting the decision to support both Ollama and llama.cpp backends

## 5. Tests

- [x] 5.1 Add test: `INFERENCE_BACKEND=ollama` (default) preserves existing `OllamaEmbedding` behaviour
- [x] 5.2 Add test: `INFERENCE_BACKEND=llamacpp` instantiates `OpenAIEmbedding` with correct URL/model
- [x] 5.3 Add test: `INFERENCE_BACKEND=llamacpp` without optional deps raises `ValueError` with install hint
- [x] 5.4 Add test: `_extract_llamacpp_chat_async` parses OpenAI chat response format correctly
- [x] 5.5 Add test: `_extract_llamaindex_async` with llamacpp falls back to chat mode when `llama-index-llms-openai-like` not installed
- [x] 5.6 Run `uv run pytest -m "not slow" -v` to verify no regressions
