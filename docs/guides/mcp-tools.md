# MCP Tools Reference

Six tools are exposed over the MCP protocol. All parameters are optional except where marked _(required)_.

## `search_documents`

Semantic similarity search over indexed documents.

| Parameter              | Type   | Default       | Description                                                                                                                                             |
| ---------------------- | ------ | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `query`                | string | _(required)_  | Natural language search query                                                                                                                           |
| `top_k`                | int    | `10`          | Maximum number of chunks to return                                                                                                                      |
| `similarity_threshold` | float  | `0.0`         | Minimum relevance score (0.0 = no filtering). When `rerank=True`, automatically scaled down 30× because cross-encoder scores occupy a lower range.      |
| `rerank`               | bool   | `true`        | Re-score results with cross-encoder for better precision                                                                                                |
| `hybrid`               | bool   | `false`       | Fuse dense vector search with sparse BM25 results via RRF before optional reranking. Use for rare terms, exact identifiers, citations, and error codes. |
| `collection`           | string | `"documents"` | ChromaDB collection to search                                                                                                                           |
| `metadata_filter`      | dict   | `null`        | ChromaDB `where` clause to filter by metadata fields, e.g. `{"category": "AI"}`. Applied server-side — only matching chunks are fetched.                |

## `ingest_documents`

Index a file or directory into the vector store.

| Parameter    | Type   | Default       | Description                               |
| ------------ | ------ | ------------- | ----------------------------------------- |
| `path`       | string | _(required)_  | Path to a file or directory to ingest     |
| `collection` | string | `"documents"` | ChromaDB collection to store documents in |

## `list_indexed_documents`

Show what's currently indexed.

| Parameter    | Type   | Default       | Description                                |
| ------------ | ------ | ------------- | ------------------------------------------ |
| `collection` | string | `"documents"` | ChromaDB collection to list documents from |

## `list_collections`

No parameters. Returns a list of objects with `name`, `document_count`, and `chunk_count`.

## `delete_documents`

Remove documents by file path, metadata filter, or drop an entire collection.

| Parameter         | Type   | Default       | Description                                                                                                            |
| ----------------- | ------ | ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `path`            | string | `null`        | Source file path whose chunks to delete                                                                                |
| `metadata_filter` | dict   | `null`        | ChromaDB `where` clause to match chunks, e.g. `{"category": "uncategorised"}`                                          |
| `collection`      | string | `"documents"` | Collection to operate on. When provided alone (without `path` or `metadata_filter`), the entire collection is dropped. |
| `dry_run`         | bool   | `false`       | Preview what would be deleted without modifying ChromaDB                                                               |

The three deletion modes (`path`, `metadata_filter`, `collection`-only) are mutually exclusive.

## `get_codebase_map`

Generate a compact codebase map showing file types, code communities, document communities, cross-links, and architectural hubs. Designed for agents starting a session on an unfamiliar codebase.

| Parameter | Type   | Default | Description                                        |
| --------- | ------ | ------- | -------------------------------------------------- |
| `path`    | string | `"."`   | Project directory path to map                      |
| `refresh` | bool   | `false` | If true, rebuild the map regardless of cache state |

Results are cached per-project keyed by git commit hash in `.opencode/codebase-graph.json`. Use `refresh=true` to force a rebuild after code changes.

**Read-only:** This tool does not modify any files or databases.

---

## Tool behaviour notes

- **Tool handlers never raise exceptions.** Errors are returned as `{"status": "error", "message": "..."}`.
- **All parameters are optional with sensible defaults** — backward compatible with existing clients.
- **Re-ingestion is an upsert** — old chunks for a file are removed before new ones are written. No duplication.
