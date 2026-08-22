# MCP Tools Reference

Seven tools are exposed over the MCP protocol. All parameters are optional except where marked _(required)_.

## `search_documents`

Semantic similarity search over indexed documents.

| Parameter              | Type   | Default       | Description                                                                                                                                                                                   |
| ---------------------- | ------ | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `query`                | string | _(required)_  | Natural language search query                                                                                                                                                                 |
| `top_k`                | int    | `10`          | Maximum number of chunks to return                                                                                                                                                            |
| `similarity_threshold` | float  | `0.0`         | Minimum canonical dense similarity (0.0 = no filtering). Hybrid/no-rerank applies it to dense evidence before RRF; successful reranking uses the calibrated 30× transform.                    |
| `rerank`               | bool   | `null`        | Tri-state: `true` forces reranking, `false` disables, `null` (default) applies policy resolver based on query type and `RETRIEVAL__RERANK_ENABLED` config                                                |
| `hybrid`               | bool   | `false`       | Fuse dense vector search with sparse BM25 results via RRF before optional reranking. Defaults to `RETRIEVAL__HYBRID_ENABLED` env var. Use for rare terms, exact identifiers, citations, and error codes. |
| `collection`           | string | `"documents"` | Vector-store collection to search                                                                                                                                                              |
| `metadata_filter`      | dict   | `null`        | ChromaDB-compatible `where` clause, e.g. `{"category": "AI"}`. It constrains both dense and sparse candidates before fusion.                                                              |

Every result includes `score_kind`: `dense_similarity_v1` for dense search,
`rrf_v1` for non-reranked hybrid fusion, or `reranker_sigmoid_v1` after a
successful rerank. `similarity_threshold` is never applied directly to an
`rrf_v1` value.

## `ingest_documents`

Index a file or directory into the vector store.

| Parameter    | Type   | Default       | Description                               |
| ------------ | ------ | ------------- | ----------------------------------------- |
| `path`       | string | _(required)_  | Path to a file or directory to ingest     |
| `collection` | string | `"documents"` | Vector-store collection to store documents in |

## `list_indexed_documents`

Show what's currently indexed.

| Parameter    | Type   | Default       | Description                                   |
| ------------ | ------ | ------------- | --------------------------------------------- |
| `collection` | string | `"documents"` | Vector-store collection to list documents from |

## `list_collections`

No parameters. Returns a list of objects with `name`, `document_count`, and `chunk_count`.

## `delete_documents`

Remove documents by file path, metadata filter, or drop an entire collection.

| Parameter         | Type   | Default       | Description                                                                                                            |
| ----------------- | ------ | ------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `path`            | string | `null`        | Source file path whose chunks to delete                                                                                |
| `metadata_filter` | dict   | `null`        | ChromaDB-compatible `where` clause to match chunks, e.g. `{"category": "uncategorised"}`                              |
| `collection`      | string | `"documents"` | Collection to operate on. When provided alone (without `path` or `metadata_filter`), the entire collection is dropped. |
| `dry_run`         | bool   | `false`       | Preview what would be deleted without modifying the vector store                                                       |

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

## `change_collection_profile`

Switch a collection between the `documents` and `codebase` profiles. This
changes retrieval behaviour only — no chunks are re-chunked or re-embedded.

| Parameter | Type | Default | Description |
| --------- | ---- | ------- | ----------- |
| `collection` | string | _(required)_ | Collection to change |
| `profile` | string | _(required)_ | `documents` or `codebase` |
| `confirm` | bool | `false` | Apply the change. When `false`, returns a preview instead |

Called without `confirm`, it returns a preview describing what would change:
which levers move, whether each applies immediately or only to future ingests,
and the current chunk count. Nothing is modified.

```json
{ "collection": "my_code", "profile": "codebase" }
```

Call again with `"confirm": true` to apply it.

Two-step by design: some levers (top_k, reranker) take effect on the next
query, while others (chunking strategy) only affect documents ingested from
then on. The preview makes that distinction visible before you commit to it.

A collection cannot be set to `hybrid` — that is a server mode, not a
collection profile. See [Configuration](configuration.md#profiles).

---

## Tool behaviour notes

- **Tool handlers never raise exceptions.** Errors are returned as `{"status": "error", "message": "..."}`.
- **All parameters are optional with sensible defaults** — backward compatible with existing clients.
- **Re-ingestion is an upsert** — old chunks for a file are removed before new ones are written. No duplication.
