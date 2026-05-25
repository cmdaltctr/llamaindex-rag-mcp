# ADR-007: CLI Interface and Parallel Ingestion

**Date:** 2026-05-15
**Status:** Accepted

> **Superseded note (2026-05-25):** the file-reader worker API described in
> this ADR was later removed because async ingestion now reads files
> sequentially. Use `EMBED_BATCH_SIZE` and `EMBED_CONCURRENCY` for supported
> throughput tuning.
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Git Commits:** `08121d7`, `60e955a`, `b28abe2`, `7857c32`

## Context

The MCP stdio interface works well for AI assistant integration but provides no
way for developers to directly ingest, search, or list documents from the
terminal. Testing the server manually requires the MCP Inspector or writing
Python scripts. Additionally, directory ingestion was sequential — reading and
embedding one file at a time — which was slow for large document collections.

A CLI interface would make the tool usable standalone (without an MCP host) and
parallel file reading would significantly improve ingestion throughput for
directories with many files.

## Decision

Add a **Typer-based CLI** with three subcommands, and implement **parallel
ingestion** using `ThreadPoolExecutor`.

### CLI (`cli.py`)

- Three subcommands: `rag-mcp ingest`, `rag-mcp search`, `rag-mcp list`
- Backward compatible: no arguments starts the MCP stdio server
- `--json` flag for machine-readable output (scripting-friendly)
- Rich-powered progress bars in TTY, plain text in non-TTY/CI
- Graceful SIGINT handling: first Ctrl+C finishes current file, second forces quit
- All output to **stderr** (`Console(stderr=True)`) — stdout reserved for MCP

### Parallel Ingestion (`ingestion.py`)

- **Two-phase pattern**: Phase 1 reads/chunks files concurrently (ThreadPoolExecutor);
  Phase 2 embeds and writes to ChromaDB serially (behind a write lock)
- `BoundedSemaphore` throttles concurrent Ollama embedding calls
- Per-file error isolation: one failed file does not abort the entire batch
- Historically configurable via file-reader workers; current supported
  throughput controls are `EMBED_BATCH_SIZE` and `EMBED_CONCURRENCY`.

## Consequences

### Positive
- Developers can ingest, search, and list from the terminal without an MCP host
- Parallel reading provides significant throughput improvement for directories
- Rich progress bars give clear visual feedback during ingestion
- `--json` mode enables shell scripting and CI integration
- Graceful SIGINT prevents data corruption during interrupted ingestion
- Two-phase pattern avoids race conditions with ChromaDB writes

### Negative
- `cli.py` is the largest module (~440 lines); some complexity in progress
  reporting and signal handling
- Parallel ingestion adds threading primitives (`_write_lock`, `_embed_semaphore`,
  `_shutdown_requested`) that must be tested for concurrency correctness
- The `ThreadPoolExecutor` approach only parallelises file I/O, not embedding —
  embedding remains serial due to ChromaDB's write constraints

### Neutral
- New config variables: `EMBED_BATCH_SIZE`, `EMBED_CONCURRENCY`
- Shell completion available via `rag-mcp --install-completion`

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Click** | Typer provides type annotations and auto-generated help; Click is more verbose |
| **argparse** | No Rich integration, more boilerplate for subcommands |
| **Multiprocessing (not threading)** | ChromaDB's Python client is not fork-safe; GIL is not a bottleneck for I/O |
| **Async file reading** | File I/O is CPU-bound (parsing PDFs/DOCX); threads are more appropriate |
| **Separate CLI tool** | Duplicating entry points and argument parsing; confusing UX |

## References

- `src/rag_mcp/cli.py` — Typer CLI with ingest, search, list subcommands
- `src/rag_mcp/ingestion.py` — `_ingest_parallel()`, `_embed_and_write()`, threading primitives
- `openspec/changes/add-cli-and-parallel/` — OpenSpec proposal and design for this feature
- `tests/test_cli.py` — 61 test methods across 11 test classes
