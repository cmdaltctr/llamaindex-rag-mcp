# Providers

The RAG MCP server supports multiple embedding and metadata LLM providers. Providers are selected independently via a two-tier system: category (`local`|`cloud`) + sub-provider — you can mix and match (e.g., cloud embeddings with a local LLM).

> **Scope:** This guide covers embedding and metadata LLM providers only. Document parsing (`DOCUMENT_BACKEND=azure`, Azure Document Intelligence) is a separate orthogonal axis — see [ADR-024](../adr/024-dual-deployment-modes.md).

## Overview

| Category | Sub-provider         | Embeddings        | Metadata LLM           | Extra deps                   |
| -------- | -------------------- | ----------------- | ---------------------- | ---------------------------- |
| `local`  | `llamacpp` (default) | `OpenAIEmbedding` | `OpenAILike` / `httpx` | `uv sync --extra llamacpp`   |
| `local`  | `ollama`             | `OllamaEmbedding` | `Ollama` / `httpx`     | None (core)                  |
| `cloud`  | `openrouter`         | `OpenAIEmbedding` | `OpenAILike` / `httpx` | `uv sync --extra openrouter` |

`llamacpp` and `openrouter` both use the OpenAI-compatible API (`OpenAIEmbedding`, `OpenAILike`) — only `api_base` and `api_key` differ. The same pattern supports any OpenAI-compatible endpoint (vLLM, TGI, LocalAI, Azure OpenAI). See [ADR-026](../adr/026-provider-registry-and-openrouter.md) for the full rationale.

## Environment variables

### Provider selection

| Env var                 | Controls                | Default      | Valid values          |
| ----------------------- | ----------------------- | ------------ | --------------------- |
| `EMBED_PROVIDER`        | Embedding model         | `local`      | `local` / `cloud`     |
| `METADATA_LLM_PROVIDER` | Metadata extraction LLM | `local`      | `local` / `cloud`     |
| `LOCAL_BACKEND`         | Local sub-provider      | `llamacpp`   | `llamacpp` / `ollama` |
| `CLOUD_BACKEND`         | Cloud sub-provider      | `openrouter` | `openrouter`          |

> **Why `METADATA_LLM_PROVIDER` defaults to `local` regardless of `EMBED_PROVIDER`:** to prevent surprising cloud API costs. If you set `EMBED_PROVIDER=cloud`, metadata extraction still uses a local LLM unless you explicitly set `METADATA_LLM_PROVIDER=cloud`.

### llama.cpp (default local backend)

| Env var                | Default                              | Purpose                         |
| ---------------------- | ------------------------------------ | ------------------------------- |
| `LLAMACPP_EMBED_MODEL` | _(required)_                         | GGUF filename for embeddings    |
| `LLAMACPP_EMBED_URL`   | `http://localhost:8080/v1`           | llama-server embedding endpoint |
| `LLAMACPP_CHAT_MODEL`  | _(required for local metadata mode)_ | GGUF filename for metadata LLM  |
| `LLAMACPP_CHAT_URL`    | `http://localhost:8081/v1`           | llama-server chat endpoint      |

```bash
uv sync --extra llamacpp

# Start two llama-server processes
llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port 8080 --embeddings
llama-server -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 --port 8081
```

```bash
# .env
EMBED_PROVIDER=local
METADATA_LLM_PROVIDER=local
LOCAL_BACKEND=llamacpp
LLAMACPP_EMBED_MODEL=Qwen3-Embedding-0.6B-Q8_0.gguf
LLAMACPP_CHAT_MODEL=Qwen3-0.6B-Q8_0.gguf
```

See [ADR-025](../adr/025-pluggable-inference-backend.md) for the full rationale.

### Ollama (alternative local backend)

| Env var                           | Default                  | Purpose                                  |
| --------------------------------- | ------------------------ | ---------------------------------------- |
| `EMBED_MODEL`                     | _(required)_             | Ollama embedding model name              |
| `OLLAMA_BASE_URL`                 | `http://localhost:11434` | Ollama server URL                        |
| `METADATA__OLLAMA_CLASSIFY_MODEL` | `qwen3:0.6b`             | Ollama model for metadata classification |
| `INGESTION__EMBED_BATCH_SIZE`     | `100`                    | Ollama `/api/embed` batch size           |

### OpenRouter (cloud backend)

OpenRouter is a cloud provider that implements the OpenAI-compatible API at `https://openrouter.ai/api/v1`. It uses the same LlamaIndex classes as llama.cpp (`OpenAIEmbedding`, `OpenAILike`) — only `api_base` and `api_key` differ.

| Env var                  | Default                       | Purpose                                                          |
| ------------------------ | ----------------------------- | ---------------------------------------------------------------- |
| `OPENROUTER_API_KEY`     | _(required)_                  | OpenRouter API key                                               |
| `OPENROUTER_EMBED_MODEL` | _(required for embeddings)_   | OpenRouter embedding model (e.g., `text-embedding-3-small`)      |
| `OPENROUTER_LLM_MODEL`   | _(required for metadata LLM)_ | OpenRouter chat model (e.g., `meta-llama/llama-3.1-8b-instruct`) |

```bash
uv sync --extra openrouter
```

```bash
# .env — cloud embeddings with local LLM (cost-efficient)
EMBED_PROVIDER=cloud
METADATA_LLM_PROVIDER=local
LOCAL_BACKEND=ollama
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_EMBED_MODEL=text-embedding-3-small
```

```bash
# .env — fully cloud
EMBED_PROVIDER=cloud
METADATA_LLM_PROVIDER=cloud
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_EMBED_MODEL=text-embedding-3-small
OPENROUTER_LLM_MODEL=meta-llama/llama-3.1-8b-instruct
```

> **Adding other OpenAI-compatible providers:** The registry pattern supports any endpoint that implements the OpenAI API (vLLM, TGI, LocalAI, Azure OpenAI, actual OpenAI). Adding one requires a new `core/providers/<kind>/<name>.py` exposing `build(settings)` with a different `api_base`, plus one `register()` line — see [Adding a new provider](#adding-a-new-provider) below.

See [ADR-026](../adr/026-provider-registry-and-openrouter.md) for the full rationale.

> **Shared classification knobs, with per-provider timeout overrides:**
> `METADATA__CLASSIFY_MAX_ATTEMPTS` governs the retry budget for **all
> three** metadata LLM backends (Ollama, llama.cpp, OpenRouter) — it has
> no per-provider override. `METADATA__CLASSIFY_TIMEOUT` (per-attempt,
> direct-chat classification) and `METADATA__PIPELINE_TIMEOUT` (the
> `llamaindex` mode's multi-extractor pipeline) are shared defaults that
> each backend can override independently:
>
> | Backend      | Classify timeout override                        | Pipeline timeout override                        |
> | ------------ | ------------------------------------------------ | ------------------------------------------------ |
> | `llamacpp`   | `METADATA__LLAMACPP_CLASSIFY_TIMEOUT_OVERRIDE`  | `METADATA__LLAMACPP_PIPELINE_TIMEOUT_OVERRIDE`  |
> | `ollama`     | `METADATA__OLLAMA_CLASSIFY_TIMEOUT_OVERRIDE`    | `METADATA__OLLAMA_PIPELINE_TIMEOUT_OVERRIDE`    |
> | `openrouter` | `METADATA__OPENROUTER_CLASSIFY_TIMEOUT_OVERRIDE`| `METADATA__OPENROUTER_PIPELINE_TIMEOUT_OVERRIDE`|
>
> Each is unset (`None`) by default and falls back to the shared
> `METADATA__CLASSIFY_TIMEOUT` / `METADATA__PIPELINE_TIMEOUT` — set one
> only on the machine that needs different tuning (e.g. a slower local
> box wants a longer `llamacpp` pipeline budget without loosening the
> fast-fail classify budget elsewhere). The model field stays per-provider
> too (`METADATA__OLLAMA_CLASSIFY_MODEL`, `LLAMACPP_CHAT_MODEL`,
> `OPENROUTER_LLM_MODEL`). See [Metadata extraction](metadata-extraction.md#timeouts).

## Registry pattern

Providers are resolved through flat, per-domain lazy registries. Each registry maps a name to a `"module:attr"` import string, resolved and cached on first `get()`. Importing a registry never imports a provider module, so a missing optional dependency degrades gracefully.

| Registry | Location |
| --- | --- |
| Embedding providers | `core/providers/embeddings/registry.py` |
| LLM providers | `core/providers/llm/registry.py` |
| Metadata extraction backends | `core/metadata/registry.py` |

Provider construction (instantiating the LlamaIndex client) lives in `compose.py` (`build_embed_model`, `build_llm_model`), enforced by `import-linter`. The registries only resolve names to callables; they do not construct.

<!-- registry-names:embeddings -->
Registered embedding providers: `ollama`, `llamacpp`, `openrouter`.
<!-- /registry-names:embeddings -->

<!-- registry-names:llm -->
Registered LLM providers: `ollama`, `llamacpp`, `openrouter`.
<!-- /registry-names:llm -->

### Adding a new provider

1. Add `core/providers/<kind>/<name>.py` exposing `build(settings)` (match the signature of `ollama.py` or `llamacpp.py`).
2. Add one `register("<name>", "rag_mcp.core.providers.<kind>.<name>:build")` line at the bottom of that registry.
3. Add the optional-dependency extra in `pyproject.toml` and, if it is an extra, an entry in `_PROVIDER_EXTRAS` (`core/providers/llm/registry.py`).
4. Add env vars to `.env.example`.
5. Add the name to the `<!-- registry-names -->` block above.
6. Add tests in `tests/test_registry_contract.py` and `tests/unit/test_provider_config.py`.

No changes to `core/ingestion/`, `core/retrieval/`, or `transports/` are needed — they consume providers through the registries and the composition root.

## ChromaDB dimension lock

ChromaDB locks the vector dimension at collection creation time. Switching from `local` + `ollama` (1024-dim for `qwen3-embedding:0.6b`) to `cloud` + `openrouter` (1536-dim for `text-embedding-3-small`) requires re-ingestion:

```bash
rm -rf chroma_db
rag-mcp ingest /path/to/docs/
```
