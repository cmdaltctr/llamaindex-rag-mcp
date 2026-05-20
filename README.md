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
| `ingest_documents` | Index a file or directory (PDF, DOCX, PPTX, TXT, Markdown, HTML, CSV). Optionally specify a target collection. |
| `search_documents` | Semantic similarity search with optional reranking, threshold filtering, collection scoping, and metadata filtering |
| `list_indexed_documents` | Show what's currently indexed. Optionally scope to a specific collection. |
| `delete_documents` | Remove documents by file path, metadata filter, or drop an entire collection |

### `search_documents` parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *(required)* | Natural language search query |
| `top_k` | int | `5` | Maximum number of chunks to return |
| `similarity_threshold` | float | `0.0` | Minimum relevance score (0.0 = no filtering). When `rerank=True`, the threshold is automatically scaled down by 30x because cross-encoder scores occupy a lower range. |
| `rerank` | bool | `false` | Re-score results with cross-encoder for better precision |
| `collection` | string | `"documents"` | ChromaDB collection to search (optional — scopes results to a single collection) |
| `metadata_filter` | dict | `null` | Optional ChromaDB `where` clause to filter results by metadata fields, e.g. `{"category": "AI"}`. Applied server-side — only matching chunks are fetched. |

### `ingest_documents` parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *(required)* | Path to a file or directory to ingest |
| `collection` | string | `"documents"` | ChromaDB collection to store documents in |

### `list_indexed_documents` parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `collection` | string | `"documents"` | ChromaDB collection to list documents from |

### `list_collections` parameters

No parameters. Returns a list of `{"name": str, "document_count": int, "chunk_count": int}`.

### `delete_documents` parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | `null` | Source file path whose chunks to delete |
| `metadata_filter` | dict | `null` | ChromaDB `where` clause to match chunks (e.g. `{"category": "uncategorised"}`) |
| `collection` | string | `"documents"` | ChromaDB collection to operate on. When provided without `path` or `metadata_filter`, the entire collection is dropped. |
| `dry_run` | bool | `false` | If `true`, preview what would be deleted without modifying ChromaDB |

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
| `EMBED_BATCH_SIZE` | `100` | Embedding batch size per Ollama API call |
| `INGEST_WORKERS` | `4` | Parallel file readers for directory ingestion |
| `EMBED_CONCURRENCY` | `2` | Max concurrent Ollama embedding requests |
| `TOP_K` | `5` | Default number of search results |
| `RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | ONNX reranker model ID |
| `RERANK_ENABLED` | `false` | Default rerank behaviour |
| `SIMILARITY_THRESHOLD` | `0.0` | Minimum score to include a result |
| `METADATA_EXTRACTION_MODE` | `keyword` | How document metadata is extracted: `disabled`, `keyword`, `ollama`, or `llamaindex` |
| `METADATA_KEYWORD_RULES` | *(uses built-in)* | Optional JSON string of `[{"pattern": "regex", "category": "name"}, ...]` overriding default keyword rules |
| `OLLAMA_CLASSIFY_MODEL` | `qwen3:0.6b` | Chat model for Ollama-based classification (only when `METADATA_EXTRACTION_MODE=ollama`) |

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

## CLI usage

The `rag-mcp` command doubles as a CLI tool. With no arguments it starts the
MCP stdio server (backward compatible). With subcommands it operates directly
from the terminal.

### All CLI subcommands

| Command | Shortcut | Description |
|---------|----------|-------------|
| `rag-mcp` | — | Start the MCP stdio server (no arguments) |
| `rag-mcp ingest <path>` | — | Index a file or directory into the vector store |
| `rag-mcp search <query>` | — | Search indexed documents for semantically relevant chunks |
| `rag-mcp list` | — | Show indexed documents with chunk counts |
| `rag-mcp list-collections` | — | Show all ChromaDB collections with document and chunk counts |
| `rag-mcp watch <dir>` | — | Watch a directory for new/changed documents and auto-ingest them |
| `rag-mcp delete` | — | Delete documents by file path, metadata filter, or drop a collection |
| `rag-mcp benchmark` | — | Benchmark embedding throughput (no ChromaDB writes) |
| `rag-mcp --version` | — | Show version |
| `rag-mcp --help` | — | Show help |
| `rag-mcp --install-completion` | — | Install shell completion |

### Common flags across subcommands

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--collection`, `-c` | `ingest`, `search`, `list`, `watch`, `delete` | ChromaDB collection name (default `"documents"`) |
| `--json` | `ingest`, `search`, `list`, `list-collections`, `delete` | Output results as JSON |
| `--workers`, `-w` | `ingest` | Number of parallel file readers |
| `--chunk-size` | `ingest` | Override chunk size |
| `--chunk-overlap` | `ingest` | Override chunk overlap |
| `--top-k`, `-k` | `search` | Max results to return |
| `--threshold`, `-t` | `search` | Minimum similarity score |
| `--rerank` | `search` | Re-score with cross-encoder reranker |
| `--debounce`, `-d` | `watch` | Debounce interval in seconds |
| `--verbose`, `-v` | `watch` | Enable DEBUG-level logging |
| `--report`, `-r` | `ingest` | Write ingestion report to a file |
| `--dry-run` | `delete` | Preview deletion without modifying ChromaDB |
| `--yes`, `-y` | `delete` | Skip confirmation prompt for collection deletion |

### Ingest a file or directory

```bash
# Index a single file
rag-mcp ingest ~/Documents/research/paper.pdf

# Index an entire directory (parallel by default, 4 workers)
rag-mcp ingest /path/to/zotero/storage/

# Ingest into a named collection (creates it automatically)
rag-mcp ingest /path/to/research/papers/ --collection research

# Customise parallelism and chunking
rag-mcp ingest /path/to/docs/ --workers 8 --chunk-size 1024 --chunk-overlap 128

# Machine-readable output for scripts
rag-mcp ingest /path/to/docs/ --json
```

Progress bars appear automatically in TTY terminals (Rich). In non-TTY
contexts (pipes, CI) plain text is emitted to stderr. Press Ctrl+C once for
graceful shutdown (finishes current file, skips the rest); press again to
force quit.

### Search indexed documents

```bash
# Basic semantic search
rag-mcp search "quantum entanglement"

# Search a specific collection only
rag-mcp search "transformer architecture" --collection research

# With reranking and threshold
rag-mcp search "machine learning" --rerank --threshold 0.3 --top-k 10

# Search with metadata filter (requires metadata extraction — MCP tool only)
# CLI search does not support --metadata-filter; use the search_documents MCP tool
# for metadata-filtered queries via the MCP client.

# JSON output for scripting
rag-mcp search "climate change" --json
```

### List indexed documents

```bash
# Human-readable table
rag-mcp list

# List documents from a specific collection
rag-mcp list --collection research

# JSON output
rag-mcp list --json
```

### List available collections

```bash
# Show all ChromaDB collections with document and chunk counts
rag-mcp list-collections

# JSON output
rag-mcp list-collections --json
```

### Delete documents

```bash
# Delete all chunks for a specific file
rag-mcp delete --path /path/to/file.pdf

# Delete chunks matching a metadata filter
rag-mcp delete --metadata '{"category":"uncategorised"}'

# Delete from a specific collection (by path)
rag-mcp delete --path /path/to/file.pdf --collection research

# Preview what would be deleted (dry-run)
rag-mcp delete --path /path/to/file.pdf --dry-run

# Drop an entire collection (requires confirmation)
rag-mcp delete --collection research

# Drop a collection without confirmation
rag-mcp delete --collection research --yes

# JSON output for scripting
rag-mcp delete --path /path/to/file.pdf --json

# Dry-run with JSON
rag-mcp delete --collection research --dry-run --json
```

The three modes (`--path`, `--metadata`, `--collection`) are mutually exclusive.
Only `--collection` requires a confirmation prompt (it permanently drops the
collection). Pass `--yes` or `--dry-run` to skip the prompt.

### Watch a directory for auto-ingestion

```bash
# Watch Zotero storage for new/changed papers
rag-mcp watch ~/Zotero/storage/

# Watch and route into a specific collection
rag-mcp watch ~/Zotero/storage/ --collection research

# Custom debounce interval (default: 2 seconds)
rag-mcp watch /path/to/docs/ --debounce 5

# Verbose mode (DEBUG-level logging)
rag-mcp watch /path/to/docs/ --verbose
```

The watcher monitors a directory tree for supported document files and
auto-ingests them as they appear or change. It includes:

- **SHA-256 content-hash deduplication** — unchanged files are skipped
- **Per-file debouncing** — rapid writes (e.g. streaming downloads) are
  coalesced into a single ingestion
- **Ingestion throttling** — at most 2 concurrent ingestions to avoid
  overwhelming the embedding pipeline
- **Consecutive-error detection** — logs a CRITICAL alert after 5
  consecutive connection failures (Ollama unreachable)
- **Graceful shutdown** — Ctrl+C cancels pending work and waits for
  in-flight ingestion to complete

> **Cold-start gap:** The watcher only detects changes after it starts.
> Run `rag-mcp ingest <path>` before starting the watcher to catch up
> on existing files.

> **Concurrency warning:** Do NOT run `rag-mcp watch` and
> `rag-mcp ingest` (or the MCP server) simultaneously on the same
> ChromaDB — two processes do not share the internal write lock.

### Auto-categorisation and metadata extraction

During ingestion, the server can automatically categorise documents and store
the result as ChromaDB metadata on every chunk. This happens once per file
(before chunking) so it has minimal overhead.

The categorisation mode is controlled by `METADATA_EXTRACTION_MODE` in `.env`:

| Mode | What happens | Dependencies | Speed |
|------|-------------|-------------|-------|
| `keyword` (default) | Regex pattern matching against built-in rules covering AI, Philosophy, Biology, Marketing, and Programming | None (`re` from stdlib) | Instant |
| `disabled` | No metadata extraction | None | N/A |
| `ollama` | Chat model classification via local Ollama (uses `OLLAMA_CLASSIFY_MODEL`, default `qwen3:0.6b`) | Ollama running with a chat model | ~2s per file |
| `llamaindex` | Stubbed for future LlamaIndex MetadataExtractor integration — falls back to keyword mode | None (stubbed) | Same as keyword |

**Default keyword rules** (built-in):

| Category | Keywords matched (case-insensitive regex) |
|----------|------------------------------------------|
| AI | `attention`, `transformer`, `token`, `embedding`, `llm`, `rag`, `neural`, `deep learning` |
| Philosophy | `mantiq`, `logic`, `reasoning`, `ontology`, `epistemology`, `ghazali`, `usul` |
| Biology | `crispr`, `genome`, `protein`, `cell`, `biology`, `cancer`, `gene` |
| Marketing | `marketing`, `seo`, `campaign`, `brand`, `pricing`, `funnel`, `conversion` |
| Programming | `javascript`, `python`, `rust`, `api`, `frontend`, `backend`, `compiler` |

If no keywords match, the category is `"uncategorised"`. You can override the
rules entirely by setting `METADATA_KEYWORD_RULES` in `.env` to a JSON string:

```bash
# In .env — custom rules for motorsport and sport content
METADATA_KEYWORD_RULES='[{"pattern": "f1|grand.?prix|motorsport", "category": "Motorsport"}, {"pattern": "football|goal|stadium", "category": "Sport"}]'
```

To filter search results by category, use the `metadata_filter` parameter on
the `search_documents` MCP tool:

```json
{
  "query": "deep learning architectures",
  "collection": "research",
  "metadata_filter": {"category": "AI"}
}
```

The filter is applied **server-side** via ChromaDB's native `where` clause —
only matching chunks leave the vector store. This is more efficient than
fetching everything and filtering client-side.

### Shell completion

```bash
rag-mcp --install-completion   # Install for current shell
rag-mcp --show-completion      # Show completion script
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

### Option 4: Multi-tenant with ChromaDB collections (built-in)

The server supports **named collections** in ChromaDB. You can ingest different
projects into different collections within the same ChromaDB, and search each
collection independently. This avoids duplicating the `chroma_db` directory or
environment config per project.

```bash
# Ingest project-specific content into named collections
rag-mcp ingest /path/to/project-a/docs/ --collection project-a
rag-mcp ingest /path/to/project-b/docs/ --collection project-b

# Search only the relevant collection
rag-mcp search "quantum computing" --collection project-a

# List all collections
rag-mcp list-collections
```

All MCP tools accept an optional `collection` parameter. The new `list_collections`
tool shows what collections are available and how many documents are in each.

> **No setup required**: Collections are created automatically on first ingest.
> They share the same embedding model from `config.py`, so vector dimensions are
> always consistent. Every new collection adds a new table inside the same SQLite
> database — no need to manage multiple directories or environment configs.

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
- **Collections**: `"What collections are available?"`
- **Delete**: `"Delete the chunks for /path/to/file.pdf"`
- **Drop collection**: `"Drop the collection named research"`

---

## Recommended custom agent prompt

If you create a dedicated agent in OpenChamber -> Settings -> Agents, use this
system prompt:

> You have access to a document RAG system via MCP tools:
> - Use `ingest_documents` when the user asks you to index or load a file/folder.
>   You can specify a `collection` to isolate content (defaults to "documents").
> - Use `search_documents` **before** answering any question that might be
>   answered by the user's documents. Always search before saying you don't know.
>   Scope to a specific `collection` when relevant. Use `metadata_filter` to
>   filter by auto-detected categories (e.g. `{"category": "AI"}`).
> - Use `list_indexed_documents` when the user asks what documents are available
>   in a specific collection.
> - Use `list_collections` to show all available collections and their sizes.
> - Use `delete_documents` to remove documents by file path, by metadata filter,
>   or to drop an entire collection. Always confirm before dropping a collection.
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

The test suite (263 tests — 261 fast, 2 slow) uses mock embeddings and an in-memory
ChromaDB client so no external services are needed for fast tests.

| File | Tests | Coverage area |
|------|-------|---------------|
| `tests/test_watcher.py` | 39 | File watcher: debounce, hash dedup, throttling, shutdown, error handling, on_deleted |
| `tests/test_reranker.py` | 23 | Sigmoid, ONNX variant, singleton, fallback, mock inference, model loading |
| `tests/test_cli.py` | 93 | CLI validation, formatting, edge cases, delete subcommand |
| `tests/test_metadata_extractor.py` | 13 | Keyword, disabled, custom rules, llamaindex stub, unknown mode fallback |
| `tests/test_ingestion.py` | 20 | Path validation, empty dir, list empty, collection routing, metadata attachment, delete functions, upsert |
| `tests/test_retrieval.py` | 17 | Empty store, threshold, rerank flag, threshold scaling, collection search, metadata filter, list collections |
| `tests/test_mcp_tools.py` | 19 | Tool discovery, ingest, search, list, list_collections, collection params, backward compat, delete_documents |
| `tests/test_signal_handling.py` | 13 | SIGINT, shutdown flag, workers clamping, lock recheck |
| `tests/test_ingestion_parallel.py` | 21 | Concurrent ingestion, all-or-nothing semantics |
| `tests/test_e2e_stdio.py` | 1 | JSON-RPC handshake over stdio subprocess |

---

## Verification checklist

- [ ] `ollama ps` shows nomic-embed-text loaded (or whatever model you chose)
- [ ] `uv run rag-mcp` starts without errors and waits on stdin
- [ ] MCP Inspector can discover and call all five tools
- [ ] OpenChamber shows `rag-docs` as **Connected** (green)
- [ ] "What documents do you have access to?" calls `list_indexed_documents`
- [ ] "What collections are available?" calls `list_collections`
- [ ] "Please index /path/to/file.pdf into the research collection" calls `ingest_documents` with `collection`
- [ ] Question about PDF content calls `search_documents` and cites the source
- [ ] "Delete the chunks for /path/to/file.pdf" calls `delete_documents` with `path`
- [ ] "Drop the collection research" calls `delete_documents` with `collection`
- [ ] `rag-mcp delete --dry-run --collection research` previews without deleting
- [ ] `rag-mcp delete --collection research --yes` drops without confirmation

---

## License

[MIT](./LICENSE)
