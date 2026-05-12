# AGENTS.md — LlamaIndex RAG MCP Server

Project conventions, workflow, and technical decisions for AI agents working on
this codebase.

## Project Overview

A standalone [MCP](https://modelcontextprotocol.io) server for document retrieval
using LlamaIndex and ChromaDB, powered by local embeddings via Ollama. Exposes
three MCP tools (`ingest_documents`, `search_documents`, `list_indexed_documents`)
over stdio transport. No API keys, no recurring costs, runs entirely on-device.

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | **Python 3.11+** | Type-annotated throughout |
| Package manager | **uv** | Not pip, not poetry. Use `uv sync`, `uv add`, `uv run` |
| Build backend | **hatchling** | Declared in `pyproject.toml` |
| MCP framework | **mcp[cli] (FastMCP >=1.0)** | The `@mcp.tool()` decorator pattern |
| Embedding | **llama-index-embeddings-ollama** | Local via Ollama (`nomic-embed-text` default) |
| Vector store | **chromadb** via `llama-index-vector-stores-chroma` | PersistentClient, local disk |
| Document reading | **llama-index-readers-file** | PDF, DOCX, PPTX, TXT, MD, HTML, CSV |
| Text splitting | **llama-index SentenceSplitter** | Configurable chunk_size / chunk_overlap |
| Reranker | **cross-encoder/ms-marco-MiniLM-L-6-v2** via ONNX | ~23 MB cross-encoder, local inference, sigmoid-normalised scores |

## Project Structure

```
rag-mcp/
├── AGENTS.md                    ← This file
├── pyproject.toml               ← Dependencies, scripts, metadata
├── .env.example                 ← Config template (copy to .env)
├── README.md                    ← Setup + usage + OpenChamber registration
├── uv.lock                      ← Locked deps (auto-generated)
├── openspec/                    ← OpenSpec spec-driven development
│   ├── changes/
│   │   └── <change-name>/
│   │       ├── .openspec.yaml
│   │       ├── proposal.md
│   │       ├── design.md
│   │       ├── specs/<capability>/spec.md
│   │       └── tasks.md
│   └── config.yaml
└── src/
    └── rag_mcp/
        ├── __init__.py          ← Package marker + version
        ├── server.py            ← FastMCP instance + tool registration
        ├── ingestion.py         ← Document loading, chunking, ChromaDB indexing
        ├── retrieval.py         ← Semantic search + reranker integration
        └── reranker.py          ← Cross-encoder reranker (ONNX)
```

## Coding Conventions

### Python

- **Type annotations** everywhere — every function signature has types. Use
  `from __future__ import annotations` in modules that need forward references.
- **British English** in comments and documentation (colour, behaviour, optimise).
  Code identifiers can use American English (embed, initialize).
- **Snake_case** for modules, functions, methods, variables.
- **PascalCase** for classes.
- **UPPER_CASE** for module-level constants.
- **Docstrings** on all public functions and classes. Use Google style:
  ```python
  def ingest_path(path: str) -> dict:
      """Index a single file or directory into the RAG vector store.

      Args:
          path: Absolute or relative path to a file or directory.

      Returns:
          Success: {"status": "ok", "files_indexed": N, "chunks_created": M}
          Error:   {"status": "error", "message": "..."}
      """
  ```
- **Max 80–100 characters per line**. Break long lines with parentheses.
- **Deep nesting <= 3 levels**. Use guard clauses and early returns.
- **Small functions** — single responsibility, <40 lines where possible.

### MCP Tools

- Tool names: `snake_case` (e.g. `search_documents`, `ingest_documents`).
- All new parameters must be **optional with sensible defaults** to preserve
  backward compatibility.
- Use **native Python types** for input schemas (str, int, float, bool, list,
  dict). FastMCP auto-generates JSON Schema from these.
- Function docstring becomes the tool description. Make it descriptive enough
  for an LLM to understand when to call the tool.
- Never raise exceptions from tool handlers — always return a dict or list.
  Let FastMCP wrap errors as `TextContent` with `isError`.

### Settings Pattern

Use LlamaIndex's global `Settings` object for shared configuration, set once at
module import time:

```python
from llama_index.core import Settings
from llama_index.embeddings.ollama import OllamaEmbedding

Settings.embed_model = OllamaEmbedding(
    model_name="nomic-embed-text",
    base_url="http://localhost:11434",
    embed_batch_size=10,
)
```

Both `ingestion.py` and `retrieval.py` independently set `Settings.embed_model`
because either may be imported first. Keep them in sync.

## Dependencies

### Adding dependencies

```bash
uv add package-name
```

This updates `pyproject.toml` and `uv.lock`. Commit both.

### Current core dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `mcp[cli]` | >=1.0.0 | MCP server framework |
| `llama-index` | >=0.11.0 | LlamaIndex core |
| `llama-index-vector-stores-chroma` | >=0.2.0 | ChromaDB vector store integration |
| `llama-index-readers-file` | >=0.2.0 | Document loading (PDF, DOCX, etc.) |
| `llama-index-embeddings-ollama` | >=0.2.0 | Local embeddings via Ollama |
| `chromadb` | >=0.5.0 | Vector database |
| `python-dotenv` | >=1.0.0 | `.env` loading |

### Dev dependencies

| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support (`asyncio_mode = "auto"`) |
| `pytest-cov` | Coverage reporting (`--cov=rag_mcp`) |

### Reranker dependencies

The reranker is already included in `pyproject.toml`:

```bash
# Already in pyproject.toml — no action needed
# onnxruntime>=1.17.0,<1.26.0
# transformers>=4.40.0
# huggingface-hub>=0.20.0
```

The reranker uses **pure ONNX Runtime** for inference — no PyTorch,
no `optimum`, no `sentence-transformers`.  The pre-exported ONNX model
is downloaded from HuggingFace Hub on first use and cached locally.
On macOS ARM, the quantised ``model_qint8_arm64.onnx`` variant (~23 MB)
is used automatically.

Note: `onnxruntime>=1.16` on macOS ARM requires no special package —
`onnxruntime-silicon` is a legacy option no longer needed.

## Architecture Decisions

### Why no hybrid search?

Hybrid search (BM25 + vector with RRF fusion) adds complexity, memory cost,
and an extra dependency (`rank-bm25`). The cross-encoder reranker provides
more precision improvement per unit of complexity. If BM25 is needed later,
it's a separate capability.

### Why no query transformation?

Multi-query expansion, HyDE, and query rewriting require an LLM call per query,
adding 2–5s of latency with unpredictable quality. Not worth it for current
use cases.

### Why similarity threshold?

A simple score filter prevents the LLM from receiving low-quality context.
Default is 0.0 (no filtering) for backward compatibility.

### Why the reranker is a singleton

The ONNX model is ~23MB. Loading it once and reusing across calls avoids
repeated I/O and memory allocation. The `CrossEncoderReranker` class uses the
singleton pattern with thread-safe lazy initialisation. If model loading
fails transiently (e.g. network timeout), the next call retries automatically.

### Why `top_k * 2` when reranking?

The reranker needs more candidates than the final `top_k` to have material to
work with. If `top_k=5`, we fetch 10 candidates from vector search, then the
reranker picks the best 5. This gives the reranker a meaningful pool without
blowing up latency.

## What to Avoid

### ❌ Hard no's

- **No API keys** — this project runs entirely on local inference. Never add
  dependencies that require cloud API keys or external services.
- **No PyTorch at runtime** — PyTorch is huge (~1GB). All ML inference uses
  pure ONNX Runtime directly. The reranker downloads pre-exported ONNX models
  from HuggingFace Hub — no PyTorch, `optimum`, or `sentence-transformers`
  required.
- **No hardcoded paths or secrets** — everything configurable via `.env`.
- **No modifying `server.py` to import embedding models directly** — the server
  delegates to `ingestion.py` and `retrieval.py` which own the embedding config.

### ⚠️ Avoid these patterns

- **Tight coupling between ingestion and retrieval** — they share config
  (chunk size, embed model) through env vars and `Settings`, but they should
  be independently importable and testable.
- **Mixing embedding models** — the same model must be used for indexing and
  querying. ChromaDB locks vector dimension at collection creation.
- **Ignoring chunk size tuning** — the default 512/64 is a starting point.
  Document it and encourage testing against real data.
- **Deeply nested if/else chains** — RAG pipelines can get complex. Use guard
  clauses, early returns, and compose functions rather than nesting.
- **Big bang refactors** — follow the OpenSpec pattern: propose, spec, design,
  implement in phases. Each phase ships independently.

### 🔍 Watch for these in reviews

- Unhandled `Exception` in tool handlers — always return a dict
- Missing type annotations on new functions
- Sync functions that do network I/O (should be async or documented as blocking)
- Importing outside the module's responsibility (e.g. vector store logic in server.py)
- Platform-specific code without fallbacks (macOS vs Linux differences)

## Development Workflow

### OpenSpec changes

For any non-trivial change:

1. **Propose**: `/opsx-propose <change-id>` — creates proposal, specs, design, tasks
2. **Implement**: `/opsx-apply` — work through tasks.md
3. **Archive**: `/opsx-archive` — move to archive when done

### Testing

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

The test suite uses:
- **EphemeralClient** patched via `conftest.py` — no `chroma_db/` directory created
- **MockEmbedding** (384-dim) — no Ollama server required
- **Module-level constant patching** — ensures `ingestion.py` and `retrieval.py`
  use the same collection name regardless of import order
- **`@pytest.mark.slow`** — E2E stdio test excluded by default

| File | Tests | Coverage area |
|------|-------|---------------|
| `tests/test_reranker.py` | 16 | Sigmoid, ONNX variant, singleton, fallback, mock inference |
| `tests/test_ingestion.py` | 4 | Path validation, empty dir, list empty |
| `tests/test_mcp_tools.py` | 5 | Tool discovery, ingest, search, list, param validation |
| `tests/test_retrieval.py` | 5 | Empty store, threshold, rerank flag, default search |
| `tests/test_e2e_stdio.py` | 1 | JSON-RPC handshake over stdio subprocess |

**Key caveat**: `conftest.py` monkeypatches both `chromadb.PersistentClient` and
`chromadb.EphemeralClient` to return a shared singleton `EphemeralClient`, AND
monkeypatches the module-level constants (`CHROMA_PERSIST_DIR`, `COLLECTION_NAME`)
in both `rag_mcp.ingestion` and `rag_mcp.retrieval` via `sys.modules`. This
ensures consistent collection naming regardless of when each module is first
imported relative to the `_isolate_env` fixture.

### Before committing

- Run `uv sync` to verify dependencies resolve
- Run `uv run pytest -m "not slow" -v` — all fast tests must pass
- Run `uv run pytest -m "not slow" --cov=rag_mcp` — coverage must stay ≥ 90%
- Update `.env.example` if new config options were added
- Update `README.md` if tool interfaces changed
- Ensure `openspec validate <change-id>` passes if working on an OpenSpec change

## MCP-Specific Notes

### Transport

`mcp.run(transport="stdio")` — the server communicates over stdin/stdout.
All logging must go to stderr (`loguru`, `logging`, or `print(..., file=sys.stderr)`).
Stdout is the MCP protocol channel.

### Tool parameters

Use `Annotated[type, Field(description="...")]` from `pydantic` if you need
richer parameter descriptions than the function signature provides:

```python
from typing import Annotated
from pydantic import Field

@mcp.tool
def search_documents(
    query: Annotated[str, Field(description="Natural language search query")],
    top_k: int = 5,
) -> list[dict]:
    ...
```

### Error responses

Tool handlers return dicts or lists, never throw exceptions:

```python
# Good
def ingest_documents(path: str) -> dict:
    if not Path(path).exists():
        return {"status": "error", "message": f"Path not found: {path}"}
    ...

# Bad — don't do this
def ingest_documents(path: str) -> dict:
    if not Path(path).exists():
        raise FileNotFoundError(path)
    ...
```

## Environment Variables

All config is loaded from `.env` via `python-dotenv`. Reference:

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

## Related Documentation

- [LlamaIndex Docs](https://docs.llamaindex.ai/) — indexing, retrieval, settings
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) — FastMCP reference
- [ChromaDB Docs](https://docs.trychroma.com/) — vector store API
- [Ollama Library](https://ollama.com/library) — embedding models
- [cross-encoder/ms-marco-MiniLM-L-6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L-6-v2) — reranker model
- This project's OpenSpec: `openspec/` directory
