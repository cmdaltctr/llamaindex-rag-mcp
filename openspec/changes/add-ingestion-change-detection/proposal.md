# Proposal: add-ingestion-change-detection

## Why

`ingest_path_async` re-embeds every file in the target path on every call. The
delete-and-re-embed loop (`core/ingestion/pipeline.py:115-122`) runs
`remove_document` on all discovered files, then re-chunks and re-embeds all of
them, with no content-hash check anywhere under `core/ingestion/`. The MCP
`ingest` tool and the CLI `rag-mcp ingest` are the two uncovered entry points —
a coding agent that ingests a directory twice pays the full local-Ollama
embedding cost both times. The watcher daemon already deduplicates with an
in-memory SHA-256 cache, but that cache dies with the process and only covers
the watch path. This is the largest source of wasted embedding work in the
system.

## What Changes

- Add content-hash change detection to `ingest_path_async` itself: before the
  delete-and-re-embed loop, compute a SHA-256 hash of each eligible non-binary
  file and compare it against the hash stored in ChromaDB chunk metadata for
  that `file_path`. Files whose hash matches every stored chunk hash are
  skipped (no delete, no re-chunk, no re-embed). Files whose hash differs, or
  whose chunks have missing or mixed hashes, are re-ingested and their chunks'
  metadata is stamped with the new hash. A file whose content hash cannot be
  read is reported as a per-file failure without stopping sibling files.
- Store the file content hash as a ChromaDB chunk metadata field (additive;
  existing chunks without the field are treated as "no stored hash" and are
  re-ingested once, after which they carry the field).
- Extend the ingestion result dict with an additive `files_skipped_unchanged`
  integer counter (and per-file `file_details` entries with
  `status: "skipped_unchanged"`), following the `metadata_degraded` additive
  precedent. All existing keys keep their names and types.
- Relocate `_sha256_file` from `daemon/_shared.py` to `core/ingestion/` so the
  pipeline can use it without inverting the layering (`core/` must not import
  from `daemon/`). The daemon imports it from its new home.
- Add an opt-out flag (`INGESTION__SKIP_UNCHANGED`, default `true`) so callers
  can force full re-embed behaviour (e.g. after an embedding-model change,
  which invalidates stored vectors but not stored hashes).
- The watcher keeps its in-memory hash cache as a cheap early-out; no watcher
  behaviour change.

Not in scope: porting LlamaIndex's docstore abstraction, per-chunk hashing
(file-level hashing only), reranker work, sentence-window chunking.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `async-ingestion`: adds requirements covering unchanged-file skips,
  per-file hash-read failures, binary-file exclusion, unconditional hash
  stamping, and additive result reporting. Follows the result-field precedent
  set by `metadata_degraded`.

## Impact

- **Code**: `core/ingestion/pipeline.py` (skip logic before the delete loop),
  `core/ingestion/writer.py` (hash metadata stamp and lookup helper),
  `core/vectordb/` (store-neutral filtered metadata read plus the ChromaDB
  implementation), new `core/ingestion/hashing.py` (relocated
  `_sha256_file`), `daemon/_shared.py` (re-export or import switch),
  `daemon/watcher.py` (import path only), `config/` ingestion settings block
  (new `skip_unchanged` flag, default `true`).
- **Contracts**: ingestion result dict gains additive keys; `file_details`
  gains one new status value. MCP tool and CLI report surfaces pass the new
  counter through unchanged.
- **Dependencies**: none new — `hashlib` is stdlib.
- **Behavioural note**: first ingest against a pre-existing collection
  re-ingests everything once (legacy chunks carry no hash). Subsequent
  ingests skip unchanged files. Changing `CHUNK_SIZE`, chunk strategy, or the
  embedding model does NOT change the file hash — the opt-out flag (or a
  collection rebuild) covers those cases.
