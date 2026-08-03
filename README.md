# LlamaIndex RAG MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Requires llama.cpp, Ollama, or OpenRouter](https://img.shields.io/badge/requires-llama.cpp_or_Ollama_or_OpenRouter-000000)](https://github.com/ggml-org/llama.cpp)

> **⚠️ Under heavy refactoring (v2.0.0).** The codebase is being restructured into a modular RAG framework across five phases. Phase 1 (subpackage extraction) is complete. Phase 2 (config/core split) is next. Everything stays backward-compatible via deprecation shims until v2.0.0. See [the refactor proposal](docs/brainstorm/refactor-proposal/PROPOSAL.md) for details.

A local document search server for AI assistants. Point it at your files — PDFs, Word docs, notes, research papers — and your AI can search them by meaning, not just keywords. Everything runs on your machine by default — no cloud, no API keys, no recurring costs. Cloud providers (OpenRouter) are available as an opt-in alternative.

**What it is:** An [MCP](https://modelcontextprotocol.io) server that gives AI assistants (Claude, GPT, Cursor, and others) the ability to search your documents using natural language.

**What it isn't:** A chatbot, a cloud service, or a replacement for your file system. It's a search layer — your AI asks it questions, it finds the relevant passages.

---

## Active Refactoring (v2.0.0)

**Progress:** Phase 1 of 5 complete ([#12](https://github.com/cmdaltctr/llamaindex-rag-mcp/pull/12)). Phase 2 (config/core split) is next.

The codebase is evolving into a **modular, swappable RAG framework** that serves two distinct use cases through one shared core: **document grounding** (facts from papers, reports, financial statements) and **codebase context** (code understanding for AI agents).

**Key changes planned:**

- **Three-layer separation** — declarative config (`config.py`), composition root (`compose.py`), dependency injection throughout. Slims `config.py` from 572 to ~150 lines.
- **Strategy folders** — `chunking/`, `retrieval/`, `metadata/`, `providers/`. Add a strategy by dropping in one `.py` file and registering it; no editing of large existing modules.
- **Profiles system** — named presets (`documents`, `codebase`, `hybrid`) bound per-collection, making the dual use cases first-class instead of implicit env-var combinations.
- **Thin transports** — MCP, CLI, and a future REST API all call the same `core/`. None contains business logic.
- **Five-phase migration** — each phase independently shippable and revertible via its own OpenSpec change. Backward-compatible re-export shims throughout.

> **⚠️ Timeline:** The refactor targets **v2.0.0**. Until then, v1.x continues with the current flat-module structure. No breaking changes until the deprecation window opens. Existing ChromaDB collections, CLI commands, and MCP tool signatures remain stable.

---

## MCP Tools

Six tools your AI can call:

| Tool                     | What it does                                                                                                    |
| ------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `ingest_documents`       | Index a file or directory (PDF, DOCX, PPTX, TXT, Markdown, HTML, CSV)                                           |
| `search_documents`       | Semantic search with optional reranking, hybrid BM25 fusion, and metadata filtering                             |
| `list_indexed_documents` | See what's currently indexed                                                                                    |
| `list_collections`       | See all document collections and their sizes                                                                    |
| `delete_documents`       | Remove documents by path, filter, or drop a whole collection                                                    |
| `get_codebase_map`       | Generate a compact codebase map with file types, code communities, document communities, and architectural hubs |

---

## CLI

The same `rag-mcp` command works as both an MCP server and a terminal tool:

| Command                    | What it does                                                    |
| -------------------------- | --------------------------------------------------------------- |
| `rag-mcp`                  | Start the MCP server                                            |
| `rag-mcp ingest <path>`    | Index a file or directory                                       |
| `rag-mcp search <query>`   | Search from the terminal (`--hybrid` enables dense+BM25 fusion) |
| `rag-mcp list`             | List indexed documents                                          |
| `rag-mcp list-collections` | List all collections                                            |
| `rag-mcp watch <dir>`      | Auto-ingest new and changed files                               |
| `rag-mcp delete`           | Delete documents or drop a collection                           |
| `rag-mcp benchmark`        | Benchmark embedding throughput                                  |

---

## Quick install

You need [uv](https://docs.astral.sh/uv/) and either [llama.cpp](https://github.com/ggml-org/llama.cpp) (default), [Ollama](https://ollama.com), or an [OpenRouter](https://openrouter.ai) API key.

```bash
# Set up the project
cp .env.example .env    # then edit .env to match your setup
uv sync --extra llamacpp  # install llama.cpp provider deps

# Start llama-server (downloads GGUF from HuggingFace automatically)
llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port 8080 --embeddings &
llama-server -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 --port 8081 &

# Verify it works — Ctrl-C to stop
uv run rag-mcp
```

All settings live in `.env` — see [Configuration](docs/guides/configuration.md) for every variable.

No output means it's working. It's waiting silently for MCP messages on stdin.

To use Ollama or OpenRouter instead, see [Providers](docs/guides/providers.md) for all options.

Then register it in your AI client — see [MCP Client Setup](docs/guides/mcp-client-setup.md).

### Optional hybrid retrieval

Hybrid retrieval is opt-in and keeps the dense-only default unchanged. Use it
for rare terms, exact identifiers, citations, error codes, and product names:

```bash
uv run rag-mcp search "What fixes MCP-1138?" --hybrid
```

MCP clients can pass the same option:

```json
{ "query": "What fixes MCP-1138?", "hybrid": true, "rerank": true }
```

The v1 sparse backend is in-memory BM25 (`HYBRID_SPARSE_BACKEND=bm25`) fused
with dense results via RRF (`HYBRID_RRF_K=60`). The BM25 index is cached per
collection and rebuilt lazily after ingestion or deletion; its memory footprint
scales with the collection's chunk count.

### Using Ollama instead

Prefer [Ollama](https://ollama.com)'s one-command model pulling? Set `LOCAL_BACKEND=ollama` in `.env`:

```bash
uv sync                # ollama uses core deps — no extra flag needed
ollama pull qwen3-embedding:0.6b
ollama pull qwen3:0.6b  # for metadata classification
```

```bash
# .env
EMBED_PROVIDER=local
METADATA_LLM_PROVIDER=local
LOCAL_BACKEND=ollama
EMBED_MODEL=qwen3-embedding:0.6b
OLLAMA_CLASSIFY_MODEL=qwen3:0.6b
```

See [ADR-025](docs/adr/025-pluggable-inference-backend.md) for the full rationale.

### Optional OpenRouter cloud provider

Use [OpenRouter](https://openrouter.ai) for cloud embeddings and/or metadata LLM without running any local model servers. OpenRouter implements the OpenAI-compatible API — the same LlamaIndex classes as llama.cpp, just a different `api_base` and `api_key`.

```bash
# Install optional deps (same packages as llamacpp — both use the OpenAI-compatible API)
uv sync --extra openrouter
```

Then set in `.env`:

```bash
# Cloud embeddings + local LLM (cost-efficient)
EMBED_PROVIDER=cloud
CLOUD_BACKEND=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_EMBED_MODEL=text-embedding-3-small

# Or fully cloud — also set:
METADATA_LLM_PROVIDER=cloud
OPENROUTER_LLM_MODEL=meta-llama/llama-3.1-8b-instruct
```

> **ChromaDB dimension lock:** Switching `EMBED_PROVIDER` changes the vector dimension. Delete `chroma_db/` and re-ingest.

See [ADR-026](docs/adr/026-provider-registry-and-openrouter.md) for the full rationale.

### Optional PDF reader (LiteParse)

The default PDF parser is **LiteParse** (when installed via `[pdf-liteparse]`),
falling back to **pypdf** if LiteParse is not present. LiteParse provides
column-aware reading order, bounding-box metadata, and faster parsing —
validated by [Experiment 11](experiments/11-liteparse-pdf-quality-2026-06-20/)
(+6.9% nDCG@10 on academic PDFs). See [ADR-020](docs/adr/020-use-liteparse-as-pdf-reader.md).

```bash
uv sync
# LiteParse is installed as a core dependency — no extra flag needed
```

---

## Supported file formats

`.pdf` `.docx` `.pptx` `.txt` `.md` `.html` `.csv`

---

## Documentation

| Guide                                                     | What's in it                                                   |
| --------------------------------------------------------- | -------------------------------------------------------------- |
| [Getting Started](docs/guides/getting-started.md)         | Prerequisites, install, verify, enable reranker                |
| [Configuration](docs/guides/configuration.md)             | All environment variables and `.env` settings                  |
| [CLI Reference](docs/guides/cli-reference.md)             | Every command, flag, and example                               |
| [MCP Tools Reference](docs/guides/mcp-tools.md)           | Tool parameters in detail                                      |
| [Providers](docs/guides/providers.md)                     | Embedding & LLM provider setup (llama.cpp, Ollama, OpenRouter) |
| [Ingestion Guide](docs/guides/ingestion.md)               | How ingestion works, embedding models, chunk sizes             |
| [Metadata Extraction](docs/guides/metadata-extraction.md) | Auto-categorisation, keyword rules, filtering                  |
| [Reranker](docs/guides/reranker.md)                       | Cross-encoder reranking and threshold scaling                  |
| [MCP Client Setup](docs/guides/mcp-client-setup.md)       | Register in OpenChamber, Claude Desktop, multi-project         |
| [Testing](docs/guides/testing.md)                         | Test suite, coverage, running tests                            |
| [Architecture](docs/guides/architecture.md)               | Why things are built the way they are (plain English)          |
| [Architecture Decisions](docs/adr/)                       | Full ADRs with alternatives and consequences                   |
| [Contributing](CONTRIBUTING.md)                           | Workflow, conventions, and how to open a PR                    |

---

## Licence

[MIT](./LICENSE)
