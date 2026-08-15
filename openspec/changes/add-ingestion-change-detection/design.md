# Design: add-ingestion-change-detection

## Context

See proposal.md for motivation. The relevant shape of the current code:

- `ingest_path_async` (`core/ingestion/pipeline.py`) discovers files, runs a
  `remove_document` per file (the upsert semantics), then re-chunks and
  re-embeds everything. It is the sole write path — `embed_and_write_async`
  is called from exactly one place (the pipeline).
- Three production entry points call it: the MCP `ingest` tool, the CLI
  `rag-mcp ingest`, and the watch daemon. Only the daemon has change
  detection, via an in-memory SHA-256 cache (`daemon/watcher.py`) fed by
  `_sha256_file` (`daemon/_shared.py`).
- `remove_document` (`core/ingestion/writer.py`) already queries chunks by
  `file_path` metadata, so per-file metadata lookup against ChromaDB is an
  established pattern in this layer.
- Settings are injected `EffectiveSettings` objects resolved once at the
  entry-point boundary (ADR-037); `core/` must not import a singleton.

## Goals / Non-Goals

**Goals:**

- Skip all ingest work (delete, chunk, embed, metadata extraction) for files
  whose content is unchanged since the last ingest into the same collection.
- Cover all three entry points with one implementation site (the pipeline).
- Survive process restarts (persist the hash in ChromaDB, not memory).
- Preserve the additive result-dict contract established by
  `metadata_degraded`.

**Non-Goals:**

- LlamaIndex-style docstore abstraction or `UPSERTS_AND_DELETE` pruning of
  files removed from disk (directory-diff deletion is a separate concern).
- Per-chunk hashing — file-level granularity only.
- Fixing multi-process SQLite write contention. Change detection reduces the
  write window but two concurrent writers to one `persist_dir` remain
  unsupported (see `transports/cli/watch.py` warning). Per-collection
  persist-dir isolation is a related future change; a collection migrated to
  a new persist dir simply re-ingests once (legacy-chunks scenario).
- Detecting embedding-model or chunking-parameter changes (hash covers file
  content only; the opt-out flag covers forced re-embeds).

## Decisions

### D1: Hash source — SHA-256 of file bytes, file-level

`hashlib.sha256` over the file's raw bytes, computed once per file per
ingest call.

Alternatives considered:

- *mtime+size proxy* — cheaper (no file read), but misses same-size
  same-mtime edits and breaks on checkouts/rsyncs that reset mtimes
  (a git checkout writes new mtimes with potentially identical content —
  a proxy would force re-ingest, while a content hash correctly skips).
- *git-commit keying* (codebase-map pattern, `core/codebase/cache.py`) —
  only valid inside git repos; ingestion targets (Zotero libraries, document
  folders) frequently are not.
- *per-chunk hashing* — finer granularity but adds a hash per chunk and
  complicates the skip decision for partial chunk overlap. File-level matches
  how the delete loop and `remove_document` already think about units.

SHA-256 cost is negligible next to chunking + local Ollama embedding for the
same file. Reuse `_sha256_file`'s chunked-read implementation (it caps at
`MAX_FILE_SIZE`), relocated per D3.

### D2: Hash storage — ChromaDB chunk metadata field

Store the hash as the canonical `source_content_hash` metadata field on every
chunk written for the file. Add a store-neutral filtered metadata read to the
`VectorStore` contract and implement it for ChromaDB; pipeline code must not
call ChromaDB APIs directly. For each `file_path`, inspect every matching
chunk. A file is unchanged only when at least one chunk exists and every
chunk has a non-null `source_content_hash` equal to the current file hash.
Missing, mixed, or different hashes make the file eligible for re-ingestion.

Alternatives considered:

- *Sidecar state file (JSON/SQLite next to the index)* — decouples hash
  lifetime from chunk lifetime, but introduces a second store that can drift
  from ChromaDB state (stale hashes after `rag-mcp delete`, collection drops,
  or direct Chroma edits) and adds a file-per-collection bookkeeping burden.
- *Collection-level Chroma metadata* — Chroma collection metadata is a
  single flat map; per-file hashes do not fit.

Metadata-on-chunk keeps the hash exactly as stale as the chunks themselves:
`remove_document` deletes chunks, the hash goes with them. The existing
`VectorStore.write_nodes` path already persists per-chunk metadata, so the
change is additive there.

### D3: Helper location — `core/ingestion/hashing.py`

Move `_sha256_file` (and `MAX_FILE_SIZE`) from `daemon/_shared.py` to a new
`core/ingestion/hashing.py`; `daemon/_shared.py` re-exports for backwards
compatibility of existing imports.

The layering rule forces this: the pipeline (`core/`) must not import from
`daemon/`. Moving the helper keeps the dependency arrow
`daemon → core/ingestion`, matching every other shared primitive.

### D4: Skip decision point — pipeline, before the delete loop

In `ingest_path_async`, after file discovery and Magika detection, exclude
binary files from change detection and keep their existing `status: "skipped"`
handling. Compute hashes for the remaining eligible files, fetch all stored
chunk hashes via `get_stored_hashes` — one filtered metadata query per file,
with the whole eligible-file list handled inside a single
`asyncio.to_thread` call — and partition the files into `unchanged` and
`to_ingest`. Only
`to_ingest` files enter the existing delete and chunk/embed loops. Files
skipped by change detection get `file_details` entries with
`status: "skipped_unchanged"` and feed the `files_skipped_unchanged` counter.

Doing it before the delete loop matters: deleting first would discard the
stored hash, making the skip impossible. Hash computation is I/O-bound, so
wrap it in `asyncio.to_thread` to honour the loop-responsiveness contract. If
`sha256_file` raises `FileNotFoundError` or `OSError`, record that file as
`status: "failed"`, leave its existing chunks untouched, and continue with
sibling files. A hash-read failure must never abort the call or cause a file
to be classified as unchanged.

### D5: Opt-out — `INGESTION__SKIP_UNCHANGED` (default `true`)

Add the boolean to `IngestionSettings` in `core/ingestion/settings.py` and to
the matching frozen `IngestionBlock` in `core/settings.py`. The config model
already nests `IngestionSettings`, so the flag follows the nested env-var
convention (ADR-037). No new tool parameter or CLI flag is needed; the env var
is the escape hatch for embedding-model or chunking-parameter changes.

### D6: Watcher stays as-is

The daemon's in-memory cache remains a cheap early-out that avoids even the
hash-lookup round trip. No behavioural change; no spec delta for
`watch-command`. A future tidy-up could remove the cache once the pipeline
check proves sufficient, but that is not worth the churn here.

## Risks / Trade-offs

- [First ingest against a pre-existing collection re-embeds everything once]
  → Documented in the spec as the legacy-chunks scenario; unavoidable without
  a backfill pass that would itself need to read every file. Acceptable.
- [Hash reads add one filtered metadata query per file per ingest] → The
  `get_stored_hashes(file_paths, collection_name)` helper accepts the whole
  eligible-file list but issues one filtered metadata query per file through
  the `VectorStore` contract — the same per-file lookup pattern
  `remove_document` already uses — with the loop executed inside a single
  `asyncio.to_thread` call. Each query reads only metadata. The cost is
  negligible against the embedding work it avoids.
- [Settings change (chunk size, embedding model) leaves stale-but-matching
  hashes, so unchanged files keep old vectors] → Mitigated by the opt-out
  flag; also surfaced in the proposal's behavioural note. A future change
  could mix chunk/embed params into the stored hash string; deliberately
  deferred (YAGNI until someone hits it).
- [Stored chunks have mixed or missing hashes after interrupted writes or
  metadata drift] → D2 validates every matching chunk and treats any missing,
  mixed, or different hash as changed. This prevents a matching first chunk
  from hiding stale chunks.

## Migration Plan

1. No on-disk migration: legacy chunks lack the hash field and are treated
   as "no stored hash" → one full re-ingest per collection, then steady-state
   skipping.
2. Rollback: revert the commit; chunks carrying the extra metadata field are
   harmless to readers that do not consult it (additive field, existing
   queries unaffected). No data cleanup needed.
3. Disable-without-rollback: set `INGESTION__SKIP_UNCHANGED=false` to
   restore full re-embed behaviour on any build that contains the change.
