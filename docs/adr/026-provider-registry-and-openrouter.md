# ADR-026: Provider registry pattern and OpenAI-compatible API providers

**Date:** 2026-07-15
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Md Hawari
**Change:** `add-openrouter-provider`
**Supersedes:** ADR-025 (partially — replaces `INFERENCE_BACKEND` with split env vars)
**Amended by:** ADR-027 (naming taxonomy — flat names replaced with `local`/`cloud` + sub-provider)

## Scope

This ADR covers the **embedding and metadata LLM provider registry** — controlled by `EMBED_PROVIDER` and `METADATA_LLM_PROVIDER`. These determine which model generates embedding vectors and which model classifies documents during ingestion.

**Not in scope:** `DOCUMENT_BACKEND` (Azure Document Intelligence, [ADR-024](./024-dual-deployment-modes.md)) is a separate orthogonal axis that controls how PDFs/DOCX are _parsed_ into text. Azure Document Intelligence extracts text, tables, and layout — it does not provide embedding or chat endpoints. The two axes are independent: a user can set `DOCUMENT_BACKEND=azure` with any `EMBED_PROVIDER`.

## Context

ADR-025 introduced a single `INFERENCE_BACKEND` env var to switch between Ollama and llama.cpp. This worked for two local backends but had three problems as the project grew:

1. **Coupled embeddings and metadata LLM.** Setting `INFERENCE_BACKEND=openrouter` would route both embeddings and metadata classification to OpenRouter — but users may want cloud embeddings with a free local LLM for metadata, or vice versa.
2. **No cloud provider support.** The if/elif chain in `config.py` and `metadata_extractor.py` made adding a third provider (OpenRouter) require touching multiple files with duplicated logic.
3. **Misleading mode name.** `METADATA_EXTRACTION_MODE=ollama` was really "local LLM classification" — it worked with llama.cpp too via `INFERENCE_BACKEND=llamacpp`, making the name confusing.

## Decision

### 1. Split `INFERENCE_BACKEND` into two-tier provider selection

| Env var                 | Controls                         | Default      |
| ----------------------- | -------------------------------- | ------------ |
| `EMBED_PROVIDER`        | Embedding model category         | `local`      |
| `METADATA_LLM_PROVIDER` | Metadata extraction LLM category | `local`      |
| `LOCAL_BACKEND`         | Local sub-provider               | `llamacpp`   |
| `CLOUD_BACKEND`         | Cloud sub-provider               | `openrouter` |

`EMBED_PROVIDER` and `METADATA_LLM_PROVIDER` accept `local` or `cloud`. The sub-provider is selected by `LOCAL_BACKEND` (for `local`) or `CLOUD_BACKEND` (for `cloud`). This allows mix-and-match: cloud embeddings with a local LLM, or vice versa.

`METADATA_LLM_PROVIDER` defaults to `local` **regardless of `EMBED_PROVIDER`** to prevent surprising cloud API costs when a user sets `EMBED_PROVIDER=cloud` without explicitly opting into cloud LLM.

`INFERENCE_BACKEND` was removed entirely — no alias, no deprecation warning. The project has a single user; backward compat is debt.

### 2. Config-based nested provider registry

Replace the if/elif chains with nested registry dicts and a single `_build_provider(category, sub_provider, registry_type)` function. Adding a new provider = one dict entry in the appropriate registry — no changes to consuming modules.

```python
LOCAL_EMBED_PROVIDERS: dict[str, _ProviderConfig] = {
    "llamacpp": { "module": "...", "cls": "...", "required_env": {...}, ... },
    "ollama":   { ... },
}
CLOUD_EMBED_PROVIDERS: dict[str, _ProviderConfig] = {
    "openrouter": { ... },
}
# Same pattern for LOCAL_LLM_PROVIDERS / CLOUD_LLM_PROVIDERS
```

`_build_provider` resolves env vars → constructor params, dynamic-imports the module, and instantiates the class.

### 3. Rename `METADATA_EXTRACTION_MODE=ollama` to `local`

The mode name `ollama` was misleading — it's a strategy (per-file LLM classification), not a provider. Renamed to `local`. The old `ollama` value is no longer accepted — use `local` instead.

### 4. OpenAI-compatible API providers (OpenRouter, llama.cpp, and future endpoints)

The OpenAI API has become the de facto standard for inference endpoints. Both local servers (llama.cpp's `llama-server`) and cloud providers (OpenRouter) implement it. The registry leverages this: `llamacpp` and `openrouter` both use `OpenAIEmbedding` and `OpenAILike` from the same LlamaIndex packages — only `api_base` and `api_key` differ.

OpenRouter is the first cloud provider added to the registry. The same pattern supports any OpenAI-compatible endpoint (vLLM, TGI, LocalAI, Azure OpenAI, actual OpenAI) — adding one requires only a new dict entry with a different `api_base`.

| Category | Sub-provider         | Type  | Embeddings        | Metadata LLM                                  |
| -------- | -------------------- | ----- | ----------------- | --------------------------------------------- |
| `local`  | `llamacpp` (default) | Local | `OpenAIEmbedding` | `OpenAILike` / `httpx → /v1/chat/completions` |
| `local`  | `ollama`             | Local | `OllamaEmbedding` | `Ollama` / `httpx → /api/generate`            |
| `cloud`  | `openrouter`         | Cloud | `OpenAIEmbedding` | `OpenAILike` / `httpx → /v1/chat/completions` |

### 5. Optional dependencies

```toml
[project.optional-dependencies]
llamacpp = [
    "llama-index-embeddings-openai>=0.2.0",
    "llama-index-llms-openai-like>=0.2.0",
]
openrouter = [
    "llama-index-embeddings-openai>=0.2.0",
    "llama-index-llms-openai-like>=0.2.0",
]
```

Both groups install the same packages because both providers implement the OpenAI-compatible API — `llama-index-embeddings-openai` provides `OpenAIEmbedding` and `llama-index-llms-openai-like` provides `OpenAILike`. The groups are kept separate so they can diverge in the future (e.g., if OpenRouter adds a rate-limiting dependency). Install with `uv sync --extra openrouter` or `uv sync --extra llamacpp`.

## Consequences

### Positive

- **Adding a future embedding provider** (e.g., `voyageai`, `cohere`) requires only: (1) one dict entry in the appropriate registry (`LOCAL_EMBED_PROVIDERS` or `CLOUD_EMBED_PROVIDERS`), (2) optional dep group in `pyproject.toml`, (3) env vars in `.env.example` — no changes to consuming modules. The `_build_provider` function handles resolution dynamically.
- **Embeddings and metadata LLM are independently configurable.** Users can mix cloud embeddings with a free local LLM, or local embeddings with a cloud LLM, without unexpected cost implications.
- **`METADATA_LLM_PROVIDER` defaults to `local`** regardless of `EMBED_PROVIDER`, preventing surprising cloud API costs when a user sets `EMBED_PROVIDER=cloud` without explicitly opting into cloud LLM.
- **`default_env` field** in the registry handles env vars with sensible defaults (e.g., `LLAMACPP_EMBED_URL` defaults to `http://localhost:8080/v1` via module-level constant), keeping required env vars minimal.
- **No backward-compat debt.** `INFERENCE_BACKEND` and `METADATA_EXTRACTION_MODE=ollama` were removed entirely — no aliases, no silent mappings, no deprecation warnings. Clean break.

### Negative

- **ChromaDB dimension lock still applies.** Switching from `local` + `ollama` (1024-dim) to `cloud` + `openrouter` (1536-dim for `text-embedding-3-small`) requires re-ingestion. Users must delete `chroma_db/` and re-ingest.
- **Four env vars instead of one.** Users must understand the two-tier system: `EMBED_PROVIDER`/`METADATA_LLM_PROVIDER` (category) + `LOCAL_BACKEND`/`CLOUD_BACKEND` (sub-provider). The `.env.example` and docs mitigate this with clear comments.
- **LLM registries are not yet wired to `_build_provider`.** `LOCAL_LLM_PROVIDERS` and `CLOUD_LLM_PROVIDERS` are defined for documentation and future use, but `metadata_extractor.py` still uses if/elif dispatch (`_dispatch_local_extraction`, `_extract_llamaindex_async`) to select the LLM. Adding a new LLM sub-provider currently requires updating these functions manually, not just a dict entry. The embedding path is fully registry-driven; the LLM path is a known gap to address when a second cloud or local LLM sub-provider is added.
- **`LOCAL_BACKEND`/`CLOUD_BACKEND` validation checks embed registries only.** At config import time, `LOCAL_BACKEND` is validated against `LOCAL_EMBED_PROVIDERS` and `CLOUD_BACKEND` against `CLOUD_EMBED_PROVIDERS`. A sub-provider valid for LLM but not embeddings would be rejected. This is acceptable while embed and LLM sub-providers are symmetric (`llamacpp`/`ollama` for local, `openrouter` for cloud), but should be widened to check the union of embed + LLM registries when they diverge.
- **Cloud dispatch hardcodes `openrouter`.** `_dispatch_local_extraction` and `_extract_llamaindex_async` route cloud LLM calls directly to `_extract_openrouter_chat_async` without checking `CLOUD_BACKEND`. This is a shortcut valid only while `openrouter` is the sole cloud sub-provider. Adding a second cloud sub-provider requires updating both functions.

### Neutral

- **`openrouter` and `llamacpp` share the same LlamaIndex classes** (`OpenAIEmbedding`, `OpenAILike`) because both implement the OpenAI-compatible API — not because they're the same thing. Only `api_base` and `api_key` differ. No new runtime dependencies beyond what `[llamacpp]` already requires.

## Alternatives Considered

| Option                                                                                      | Rejected Because                                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Keep single `INFERENCE_BACKEND` and add `openrouter` as a third value**                   | Couples embeddings and metadata LLM — setting `INFERENCE_BACKEND=openrouter` forces both to cloud, with no way to mix local LLM + cloud embeddings. Also requires if/elif changes in multiple files for each new provider. |
| **Inherit `METADATA_LLM_PROVIDER` from `EMBED_PROVIDER` by default**                        | Surprising cloud API costs — a user setting `EMBED_PROVIDER=cloud` for embeddings would unknowingly route metadata LLM calls to a paid API. Explicit opt-in is safer.                                                      |
| **Keep `INFERENCE_BACKEND` as a deprecated alias**                                          | Backward compat is debt for a single-user project. No alias, no warnings — clean break is simpler.                                                                                                                         |
| **Keep `METADATA_EXTRACTION_MODE=ollama` as a silent alias for `local`**                    | Same reasoning — pure debt. The rename is a clean break.                                                                                                                                                                   |
| **Use a single registry for both embeddings and LLM**                                       | Embeddings and LLMs have different constructor signatures, different env vars, and different LlamaIndex module paths. A single registry would need conditional logic to handle both, defeating the simplicity goal.        |
| **Use flat provider names (`ollama`, `llamacpp`, `openrouter`) as `EMBED_PROVIDER` values** | Confuses users — `ollama` and `llamacpp` are both local, `openrouter` is cloud. Flat naming doesn't convey the category. Two-tier `local`/`cloud` + sub-provider is clearer and supports mix-and-match.                    |
| **Do nothing / status quo**                                                                 | Cannot add OpenRouter without touching multiple files. `INFERENCE_BACKEND` coupling remains a design limitation.                                                                                                           |

## References

- [ADR-025](./025-pluggable-inference-backend.md) — Original pluggable inference backend decision (partially superseded)
- [`src/rag_mcp/config.py`](../../src/rag_mcp/config.py) — Provider registries and `_build_provider` function
- [`src/rag_mcp/metadata_extractor.py`](../../src/rag_mcp/metadata_extractor.py) — `_dispatch_local_extraction` and provider-specific extraction functions
- [`openspec/changes/add-openrouter-provider/`](../../openspec/changes/add-openrouter-provider/) — OpenSpec change with full design rationale
- [OpenRouter API documentation](https://openrouter.ai/docs) — OpenAI-compatible endpoints
