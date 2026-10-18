# Providers

OMRG supports multiple embedding and metadata LLM providers. Providers are selected independently via a two-tier system: category (`local`|`cloud`) + sub-provider — you can mix and match (e.g., cloud embeddings with a local LLM).

> **Scope:** This guide covers embedding and metadata LLM providers, and the two Chat-only providers (OpenAI-compatible and Anthropic). Document parsing (`DOCUMENT_BACKEND=azure`, Azure Document Intelligence) is a separate orthogonal axis — see [ADR-024](../adr/024-dual-deployment-modes.md).

## Overview

| Category | Sub-provider         | Embeddings        | Metadata LLM           | Extra deps                   |
| -------- | -------------------- | ----------------- | ---------------------- | ---------------------------- |
| `local`  | `llamacpp` (default) | `OpenAIEmbedding` | `OpenAILike` / `httpx` | None (base install)          |
| `local`  | `ollama`             | `OllamaEmbedding` | `Ollama` / `httpx`     | None (core)                  |
| `cloud`  | `openrouter`         | `OpenAIEmbedding` | `OpenAILike` / `httpx` | None (base install)          |

The LlamaIndex OpenAI-like packages are in the base install. The `llamacpp` and `openrouter` extras stay as empty extras, so `uv sync --extra llamacpp` and `uv sync --extra openrouter` still work.

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
# No extra needed: the OpenAI-like packages are in the base install

# Start two llama-server processes
llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port 8080 --embeddings
llama-server -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 --port 8081
```

**Managed server or your own.** You can start `llama-server` yourself, as above. `omrg web` can also start, stop and restart one chat server for you (Settings > Providers > llama.cpp > Local server). omrg manages only the server it started. It never touches a server you started yourself. It does not manage the embedding server. See [Local llama.cpp server](configuration.md#local-llamacpp-server) for the settings and guardrails.

```bash
# .env
EMBED_PROVIDER=local
METADATA_LLM_PROVIDER=local
LOCAL_BACKEND=llamacpp
LLAMACPP_EMBED_MODEL=Qwen3-Embedding-0.6B-Q8_0.gguf
LLAMACPP_CHAT_MODEL=Qwen3-0.6B-Q8_0.gguf
```

See [ADR-025](../adr/025-pluggable-inference-backend.md) for the full rationale.

### Chat-only providers (OpenAI-compatible and Anthropic)

These two providers serve the answers role only (`ANSWER__PROVIDER`, or Settings > Chat in `omrg web`). They are not valid for `EMBED_PROVIDER`, `LOCAL_BACKEND` or `CLOUD_BACKEND`.

| Provider | Env var | Default | Purpose |
|---|---|---|---|
| `openai_compatible` | `OPENAI_COMPATIBLE_BASE_URL` | `https://api.openai.com/v1` | Address of any server that speaks the OpenAI chat API (OpenAI, Together, vLLM, LM Studio) |
| `openai_compatible` | `OPENAI_COMPATIBLE_API_KEY` | unset | Optional. LM Studio and vLLM need none. Sent only to the address above |
| `anthropic` | `ANTHROPIC_API_KEY` | unset | Required. The address is fixed at `https://api.anthropic.com` |

`openai_compatible` uses `OpenAILike` from the base install. The address can be on this machine or remote. `anthropic` needs an extra, because it pulls boto3 and Google SDKs (about 40 MB):

```bash
uv sync --extra anthropic
```

The connection test sends `GET {base_url}/models` for `openai_compatible`, with a bearer header only when a key is set. For `anthropic` it sends `GET /v1/models` with the headers `x-api-key` and `anthropic-version: 2023-06-01`, and sends nothing when no key is set.

### Where provider values come from

For each address and key, the server uses the first source it finds, highest first: process environment, `.env`, `omrg.jsonc` in the user config folder, a value saved in `omrg web` Settings, a key file `secrets/<provider>.key` (keys only), the default. `GET /v1/connections` reports the source as `env`, `config-file`, `saved`, `keychain`, `key-file`, `default` or `none`, and the top-level `user_config_dir` (with `~` for home).

- The environment, `.env` and `omrg.jsonc` lock the field in Settings. The card shows "Set from environment (read-only here)" or "Set from config file (read-only here)".
- A key file does not lock. The card shows "Set from key file (read-only here). Saving a key in the keychain overrides it."
- The CLI and the stdio MCP server read the environment, `.env` and the user config folder. They do not see values saved in the web page.
- The files in the user config folder are plaintext. The keychain stays the advice on a desktop. See [Configuration](configuration.md#user-config-folder).

### Ollama (alternative local backend)

| Env var                           | Default                  | Purpose                                  |
| --------------------------------- | ------------------------ | ---------------------------------------- |
| `EMBED_MODEL`                     | _(required)_             | Ollama embedding model name              |
| `OLLAMA_BASE_URL`                 | `http://localhost:11434` | Ollama server URL                        |
| `OLLAMA_CONTEXT_WINDOW`           | `16384`                  | Context window in tokens (2,048 to 262,144) for Chat and metadata extraction |
| `METADATA__OLLAMA_CLASSIFY_MODEL` | `qwen3:0.6b`             | Ollama model for metadata classification |
| `INGESTION__EMBED_BATCH_SIZE`     | `100`                    | Ollama `/api/embed` batch size           |

Context window. omrg sends `OLLAMA_CONTEXT_WINDOW` on every Chat and metadata call, so Ollama never reserves memory for the model maximum (TDR-036). Embedding models are not covered. See [Context windows](configuration.md#context-windows).

### OpenRouter (cloud backend)

OpenRouter is a cloud provider that implements the OpenAI-compatible API at `https://openrouter.ai/api/v1`. It uses the same LlamaIndex classes as llama.cpp (`OpenAIEmbedding`, `OpenAILike`) — only `api_base` and `api_key` differ.

| Env var                  | Default                       | Purpose                                                          |
| ------------------------ | ----------------------------- | ---------------------------------------------------------------- |
| `OPENROUTER_API_KEY`     | _(required)_                  | OpenRouter API key                                               |
| `OPENROUTER_EMBED_MODEL` | _(required for embeddings)_   | OpenRouter embedding model (e.g., `text-embedding-3-small`)      |
| `OPENROUTER_LLM_MODEL`   | _(required for metadata LLM)_ | OpenRouter chat model (e.g., `meta-llama/llama-3.1-8b-instruct`) |

```bash
# No extra needed: the OpenAI-like packages are in the base install
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

Provider construction (instantiating the LlamaIndex client) lives in `compose.py` (`build_embed_model`), enforced by `import-linter`. The registries only resolve names to callables; they do not construct. Metadata extraction resolves LLMs through its own dispatch in `core/metadata/extractor.py`, not through the composition root.

<!-- registry-names:embeddings -->
Registered embedding providers: `ollama`, `llamacpp`, `openrouter`.
<!-- /registry-names:embeddings -->

<!-- registry-names:llm -->
Registered LLM providers: `ollama`, `llamacpp`, `openrouter`, `openai_compatible`, `anthropic`.
<!-- /registry-names:llm -->

### Adding a new provider

1. Add `core/providers/<kind>/<name>.py` exposing `build(settings)` (match the signature of `ollama.py` or `llamacpp.py`).
2. Add one `register("<name>", "omrg.core.providers.<kind>.<name>:build")` line at the bottom of that registry.
3. Add the optional-dependency extra in `pyproject.toml` and, if it is an extra, an entry in `_PROVIDER_EXTRAS` (`core/providers/llm/registry.py`).
4. Add env vars to `.env.example`.
5. Add the name to the `<!-- registry-names -->` block above.
6. Add tests in `tests/test_registry_contract.py` and `tests/unit/test_provider_config.py`.

No changes to `core/ingestion/`, `core/retrieval/`, or `transports/` are needed — they consume providers through the registries and the composition root.

## ChromaDB dimension lock

ChromaDB locks the vector dimension at collection creation time. Switching from `local` + `ollama` (1024-dim for `qwen3-embedding:0.6b`) to `cloud` + `openrouter` (1536-dim for `text-embedding-3-small`) requires re-ingestion:

```bash
rm -rf chroma_db
omrg ingest /path/to/docs/
```
