# Design: CLI Interface & Parallel Ingestion

**Change ID**: `add-cli-and-parallel`

## Architecture Overview

```
                      ┌──────────────────────────┐
                      │     pyproject.toml        │
                      │                           │
                      │  [project.scripts]        │
                      │  rag-mcp = server:main    │  ← MCP stdio (unchanged)
                      │  rag-mcp = cli:app        │  ← NEW: Typer CLI
                      └──────────┬───────────────┘
                                 │
                  ┌──────────────┴──────────────┐
                  │                             │
          ┌───────▼───────┐            ┌───────▼───────┐
          │   server.py   │            │    cli.py     │  ← NEW
          │  (unchanged)  │            │  (Typer app)  │
          └───────┬───────┘            └───────┬───────┘
                  │                             │
                  └──────────┬──────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
      ┌───────▼───────┐ ┌───▼────┐ ┌──────▼───────┐
      │ ingestion.py  │ │config │ │ retrieval.py  │
      │ (refactored)  │ │  .py  │ │ (unchanged)   │
      └───────────────┘ └───────┘ └──────────────┘
```

The key insight: **the CLI is a thin shell around existing functions.** There is no
duplication of ingestion, search, or list logic. `cli.py` imports `ingest_path`,
`search`, and `list_documents` from the same modules that `server.py` uses.

## Decision Records

### DR-001: CLI Framework → Typer

**Context**: Need to add `rag-mcp ingest`, `rag-mcp search`, `rag-mcp list`
commands with proper help text, completion, and error messages.

**Options considered**:
- **argparse** (stdlib, verbose, no completion)
- **click** (mature, decorator-based, zero-deps)
- **typer** (click-based, type-hint-driven, Rich integration, `--install-completion`)
- **fire** (auto-generates, unpredictable error messages)

**Decision**: **Typer**. The project is already fully type-annotated. Typer turns
function signatures directly into CLI definitions. Rich (for progress bars) is
bundled with Typer, so progress reporting comes at zero additional dependency cost.

**Cost**: ~2.5 MB (typer + rich + shellingham). `uv add typer`.

### DR-002: Concurrency Strategy → Increase embed_batch_size + optional file-level parallelism

**Context**: Ollama serialises embedding requests internally regardless of how many
threads send them. The `/api/embed` endpoint supports batched input. The current
`embed_batch_size=10` means ~120 API calls for 1,200 chunks; increasing to 100
drops that to ~12 calls — a ~10× reduction in round-trips.

**Decision**: **Primary optimisation: increase `embed_batch_size` from 10 to 100**.
This is a one-line config change with massive impact. Then, optionally, use
`ThreadPoolExecutor` for file reading and chunking (I/O-bound, ~30% of total time)
with ChromaDB writes serialised behind a lock.

**Why not multiprocessing**: ChromaDB is not process-safe. LlamaIndex's
`IngestionPipeline` with `num_workers` uses `multiprocessing.Pool("spawn")` which
can corrupt ChromaDB's SQLite database and adds pickle overhead for no benefit here.

**Worker default**: 4 (conservative). Configurable via `INGEST_WORKERS` env var
and `--workers N` CLI flag.

### DR-003: ChromaDB Write Pattern → batch-then-write (two-phase)

**Context**: ChromaDB's `PersistentClient` is thread-safe for reads but concurrent
writes can hit SQLite `database is locked` under contention. `upsert()` has a
known data race in hnswlib's repair path.

**Decision**: Two-phase ingestion for parallel mode:

1. **Phase 1 (parallel)**: Read files, split into chunks, compute embeddings.
   Collect all `(ids, embeddings, metadatas, documents)` tuples.
2. **Phase 2 (serial)**: Single `collection.add()` call with all data.

For single-file or single-threaded mode, the existing `VectorStoreIndex(nodes, ...)`
flow is kept as-is. The two-phase approach only triggers when `--workers > 1`.

### DR-004: Progress Reporting → Rich Progress

**Context**: Need to show users what's happening during potentially long ingestions.

**Decision**: **Rich `Progress` context manager**. Typer already pulls in Rich as a
dependency. Rich supports multi-task progress bars with ETA, throughput, and
elapsed/remaining time. Automatically downgrades to plain text in non-TTY contexts
(pipes, CI, non-interactive terminals).

```python
with Progress(
    SpinnerColumn(),
    TextColumn("[bold blue]{task.description}"),
    BarColumn(),
    MofNCompleteColumn(),
    TimeElapsedColumn(),
    TimeRemainingColumn(),
) as progress:
    read_task = progress.add_task("[green]Reading files...", total=len(files))
    embed_task = progress.add_task("[cyan]Embedding chunks...", total=total_chunks)
    # ...
```

### DR-005: Ollama Concurrency Gate → BoundedSemaphore(2)

**Context**: Ollama does not parallelise embedding model inference, but it still
accepts concurrent requests (queuing them internally). Sending too many concurrent
requests can cause memory pressure and timeouts.

**Decision**: Use `threading.BoundedSemaphore(2)` to gate concurrent embedding
API calls. The semaphore acquisition happens at the Ollama API call boundary,
ensuring that at most 2 threads are waiting for or executing embedding requests
at any time. This is adjustable via `EMBED_CONCURRENCY` env var.

### DR-006: Entry Point Naming → single `rag-mcp` command with subcommand detection

**Context**: Need to distinguish between MCP server mode (`rag-mcp` with no args)
and CLI mode (`rag-mcp ingest`, `rag-mcp search`, `rag-mcp list`).

**Decision**: **Single entry point with subcommand detection.** The `main()`
function in `server.py` checks `sys.argv`:

- If `sys.argv == ["rag-mcp"]` (no args) → start MCP server (backward compatible)
- Otherwise → delegate to `cli.app()`

This avoids needing a separate `rag-mcp-cli` entry point and keeps the user
experience simple: one command, two modes.

## Component Design

### New file: `src/rag_mcp/cli.py`

```
cli.py
├── app: typer.Typer          # Top-level Typer application
├── ingest(path, workers, ...) # Ingestion command
├── search(query, top_k, ...) # Search command
└── list()                     # List command
```

Each command wraps the existing functions `ingest_path()`, `search()`, and
`list_documents()`. Progress bars are managed here.

### Modified file: `src/rag_mcp/config.py`

```python
# New config constants
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "100"))  # was hardcoded 10
INGEST_WORKERS = int(os.getenv("INGEST_WORKERS", "4"))
EMBED_CONCURRENCY = int(os.getenv("EMBED_CONCURRENCY", "2"))
```

### Modified file: `src/rag_mcp/ingestion.py`

- Extract `_read_and_chunk_file(path: Path) -> list[Node]` for parallel use
- Add `_ingest_parallel(files: list[Path])` using ThreadPoolExecutor
- Keep `ingest_path()` as the unified entry point — it detects whether to use
  parallel or single-threaded mode
- Add `_write_lock` for ChromaDB serialisation when running in parallel mode

### Unchanged files

- `server.py` — only `main()` gains `sys.argv` check; MCP tool handlers unchanged
- `retrieval.py` — no changes needed
- `reranker.py` — no changes needed
- All tests — should pass without modification

## Data Flow: Parallel Ingestion

```
ingest_path("/path/to/zotero/storage")
  │
  ├── Discover files (recursive, SUPPORTED_EXTENSIONS)
  │
  ├── [PARALLEL PHASE] ThreadPoolExecutor(workers=N)
  │   ├── Worker 1: _read_and_chunk_file(file_1) → list of Node
  │   ├── Worker 2: _read_and_chunk_file(file_2) → list of Node
  │   └── ...
  │       └── All nodes collected into `all_nodes` list
  │
  ├── [SERIAL PHASE] Embedding (LlamaIndex VectorStoreIndex)
  │   └── Settings.embed_model (OllamaEmbedding, batch_size=100)
  │       └── BoundedSemaphore(2) gate per API call
  │
  ├── [SERIAL PHASE] ChromaDB write
  │   └── collection.add(ids, embeddings, metadatas, documents)
  │
  └── Return {"status": "ok", "files_indexed": N, "chunks_created": M}
```

## Error Handling

| Scenario                                    | Behaviour                                                                          |
| ------------------------------------------- | ---------------------------------------------------------------------------------- |
| Path does not exist                         | `click.Abort` with message to stderr, exit code 1                                   |
| Unsupported file extension                  | Skip file, log warning, continue with remaining files                              |
| File read fails (permission, corrupt)       | Skip file, log error, continue                                                     |
| Ollama unreachable                          | Fail fast with clear message: "Is Ollama running on {OLLAMA_BASE_URL}?"            |
| ChromaDB write fails                        | Roll back (delete any partial add within the transaction boundary)                 |
| Ctrl+C during parallel phase                | Signal handler sets shutdown flag; workers finish current file then stop           |
| Ctrl+C during embedding/write               | No partial writes — embeddings are collected before ChromaDB add                   |
| `--workers=0` or negative                   | Clamped to 1 (single-threaded fallback)                                            |
| Non-TTY output (pipe, redirect, CI)         | Progress bars disabled; plain text "Processing file N/M..." output                 |
