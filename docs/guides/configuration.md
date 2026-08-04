# Configuration

All configuration lives in a `.env` file at the project root. Copy the example to get started:

```bash
cp .env.example .env
```

Environment variables from your shell override `.env` values, so you can also set them inline for a single run:

```bash
METADATA_EXTRACTION_MODE=disabled uv run rag-mcp ingest /path/to/docs/
```

## Resolution order

Settings resolve through a precedence chain. Each layer overrides the one
below it; the highest layer wins:

```
subpackage model field defaults            (lowest — lives next to the code that owns the knob)
  → config/defaults.yaml                    (shipped as package data, non-secret global defaults)
    → environment variables / .env          (your shell and .env file)
      → explicit instantiation args         (highest — passed when constructing Settings)
```

A typed Pydantic `Settings` object composes per-subpackage settings models
(`core/chunking/settings.py`, `core/retrieval/settings.py`,
`core/metadata/settings.py`) through multiple inheritance, so each knob's
default sits beside the code that consumes it. `config/defaults.yaml` is read
via `importlib.resources` and ships as package data. Higher layers never need
to repeat a value the lower layers already provide.

> **Never put secrets, API keys, or machine-specific absolute paths in
> `config/defaults.yaml`.** It is committed to the repository. Secrets and
> per-machine values belong in `.env` (see below).

## Three-layer architecture (config / compose / DI)

Since ADR-031 (Phase 2 of the refactor), configuration and wiring live in
three layers, enforced mechanically by `import-linter`:

1. **`config/` — typed resolver (pure data).** Parses, validates, and resolves
   every setting into a single `Settings` object. It performs **zero object
   construction** — no providers, no LlamaIndex globals. The resolver is the
   single source of truth for *resolved values* (ADR-006, amended).
2. **`compose.py` — composition root.** The **only** module that constructs
   provider and pipeline objects (`build_embed_model`, `build_llm_model`,
   `build_reranker`), resolves the lazy registries against `Settings`, and
   wires LlamaIndex's global `Settings.embed_model` via `ensure_runtime_setup()`.
   Provider construction happens here, not in `config`.
3. **Dependency injection everywhere else.** Business modules
   (`ingestion`, `retrieval`, `metadata`, `chunking`) receive their
   dependencies as parameters. They never import concrete provider classes and
   never reach into `config` for a constructed object.

Read structured settings from the resolver:

```python
from rag_mcp.config import settings

print(settings.top_k, settings.chunk_size, settings.rerank_enabled)
```

### Deprecated legacy constants (PEP 562 shim)

The bare module-level constants the older code used (`TOP_K`, `CHUNK_SIZE`,
`RERANK_ENABLED`, `EMBED_MODEL`, …) are **deprecated**. They still resolve via
a PEP 562 module-level `__getattr__` shim that reads from the `Settings`
singleton and emits a `DeprecationWarning` on each access, so external and
experiment code keeps working during migration. The shim is **removed in
v2.0.0**. New code must read from the structured `settings` object as shown
above.

See ADR-031 for the full design, including the `import-linter` contracts that
keep the three layers honest.

## What `.env` actually does

`.env` is just a convenience file. Without it, you'd have to export env vars in your shell every time:

```bash
EMBED_MODEL=qwen3-embedding:0.6b OLLAMA_BASE_URL=http://localhost:11434 uv run rag-mcp
```

Instead, the resolver calls `load_dotenv()` at import time, which reads `.env` and puts those key-values into the process environment as if you'd exported them yourself. The Pydantic `Settings` model then reads them through pydantic-settings.

**That's it.** `.env` is not parsed by the application logic — it's loaded into the OS environment by `python-dotenv` before the `Settings` model reads it.

**Flow:**

1. `config` imports → `load_dotenv()` reads `.env` → injects vars into `os.environ`
2. The Pydantic `Settings` model reads each field from `os.environ` (your shell or `.env`). If a var is absent, it falls back to `config/defaults.yaml`, then to the subpackage model's field default.

**Why have both `.env` and shipped defaults?**

- `.env` lets you customize without editing code
- Shipped defaults (`config/defaults.yaml` + subpackage model fields) mean the app works out-of-the-box (except `EMBED_MODEL`)
- `.env.example` is a template showing what you _can_ set — you copy it to `.env` and tweak

**You could delete `.env` entirely** and the server runs fine with all shipped defaults — you'd just need `EMBED_MODEL` set in your shell:

```bash
EMBED_MODEL=qwen3-embedding:0.6b uv run rag-mcp
```

## All settings by category

Each row below pairs an **env var** (what you set in `.env` or your shell) with its **settings field** (the structured `Settings` attribute you read in code). The **Default** column is the fallback used when the env var is absent (from `config/defaults.yaml` or the subpackage model). The **`.env.example`** column shows the current value in the checked-in template — _(not set)_ means the line is commented out, so the default is used. The legacy bare-constant names (`TOP_K`, `CHUNK_SIZE`, …) are preserved as the deprecated PEP 562 shim described above.

### Provider selection

| Env var                 | Default      | `.env.example` | Config constant         | Purpose                                                           |
| ----------------------- | ------------ | -------------- | ----------------------- | ----------------------------------------------------------------- |
| `EMBED_PROVIDER`        | `local`      | `local`        | `EMBED_PROVIDER`        | `local` / `cloud` category (ADR-026)                              |
| `METADATA_LLM_PROVIDER` | `local`      | `local`        | `METADATA_LLM_PROVIDER` | Metadata LLM category — independent of `EMBED_PROVIDER` (ADR-026) |
| `LOCAL_BACKEND`         | `llamacpp`   | `llamacpp`     | `LOCAL_BACKEND`         | Local sub-provider: `llamacpp` / `ollama`                         |
| `CLOUD_BACKEND`         | `openrouter` | _(commented)_  | `CLOUD_BACKEND`         | Cloud sub-provider: `openrouter`                                  |

When `LOCAL_BACKEND=llamacpp` or `CLOUD_BACKEND=openrouter`, install optional deps first:

```bash
uv sync --extra llamacpp     # for llama.cpp
uv sync --extra openrouter   # for OpenRouter
```

See [Providers](providers.md) for full setup instructions for each provider.

### llama.cpp (local sub-provider)

| Env var                | Default                          | `.env.example` | Config constant        | Purpose                                              |
| ---------------------- | -------------------------------- | -------------- | ---------------------- | ---------------------------------------------------- |
| `LLAMACPP_EMBED_URL`   | `http://localhost:8080/v1`       | _(not set)_    | `LLAMACPP_EMBED_URL`   | llama-server embedding endpoint (llamacpp only)      |
| `LLAMACPP_EMBED_MODEL` | _(none — required for llamacpp)_ | _(not set)_    | `LLAMACPP_EMBED_MODEL` | GGUF filename for embeddings (llamacpp only)         |
| `LLAMACPP_CHAT_URL`    | `http://localhost:8081/v1`       | _(not set)_    | `LLAMACPP_CHAT_URL`    | llama-server chat endpoint (llamacpp only)           |
| `LLAMACPP_CHAT_MODEL`  | _(none — required for llamacpp)_ | _(not set)_    | `LLAMACPP_CHAT_MODEL`  | GGUF filename for metadata extraction LLM (llamacpp) |

### OpenRouter (cloud sub-provider)

| Env var                  | Default                                       | `.env.example` | Config constant          | Purpose                                                          |
| ------------------------ | --------------------------------------------- | -------------- | ------------------------ | ---------------------------------------------------------------- |
| `OPENROUTER_API_KEY`     | _(none — required for openrouter)_            | _(not set)_    | `OPENROUTER_API_KEY`     | OpenRouter API key                                               |
| `OPENROUTER_EMBED_MODEL` | _(none — required for openrouter embeddings)_ | _(not set)_    | `OPENROUTER_EMBED_MODEL` | OpenRouter embedding model (e.g., `text-embedding-3-small`)      |
| `OPENROUTER_LLM_MODEL`   | _(none — required for openrouter LLM)_        | _(not set)_    | `OPENROUTER_LLM_MODEL`   | OpenRouter chat model (e.g., `meta-llama/llama-3.1-8b-instruct`) |

When `LOCAL_BACKEND=ollama`, the provider uses `OLLAMA_BASE_URL` and `EMBED_MODEL` (below). When `LOCAL_BACKEND=llamacpp`, it uses `LLAMACPP_EMBED_URL` and `LLAMACPP_EMBED_MODEL`. When `CLOUD_BACKEND=openrouter`, it uses `OPENROUTER_EMBED_MODEL` and `OPENROUTER_API_KEY`.

### Embedding (required for ollama sub-provider)

| Env var             | Default                        | `.env.example`           | Config constant     | Purpose                            |
| ------------------- | ------------------------------ | ------------------------ | ------------------- | ---------------------------------- |
| `EMBED_MODEL`       | _(none — required for ollama)_ | `qwen3-embedding:0.6b`   | `EMBED_MODEL_NAME`  | Ollama embedding model name        |
| `OLLAMA_BASE_URL`   | `http://localhost:11434`       | `http://localhost:11434` | `OLLAMA_BASE_URL`   | Ollama server URL                  |
| `EMBED_BATCH_SIZE`  | `100`                          | `100`                    | `EMBED_BATCH_SIZE`  | Ollama `/api/embed` batch size     |
| `EMBED_CONCURRENCY` | `2`                            | `4`                      | `EMBED_CONCURRENCY` | Max concurrent embedding API calls |

### ChromaDB storage

| Env var                 | Default       | `.env.example` | Config constant         | Purpose                        |
| ----------------------- | ------------- | -------------- | ----------------------- | ------------------------------ |
| `CHROMA_PERSIST_DIR`    | `./chroma_db` | `./chroma_db`  | `CHROMA_PERSIST_DIR`    | Vector DB disk path            |
| `COLLECTION_NAME`       | `documents`   | `documents`    | `COLLECTION_NAME`       | Default collection name        |
| `CHROMA_SCAN_PAGE_SIZE` | `10000`       | _(not set)_    | `CHROMA_SCAN_PAGE_SIZE` | Page size for collection scans |

### Chunking

| Env var                       | Default | `.env.example` | Config constant               | Purpose                                  |
| ----------------------------- | ------- | -------------- | ----------------------------- | ---------------------------------------- |
| `CHUNK_SIZE`                  | `512`   | `512`          | `CHUNK_SIZE`                  | Token chunk size for non-Markdown        |
| `CHUNK_OVERLAP`               | `100`   | `100`          | `CHUNK_OVERLAP`               | Overlap between chunks (ADR-018)         |
| `MARKDOWN_CHUNK_SIZE`         | `1024`  | `1024`         | `MARKDOWN_CHUNK_SIZE`         | Markdown-only chunk size (Experiment 6c) |
| `MARKDOWN_HEADING_PREPEND`    | `false` | _(not set)_    | `MARKDOWN_HEADING_PREPEND`    | Prepend headings to chunks               |
| `MARKDOWN_MIN_CHUNK_FRACTION` | `0.0`   | _(not set)_    | `MARKDOWN_MIN_CHUNK_FRACTION` | Min chunk size as fraction of CHUNK_SIZE |

### Retrieval

| Env var                 | Default | `.env.example` | Config constant         | Purpose                         |
| ----------------------- | ------- | -------------- | ----------------------- | ------------------------------- |
| `TOP_K`                 | `10`    | `10`           | `TOP_K`                 | Default results count (ADR-018) |
| `SIMILARITY_THRESHOLD`  | `0.0`   | `0.0`          | `SIMILARITY_THRESHOLD`  | Min relevance score             |
| `HYBRID_ENABLED`        | `false` | `false`        | `HYBRID_ENABLED`        | Dense + sparse BM25 fusion      |
| `HYBRID_RRF_K`          | `60`    | `60`           | `HYBRID_RRF_K`          | RRF constant                    |
| `HYBRID_SPARSE_BACKEND` | `bm25`  | `bm25`         | `HYBRID_SPARSE_BACKEND` | `bm25` / `native` / `auto`      |

### Reranker policy

| Env var                       | Default                                  | `.env.example`                            | Config constant               | Purpose                              |
| ----------------------------- | ---------------------------------------- | ----------------------------------------- | ----------------------------- | ------------------------------------ |
| `RERANK_MODEL`                | `cross-encoder/ms-marco-MiniLM-L-6-v2`   | `cross-encoder/ms-marco-MiniLM-L-6-v2`   | `RERANK_MODEL` (in reranker.py) | HuggingFace model ID              |
| `RERANK_ENABLED`              | `false`                                  | `false`                                   | `RERANK_ENABLED`              | Global rerank default (ADR-019)      |
| `RERANK_ENABLED_FOR_SEMANTIC` | `true`                                   | `true`                                    | `RERANK_ENABLED_FOR_SEMANTIC` | Policy override for semantic queries |
| `HARD_TECHNICAL_THRESHOLD`    | `0.3`                                    | `0.3`                                     | `HARD_TECHNICAL_THRESHOLD`    | Identifier-heavy fraction cutoff     |
| `RERANK_FETCH_MULTIPLIER`     | `3`                                      | `3`                                       | `RERANK_FETCH_MULTIPLIER`     | Candidate pool multiplier            |
| `RERANK_MAX_FETCH`            | `100`                                    | `100`                                     | `RERANK_MAX_FETCH`            | Max candidate pool size              |

### PDF reader

| Env var                 | Default  | `.env.example` | Config constant                      | Purpose                                                |
| ----------------------- | -------- | -------------- | ------------------------------------ | ------------------------------------------------------ |
| `PDF_READER`            | `auto`   | `auto`         | `PDF_READER` / `RESOLVED_PDF_READER` | `auto` / `liteparse` / `pypdfium2` / `pypdf` (ADR-020) |
| `LITEPARSE_OCR_ENABLED` | `false`  | `false`        | `LITEPARSE_OCR_ENABLED`              | OCR in LiteParse                                       |
| `LITEPARSE_NUM_WORKERS` | _(none)_ | _(not set)_    | `LITEPARSE_NUM_WORKERS`              | LiteParse worker threads                               |

### Metadata extraction

| Env var                          | Default      | `.env.example` | Config constant                                  | Purpose                                          |
| -------------------------------- | ------------ | -------------- | ------------------------------------------------ | ------------------------------------------------ |
| `METADATA_EXTRACTION_MODE`       | `keyword`    | `llamaindex`   | `METADATA_EXTRACTION_MODE`                       | `disabled` / `keyword` / `local` / `llamaindex`  |
| `METADATA_KEYWORD_RULES`         | _(none)_     | _(not set)_    | `METADATA_KEYWORD_RULES`                         | JSON override for keyword rules                  |
| `OLLAMA_CLASSIFY_MODEL`          | `qwen3:0.6b` | `qwen3:0.6b`   | `OLLAMA_CLASSIFY_MODEL`                          | Ollama model for classification (ollama backend) |
| `OLLAMA_CLASSIFY_MAX_ATTEMPTS`   | `3`          | _(not set)_    | `OLLAMA_CLASSIFY_MAX_ATTEMPTS`                   | Retry budget                                     |
| `OLLAMA_CLASSIFY_TIMEOUT`        | `30.0`       | _(not set)_    | `OLLAMA_CLASSIFY_TIMEOUT`                        | Per-attempt timeout (seconds)                    |
| `LLAMANDEX_EXTRACTOR_MAX_CHUNKS` | `10`         | _(not set)_    | _(read at call-time in `metadata_extractor.py`)_ | Max chunks for LlamaIndex extractor              |

### Codebase map

| Env var                    | Default     | `.env.example` | Config constant            | Purpose                       |
| -------------------------- | ----------- | -------------- | -------------------------- | ----------------------------- |
| `MAGIKA_BINARY`            | `magika`    | _(not set)_    | `MAGIKA_BINARY`            | Path to Magika CLI            |
| `DOC_SIMILARITY_THRESHOLD` | `0.85`      | _(not set)_    | `DOC_SIMILARITY_THRESHOLD` | Document graph edge threshold |
| `CODEBASE_MAP_CACHE_DIR`   | `.opencode` | _(not set)_    | `CODEBASE_MAP_CACHE_DIR`   | Cache directory               |
| `CODEBASE_MAP_MAX_FILES`   | `5000`      | _(not set)_    | `CODEBASE_MAP_MAX_FILES`   | Max files to scan             |
| `CODEBASE_MAP_MAX_DEPTH`   | `10`        | _(not set)_    | `CODEBASE_MAP_MAX_DEPTH`   | Max directory depth           |

### Document backend (Azure)

| Env var                           | Default           | `.env.example` | Config constant                   | Purpose                     |
| --------------------------------- | ----------------- | -------------- | --------------------------------- | --------------------------- |
| `DOCUMENT_BACKEND`                | `local`           | `local`        | `DOCUMENT_BACKEND`                | `local` / `azure` (ADR-024) |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | _(empty)_         | _(not set)_    | `AZURE_DOC_INTELLIGENCE_ENDPOINT` | Azure endpoint URL          |
| `AZURE_DOC_INTELLIGENCE_KEY`      | _(empty)_         | _(redacted)_   | `AZURE_DOC_INTELLIGENCE_KEY`      | Azure API key               |
| `AZURE_DOC_INTELLIGENCE_MODEL`    | `prebuilt-layout` | _(not set)_    | `AZURE_DOC_INTELLIGENCE_MODEL`    | Azure model                 |

### Hardcoded (not env-configurable)

| Constant                     | Value                                          | Purpose                                            |
| ---------------------------- | ---------------------------------------------- | -------------------------------------------------- |
| `SUPPORTED_EXTENSIONS`       | `{.pdf, .docx, .pptx, .txt, .md, .html, .csv}` | Allowed file types                                 |
| `MAGIKA_LABEL_TO_TREESITTER` | 23-entry dict                                  | Magika → tree-sitter language map                  |
| `_QUERY_EMBED_CACHE_MAXSIZE` | `128`                                          | LRU cache for query embeddings (in `retrieval.py`) |

## Call-time env reads

Most settings are resolved once into the `Settings` object at import time. One knob is deliberately read at call time instead:

- **`LLAMANDEX_EXTRACTOR_MAX_CHUNKS`** — read at call-time inside `metadata_extractor.py` rather than imported from `config`. This is intentional so tests can override it with `monkeypatch.setenv` after module load.

> **Historical note.** Earlier revisions listed a second exception: `reranker.py` imported `dotenv` independently and read `RERANK_MODEL` directly to dodge a circular import with `config.py` (gotcha #4 in AGENTS.md). That exception is **gone** since ADR-031 — the reranker now receives its model ID via dependency injection from `compose.py`, and `RERANK_MODEL` is a structured settings field. There is no longer a `dotenv` import outside the resolver.

## Config-time validation

The resolver performs validation at import time:

- **`EMBED_MODEL`** missing → raises `ValueError` (only when `EMBED_PROVIDER=local` + `LOCAL_BACKEND=ollama`)
- **`EMBED_PROVIDER`** invalid → warns + falls back to `local`
- **`LOCAL_BACKEND`** invalid → warns + falls back to `llamacpp`
- **`LOCAL_BACKEND=llamacpp`** without `llama-index-embeddings-openai` → raises `ImportError` with install hint
- **`LOCAL_BACKEND=llamacpp`** without `LLAMACPP_EMBED_MODEL` → raises `ValueError`
- **`CLOUD_BACKEND=openrouter`** without `OPENROUTER_API_KEY` → raises `ValueError`
- **`CLOUD_BACKEND=openrouter`** without optional deps → raises `ImportError` with install hint
- **`HYBRID_SPARSE_BACKEND`** invalid → warns + falls back to `bm25`
- **`PDF_READER`** invalid → warns + falls back to `auto`
- **`DOCUMENT_BACKEND`** invalid → warns + falls back to `local`
- **`DOCUMENT_BACKEND=azure`** without credentials → warns + falls back to `local`
- **`RESOLVED_PDF_READER`** and **`RESOLVED_HYBRID_SPARSE_BACKEND`** — resolved at import time by probing installed packages

## Architecture note

Configuration is split across two modules since ADR-031 (Phase 2):

- **`src/rag_mcp/config/`** — the typed resolver. Single source of truth for every *resolved settings value*. It parses and validates only; it builds no objects.
- **`src/rag_mcp/compose.py`** — the composition root. The only place runtime objects (embedding model, LLM, reranker) are constructed and where LlamaIndex's global `Settings.embed_model` is wired via `ensure_runtime_setup()`.

Never construct providers or set `Settings.embed_model` in `ingestion.py`, `retrieval.py`, `metadata_extractor.py`, or `server.py` — those modules receive their dependencies as parameters. The `import-linter` contracts in `pyproject.toml` fail the build if a business module imports a concrete provider class. The legacy bare constants (`TOP_K`, `CHUNK_SIZE`, …) are a deprecated PEP 562 shim over the `Settings` singleton, removed in v2.0.0.
