# Design: add-per-collection-persist-dirs

## Context

Post-ADR-049 topology: `VECTOR_STORE` defaults to `lancedb` (each
collection a `.lance` table directory under `LANCEDB_URI`); `chroma` is
the opt-in extra behind the CVE-quarantine. Experiment 19 qualified
concurrent multi-collection writes on LanceDB; TDR-013 narrowed the
ingestion write lock to the mutation section.

- `LanceVectorStore` (core/vectordb/lancedb.py) opens tables by
  collection name; the name becomes a path component under the URI.
- `ChromaVectorStore.__init__(persist_dir=...)` accepts a per-instance
  override; `_get_client()` otherwise lazily reads the flat global
  `chroma_persist_dir`.
- The daemon watcher warns generically that two processes do not share
  an internal write lock.
- Prior art retained from the original design: LlamaIndex's
  `from_namespaced_persist_dir` filesystem-as-registry discovery; the
  rejection of an always-running HTTP Chroma server (breaks local-first
  stdio).

## Goals / Non-Goals

**Goals:**

- A specified, regression-tested isolation guarantee on the default
  LanceDB path.
- Path-component safety for collection names on both backends.
- One SQLite file per independently-written collection on the opt-in
  Chroma path, with explicit opt-in grouping.
- A Chroma-only migration that never recomputes embeddings.
- Keep the layout contract stable for the deferred Option 2 (runtime
  grouping tool) and cloud-evolution paths recorded below.

**Non-Goals:**

- Any change to LanceDB's storage engine or table layout — the guarantee
  documents and pins what LanceDB already does natively.
- HTTP Chroma server mode; runtime-mutable grouping; cross-process
  locking; change detection (separate change).
- Migration on the default path (there is no legacy default-path data to
  migrate; LanceDB is new-in-place).

## Decisions

### D1: Two backend rules, one capability

LanceDB: `{lancedb_uri}/{collection_name}.lance` — native, already
isolated; the change adds specification + tests, not mechanism. Chroma
local: `{chroma_persist_dir}/{collection_name}/` — the subdirectory is
the minimal unit that isolates the SQLite file lock (filename
namespacing inside one `persist_dir` changes nothing; the whole
directory is the database). Group directories
(`{chroma_persist_dir}/{group}/`) remain explicit opt-in co-location.

### D2: Resolution at the composition root, config holds the data

The grouping table is a static dict (collection → group), loaded from a
flat JSON-encoded setting, following the `CHROMA_PERSIST_DIR` /
`VECTOR_STORE` convention. `compose.py` resolves per-collection
directories with a pure `dict.get` + default rule — no `if/elif` over
names, no registry for a lookup — and provides a directory-keyed store
cache for Chroma local mode so co-located collections share one client.
LanceDB needs no provider: one store object already serves all tables.
The production Chroma `_get_client()` path rejects a missing injected
directory instead of reading the lazy flat default.

### D3: Path-component validation at the filesystem boundary

Both adapters validate collection and group names before touching disk:
non-empty, single path component, no absolute paths, separators, `.` or
`..`. The resolver does not rely on backend-level validation and never
creates directories itself — creation stays with the store engine
(Lance/Chroma create on first write), keeping resolution pure.

### D4: Chroma migration = API export/import, not directory moves

Every collection in a legacy flat Chroma directory shares its SQLite
database; there is no per-collection directory to move. With the server
stopped, `rag-mcp migrate-storage` exports each collection through the
ChromaDB API and imports records into the resolved destination
staging directory, verifies, then swaps atomically. Prior exact imports
resume; conflicts abort before the swap; rollback restores backups.
Re-ingestion (recomputing embeddings) remains the documented fallback.
The command is available only when the `chroma` extra is installed and
`VECTOR_STORE=chroma`; it MUST NOT touch LanceDB stores.

### D5: Mapping changes require explicit migration (Chroma only)

`collection_group_map` is static after first write. Changing a
collection's mapping without moving data makes it appear empty at the
new path. Operators run D4 per mapping change or re-ingest. The
resolver never moves data automatically.

## Risks / Trade-offs

- [Chroma-extra users see collections "disappear" under the new layout]
  → One-time migration command + release notes; detection lists
  affected collections before any write.
- [Same-collection concurrent writes still contend, both backends] →
  Out of scope, documented; the split watcher warning states it plainly.
- [Grouping misconfiguration silently co-locates Chroma collections] →
  Explicit opt-in only; a startup log line lists groups sharing a
  directory.
- [Spec-only guarantee on LanceDB could rot] → Regression test asserts
  two collections resolve to distinct table paths against a real
  temporary store.

## Migration Plan

1. LanceDB default users: nothing. The layout is already in place.
2. Chroma-extra users: stop servers; `rag-mcp migrate-storage` moves
   flat-layout collections into per-collection directories with
   verification and rollback; re-ingest remains the fallback.
3. Mapping changes after migration: re-run the migration for affected
   collections or re-ingest.

## Deferred (recorded, unchanged from the original design)

1. Option 2 — runtime-mutable grouping via an MCP tool writing a state
   file; additive on this layout contract.
2. The agentic retrieval loop that would eventually justify Option 2.
3. Cloud evolution — selecting hosted backends at the `compose.py` seam;
   already partially realised by ADR-045 (Chroma Cloud) and ADR-049.
