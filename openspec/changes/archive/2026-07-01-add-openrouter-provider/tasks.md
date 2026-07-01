## 1. Provider Registry in config.py

- [x] 1.1 Define `EMBED_PROVIDERS` registry dict with entries for `ollama`, `llamacpp`, and `openrouter` (module, class, required_env, optional_env, static_params, extra_dep)
- [x] 1.2 Define `LLM_PROVIDERS` registry dict with entries for `ollama`, `llamacpp`, and `openrouter`
- [x] 1.3 Implement `_build_provider(registry, provider_name)` function — resolves env vars, dynamic import, instantiate class, return instance
- [x] 1.4 Add `EMBED_PROVIDER` env var (replaces `INFERENCE_BACKEND`) with backward-compat mapping + deprecation warning
- [x] 1.5 Add `METADATA_LLM_PROVIDER` env var (defaults to `ollama` when not set, regardless of `EMBED_PROVIDER`)
- [x] 1.6 Add OpenRouter env vars: `OPENROUTER_API_KEY`, `OPENROUTER_EMBED_MODEL`, `OPENROUTER_LLM_MODEL`
- [x] 1.7 Replace the if/elif embedding setup block (lines 79-108) with `_build_provider(EMBED_PROVIDERS, EMBED_PROVIDER)` call
- [x] 1.8 Validate `EMBED_MODEL` requirement only for `ollama` provider (not `llamacpp` or `openrouter` which have their own model env vars)

## 2. Metadata Extractor Refactor

- [x] 2.1 Replace `INFERENCE_BACKEND` imports with `METADATA_LLM_PROVIDER` in `metadata_extractor.py`
- [x] 2.2 Rename `METADATA_EXTRACTION_MODE=ollama` to `local` in dispatch logic (`extract_metadata_async`)
- [x] 2.3 Add silent mapping: `ollama` → `local` (no warning, pure rename)
- [x] 2.4 Update `_extract_llamaindex_async` to use `METADATA_LLM_PROVIDER` for LLM selection (ollama → `Ollama`, llamacpp → `OpenAILike`, openrouter → `OpenAILike` with OpenRouter base URL)
- [x] 2.5 Update `local` mode dispatch to use `METADATA_LLM_PROVIDER` (ollama → `_extract_ollama_async`, llamacpp → `_extract_llamacpp_chat_async`, openrouter → new `_extract_openrouter_chat_async`)
- [x] 2.6 Implement `_extract_openrouter_chat_async` — httpx POST to `https://openrouter.ai/api/v1/chat/completions` with `OPENROUTER_API_KEY` auth and `OPENROUTER_LLM_MODEL`
- [x] 2.7 Update fallback messages from "ollama" / "llamacpp chat" to use `METADATA_LLM_PROVIDER` value

## 3. Dependencies & Config Files

- [x] 3.1 Add `[openrouter]` optional dependency group in `pyproject.toml` with `llama-index-embeddings-openai` and `llama-index-llms-openai-like`
- [x] 3.2 Update `.env.example` with new selector names (`EMBED_PROVIDER`, `METADATA_LLM_PROVIDER`), OpenRouter env vars, and `METADATA_EXTRACTION_MODE=local` rename
- [x] 3.3 Add `EMBED_PROVIDER=ollama` to `.env` (replacing `INFERENCE_BACKEND` if present)
- [x] 3.4 Verify backward compat: temporarily set `INFERENCE_BACKEND=ollama` instead of `EMBED_PROVIDER` and confirm deprecation warning appears

## 4. Tests

- [x] 4.1 Update tests referencing `INFERENCE_BACKEND` to use `EMBED_PROVIDER` (or test backward-compat mapping)
- [x] 4.2 Update tests referencing `METADATA_EXTRACTION_MODE=ollama` to use `local`
- [x] 4.3 Add test: `EMBED_PROVIDER=openrouter` with missing `OPENROUTER_API_KEY` raises `ValueError`
- [x] 4.4 Add test: `EMBED_PROVIDER=openrouter` with missing optional deps raises `ImportError`
- [x] 4.5 Add test: `METADATA_LLM_PROVIDER` defaults to `ollama` when not set (regardless of `EMBED_PROVIDER`)
- [x] 4.6 Add test: legacy `INFERENCE_BACKEND` maps to `EMBED_PROVIDER` with deprecation warning
- [x] 4.7 Add test: `METADATA_EXTRACTION_MODE=ollama` silently maps to `local`
- [x] 4.8 Run `uv run pytest -m "not slow" --cov=rag_mcp` and verify coverage thresholds

## 5. Validation

- [x] 5.1 Run `openspec validate --all --strict` and fix any issues
- [x] 5.2 Run `uv run pytest -m "not slow" -v` — all tests pass
- [ ] 5.3 Manual smoke test: `EMBED_PROVIDER=ollama` still works (no regression)
- [x] 5.4 Create ADR documenting the provider registry pattern and EMBED_PROVIDER/METADATA_LLM_PROVIDER split
