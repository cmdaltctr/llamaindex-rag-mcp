# MCP Tools Reference

Seven tools are exposed over the MCP protocol. All parameters are optional except where marked _(required)_.

## `search_documents`

Semantic similarity search over indexed documents.

| Parameter              | Type   | Default       | Description                                                                                                                                                                                              |
| ---------------------- | ------ | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `query`                | string | _(required)_  | Natural language search query                                                                                                                                                                            |
| `top_k`                | int    | `10`          | Maximum number of chunks to return                                                                                                                                                                       |
| `similarity_threshold` | float  | `0.0`         | Minimum canonical dense similarity (0.0 = no filtering). Hybrid/no-rerank applies it to dense evidence before RRF; successful reranking uses the calibrated 30× transform.                               |
| `rerank`               | bool   | `null`        | Tri-state: `true` forces reranking, `false` disables, `null` (default) applies policy resolver based on query type and `RETRIEVAL__RERANK_ENABLED` config                                                |
| `hybrid`               | bool   | `false`       | Fuse dense vector search with sparse BM25 results via RRF before optional reranking. Defaults to `RETRIEVAL__HYBRID_ENABLED` env var. Use for rare terms, exact identifiers, citations, and error codes. |
| `expand_window`        | int    | `0`           | Neighbours added per side of each retrieved chunk during context assembly. Expanded neighbours merge into the retrieved chunk. Retrieved rows are never displaced. |
| `collection`           | string | `"documents"` | Vector-store collection to search                                                                                                                                                                        |
| `metadata_filter`      | dict   | `null`        | ChromaDB-compatible `where` clause, e.g. `{"category": "AI"}`. It constrains both dense and sparse candidates before fusion.                                                                             |
| `diagnostics`          | bool   | `false`       | Include core-produced ranking, policy, threshold, reranker, and sparse-backend diagnostics. Keep disabled for lean responses.                                                                            |

When `diagnostics` is `true`, results also preserve every diagnostic field
produced by core retrieval. The transport does not define or rename these
fields.

When `diagnostics` is `true`, each result row also carries a `timings` mapping
of per-stage retrieval wall-clock durations in seconds:

| Key                 | Stage                | Present when                           |
| ------------------- | -------------------- | -------------------------------------- |
| `embedding_seconds` | Query embedding      | Always (every search embeds the query) |
| `dense_seconds`     | Dense vector search  | Always                                 |
| `sparse_seconds`    | Sparse (BM25) search | Hybrid queries only                    |
| `fusion_seconds`    | RRF fusion           | Hybrid queries only                    |
| `rerank_seconds`    | Cross-encoder rerank | Reranking ran (success or failure)     |
| `assembly_seconds`  | Context assembly     | Always (every search assembles results) |

A stage that did not run is absent from the mapping. Absence means "did not
execute", never "took zero time". No total duration is emitted.

Dense and sparse stages run concurrently in hybrid mode, so their durations
overlap. Do not sum `dense_seconds` and `sparse_seconds` to get wall time.
Compare each stage independently.

Every ranked result includes `score_kind`: `dense_similarity_v1` for dense search,
`rrf_v1` for non-reranked hybrid fusion, or `reranker_sigmoid_v1` after a
successful rerank. `similarity_threshold` is never applied directly to an
`rrf_v1` value.

### Context assembly

Every search runs an assembly stage between final ranking and return
([ADR-056](../adr/056-lineage-navigation-replaces-a-document-store.md)). The
stage reshapes returned evidence. It never re-ranks, re-scores, or drops
evidence.

**Overlap is removed by default.** Adjacent chunks of one source version
merge into one row. Only the longest exact suffix/prefix match within the
configured `chunk_overlap` budget is removed. When no exact match fits, the
texts concatenate without deletion. A merged row's text is a superset of each
constituent's unique content, so no evidence is lost.

A merged row carries a `chunk_ids` array. It lists the `chunk_id` of every
constituent chunk in ascending order. Its `source_chunk_index` is the lowest
constituent index. Its `score` is the best constituent score. Use any listed
`chunk_id` as a citation; each resolves to exactly one stored chunk. Unmerged
rows keep the plain `chunk_id` key and gain nothing.

**Neighbour expansion is opt-in.** Set `expand_window` above zero to add each
retrieved chunk's neighbours to its context. Expansion is bounded by the
window. Expanded neighbours merge into the retrieved chunk under the merging
rules above. Retrieved rows are never dropped to honour `top_k` after
expansion. Rows added purely by expansion were never ranked, so they carry no
`score` and no `score_kind`.

**The client still owns final context budgeting.** Assembly removes duplicate
text and can add requested neighbours. It does not truncate to a token limit.
Count tokens on the returned text before you send it to a model.

When `diagnostics` is `true`, each row also reports `assembly_merged`,
`assembly_chunk_count`, and `assembly_expanded`.

Every result also carries additive lineage fields: `source_id`,
`source_version`, `chunk_id`, `source_chunk_index`, and `source_chunk_count`
([ADR-052](../adr/052-stable-source-chunk-lineage.md)). Values are `null` for
rows stored without lineage, such as experiment precomputed rows. The
internal attempt-specific vector row ID is not exposed; use `chunk_id` as the
stable per-chunk reference, and `source_id` plus `source_version` to select
one complete source version.

## `ingest_documents`

Index a file or directory into the vector store.

| Parameter    | Type   | Default       | Description                                   |
| ------------ | ------ | ------------- | --------------------------------------------- |
| `path`       | string | _(required)_  | Path to a file or directory to ingest         |
| `collection` | string | `"documents"` | Vector-store collection to store documents in |

## `list_indexed_documents`

Show what's currently indexed.

| Parameter    | Type   | Default       | Description                                    |
| ------------ | ------ | ------------- | ---------------------------------------------- |
| `collection` | string | `"documents"` | Vector-store collection to list documents from |

Each row is `{"source": <path>, "source_id": <id or null>, "chunks": <count>, "orphaned": <true, false, or null>}`.
Chunks are grouped by `source_id`, so one indexed file appears once with its
chunk total. Rows without lineage metadata (for example experiment
precomputed rows) fall back to path grouping and report `source_id: null`.

The `orphaned` field is machine-local:

- `true`: The absolute source path is missing on this machine.
- `false`: The absolute source path exists on this machine.
- `null`: The row has no absolute path that this machine can check.

This field does not prove that a source is missing elsewhere. An index can
contain paths created on another machine. Listing is read-only and never
deletes indexed chunks. Use [`delete_documents`](#delete_documents) with
`dry_run: true` to preview manual cleanup before explicit deletion.

## `list_collections`

No parameters. Returns a list of objects with `name`, `document_count`, and `chunk_count`.

## `delete_documents`

Remove documents by file path, metadata filter, or drop an entire collection.

| Parameter         | Type   | Default       | Description                                                                                                                                    |
| ----------------- | ------ | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `path`            | string | `null`        | Source file path whose chunks to delete. The path is canonicalised and matched by its derived `source_id`, the same derivation ingestion uses. |
| `metadata_filter` | dict   | `null`        | ChromaDB-compatible `where` clause to match chunks, e.g. `{"category": "uncategorised"}`                                                       |
| `collection`      | string | `"documents"` | Collection to operate on. When provided alone (without `path` or `metadata_filter`), the entire collection is dropped.                         |
| `dry_run`         | bool   | `false`       | Preview what would be deleted without modifying the vector store                                                                               |

The three deletion modes (`path`, `metadata_filter`, `collection`-only) are mutually exclusive.

A `./`-prefixed path is canonicalised before matching, so `./notes/a.md` and
its absolute form delete the same source.

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

| Parameter    | Type   | Default      | Description                                               |
| ------------ | ------ | ------------ | --------------------------------------------------------- |
| `collection` | string | _(required)_ | Collection to change                                      |
| `profile`    | string | _(required)_ | `documents` or `codebase`                                 |
| `confirm`    | bool   | `false`      | Apply the change. When `false`, returns a preview instead |

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
