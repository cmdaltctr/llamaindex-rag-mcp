# Providers

The RAG MCP server supports multiple embedding and metadata LLM providers. Providers are selected independently via two environment variables — you can mix and match (e.g., cloud embeddings with a local LLM).

## Overview

| Provider | Type | Embeddings | Metadata LLM | Extra deps |
| --- | --- | --- | --- | --- |
| `ollama` (default) | Local | `OllamaEmbedding` | `Ollama` / `httpx` | None (core) |
| `llamacpp` | Local | `OpenAIEmbedding` | `OpenAILike` / `httpx` | `uv sync --extra llamacpp` |
| `openrouter` | Cloud | `OpenAIEmbedding` | `OpenAILike` / `httpx` | `uv sync --extra openrouter` |

## Environment variables

### Provider selection

| Env var | Controls | Default | Backward compat |
| --- | --- | --- | --- |
| `EMBED_PROVIDER` | Embedding model | `ollama` | `INFERENCE_BACKEND` maps to it (deprecated, warns) |
| `METADATA_LLM_PROVIDER` | Metadata extraction LLM | `ollama` | New — no legacy equivalent |

> **Why `METADATA_LLM_PROVIDER` defaults to `ollama` regardless of `EMBED_PROVIDER`:** to prevent surprising cloud API costs. If you set `EMBED_PROVIDER=openrouter`, metadata extraction still uses local Ollama unless you explicitly set `METADATA_LLM_PROVIDER=openrouter`.

### Ollama (default)

| Env var | Default | Purpose |
| --- | --- | --- |
| `EMBED_MODEL` | _(required)_ | Ollama embedding model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_CLASSIFY_MODEL` | `qwen3:0.6b` | Ollama model for metadata classification |
| `EMBED_BATCH_SIZE` | `100` | Ollama `/api/embed` batch size |

### llama.cpp

| Env var | Default | Purpose |
| --- | --- | --- |
| `LLAMACPP_EMBED_MODEL` | _(required)_ | GGUF filename for embeddings |
| `LLAMACPP_EMBED_URL` | `http://localhost:8080/v1` | llama-server embedding endpoint |
| `LLAMACPP_CHAT_MODEL` | _(required for local metadata mode)_ | GGUF filename for metadata LLM |
| `LLAMACPP_CHAT_URL` | `http://localhost:8081/v1` | llama-server chat endpoint |

```bash
uv sync --extra llamacpp

# Start two llama-server processes
llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port 8080 --embeddings
llama-server -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 --port 8081
```

```bash
# .env
EMBED_PROVIDER=llamacpp
METADATA_LLM_PROVIDER=llamacpp
LLAMACPP_EMBED_MODEL=Qwen3-Embedding-0.6B-Q8_0.gguf
LLAMACPP_CHAT_MODEL=Qwen3-0.6B-Q8_0.gguf
```

See [ADR-025](../adr/025-pluggable-inference-backend.md) for the full rationale.

### OpenRouter (cloud)

| Env var | Default | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | _(required)_ | OpenRouter API key |
| `OPENROUTER_EMBED_MODEL` | _(required for embeddings)_ | OpenRouter embedding model (e.g., `text-embedding-3-small`) |
| `OPENROUTER_LLM_MODEL` | _(required for metadata LLM)_ | OpenRouter chat model (e.g., `meta-llama/llama-3.1-8b-instruct`) |

```bash
uv sync --extra openrouter
```

```bash
# .env — cloud embeddings with local LLM (cost-efficient)
EMBED_PROVIDER=openrouter
METADATA_LLM_PROVIDER=ollama
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_EMBED_MODEL=text-embedding-3-small
```

```bash
# .env — fully cloud
EMBED_PROVIDER=openrouter
METADATA_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_EMBED_MODEL=text-embedding-3-small
OPENROUTER_LLM_MODEL=meta-llama/llama-3.1-8b-instruct
```

OpenRouter provides OpenAI-compatible endpoints at `https://openrouter.ai/api/v1`. Both embeddings and LLM use the same LlamaIndex classes as llama.cpp — only the `api_base` and `api_key` differ.

See [ADR-026](../adr/026-provider-registry-and-openrouter.md) for the full rationale.

## Registry pattern

Providers are defined in two registry dicts in `config.py`:

- `EMBED_PROVIDERS` — embedding model providers
- `LLM_PROVIDERS` — metadata extraction LLM providers

Each entry specifies the module, class, required/optional env vars, static params, and the optional dependency name. The `_build_provider(registry, provider_name)` function resolves env vars, dynamic-imports the module, and instantiates the class.

### Adding a new provider

1. Add an entry to `EMBED_PROVIDERS` or `LLM_PROVIDERS` in `src/rag_mcp/config.py`
2. Add an optional dependency group in `pyproject.toml`
3. Add env vars to `.env.example`
4. Add tests in `tests/unit/test_inference_backend.py`

No changes to `ingestion.py`, `retrieval.py`, `metadata_extractor.py`, or `server.py` are needed — they consume providers through `config.py`.

## Backward compatibility

### `INFERENCE_BACKEND` (deprecated)

The old `INFERENCE_BACKEND` env var still works but is deprecated:

- If `EMBED_PROVIDER` is not set but `INFERENCE_BACKEND` is, the value is copied to `EMBED_PROVIDER` with a `DeprecationWarning`.
- `INFERENCE_BACKEND` is still importable from `config.py` — it returns `EMBED_PROVIDER`'s value.

### `METADATA_EXTRACTION_MODE=ollama` (renamed to `local`)

The metadata extraction mode `ollama` has been renamed to `local` to reflect that it's a strategy (local LLM classification), not a specific provider. The old name silently maps to the new one — no warning, no breakage.

## ChromaDB dimension lock

ChromaDB locks the vector dimension at collection creation time. Switching `EMBED_PROVIDER` from `ollama` (1024-dim for `qwen3-embedding:0.6b`) to `openrouter` (1536-dim for `text-embedding-3-small`) requires re-ingestion:

```bash
rm -rf chroma_db
rag-mcp ingest /path/to/docs/
```
