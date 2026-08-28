# ADR-025: Pluggable inference backend — Ollama and llama.cpp

**Date:** 2026-07-01
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Md Hawari
**Change:** `add-llamacpp-backend`

## Context

The RAG MCP server hardcoded Ollama as the sole inference backend for embeddings (`OllamaEmbedding`) and metadata extraction LLM calls (Ollama's `/api/generate` and `llama_index.llms.ollama.Ollama`). Ollama is a convenience wrapper over llama.cpp that adds:

- ~20-27% overhead per request (wrapper layer, model loading/unloading)
- Serial request handling — collapses at 5+ concurrent users
- A custom API (`/api/generate`) that isn't OpenAI-compatible

Researchers and power users who want maximum throughput prefer llama.cpp's `llama-server` directly. It exposes OpenAI-compatible endpoints (`/v1/embeddings`, `/v1/chat/completions`), supports parallel slots for concurrent requests, and has no wrapper overhead. Hugging Face acquired llama.cpp in February 2026, ensuring long-term maintenance and ecosystem alignment.

## Decision

Support both backends via a single `INFERENCE_BACKEND` environment variable (`ollama` | `llamacpp`), defaulting to `ollama` to preserve existing behaviour.

### Backend selection

| `INFERENCE_BACKEND` | Embeddings                            | Metadata LLM (ollama mode)       | Metadata LLM (llamaindex mode)            |
| ------------------- | ------------------------------------- | -------------------------------- | ----------------------------------------- |
| `ollama` (default)  | `OllamaEmbedding` → `/api/embeddings` | `httpx` → `/api/generate`        | `llama_index.llms.ollama.Ollama`          |
| `llamacpp`          | `OpenAIEmbedding` → `/v1/embeddings`  | `httpx` → `/v1/chat/completions` | `llama_index.llms.openai_like.OpenAILike` |

### Optional dependencies

`llama-index-embeddings-openai` and `llama-index-llms-openai-like` are optional, under the `llamacpp` extra:

```bash
uv sync --extra llamacpp
```

If `INFERENCE_BACKEND=llamacpp` but the deps aren't installed, the system raises an `ImportError` with the install hint.

### Two server processes for llama.cpp

Unlike Ollama (which serves both embeddings and chat on one port), llama.cpp requires separate `llama-server` processes for each model:

```bash
llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port 8080 --embeddings
llama-server -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 --port 8081
```

Models are cached in `~/.cache/huggingface/hub` (standard HF cache). This is documented in `.env.example`. Users manage these processes themselves.

### Model downloads

Ollama uses `ollama pull <tag>`. llama.cpp can download GGUF directly from HuggingFace via the `-hf` flag:

```bash
llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port 8080 --embeddings
```

For offline use, download with `hf download` (replaces deprecated `huggingface-cli`) to the default HF cache:

```bash
hf download Qwen/Qwen3-Embedding-0.6B-GGUF Qwen3-Embedding-0.6B-Q8_0.gguf
hf download Qwen/Qwen3-0.6B-GGUF Qwen3-0.6B-Q8_0.gguf
```

Files go to `~/.cache/huggingface/hub` — `llama-server -hf` will find them there.

## Consequences

### Positive

- Users can choose between convenience (Ollama) and raw performance (llama.cpp) without code changes.
- OpenAI-compatible API future-proofs the project for any OpenAI-compatible backend.
- No breaking changes — existing `ollama` users see zero difference.

### Negative

- Two code paths to maintain for metadata extraction (Ollama `/api/generate` vs OpenAI `/v1/chat/completions`).
- llama.cpp users must manage two server processes manually.

### Neutral

- `LLAMACPP_*` env vars are ignored when `INFERENCE_BACKEND=ollama` (default).
- The `llamacpp` extra installs `llama-index-embeddings-openai` and `llama-index-llms-openai-like`, which are also usable with other OpenAI-compatible backends.

## Alternatives Considered

| Option                                                        | Rejected Because                                                                                                                                   |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Separate `EMBED_BACKEND` and `LLM_BACKEND` env vars**       | No real use case for splitting backends; adds configuration complexity.                                                                            |
| **`llama-cpp-python` with in-process model loading**          | Couples the MCP server process to model loading, increases memory footprint, and loses the server's batching/concurrency benefits.                 |
| **Raw `httpx` for all LLM calls (no LlamaIndex LLM objects)** | LlamaIndex's extractors (`TitleExtractor`, `KeywordExtractor`, `SummaryExtractor`) expect an LLM object. `OpenAILike` satisfies this interface.    |
| **Supporting vLLM/TGI/SGLang**                                | Out of scope. They expose OpenAI-compatible APIs, so users can point `LLAMACPP_*_URL` at them if desired, but we don't document or test that path. |

## References

- [`src/rag_mcp/config.py`](../../src/rag_mcp/config.py) — `INFERENCE_BACKEND` selection logic
- [`src/rag_mcp/metadata_extractor.py`](../../src/rag_mcp/metadata_extractor.py) — llamacpp chat extraction path
- [`.env.example`](../../.env.example) — `LLAMACPP_*` env vars and setup instructions
- [`docs/guides/configuration.md`](../guides/configuration.md) — Inference backend configuration table
- [llama.cpp GitHub](https://github.com/ggml-org/llama.cpp)
- [HuggingFace GGUF docs](https://huggingface.co/docs/hub/en/gguf-llamacpp)

---

## Update (2026-08-04, Phase 2)

**Amended by:** [ADR-031](./031-three-layer-config-compose-di.md) — Three-Layer
Architecture — Config, Compose, DI.

The provider registry this ADR introduced has been **physically relocated**.
The nested registry dicts and the `_build_provider` function that previously
lived in `config.py` have moved into a dedicated `core/providers/` package:
`common.py` holds shared connection config, and `embeddings/` and `llm/`
subpackages hold their respective registries and provider modules.

What changed:

- **Location only, not interface.** The registry's resolution behaviour, the
  `local`/`cloud` + sub-provider selection, and every env var are unchanged.
  `_build_provider`'s logic now lives in `compose.py` (`build_embed_model`,
  `build_llm_model`) as part of the composition root.
- **Registries are now lazy.** Each registry is a `Dict[str, str]` mapping a
  name to a `"module:attr"` import string, resolved and cached on first
  `get()`. Importing a registry no longer imports the provider modules, so a
  missing optional dependency degrades to "provider unavailable" instead of
  breaking import.
- **The same lazy contract is reused** by `core/chunking/registry.py`,
  `core/retrieval/registry.py`, and `core/metadata/registry.py` — every
  strategy folder now uses one registry shape.

See ADR-031 for the composition-root design and the `import-linter` contracts
that confine provider construction to `compose.py`.

---

## Update (2026-08-15, add-chroma-cloud-backend)

The `llamacpp` extra originally installed
`llama-index-embeddings-openai` (providing `OpenAIEmbedding`). That
package's fixed model enum cannot express provider-prefixed model IDs, so
the llamacpp and openrouter embedding providers now use
`OpenAILikeEmbedding` from `llama-index-embeddings-openai-like>=0.3.0`
instead. The `llamacpp` extra installs `llama-index-embeddings-openai-like`
(and `llama-index-llms-openai-like` for the chat side). See the
add-chroma-cloud-backend change and the ADR-026 update for rationale.
