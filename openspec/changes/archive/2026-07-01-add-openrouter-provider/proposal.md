## Why

The server currently supports only local inference backends (Ollama, llama.cpp) for embeddings and metadata extraction. Users who want cloud embeddings (e.g., OpenRouter's hosted models) have no code path — they must run a local model server regardless. Additionally, the `INFERENCE_BACKEND` selector conflates embedding provider and metadata LLM provider into one knob, making it impossible to mix (e.g., cloud embeddings + local LLM). The `METADATA_EXTRACTION_MODE=ollama` mode name is misleading since it already dispatches to llama.cpp, creating confusion.

## What Changes

- Deprecate `INFERENCE_BACKEND` env var in favour of `EMBED_PROVIDER` (old name still works with deprecation warning)
- Deprecate `METADATA_EXTRACTION_MODE=ollama` in favour of `METADATA_EXTRACTION_MODE=local` (old value silently mapped, no warning)
- Add `EMBED_PROVIDER=openrouter` — OpenRouter cloud embeddings via OpenAI-compatible API
- Add `METADATA_LLM_PROVIDER` env var — independently selects which LLM serves metadata extraction (`ollama`, `llamacpp`, `openrouter`)
- Refactor provider selection from scattered if/elif chains to a config-based registry dict in `config.py`
- Add `openrouter` optional dependency group in `pyproject.toml`
- Change `METADATA_EXTRACTION_MODE` default from `keyword` to `llamaindex` (already done in config.py)
- Update `.env.example` with OpenRouter env vars and new selector names

## Capabilities

### New Capabilities

- `cloud-embed-providers`: Cloud embedding provider support via config-based registry, starting with OpenRouter

### Modified Capabilities

- `inference-backend`: Split single `INFERENCE_BACKEND` into `EMBED_PROVIDER` + `METADATA_LLM_PROVIDER`; rename `ollama` metadata mode to `local`; refactor to config-based registry
- `metadata-extraction`: Rename `ollama` mode to `local`; add `METADATA_LLM_PROVIDER` dispatch; default changed from `keyword` to `llamaindex`

## Impact

- **`config.py`** — major refactor of embedding/LLM provider selection (registry dict replaces if/elif)
- **`metadata_extractor.py`** — update dispatch logic to use `METADATA_LLM_PROVIDER` instead of `INFERENCE_BACKEND`
- **`pyproject.toml`** — add `[openrouter]` optional dep group
- **`.env.example`** — document new env vars and selector names
- **Tests** — update all tests that reference `INFERENCE_BACKEND` or `METADATA_EXTRACTION_MODE=ollama`
- **Backward compat** — `INFERENCE_BACKEND` still works (deprecation warning), `METADATA_EXTRACTION_MODE=ollama` silently maps to `local`
- **ChromaDB** — dimension lock still applies; switching providers requires re-ingestion if dimensions differ
