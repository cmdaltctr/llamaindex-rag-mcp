## Context

The RAG MCP server currently has zero deletion capabilities. Every document ingested stays in ChromaDB permanently. The system is append-only by design: `ingestion.py` has `ingest_path()` (write), `retrieval.py` has `search()` and `list_collections()` (read), but nothing for removal.

ChromaDB already supports deletion natively:
- `collection.delete(ids=[...], where={...}, where_document={...})` — delete individual chunks
- `client.delete_collection(name)` — drop an entire collection

Both APIs are accessible from the existing codebase — the `collection` object obtained from `_get_chroma_collection()` is a raw `chromadb.Collection` with full `.delete()` capabilities. No new dependencies, no LlamaIndex abstraction needed.

Key constraints:
- **Zero new Python dependencies** — use ChromaDB's existing `delete()` API
- **Backward compatible** — all existing commands and tools must keep working unchanged (except re-ingestion, which becomes upsert)
- **British English** — all docs, comments, log messages
- **Safety first** — `dry_run` parameter and CLI confirmation prompt for collection drop

## Goals / Non-Goals

**Goals:**
- Delete all chunks for a specific source file (`remove_document`)
- Delete chunks matching an arbitrary metadata filter (`remove_by_metadata`)
- Drop (delete) an entire ChromaDB collection (`remove_collection`)
- Make re-ingestion automatically replace old chunks (upsert semantics)
- Expose all deletion operations via a single `delete_documents` MCP tool and a single `delete` CLI subcommand
- Make the watcher auto-remove vectors when files are deleted from a watched directory

**Non-Goals:**
- Clear a collection without dropping it (drop it and re-ingest — collections auto-create on first ingest)
- Delete individual chunks by ChromaDB ID (too granular — not a common user need)
- Undo/restore of deleted data (irreversible — safety is at the interface level)
- Batch delete by directory (could be built on top of `remove_document` in v2)
- Separate `delete-collection` CLI subcommand or `delete_collection` MCP tool (folded into `delete --collection` and `delete_documents` with only the `collection` parameter)

## Decisions

### 1. Delete API: direct ChromaDB, not LlamaIndex

**Choice**: Call `collection.delete(where={"file_path": file_path})` directly on the raw ChromaDB collection, bypassing LlamaIndex's `ChromaVectorStore.delete()` / `delete_nodes()`.

**Alternatives considered**:
- *LlamaIndex's `ChromaVectorStore.delete(ref_doc_id=...)`*: Works but requires filtering by `ref_doc_id` (which equals `file_path` due to `filename_as_id=True`). However, the metadata key `file_path` is more intuitive and already used by `list_documents()` and `search()` for source attribution. Direct ChromaDB is also simpler — one line vs setting up a `VectorStoreIndex` first.
- *LlamaIndex's `ChromaVectorStore.delete_nodes(filters=[...])`*: Requires translating Python dicts into LlamaIndex `MetadataFilters` objects, adding unnecessary abstraction.

**Rationale**: The `file_path` key is always present (set by `SimpleDirectoryReader`). A single `collection.delete(where={"file_path": file_path})` is clean, fast, and matches the metadata key pattern already in use.

### 2. Re-ingestion upsert: delete-before-embed

**Choice**: In `ingest_path()`, call `remove_document()` for each file **before** chunking and embedding. This gives replace-on-reingest semantics automatically — no flag needed.

```python
# In ingest_path(), before reading/chunking each file:
for file_path in files_to_index:
    _remove_document(str(file_path), collection_name=collection_name)
```

**Alternatives considered**:
- *`--replace` flag on ingest*: More explicit but adds friction. Users would need to remember the flag. The default (append) creates silent duplicates, which is worse UX than auto-replace.
- *Dedup by content hash before insert*: Would require checking ChromaDB for existing hashes before every insert, doubling the ChromaDB queries. Slower and more complex.

**Rationale**: If you re-ingest a file, you almost certainly want the new chunks to replace the old ones — not create duplicates. Making this automatic is the right default.

### 3. CLI design: one `delete` subcommand, three flags

**Choice**: A single `rag-mcp delete` subcommand with three mutually-exclusive flags. `--collection` drops the entire collection (not just clears it). No separate `delete-collection` subcommand.

```
rag-mcp delete --path /file.pdf                          → delete chunks for a file
rag-mcp delete --path /file.pdf --collection research    → delete by file in specific collection
rag-mcp delete --metadata '{"category":"uncategorised"}' → delete chunks matching filter
rag-mcp delete --collection research                     → DROP the entire collection
```

**Alternatives considered**:
- *Separate `delete-collection` subcommand*: Would add a second subcommand for what is conceptually one operation. Folding it into `delete --collection` keeps the CLI surface smaller.
- *`--collection` meaning CLEAR instead of DROP*: Rejected — "delete a collection" naturally means dropping it, not just emptying it. If the collection is empty, you might as well drop it and re-create on next ingest. Collections auto-create, so there's no benefit to keeping an empty shell around.

**Rationale**: One subcommand, three modes, clear semantics. `--collection` drops because that's what "delete collection" means to users.

### 4. Safety: dry_run + collection-drop confirmation

**Choice**: `--dry-run` flag available on all delete operations. Only `--collection` (collection drop) requires CLI confirmation — chunk-level deletions (`--path`, `--metadata`) do not.

```bash
rag-mcp delete --path /file.pdf --dry-run
# → "Would delete 12 chunks from 1 source file"

rag-mcp delete --collection research
# → "Delete entire collection 'research'? This cannot be undone. [y/N]: "

rag-mcp delete --collection research --yes
# → executes immediately, no prompt
```

**Rationale**: Collection drop is a larger, more destructive operation than deleting a file's chunks. A file-level delete is reversible (re-ingest the file). A collection drop is not (the collection metadata, schema, and all content are gone forever). Different safety thresholds.

### 5. Re-ingestion timing: delete before reading

**Choice**: Call `remove_document()` before `SimpleDirectoryReader.load_data()` — i.e., before the file is read and chunked.

**Alternatives considered**:
- *Delete after chunking, before embedding*: If reading/chunking fails, the old chunks survive — good. But requires holding both old and new nodes in memory simultaneously, doubling memory for large files.
- *Delete after embedding*: If embedding fails, the old chunks were already deleted — bad.

**Rationale**: Delete before reading. If reading fails, the old chunks survive (the file hasn't been re-indexed yet). If the file is gone, `remove_document()` is a no-op on an already-empty where filter. The window between delete and re-insert is minimal and ChromaDB's insert is atomic.

### 6. Watcher integration: always-on, no debounce

**Choice**: `on_deleted` handler fires immediately — no debouncing. On file deletion, it cancels any pending ingest timer, clears the hash cache entry, and calls `remove_document()`.

```python
def on_deleted(self, event):
    file_path = event.src_path
    # Cancel any pending ingest timer
    with self._timers_lock:
        old_timer = self._timers.pop(file_path, None)
        if old_timer:
            old_timer.cancel()
    # Clear hash cache
    self._hash_cache.pop(file_path, None)
    # Remove vectors
    from .ingestion import remove_document

    remove_document(file_path, collection_name=self._collection_name)
```

**Rationale**: Deletion is idempotent — calling `collection.delete(where=...)` on an already-empty where filter is a no-op. Debouncing would add unnecessary delay. Timer cancellation prevents the race condition where a file is modified, then deleted before the ingest timer fires.

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Accidental collection drop via MCP** | Low | High | `dry_run` parameter on MCP tool; clients can preview before committing. Collection drop only happens when `collection` is provided without `path` or `metadata_filter`. |
| **Re-ingestion deletes before file read fails** | Low | Low | Delete-before-read: if file doesn't exist, `remove_document()` is a no-op. If file is corrupt, old chunks survive. Window is minimal. |
| **Watcher false-positive on_delete** | Low | Low | Watchdog fires `on_deleted` only on actual filesystem deletion. Temporary files (`.tmp`, `.part`) are already excluded by ignore patterns. |
| **Concurrent delete+search race** | Low | Low | ChromaDB's SQLite backend provides file-level locking. A delete during a search query returns partial results — acceptable. |
| **Large metadata filter impact** | Medium | Low | `collection.delete(where={"category": "uncategorised"})` could delete thousands of chunks in one call. `dry_run` parameter lets users preview the impact. |

## Resolved Questions

| Question | Decision |
|----------|----------|
| Re-ingestion behaviour | Automatic upsert — `remove_document()` called before chunking for each file ingested. No flag needed. |
| CLI `--collection` semantics | DROP the collection. "Delete a collection" means remove it entirely. |
| Separate `delete-collection` CLI? | No — folded into `delete --collection`. One subcommand, three modes. |
| Separate `delete_collection` MCP tool? | No — `delete_documents` with only `collection` parameter drops the collection. |
| Watcher: always-on or opt-in? | Always-on. Deleting a file from a watched directory must remove its vectors. |
| Clear a collection without dropping? | Not needed. Drop and re-ingest — collections auto-create on first ingest. |
| Delete by directory? | No — `--path` accepts a single file. For directories, iterate with a script. |
