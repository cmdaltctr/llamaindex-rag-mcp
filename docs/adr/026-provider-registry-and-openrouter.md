# ADR-026: Provider registry pattern and OpenRouter cloud provider

**Date:** 2026-07-15
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Md Hawari
**Change:** `add-openrouter-provider`
**Supersedes:** ADR-025 (partially — replaces `INFERENCE_BACKEND` with split env vars)

## Context

ADR-025 introduced a single `INFERENCE_BACKEND` env var to switch between Ollama and llama.cpp. This worked for two local backends but had three problems as the project grew:

1. **Coupled embeddings and metadata LLM.** Setting `INFERENCE_BACKEND=openrouter` would route both embeddings and metadata classification to OpenRouter — but users may want cloud embeddings with a free local LLM for metadata, or vice versa.
2. **No cloud provider support.** The if/elif chain in `config.py` and `metadata_extractor.py` made adding a third provider (OpenRouter) require touching multiple files with duplicated logic.
3. **Misleading mode name.** `METADATA_EXTRACTION_MODE=ollama` was really "local LLM classification" — it worked with llama.cpp too via `INFERENCE_BACKEND=llamacpp`, making the name confusing.

## Decision

### 1. Split `INFERENCE_BACKEND` into two env vars

| Env var                 | Controls                     | Default  | Backward compat                                         |
| ----------------------- | ---------------------------- | -------- | ------------------------------------------------------- |
| `EMBED_PROVIDER`        | Embedding model only         | `ollama` | `INFERENCE_BACKEND` maps to it with deprecation warning |
| `METADATA_LLM_PROVIDER` | Metadata extraction LLM only | `ollama` | New — no legacy equivalent                              |

`METADATA_LLM_PROVIDER` defaults to `ollama` **regardless of `EMBED_PROVIDER`** to prevent surprising cloud API costs when a user sets `EMBED_PROVIDER=openrouter` without explicitly opting into cloud LLM.

### 2. Config-based provider registry

Replace the if/elif chains with two registry dicts (`EMBED_PROVIDERS`, `LLM_PROVIDERS`) and a single `_build_provider(registry, provider_name)` function. Adding a new provider = one dict entry — no changes to consuming modules.

```python
EMBED_PROVIDERS: dict[str, _ProviderConfig] = {
    "ollama":     { "module": "...", "cls": "...", "required_env": {...}, ... },
    "llamacpp":   { ... },
    "openrouter": { ... },
}
```

`_build_provider` resolves env vars → constructor params, dynamic-imports the module, and instantiates the class.

### 3. Rename `METADATA_EXTRACTION_MODE=ollama` to `local`

The mode name `ollama` was misleading — it's a strategy (per-file LLM classification), not a provider. Renamed to `local` with silent backward-compat mapping (`ollama` → `local`, no warning).

### 4. OpenRouter as a cloud provider

OpenRouter provides OpenAI-compatible endpoints at `https://openrouter.ai/api/v1`. Both embeddings (`OpenAIEmbedding`) and LLM (`OpenAILike`) use the same underlying LlamaIndex classes as llama.cpp — only the `api_base` and `api_key` differ.

| Provider           | Embeddings        | Metadata LLM                                  |
| ------------------ | ----------------- | --------------------------------------------- |
| `ollama` (default) | `OllamaEmbedding` | `Ollama` / `httpx → /api/generate`            |
| `llamacpp`         | `OpenAIEmbedding` | `OpenAILike` / `httpx → /v1/chat/completions` |
| `openrouter`       | `OpenAIEmbedding` | `OpenAILike` / `httpx → /v1/chat/completions` |

### 5. Optional dependencies

```toml
[project.optional-dependencies]
openrouter = [
    "llama-index-embeddings-openai>=0.2.0",
    "llama-index-llms-openai-like>=0.2.0",
]
```

Same packages as `llamacpp` — install with `uv sync --extra openrouter`.

## Consequences

### Positive

- **Adding a future provider** (e.g., `voyageai`, `cohere`) requires only: (1) one dict entry in `EMBED_PROVIDERS` or `LLM_PROVIDERS`, (2) optional dep group in `pyproject.toml`, (3) env vars in `.env.example` — no changes to consuming modules.
- **Embeddings and metadata LLM are independently configurable.** Users can mix cloud embeddings with a free local LLM, or local embeddings with a cloud LLM, without unexpected cost implications.
- **`METADATA_LLM_PROVIDER` defaults to `ollama`** regardless of `EMBED_PROVIDER`, preventing surprising cloud API costs when a user sets `EMBED_PROVIDER=openrouter` without explicitly opting into cloud LLM.
- **`INFERENCE_BACKEND` remains as a read-only alias** — existing code and tests that import it still work without changes.
- **`default_env` field** in the registry handles env vars with sensible defaults (e.g., `LLAMACPP_EMBED_URL` defaults to `http://localhost:8080/v1` via module-level constant), keeping required env vars minimal.

### Negative

- **ChromaDB dimension lock still applies.** Switching `EMBED_PROVIDER` from `ollama` (1024-dim) to `openrouter` (1536-dim for `text-embedding-3-small`) requires re-ingestion. Users must delete `chroma_db/` and re-ingest.
- **Two env vars instead of one.** Users must understand the split between `EMBED_PROVIDER` and `METADATA_LLM_PROVIDER`. The `.env.example` and docs mitigate this with clear comments.
- **`INFERENCE_BACKEND` deprecation warning** may confuse users who haven't read the migration guide — they see a warning but the app still works.

### Neutral

- **`METADATA_EXTRACTION_MODE=ollama` silently maps to `local`** — no warning, no log entry. Existing `.env` files with `ollama` mode continue to work identically.
- **OpenRouter uses the same LlamaIndex classes as llamacpp** (`OpenAIEmbedding`, `OpenAILike`) — only `api_base` and `api_key` differ. No new runtime dependencies beyond what `[llamacpp]` already requires.

## Alternatives Considered

| Option                                                                    | Rejected Because                                                                                                                                                                                                           |
| ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Keep single `INFERENCE_BACKEND` and add `openrouter` as a third value** | Couples embeddings and metadata LLM — setting `INFERENCE_BACKEND=openrouter` forces both to cloud, with no way to mix local LLM + cloud embeddings. Also requires if/elif changes in multiple files for each new provider. |
| **Inherit `METADATA_LLM_PROVIDER` from `EMBED_PROVIDER` by default**      | Surprising cloud API costs — a user setting `EMBED_PROVIDER=openrouter` for embeddings would unknowingly route metadata LLM calls to a paid API. Explicit opt-in is safer.                                                 |
| **Warn on `METADATA_EXTRACTION_MODE=ollama` instead of silent mapping**   | The rename is purely cosmetic — `ollama` mode always worked with any backend. A warning would annoy users without providing actionable information.                                                                        |
| **Use a single registry for both embeddings and LLM**                     | Embeddings and LLMs have different constructor signatures, different env vars, and different LlamaIndex module paths. A single registry would need conditional logic to handle both, defeating the simplicity goal.        |
| **Do nothing / status quo**                                               | Cannot add OpenRouter without touching multiple files. `INFERENCE_BACKEND` coupling remains a design limitation.                                                                                                           |

## References

- [ADR-025](./025-pluggable-inference-backend.md) — Original pluggable inference backend decision (partially superseded)
- [`src/rag_mcp/config.py`](../../src/rag_mcp/config.py) — Provider registries and `_build_provider` function
- [`src/rag_mcp/metadata_extractor.py`](../../src/rag_mcp/metadata_extractor.py) — `_dispatch_local_extraction` and provider-specific extraction functions
- [`openspec/changes/add-openrouter-provider/`](../../openspec/changes/add-openrouter-provider/) — OpenSpec change with full design rationale
- [OpenRouter API documentation](https://openrouter.ai/docs) — OpenAI-compatible endpoints
