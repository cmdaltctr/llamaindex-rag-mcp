## Context

The RAG MCP server currently hardcodes Ollama as the inference backend for both embeddings (`OllamaEmbedding` in `config.py`) and metadata extraction LLM calls (`/api/generate` and `llama_index.llms.ollama.Ollama` in `metadata_extractor.py`). Ollama wraps llama.cpp, adding a convenience layer but also overhead (~20-27%) and serial request handling that slows batch ingestion.

llama.cpp's `llama-server` exposes OpenAI-compatible endpoints (`/v1/embeddings`, `/v1/chat/completions`) with better concurrency via parallel slots and no wrapper overhead. Supporting both backends lets users choose: Ollama for convenience (one-command model pulling), llama.cpp for raw performance.

## Goals / Non-Goals

**Goals:**

- Allow users to switch between Ollama and llama.cpp via a single env var (`INFERENCE_BACKEND`)
- Default to `ollama` so existing users see zero change
- Use LlamaIndex's existing OpenAI-compatible integration classes (`OpenAIEmbedding`, `OpenAILike`) for llama.cpp — no custom HTTP client needed for embeddings
- Keep the metadata extraction degradation ladder intact: `llamaindex` → `ollama` → `keyword`

**Non-Goals:**

- Automatically detecting which backend is running (user declares via env var)
- Supporting other backends (vLLM, TGI, SGLang) — those also expose OpenAI-compatible APIs but are out of scope
- Auto-downloading GGUF models for llama.cpp (llama-server's `-hf` flag handles this; `hf download` for offline use is documented)
- Running two `llama-server` processes automatically (documented in `.env.example`, user manages)
- Changing the reranker (ONNX-based, backend-independent)

## Decisions

### 1. Single env var: `INFERENCE_BACKEND=ollama|llamacpp`

**Rationale**: One switch controls both embeddings and metadata extraction. Avoids inconsistent states where embeddings use one backend and LLM uses another.

**Alternative considered**: Separate `EMBED_BACKEND` and `LLM_BACKEND` env vars. Rejected — adds complexity for no real use case. Users running llama.cpp want both on it.

### 2. Use `OpenAIEmbedding` for llama.cpp embeddings, not `llama-cpp-python`

**Rationale**: `llama-server` exposes `/v1/embeddings` (OpenAI-compatible). `OpenAIEmbedding` from `llama-index-embeddings-openai` already supports custom `base_url`. This is a thin config swap, no new client code.

**Alternative considered**: `llama-cpp-python` with in-process loading. Rejected — couples the MCP server process to model loading, increases memory footprint, and loses the server's batching/concurrency benefits.

### 3. Use `OpenAILike` LLM for llama.cpp metadata extraction

**Rationale**: `llama-index-llms-openai-like` is designed for OpenAI-compatible endpoints that aren't OpenAI. It supports custom `base_url` and `model` — exactly what `llama-server` provides.

**Alternative considered**: Raw `httpx` calls to `/v1/chat/completions`. Rejected for the `llamaindex` mode — LlamaIndex's extractors expect an LLM object. For the `ollama` metadata mode, we do use raw `httpx` (already the pattern for Ollama's `/api/generate`).

### 4. Raw `httpx` for `ollama` metadata mode with llama.cpp

**Rationale**: The existing `_extract_ollama_async` uses `httpx` to call Ollama's `/api/generate`. For llama.cpp, we need `/v1/chat/completions` with a different request/response shape. A new `_extract_llamacpp_chat_async` function handles this, keeping the existing Ollama path untouched.

### 5. Optional dependency group: `[llamacpp]`

**Rationale**: `llama-index-embeddings-openai` and `llama-index-llms-openai-like` are only needed when `INFERENCE_BACKEND=llamacpp`. Making them optional keeps the default install lean. Users opt in with `uv sync --extra llamacpp`.

## Risks / Trade-offs

- **[Risk] llama.cpp requires two server processes** (embedding + chat) → Mitigated: documented in `.env.example` with clear commands. Ollama serves both on one port; llama.cpp users accept this trade-off.
- **[Risk] Model name mismatch** — Ollama uses tags (`qwen3-embedding:0.6b`), llama.cpp uses filenames (`Qwen3-Embedding-0.6B-Q8_0.gguf`) → Mitigated: separate env vars for each backend's model name.
- **[Risk] Optional deps not installed but `INFERENCE_BACKEND=llamacpp` set** → Mitigated: graceful `ImportError` with clear warning message, same pattern as existing `llama-index-llms-ollama` handling.
- **[Trade-off] Two code paths to maintain** — The `httpx`-based metadata extraction now has Ollama and llama.cpp variants. Acceptable given the different API shapes (`/api/generate` vs `/v1/chat/completions`).
