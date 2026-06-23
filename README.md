# LlamaIndex RAG MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Requires Ollama](https://img.shields.io/badge/requires-Ollama-000000?logo=ollama)](https://ollama.com)

A local document search server for AI assistants. Point it at your files — PDFs, Word docs, notes, research papers — and your AI can search them by meaning, not just keywords. Everything runs on your machine. No cloud, no API keys, no recurring costs.

**What it is:** An [MCP](https://modelcontextprotocol.io) server that gives AI assistants (Claude, GPT, Cursor, and others) the ability to search your documents using natural language.

**What it isn't:** A chatbot, a cloud service, or a replacement for your file system. It's a search layer — your AI asks it questions, it finds the relevant passages.

---

## MCP Tools

Five tools your AI can call:

| Tool | What it does |
|------|-------------|
| `ingest_documents` | Index a file or directory (PDF, DOCX, PPTX, TXT, Markdown, HTML, CSV) |
| `search_documents` | Semantic search with optional reranking, hybrid BM25 fusion, and metadata filtering |
| `list_indexed_documents` | See what's currently indexed |
| `list_collections` | See all document collections and their sizes |
| `delete_documents` | Remove documents by path, filter, or drop a whole collection |

---

## CLI

The same `rag-mcp` command works as both an MCP server and a terminal tool:

| Command | What it does |
|---------|-------------|
| `rag-mcp` | Start the MCP server |
| `rag-mcp ingest <path>` | Index a file or directory |
| `rag-mcp search <query>` | Search from the terminal (`--hybrid` enables dense+BM25 fusion) |
| `rag-mcp list` | List indexed documents |
| `rag-mcp list-collections` | List all collections |
| `rag-mcp watch <dir>` | Auto-ingest new and changed files |
| `rag-mcp delete` | Delete documents or drop a collection |
| `rag-mcp benchmark` | Benchmark embedding throughput |

---

## Quick install

You need [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com) installed first.

```bash
# Pull the embedding model
ollama pull nomic-embed-text

# Set up the project
cp .env.example .env
uv sync

# Verify it works — Ctrl-C to stop
uv run rag-mcp
```

No output means it's working. It's waiting silently for MCP messages on stdin.

Then register it in your AI client — see [MCP Client Setup](docs/guides/mcp-client-setup.md).

### Optional hybrid retrieval

Hybrid retrieval is opt-in and keeps the dense-only default unchanged. Use it
for rare terms, exact identifiers, citations, error codes, and product names:

```bash
uv run rag-mcp search "What fixes MCP-1138?" --hybrid
```

MCP clients can pass the same option:

```json
{"query": "What fixes MCP-1138?", "hybrid": true, "rerank": true}
```

The v1 sparse backend is in-memory BM25 (`HYBRID_SPARSE_BACKEND=bm25`) fused
with dense results via RRF (`HYBRID_RRF_K=60`). The BM25 index is cached per
collection and rebuilt lazily after ingestion or deletion; its memory footprint
scales with the collection's chunk count.

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

| Guide | What's in it |
|-------|-------------|
| [Getting Started](docs/guides/getting-started.md) | Prerequisites, install, verify, enable reranker |
| [Configuration](docs/guides/configuration.md) | All environment variables and `.env` settings |
| [CLI Reference](docs/guides/cli-reference.md) | Every command, flag, and example |
| [MCP Tools Reference](docs/guides/mcp-tools.md) | Tool parameters in detail |
| [Ingestion Guide](docs/guides/ingestion.md) | How ingestion works, embedding models, chunk sizes |
| [Metadata Extraction](docs/guides/metadata-extraction.md) | Auto-categorisation, keyword rules, filtering |
| [Reranker](docs/guides/reranker.md) | Cross-encoder reranking and threshold scaling |
| [MCP Client Setup](docs/guides/mcp-client-setup.md) | Register in OpenChamber, Claude Desktop, multi-project |
| [Testing](docs/guides/testing.md) | Test suite, coverage, running tests |
| [Architecture](docs/guides/architecture.md) | Why things are built the way they are (plain English) |
| [Architecture Decisions](docs/adr/) | Full ADRs with alternatives and consequences |
| [Contributing](CONTRIBUTING.md) | Workflow, conventions, and how to open a PR |

---

## Licence

[MIT](./LICENSE)
