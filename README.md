# LlamaIndex RAG MCP Server

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Requires Ollama](https://img.shields.io/badge/requires-Ollama-000000?logo=ollama)](https://ollama.com)

A standalone [MCP](https://modelcontextprotocol.io) server for document retrieval
using LlamaIndex and ChromaDB — powered by **local embeddings via Ollama**.
No API keys, no recurring costs, runs entirely on your machine.

## Tools

| Tool | Description |
|------|-------------|
| `ingest_documents` | Index a file or directory (PDF, DOCX, PPTX, TXT, Markdown, HTML, CSV) |
| `search_documents` | Semantic similarity search with optional reranking and threshold filtering |
| `list_indexed_documents` | Show what's currently in the store |

### `search_documents` parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *(required)* | Natural language search query |
| `top_k` | int | `5` | Maximum number of chunks to return |
| `similarity_threshold` | float | `0.0` | Minimum relevance score (0.0 = no filtering). When `rerank=True`, the threshold is automatically scaled down by 30x because cross-encoder scores occupy a lower range. |
| `rerank` | bool | `false` | Re-score results with cross-encoder for better precision |

---

## Configuration

All configuration is centralised in `src/rag_mcp/config.py` — the single source of
truth for the embedding model, paths, and defaults. Both `ingestion.py` and
`retrieval.py` import from this module so there is no configuration drift.

Environment variables are loaded from a `.env` file (copy from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | ChromaDB on-disk storage path |
| `COLLECTION_NAME` | `documents` | ChromaDB collection name |
| `CHUNK_SIZE` | `512` | Text splitter chunk size (characters) |
| `CHUNK_OVERLAP` | `64` | Chunk overlap (characters) |
| `TOP_K` | `5` | Default number of search results |
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | ONNX reranker model ID |
| `RERANK_ENABLED` | `false` | Default rerank behaviour |
| `SIMILARITY_THRESHOLD` | `0.0` | Minimum score to include a result |

---

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — install once:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **[Ollama](https://ollama.com)** — install and start:
  ```bash
  brew install ollama
  ollama serve &
  ```

---

## Setup

```bash
# 1. Clone / copy this folder
cd llamaindex-rag-mcp

# 2. Pull your embedding model(s) via Ollama
ollama pull nomic-embed-text     # recommended (best balance of speed + quality)
# ollama pull mxbai-embed-large  # optional (higher accuracy, 512-token limit)
# ollama pull all-minilm         # optional (blazing fast, 256-token limit)

# 3. Create .env from the example (already configured for Ollama)
cp .env.example .env
# Optionally edit EMBED_MODEL if you want a different model

# 4. Install Python dependencies
uv sync
```

---

## Test the server

```bash
uv run rag-mcp
```

No output means it's working — it's silently waiting for MCP messages on stdin.
Press Ctrl-C to stop.

To inspect the tools with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run rag-mcp
```

---

## How to ingest documents

Ingestion happens through the MCP tool `ingest_documents` — call it from any
MCP host (OpenChamber, Claude Desktop, etc.) with a file or directory path.

### From OpenChamber / Claude Desktop

Just ask the AI:

> "Index the file ~/Documents/research/paper.pdf"
> "Ingest everything in /path/to/my/docs/"

The AI will call `ingest_documents` automatically.

### From command line (for testing)

Using the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run rag-mcp
```

Then in the Inspector UI, call `ingest_documents` with `{"path": "/your/file.pdf"}`.

Or via a quick Python script:

```python
import subprocess, json

proc = subprocess.Popen(
    ['uv', 'run', 'rag-mcp'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
)

# Send the initialize + tools/call requests (see integration test in source)

proc.terminate()
```

### Supported file formats

`.pdf` `.docx` `.pptx` `.txt` `.md` `.html` `.csv`

For directories, the server recursively finds all supported files.

---

## Choosing an embedding model

Set `EMBED_MODEL` in `.env` to any Ollama embedding model. Here's how they
compare:

| Model | Params | Dims | Context | MTEB | Pull command | Use case |
|-------|--------|------|---------|------|-------------|----------|
| **nomic-embed-text** (recommended) | 137M | 768 | 8,192 | 62.4 | `ollama pull nomic-embed-text` | **Default** — matches OpenAI ada-003 quality, 8K context, free |
| mxbai-embed-large | 334M | 1,024 | 512 | 64.7 | `ollama pull mxbai-embed-large` | Highest accuracy for short chunks (MTEB 64.7) |
| all-minilm | 23M | 384 | 256 | ~58 | `ollama pull all-minilm` | Blazing fast (~5-15ms/embed), tiny footprint |

To switch models:

```bash
# 1. Pull the model if you haven't already
ollama pull mxbai-embed-large

# 2. Update .env
sed -i '' 's/EMBED_MODEL=.*/EMBED_MODEL=mxbai-embed-large/' .env

# 3. Delete the old vector store (dimensions differ between models)
rm -rf chroma_db

# 4. Re-index your documents
```

> **Why delete chroma_db?** Each embedding model produces vectors of a fixed
> dimension (nomic=768, mxbai=1024, minilm=384, etc.). ChromaDB locks the
> dimension at collection creation time. Switching models means starting fresh.

---

## Register in OpenChamber

### Method A -- Via UI (recommended)

1. Open **OpenChamber -> Settings -> MCP**
2. Click **"+ New MCP Server"**
3. Name: `rag-docs`
4. Transport: **Local / stdio**
5. Command (one token per line):
   ```
   uv
   run
   --project
   /absolute/path/to/llamaindex-rag-mcp
   rag-mcp
   ```
6. Environment variables:
   ```
   EMBED_MODEL          = nomic-embed-text
   OLLAMA_BASE_URL      = http://localhost:11434
   CHROMA_PERSIST_DIR   = /absolute/path/to/llamaindex-rag-mcp/chroma_db
   ```
7. Click **Create** — the server should connect immediately (green indicator).

### Method B — Direct JSON edit

Add this block to `~/.opencode/opencode.json` (user-level, available in all
projects) or `<project>/.opencode/opencode.json` (project-scoped):

```json
{
  "mcp": {
    "rag-docs": {
      "type": "local",
      "command": ["uv", "run", "--project", "/absolute/path/to/llamaindex-rag-mcp", "rag-mcp"],
      "environment": {
        "EMBED_MODEL": "nomic-embed-text",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "CHROMA_PERSIST_DIR": "/absolute/path/to/llamaindex-rag-mcp/chroma_db"
      },
      "enabled": true
    }
  }
}
```

Then refresh in **OpenChamber -> Settings -> MCP**.

---

## Multi-project setup

OpenChamber has multiple chat sessions and projects. By default, the MCP server
uses one flat ChromaDB — **every chat and every project searches the same store**.
That works if you want a single knowledge base, but if you want each project to
have its own isolated document store, here's how to set it up.

### Option 1: One shared store (simplest — current default)

The global `~/.opencode/opencode.json` points at one ChromaDB. Anything you
index is visible from any chat, any project. Best for general reference docs
you want everywhere.

### Option 2: Project-scoped stores (recommended for isolation)

Put a per-project `opencode.json` inside the project, each with its own
`CHROMA_PERSIST_DIR`:

```bash
cd ~/Development/PROJECTS/my-project
mkdir -p .opencode rag-store
```

> **No init needed** — just set `CHROMA_PERSIST_DIR` to any path. The first
> `ingest_documents` call creates the directory, database, and collection
> automatically. No CLI setup step.

**`my-project/.opencode/opencode.json`**:
```json
{
  "mcp": {
    "rag-docs": {
      "type": "local",
      "command": [
        "uv", "run", "--project",
        "/absolute/path/to/llamaindex-rag-mcp",
        "rag-mcp"
      ],
      "environment": {
        "EMBED_MODEL": "nomic-embed-text",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "CHROMA_PERSIST_DIR": "/absolute/path/to/my-project/rag-store/chroma_db"
      },
      "enabled": true
    }
  }
}
```

When OpenChamber opens that project, it loads this config and the MCP server
starts pointing at that project's own ChromaDB. The global
`~/.opencode/opencode.json` is still active, but **project-level configs take
precedence** in OpenChamber.

> **Potential naming conflict**: Both the global and project configs use the
> same server name `rag-docs`. If OpenChamber complains about a duplicate, give
> the project-scoped one a unique name like `rag-docs-project-x` (the server
> name just needs to be `^[a-z0-9][a-z0-9_-]*[a-z0-9]$`).

### Option 3: Drop the global, use per-project exclusively

Remove `rag-docs` from `~/.opencode/opencode.json` entirely and only set it up
per project. The MCP server only spins up when you're inside a project with an
`opencode.json`. Cleaner, but you have to configure each project.

### Option 4: Multi-tenant with namespace (code change required)

Add an optional `namespace` parameter to `ingest_documents` that gets stored
in each chunk's ChromaDB metadata. At search time, filter by namespace. This
lets one ChromaDB serve all projects while keeping results isolated. Worth
doing if you have many projects and don't want to duplicate setup.

---

## AI agent quickstart

If you are an AI agent (e.g. Claude, GPT, Cursor, Windsurf) setting this server
up for a user, follow these steps in order:

### 1. Install prerequisites

```bash
# Install uv (Python package manager) if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install and start Ollama if not already running
# macOS:
brew install ollama
# Linux:
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server (background)
ollama serve &

# Pull the embedding model
ollama pull nomic-embed-text
```

### 2. Install the server

```bash
cd /path/to/llamaindex-rag-mcp
cp .env.example .env
uv sync
```

### 3. Verify it works

```bash
uv run rag-mcp
# Should start silently (waiting for MCP on stdin). Ctrl-C to stop.
```

### 4. Enable the reranker (recommended)

The reranker significantly improves search precision. To enable it:

1. Edit `.env` and set:
   ```
   RERANK_ENABLED=true
   ```

2. Trigger the first download by running any search with `rerank=True`:
   > "Search my documents for [topic], use reranking"

   The ~23MB ONNX model downloads from HuggingFace Hub on first use (~7s cold
   start). It caches in `~/.cache/huggingface/` — no repeat downloads.

3. No internet required after the first download. If the download fails, the
   server gracefully falls back to un-reranked results (no crash).

### 5. Register in your MCP host

Add to `~/.opencode/opencode.json` (or equivalent for your MCP client):

```json
{
  "mcp": {
    "rag-docs": {
      "type": "local",
      "command": ["uv", "run", "--project", "/absolute/path/to/llamaindex-rag-mcp", "rag-mcp"],
      "environment": {
        "EMBED_MODEL": "nomic-embed-text",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "CHROMA_PERSIST_DIR": "/absolute/path/to/llamaindex-rag-mcp/chroma_db"
      },
      "enabled": true
    }
  }
}
```

### 6. Ingest documents and search

Once connected, use the MCP tools:

- **Ingest**: `"Index the file /path/to/document.pdf"`
- **Search**: `"Search my documents for information about X"`
- **List**: `"What documents do you have access to?"`

---

## Recommended custom agent prompt

If you create a dedicated agent in OpenChamber -> Settings -> Agents, use this
system prompt:

> You have access to a document RAG system via MCP tools:
> - Use `ingest_documents` when the user asks you to index or load a file/folder.
> - Use `search_documents` **before** answering any question that might be
>   answered by the user's documents. Always search before saying you don't know.
> - Use `list_indexed_documents` when the user asks what documents are available.
> Always cite the source file and page when quoting from retrieved chunks.

---

## Reranker (optional)

The server includes an optional **cross-encoder reranker** that re-scores vector
search results for significantly better retrieval precision. It uses
`cross-encoder/ms-marco-MiniLM-L-6-v2` — a ~23MB quantised ONNX model that runs
locally via **pure ONNX Runtime**. No PyTorch, no `sentence-transformers`, no API
keys needed.

### How it works

Without the reranker, search works like this:

```
query -> embed -> cosine similarity -> return top_k
```

With the reranker enabled:

```
query -> embed -> cosine similarity (top_k * 2) -> cross-encoder re-score -> return top_k
```

The cross-encoder evaluates each (query, document) pair jointly, which is slower
but much more accurate than bi-encoder cosine similarity alone. The vector search
fetches `top_k * 2` candidates so the reranker has a meaningful pool to re-score.

### Threshold auto-scaling

Cross-encoder sigmoid scores occupy a much lower range than cosine similarity.
Valid reranker results can score as low as 0.015, while cosine similarity rarely
goes below 0.3 for relevant matches.

When `rerank=True`, the `similarity_threshold` is **automatically scaled down by
30x** so that a user-supplied value of 0.3 becomes 0.01. Users always supply a
single threshold in cosine-similarity terms; the system handles the conversion
transparently.

This was calibrated from experiment data:

- Strong reranker matches: 0.79-1.0
- Weak but correct matches: 0.015 (Colosseum query)
- Clear noise: < 0.003

### Enabling the reranker

**Per-query** (recommended — call with `rerank=True`):

> "Search for quantum superposition, use reranking"

**Via environment variable** (always on by default):

```bash
# In .env
RERANK_ENABLED=true
```

**Via environment variable** (set a default threshold):

```bash
SIMILARITY_THRESHOLD=0.3
```

### First-run download

The first time you call `search_documents` with `rerank=True`, the model
(~23MB quantised ONNX) downloads from HuggingFace Hub and caches in
`~/.cache/huggingface/`. On macOS ARM64, the quantised
`model_qint8_arm64.onnx` variant is used automatically. Subsequent calls use
the cached model (singleton pattern — loaded once, reused across calls).

### When to use reranking

| Scenario | Recommendation |
|----------|---------------|
| Quick lookups, broad recall | `rerank=False` (default — faster) |
| Precision-critical answers | `rerank=True` — better ranking |
| Filtering noise | `similarity_threshold=0.3` + `rerank=True` |
| Many similar results | `rerank=True` — breaks ties better |

### Fallback behaviour

If the reranker model fails to load (no internet for first download, corrupt
cache, etc.), the server **gracefully falls back** to un-reranked vector search
results. You'll see a warning in stderr logs. The server never crashes due to
reranker issues. The next call will retry loading automatically.

---

## Testing

```bash
# Run all fast tests (no Ollama, no ONNX download, no disk I/O)
uv run pytest -m "not slow" -v

# Run with coverage report
uv run pytest -m "not slow" --cov=rag_mcp --cov-report=term-missing

# Run E2E stdio smoke test (requires `uv run rag-mcp` to work)
uv run pytest -m slow -v

# Run a single test file
uv run pytest tests/test_reranker.py -v
```

The test suite (43 tests, 97% coverage) uses mock embeddings and an in-memory
ChromaDB client so no external services are needed for fast tests.

| File | Tests | Coverage area |
|------|-------|---------------|
| `tests/test_reranker.py` | 23 | Sigmoid, ONNX variant, singleton, fallback, mock inference, model loading |
| `tests/test_ingestion.py` | 4 | Path validation, empty dir, list empty |
| `tests/test_mcp_tools.py` | 5 | Tool discovery, ingest, search, list, param validation |
| `tests/test_retrieval.py` | 11 | Empty store, threshold, rerank flag, threshold scaling (6 tests) |
| `tests/test_e2e_stdio.py` | 1 | JSON-RPC handshake over stdio subprocess |

---

## Verification checklist

- [ ] `ollama ps` shows nomic-embed-text loaded (or whatever model you chose)
- [ ] `uv run rag-mcp` starts without errors and waits on stdin
- [ ] MCP Inspector can discover and call all three tools
- [ ] OpenChamber shows `rag-docs` as **Connected** (green)
- [ ] "What documents do you have access to?" calls `list_indexed_documents`
- [ ] "Please index /path/to/file.pdf" calls `ingest_documents`
- [ ] Question about PDF content calls `search_documents` and cites the source

---

## License

[MIT](./LICENSE)
