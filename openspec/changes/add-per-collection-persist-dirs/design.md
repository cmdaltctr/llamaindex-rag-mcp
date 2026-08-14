# Design: add-per-collection-persist-dirs

## Context

See proposal.md for motivation. The relevant shape of the current code:

- `ChromaVectorStore.__init__(persist_dir=...)` (`core/vectordb/chroma.py`)
  already accepts a per-instance override; when omitted, `_get_client()`
  lazily reads the flat global `chroma_persist_dir` default
  (`get_default_effective_settings().chroma_persist_dir`).
- Every MCP tool already takes `collection: str` per call; the CLI and
  daemon likewise pass a collection name per operation.
- `chroma_persist_dir` is one flat setting (`config/__init__.py`,
  `core/settings.py`, default `./chroma_db`). No per-collection mapping
  exists.
- ChromaDB's documented constraint: embedded `PersistentClient` is not
  process-safe; avoid multiple processes writing the same local path. The
  SQLite write lock is per-file, and all collections in one `persist_dir`
  share one SQLite file.
- Prior art studied: LlamaIndex core's `from_namespaced_persist_dir`
  (filesystem-as-registry discovery), LlamaIndex's Chroma integration
  (caller-owned client, defaults to `HttpClient` — rejected here as it
  requires an always-running server, breaking local-first stdio).

## Goals / Non-Goals

**Goals:**

- One SQLite file per independently-written collection by default; write
  lock contention becomes opt-in and explicit.
- Resolution at the composition root; the store receives an
  already-resolved directory (the "persist directory arrives resolved"
  contract in the `vectordb-abstraction` delta).
- A documented one-time migration for existing flat-layout data with no
  embedding recomputation.
- Keep the layout contract stable so Option 2 (runtime grouping tool),
  the agentic retrieval loop, and cloud evolution can land later without
  redesign.

**Non-Goals:**

- HTTP Chroma server mode (`chroma run` / managed cloud) — deferred; see
  ADR future work.
- Runtime-mutable grouping (Option 2 MCP tool + state file) — deferred,
  additive follow-up.
- Cross-process locking, change detection (separate change), transport
  changes.

## Decisions

### D1: Directory-per-collection subdirectories, not filename namespacing

Layout: `{chroma_persist_dir}/{collection_name}/` per collection, with
opt-in mapping entries assigning collections to shared group directories
(`{chroma_persist_dir}/{group}/`).

Alternatives considered:

- *LlamaIndex-style filename namespacing inside one directory* — works for
  their JSON-backed `SimpleVectorStore` because separate files carry no
  shared lock. For Chroma, one `persist_dir` is one SQLite file, so
  filenames inside it change nothing about contention. Subdirectories are
  the minimal unit that isolates the lock.
- *Chroma HTTP server* — solves contention by single-owner serialisation
  but adds an always-running daemon and a network listener, against the
  local-first stdio constraint.

### D2: Static mapping table, resolved at the composition root

The grouping table is configuration data: a dict mapping collection name →
group directory name, loaded from a flat, JSON-encoded environment variable
or the defaults source. It follows the cross-cutting Storage convention used
by `CHROMA_PERSIST_DIR` and `VECTOR_STORE`; the nested `__` convention applies
only to subpackage blocks. The default rule needs no table entry: an unmapped
collection resolves to its own subdirectory.

Resolution lives in `compose.py`, using dispatch over configured data (a
`dict.get` plus the default rule) — no `if/elif` over collection names, no
registry needed for a pure lookup. `config/` holds the data; `compose.py`
holds the resolution; consistent with the config-composition-root
invariant. A directory-keyed provider builds or reuses one
`ChromaVectorStore` for the operation's resolved path, then injects that store
through MCP, CLI, watcher, ingestion, retrieval, deletion, listing, profile,
and codebase-map paths. The production `_get_client()` path rejects a missing
injected directory instead of reading the lazy flat default.

Filesystem-as-registry (the LlamaIndex trick): a group directory that does
not exist is created on first use; listing the parent directory enumerates
all storage locations. No sidecar state file exists in this option.

Collection names and mapped group names MUST be validated before path
construction. Each value must be a non-empty, safe single path component.
Absolute paths, separators, `.`, and `..` are rejected so no resolved path can
escape `chroma_persist_dir`. The resolver does not rely on ChromaDB validation.

### D3: Migration = API export/import, not directory moves

A Chroma `persist_dir` is self-contained, but every collection in the legacy
flat layout shares its SQLite database. No per-collection directory exists to
move. With the server stopped, `rag-mcp migrate-storage` exports each
collection through the ChromaDB API, including IDs, embeddings, documents,
and metadata, then imports those records into the resolved destination. The
migration copies stored vectors and MUST NOT invoke the embedding provider.

The command creates a backup of the source root before writing. It builds each
destination in a sibling staging directory, verifies the copied records, then
renames the staging directory into place. An existing destination is copied to
staging first and may receive another grouped collection only when no
collection name or record conflicts. An exact prior import is skipped, so a
partial run can resume safely. A conflict aborts before the destination swap;
a failed import leaves the source and existing destination unchanged. Rollback
restores the source backup and the retained pre-swap destination backup.
Re-ingestion remains a fallback and recomputes embeddings.

### D4: Empty/absent directories never create collections implicitly

Directory creation happens lazily on first write via Chroma's own
`PersistentClient(path=...)` behaviour (it creates the path). The resolver
returns a path; it does not touch the filesystem. This keeps resolution
pure and testable without disk I/O.

### D5: Mapping changes require explicit migration

`collection_group_map` is static after a collection's first write. Changing an
own-directory, group-directory, or group-to-group mapping without moving data
would make the collection appear empty at its new path. The operator MUST run
the D3 migration for each mapping change, or re-ingest the collection. The
resolver never moves existing data automatically.

## Risks / Trade-offs

- [BREAKING: existing collections invisible under the new default layout]
  → One-time migration command (D3) + clear release notes. Group mappings
  always resolve below the parent root, so they cannot expose the legacy flat
  store. Transitional compatibility uses migration or re-ingestion only.
- [Two agents writing the SAME collection still contend] → Out of scope;
  documented. Same-collection concurrency requires the server mode
  (deferred).
- [No cross-collection single query] → Chroma cannot query multiple
  collections in one call regardless of layout; app-level fan-out would be
  needed either way. Not a regression.
- [Mapping misconfiguration silently co-locates collections] → Grouping is
  explicit opt-in; docs state the contention consequence; a startup log
  line lists group members sharing a directory.
- [N directories, N SQLite files overhead] → Irrelevant at dozens of
  collections; noted for scale.

## Migration Plan

1. Detect collections in the configured flat `chroma_persist_dir` (default
   `./chroma_db`) and require the server to be stopped.
2. Back up the source root. Export and import each collection through the
   ChromaDB API into its resolved staging destination, then verify IDs,
   embeddings, documents, and metadata before the destination swap.
3. Resume exact prior imports, reject conflicts, and report partial failures.
   Restore retained backups for rollback.
4. Use re-ingestion only as the documented fallback. It recomputes embeddings.

## Open Questions

None blocking. The mapping table uses one flat, JSON-encoded environment
variable, as defined in D2.
