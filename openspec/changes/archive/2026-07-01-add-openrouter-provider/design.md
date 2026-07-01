## Context

The RAG MCP server currently uses a single `INFERENCE_BACKEND` env var that drives both embedding model selection and metadata extraction LLM selection. Two values are supported: `ollama` (default) and `llamacpp`. The selection logic is scattered across `config.py` (embeddings) and `metadata_extractor.py` (LLM) as if/elif chains.

`METADATA_EXTRACTION_MODE` controls the extraction _strategy_ (`disabled`, `keyword`, `ollama`, `llamaindex`). The `ollama` mode name is misleading — it already dispatches to llama.cpp when `INFERENCE_BACKEND=llamacpp`. The code default was `keyword` (regex, no LLM); the `.env.example` recommended `llamaindex`. The code default has been changed to `llamaindex`.

Azure Document Intelligence exists as a `DOCUMENT_BACKEND` for PDF/DOCX parsing — it is unrelated to embeddings or metadata LLM.

## Goals / Non-Goals

**Goals:**

- Add OpenRouter as a cloud embedding and metadata LLM provider
- Split `INFERENCE_BACKEND` into two independent selectors: `EMBED_PROVIDER` and `METADATA_LLM_PROVIDER`
- Rename `METADATA_EXTRACTION_MODE=ollama` to `local` for clarity
- Refactor provider selection from if/elif chains to a config-based registry dict
- Maintain backward compatibility with deprecation warnings for old env var names

**Non-Goals:**

- Azure embeddings (Azure Document Intelligence is document parsing only — separate concern)
- Removing `keyword` metadata mode (planned for a future proposal)
- Adding other cloud providers (OpenAI, Cohere, etc.) — the registry makes this easy, but this change only adds OpenRouter
- Changing the metadata extraction strategies themselves (`local` and `llamaindex` logic stays the same)

## Decisions

### Decision 1: Config-based provider registry

**Choice:** Replace if/elif chains with a registry dict in `config.py`.

**Rationale:** Three providers across two code paths = 6 if/elif branches today. Adding OpenRouter means 9. A registry centralises provider definitions — adding a provider is one dict entry, not touching 3 files.

**Structure:**

```python
EMBED_PROVIDERS = {
    "ollama": {
        "module": "llama_index.embeddings.ollama",
        "class": "OllamaEmbedding",
        "required_env": {"EMBED_MODEL": "model_name", "OLLAMA_BASE_URL": "base_url"},
        "optional_env": {"EMBED_BATCH_SIZE": "embed_batch_size"},
        "extra_dep": "llama-index-embeddings-ollama",
    },
    "llamacpp": {
        "module": "llama_index.embeddings.openai",
        "class": "OpenAIEmbedding",
        "required_env": {"LLAMACPP_EMBED_MODEL": "model", "LLAMACPP_EMBED_URL": "api_base"},
        "static_params": {"api_key": "no-key"},
        "optional_env": {"EMBED_BATCH_SIZE": "embed_batch_size"},
        "extra_dep": "llama-index-embeddings-openai",
    },
    "openrouter": {
        "module": "llama_index.embeddings.openai",
        "class": "OpenAIEmbedding",
        "required_env": {"OPENROUTER_EMBED_MODEL": "model", "OPENROUTER_API_KEY": "api_key"},
        "static_params": {"api_base": "https://openrouter.ai/api/v1"},
        "optional_env": {"EMBED_BATCH_SIZE": "embed_batch_size"},
        "extra_dep": "llama-index-embeddings-openai",
    },
}
```

Same pattern for `LLM_PROVIDERS` (metadata LLM). A single `_build_provider(registry, provider_name)` function does dynamic import + param resolution.

**Alternative considered:** Keep if/elif, just add `openrouter` branch. Rejected because more providers are planned and the scattered branches are already hard to maintain.

### Decision 2: Split `INFERENCE_BACKEND` into `EMBED_PROVIDER` + `METADATA_LLM_PROVIDER`

**Choice:** Two independent selectors.

**Rationale:** Users may want cloud embeddings (OpenRouter) with local LLM (Ollama) for metadata, or vice versa. Coupling them forces running unnecessary services.

**Backward compat:** If `INFERENCE_BACKEND` is set and `EMBED_PROVIDER` is not, map `INFERENCE_BACKEND` → `EMBED_PROVIDER` and log a deprecation warning. Same for `METADATA_LLM_PROVIDER` (defaults to `EMBED_PROVIDER` value if not set).

### Decision 3: Rename `METADATA_EXTRACTION_MODE=ollama` to `local`

**Choice:** Silent mapping — `ollama` → `local` with no warning (it's a pure rename, not a semantic change).

**Rationale:** `ollama` was always a misnomer — the mode dispatches to whatever `INFERENCE_BACKEND`/`METADATA_LLM_PROVIDER` is set. `local` accurately describes the strategy: per-file LLM classification via the configured provider.

### Decision 4: OpenRouter uses `OpenAIEmbedding` + `OpenAILike`

**Choice:** Reuse the same LlamaIndex classes that llamacpp uses.

**Rationale:** OpenRouter exposes an OpenAI-compatible API. The llamacpp backend already proves this works — `OpenAIEmbedding` for embeddings, `OpenAILike` for LLM. The only differences are `api_base` (`https://openrouter.ai/api/v1`) and `api_key` (real key vs `no-key`).

### Decision 5: `METADATA_LLM_PROVIDER` defaults to `ollama`

**Choice:** If `METADATA_LLM_PROVIDER` is not set, it defaults to `ollama`.

**Rationale:** If a user sets `EMBED_PROVIDER=openrouter` for cloud embeddings but forgets `METADATA_LLM_PROVIDER`, inheriting `openrouter` would silently make paid cloud LLM calls per ingested file — a surprising cost side-effect from an unrelated setting. Defaulting to `ollama` (safe, local, free) requires explicit opt-in for cloud LLM costs. Users who want the same provider for both simply set `METADATA_LLM_PROVIDER=openrouter` explicitly.

**Alternative considered:** Default `METADATA_LLM_PROVIDER` to `EMBED_PROVIDER` value. Rejected because of the silent cost risk described above.

## Migration Plan

**Rollout order:**

1. Both `EMBED_PROVIDER` and `INFERENCE_BACKEND` are read at config load. If `EMBED_PROVIDER` is set, it takes precedence. If only `INFERENCE_BACKEND` is set, it's mapped with a deprecation warning.
2. Both `METADATA_EXTRACTION_MODE=local` and `METADATA_EXTRACTION_MODE=ollama` are accepted. `ollama` is silently mapped to `local`.
3. Users should update their `.env` files at their convenience — old names continue to work across at least one minor release cycle.
4. `INFERENCE_BACKEND` support will be removed in a future major version.

**Conflict resolution:** If both `EMBED_PROVIDER` and `INFERENCE_BACKEND` are set, `EMBED_PROVIDER` wins and a warning is logged advising removal of `INFERENCE_BACKEND`.

**Rollback strategy:** Revert to previous `config.py` and `metadata_extractor.py`. No data migration needed — ChromaDB collections are unaffected by selector name changes.

## Risks / Trade-offs

- **[ChromaDB dimension lock]** Switching `EMBED_PROVIDER` changes embedding dimensions → existing collections break. → Mitigation: Document in `.env.example` that switching providers requires re-ingestion. No runtime check (dimensions are only known after first embedding call).
- **[Dynamic imports hurt static analysis]** Pyright/mypy can't follow `importlib.import_module()` calls. → Mitigation: Type the registry as `dict[str, ProviderConfig]` with a TypedDict; the return type of `_build_provider` is `Any` but consumers already treat it as duck-typed.
- **[Backward compat complexity]** Supporting old `INFERENCE_BACKEND` name adds a mapping layer. → Mitigation: Deprecation warning with clear migration message. Remove in a future major version.
- **[OpenRouter API costs]** Cloud embeddings cost money per call. → Mitigation: Not a code concern — document in `.env.example`. The `EMBED_BATCH_SIZE` knob already exists for cost control.
- **[OpenRouter rate limits]** Metadata extraction makes per-file LLM calls. → Mitigation: Existing retry/backoff logic in `_extract_ollama_async` and `_extract_llamacpp_chat_async` applies. The OpenRouter LLM path will use `OpenAILike` which has its own retry handling via LlamaIndex.
