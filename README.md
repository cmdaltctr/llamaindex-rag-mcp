# LlamaIndex RAG MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Requires llama.cpp, Ollama, or OpenRouter](https://img.shields.io/badge/requires-llama.cpp_or_Ollama_or_OpenRouter-000000)](https://github.com/ggml-org/llama.cpp)

A local document search server for AI assistants. Point it at your files — PDFs,
Word docs, notes, papers, source code — and your AI can search them by meaning
rather than keywords.

Everything runs on your machine by default. No cloud, no API keys, no recurring
costs. Cloud providers are available if you want them, never required.

**What it is:** an [MCP](https://modelcontextprotocol.io) server that lets AI
assistants — Claude, GPT, Cursor and others — search your documents in natural
language.

**What it isn't:** a chatbot, a cloud service, or a replacement for your file
system. It is a search layer. Your AI asks it questions; it finds the relevant
passages.

---

## Two jobs, one server

The same server handles two quite different tasks, and they want opposite
settings. You pick per collection.

| | Document grounding | Codebase context |
|---|---|---|
| For | Papers, reports, financial statements | Source code |
| Profile | `documents` | `codebase` |
| Results returned | 10 | 20 |
| Reranker | on — improves prose | off — measured 19–27% *worse* on code |
| Search | embeddings only | embeddings + keyword (BM25) |

```bash
rag-mcp set-profile -c my_papers -p documents
rag-mcp set-profile -c my_code   -p codebase
```

Both collections then behave correctly in the same running server. See
[Configuration](docs/guides/configuration.md#profiles).

---

## Install

You need [uv](https://docs.astral.sh/uv/) and one of
[llama.cpp](https://github.com/ggml-org/llama.cpp) (default),
[Ollama](https://ollama.com), or an [OpenRouter](https://openrouter.ai) key.

```bash
cp .env.example .env      # then edit it — see below
uv sync --extra llamacpp

# start llama-server (downloads the GGUF models automatically)
llama-server -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --port 8080 --embeddings &
llama-server -hf Qwen/Qwen3-0.6B-GGUF:Q8_0 --port 8081 &

uv run rag-mcp            # Ctrl-C to stop
```

No output means it is working — it waits silently for MCP messages on stdin.

Then register it with your AI client: [MCP client setup](docs/guides/mcp-client-setup.md).

### What goes in `.env`

Connection details and secrets. Nothing else.

```bash
CHROMA_PERSIST_DIR=./chroma_db
COLLECTION_NAME=documents
EMBED_MODEL=qwen3-embedding:0.6b
OLLAMA_BASE_URL=http://localhost:11434
# plus any API keys
```

Tuning belongs in `src/rag_mcp/config/defaults.yaml`; per-collection behaviour
belongs in a profile. Putting tuning in `.env` silently overrides your profiles
— see [Configuration](docs/guides/configuration.md) for the precedence rules.

---

## MCP tools

Seven tools your AI can call:

| Tool | What it does |
|---|---|
| `ingest_documents` | Index a file or directory |
| `search_documents` | Search by meaning, with optional reranking, hybrid search and metadata filters |
| `list_indexed_documents` | See what is indexed |
| `list_collections` | See all collections and their sizes |
| `delete_documents` | Remove documents, or drop a collection |
| `get_codebase_map` | Generate a compact map of a codebase: file types, code communities, architectural hubs |
| `change_collection_profile` | Switch a collection between `documents` and `codebase` |

Details: [MCP tools reference](docs/guides/mcp-tools.md).

---

## CLI

The same `rag-mcp` command is both the MCP server and a terminal tool.

| Command | What it does |
|---|---|
| `rag-mcp` | Start the MCP server |
| `rag-mcp ingest <path>` | Index a file or directory |
| `rag-mcp search <query>` | Search from the terminal |
| `rag-mcp list` | List indexed documents |
| `rag-mcp list-collections` | List all collections |
| `rag-mcp watch <dir>` | Auto-ingest new and changed files |
| `rag-mcp delete` | Delete documents or drop a collection |
| `rag-mcp set-profile` | Bind a collection to a profile |
| `rag-mcp benchmark` | Benchmark embedding throughput |

Every flag and example: [CLI reference](docs/guides/cli-reference.md).

---

## Supported files

`.pdf` `.docx` `.pptx` `.txt` `.md` `.html` `.csv`

Source code is handled too — the codebase map and code graph use tree-sitter
parsing across around 16 languages.

---

## Optional extras

**Hybrid search** — combines keyword matching with embedding search. Worth it
for exact identifiers, error codes, product names, citations. On by default in
the `codebase` profile.

```bash
uv run rag-mcp search "What fixes MCP-1138?" --hybrid
```

**Ollama instead of llama.cpp** — simpler model management.

```bash
uv sync                            # no extra needed
ollama pull qwen3-embedding:0.6b
ollama pull qwen3:0.6b
```

```bash
# .env
LOCAL_BACKEND=ollama
EMBED_MODEL=qwen3-embedding:0.6b
```

**OpenRouter for cloud embeddings or LLM** — no local model servers.

```bash
uv sync --extra openrouter
```

```bash
# .env
EMBED_PROVIDER=cloud
CLOUD_BACKEND=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_EMBED_MODEL=text-embedding-3-small
```

Switching embedding provider changes the vector dimension. ChromaDB locks
dimensions per collection, so delete `chroma_db/` and re-ingest.

**Azure Document Intelligence** for complex PDFs (`uv sync --extra azure`).
Opt-in, and falls back to local parsing if unreachable.

Full setup for each: [Providers](docs/guides/providers.md).

---

## Documentation

| Guide | What is in it |
|---|---|
| [Getting started](docs/guides/getting-started.md) | Install, verify, first ingest |
| [Configuration](docs/guides/configuration.md) | Every setting, where it goes, and which one wins |
| [Architecture](docs/guides/architecture.md) | How the pieces fit together |
| [CLI reference](docs/guides/cli-reference.md) | Every command and flag |
| [MCP tools](docs/guides/mcp-tools.md) | Tool parameters in detail |
| [MCP client setup](docs/guides/mcp-client-setup.md) | Claude Desktop, OpenChamber, multi-project |
| [Providers](docs/guides/providers.md) | llama.cpp, Ollama, OpenRouter |
| [Ingestion](docs/guides/ingestion.md) | How chunking and embedding work |
| [Metadata extraction](docs/guides/metadata-extraction.md) | Auto-categorisation and filtering |
| [Reranker](docs/guides/reranker.md) | When reranking helps, and when it does not |
| [Testing](docs/guides/testing.md) | Running the suite, writing tests |
| [Decision records](docs/adr/) | Why things are the way they are |
| [Contributing](CONTRIBUTING.md) | Workflow and conventions |

---

## Version 2.0.0

v2 restructured the codebase into a modular framework and, in doing so, broke
three things. If you are coming from v1:

- **Settings are renamed.** `TOP_K` is now `RETRIEVAL__TOP_K`, `CHUNK_SIZE` is
  `CHUNKING__CHUNK_SIZE`, and so on. The server refuses to start on an old name
  and tells you the replacement rather than silently ignoring it.
- **Old import paths are gone.** `rag_mcp.server`, `rag_mcp.cli`,
  `rag_mcp.ingestion` and the rest now live under `rag_mcp.core.*`,
  `rag_mcp.transports.*` and `rag_mcp.integrations.*`.
- **Custom profile YAML needs converting** to nested blocks.

Your ChromaDB collections, CLI commands and MCP tool signatures are unchanged,
and rolling back is code-only — no data migration either way.

The migration table and the full reasoning are in
[ADR-037](docs/adr/037-architecture-v2-conformance.md).

---

## Licence

[MIT](./LICENSE)
