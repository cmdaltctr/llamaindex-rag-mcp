# Proposal: CLI Interface & Parallel Ingestion

**Change ID**: `add-cli-and-parallel`
**Status**: in_progress — implementation complete, automated tests in progress
**Created**: 2026-05-18
**Last updated**: 2026-05-18 (testing plan added)

## Summary

Add a command-line interface (`rag-mcp ingest`, `rag-mcp search`, `rag-mcp list`)
and optimise ingestion throughput by increasing the Ollama embedding batch size
and adding concurrent file processing. The MCP stdio server remains unchanged
and fully backward-compatible.

## Motivation

### Current pain points

1. **No CLI**. The only way to interact with the RAG store is through an MCP
   client (Claude Desktop, Cursor, etc.). This means:
   - You cannot batch-ingest a folder of documents from a terminal
   - You cannot search the RAG store without going through an AI agent
   - You cannot list what's in the store without a tool call
   - Large ingestions that exceed the MCP client timeout (~60s) fail silently

2. **Linear, slow ingestion**. `ingest_path()` processes files one at a time
   with `embed_batch_size=10`. A typical Zotero library of 60 research papers
   (~1,200 chunks) requires hundreds of sequential Ollama API calls. While
   Ollama serialises embedding requests internally, the batching within each
   call is currently under-optimised.

3. **No progress feedback**. There is no way to know how far along an ingestion
   is, whether it's stalled, or how long it will take. The MCP client just
   waits until timeout or completion.

### Who benefits

- **Developers** who want to pre-seed the RAG store before connecting an MCP
  client
- **Researchers** with large document collections (Zotero libraries,
  paper repositories)
- **CI/CD pipelines** that need to verify the RAG store is populated
- **Anyone** troubleshooting ingestion issues without the indirection of
  an MCP client

## Scope

### In scope

| Capability                   | Description                                                                   |
| ---------------------------- | ----------------------------------------------------------------------------- |
| CLI entry point              | `rag-mcp ingest <path>`, `rag-mcp search <query>`, `rag-mcp list`             |
| `embed_batch_size` increase  | Raise from 10 to 100, configurable via `EMBED_BATCH_SIZE` env var              |
| File-level parallel reading  | Use `ThreadPoolExecutor` to read and chunk multiple files concurrently         |
| Progress reporting           | Rich-powered progress bars showing files processed, chunks embedded, and ETA  |
| ChromaDB write safety        | Serialise vector store writes behind a lock or batch-then-write               |
| Ollama concurrency gate      | BoundedSemaphore to prevent overwhelming Ollama with parallel embedding calls |
| Worker configuration         | `--workers N` CLI flag and `INGEST_WORKERS` env var                            |
| Graceful SIGINT handling     | Clean shutdown on Ctrl+C, no partial state left in ChromaDB                   |
| Path validation hardening    | Resolve relative paths, deny traversal attempts, verify file existence         |
| ANSI-safe progress output    | Detect non-TTY contexts, downgrade to plain text                               |

### Out of scope

| What                                          | Why                                                                          |
| --------------------------------------------- | ---------------------------------------------------------------------------- |
| Hybrid search (BM25 + vector)                 | Separate capability — adds complexity without proportional gain              |
| MCP server changes to async transport         | The MCP transport remains stdio/sync; CLI is a separate entry point          |
| Multi-process ingestion                       | ChromaDB is not process-safe; threading is sufficient                        |
| Incremental re-indexing (change detection)    | Separate feature — would require file modification tracking                  |
| Collection/Database namespacing               | Separate feature — current single-collection is fine for personal use        |
| Web UI or REST API                            | Out of scope for a local-only MCP server                                     |
| PyTorch or sentence-transformers dependencies | Hard constraint — project must remain PyTorch-free                           |

## Success Criteria

1. `uv run rag-mcp ingest /path/to/zotero/storage` completes for 60+ PDFs
   without MCP timeout
2. Ingestion with 60 files completes at least 3× faster than the current
   sequential approach
3. Progress bars are displayed during ingestion and search
4. `uv run rag-mcp search "query"` returns results matching the
   `search_documents` MCP tool
5. `uv run rag-mcp list` shows indexed documents with chunk counts
6. Ctrl+C during ingestion leaves ChromaDB in a consistent state
7. All existing MCP tool interfaces remain unchanged
8. All existing tests pass without modification
9. New command-line entry point has test coverage
10. `--help` output is clear and discoverable
11. CLI integration tests cover all three commands (`ingest`, `search`, `list`) via `CliRunner`
12. JSON output mode is tested on all commands
13. Progress reporting (Rich + plain-text) has automated coverage
14. Concurrent write lock and semaphore throttling are tested with actual threads
15. Path resolution (`expanduser`, `resolve`) has test coverage
16. SIGINT handler logic is tested (shutdown flag, exit code 130, interrupt message)
17. `_sanitise_display_name` has isolated unit tests

## Artifacts

| Document | Purpose |
|----------|---------|
| `proposal.md` | This document — motivation, scope, success criteria |
| `design.md` | Architecture decisions, component design, data flow |
| `risks.md` | Security assessment with 10 findings, mitigations, and dependency audit |
| `testing.plan.md` | Comprehensive test gap analysis, test design, and implementation plan |
| `tasks.md` | Phased implementation checklist (Phases 1–8) |
| `specs/cli/spec.md` | CLI capability requirements (SHALL/MUST with scenarios) |
| `specs/parallel-ingestion/spec.md` | Parallel ingestion capability requirements |

## Risks

| Risk                                                                      | Severity | Mitigation                                                                           |
| ------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------ |
| Concurrent ChromaDB writes cause SQLite lock contention or corruption       | HIGH     | Serialise all writes with `threading.Lock`; batch-then-write approach                |
| Parallel embedding calls overwhelm Ollama                                 | HIGH     | `BoundedSemaphore(2)` gate; configurable `--workers` with conservative default (4)   |
| Large ingestion exceeds MCP client timeout (if called via MCP)            | MEDIUM   | Document timeout workaround; CLI bypasses the timeout entirely                       |
| CTRL+C during ingestion leaves partial chunks                             | MEDIUM   | Signal handler; atomic write-phase approach (collect → embed → single ChromaDB add)  |
| Typer/Rich dependency adds ~2.5 MB                                        | LOW      | Typer is lightweight; Rich is already bundled with Typer                             |
| ChromaDB persist directory path confusion                                 | LOW      | Print the effective `CHROMA_PERSIST_DIR` on startup and in `--help`                  |
