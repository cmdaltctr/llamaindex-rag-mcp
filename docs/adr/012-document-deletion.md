# ADR-012: Document Deletion

**Date**: 2026-05-20
**Status**: Accepted

## Context

The RAG MCP server was append-only — every document ingested stayed in
ChromaDB permanently. There was no way to remove individual documents,
clean up stale vectors, or drop collections. Re-ingesting a file created
duplicate chunks. The file watcher accumulated orphaned vectors from
deleted files with no cleanup path.

## Decision

### 1. Direct ChromaDB delete API (not LlamaIndex)

Deletion functions call `collection.delete(where=...)` directly on the
raw ChromaDB collection, bypassing LlamaIndex's
`ChromaVectorStore.delete()` / `delete_nodes()`.

**Rationale**: The `file_path` metadata key is always present (set by
`SimpleDirectoryReader`). A single `collection.delete(where={"file_path": file_path})`
is clean, fast, and matches the metadata key pattern already in use.

### 2. Delete-before-read upsert semantics

When `ingest_path()` processes a file, it calls `remove_document()` for
that file path **before** reading and chunking. This ensures re-ingesting
the same file replaces its old chunks rather than appending duplicates.

If reading/chunking fails, the old chunks survive (the file has not been
re-indexed yet). The delete phase runs single-threaded even in the
parallel ingestion path to avoid concurrent ChromaDB access issues.

### 3. One CLI delete subcommand, three modes

A single `rag-mcp delete` subcommand with three mutually-exclusive flags:
`--path`, `--metadata`, `--collection`. `--collection` drops the entire
collection (not just clears it).

`--dry-run` is available on all modes. Only `--collection` requires a
confirmation prompt (it drops the entire collection, which is irreversible).

### 4. One MCP delete_documents tool

A single `delete_documents` MCP tool accepts `path`, `metadata_filter`,
`collection`, and `dry_run` parameters. When `collection` is provided
without `path` or `metadata_filter`, the collection itself is dropped.

### 5. Watcher on_deleted is immediate (no debounce)

The `on_deleted` handler fires immediately — no debouncing. On file
deletion, it cancels any pending ingest timer, clears the hash cache
entry, and calls `remove_document()`. Deletion is idempotent, so
debouncing is unnecessary.

## Consequences

- **Positive**: Users can now remove stale documents, clean up by
  metadata filter, and entirely drop collections.
- **Positive**: The file watcher automatically cleans up after deleted
  files, preventing orphaned vector accumulation.
- **Positive**: Re-ingestion is now upsert semantics — the intuitive
  behaviour. No more duplicate chunks.
- **Breaking**: The only breaking change — re-ingestion changes from
  append to replace. Existing workflows that relied on append semantics
  will need updating.
- **Safety**: Collection drop requires confirmation. Dry-run is
  available on all operations.

## Alternatives Considered

- **LlamaIndex `delete_nodes`**: Required translating Python dicts into
  `MetadataFilters` objects, adding unnecessary abstraction.
- **Content-hash dedup**: Would require checking ChromaDB for existing
  hashes before every insert, doubling the query count. Slower and more
  complex.
- **Separate `delete-collection` subcommand**: Folded into `delete --collection`
  to keep the CLI surface smaller.
- **Clear instead of drop**: Rejected — "delete a collection" naturally
  means removing it entirely. Collections auto-create on first ingest.

## References

- [Design Document](../openspec/changes/add-document-deletion/design.md)
- [Specification](../openspec/changes/add-document-deletion/specs/document-deletion/spec.md)
- [Source: ingestion.py](../src/rag_mcp/ingestion.py) — `remove_document`,
  `remove_by_metadata`, `remove_collection`
- [Source: server.py](../src/rag_mcp/server.py) — `delete_documents` MCP tool
- [Source: cli.py](../src/rag_mcp/cli.py) — `delete` subcommand
- [Source: watcher.py](../src/rag_mcp/watcher.py) — `on_deleted` handler
