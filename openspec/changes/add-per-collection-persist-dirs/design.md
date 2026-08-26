# Design: add-per-collection-persist-dirs

## Context

Post-ADR-049 topology: `VECTOR_STORE` defaults to `lancedb` (each
collection a `.lance` table directory under `LANCEDB_URI`); `chroma` is
the opt-in extra behind the CVE-quarantine.

Concurrency facts established at v3 (correcting the 2026-08-22 re-scope,
which overstated both):

- Experiment 19 (`19-lancedb-lifecycle-qualification-2026-08-21`, gate
  G13) qualified a dense search on one populated collection completing
  while an ingestion into a second collection was in flight — a
  concurrent read during a write. It did **not** test two concurrent
  writers, and this design does not cite it as qualifying concurrent
  writes.
- The ingestion mutation lock (`write_lock`, `core/ingestion/_state.py`,
  acquired in `replacement.py`'s `_commit_sync`) is process-global. It
  serialises write/verify/cleanup mutations across all collections
  within one process. It is not per-collection, and it provides no
  cross-process protection.
- TDR-013 narrowed the lock to the mutation section; it did not make it
  per-collection.

Layer separation this design must respect:

| Layer | What it is | Scope |
| --- | --- | --- |
| Process orchestration lock | `write_lock` around commit sections | One process, all collections |
| LanceDB physical layout | one `.lance` table directory per collection | On-disk isolation of table data |
| Cross-process safety | LanceDB/Chroma file locking semantics | **Unverified for concurrent writers** |

- `LanceVectorStore` opens tables by collection name; the name becomes
  a path component under the URI.
- `ChromaVectorStore` keeps every local-mode collection in one shared
  SQLite file inside `chroma_persist_dir`.

## Goals / Non-Goals

**Goals (default-path scope):**

- Path-component safety for LanceDB collection names at the adapter's
  table-name/filesystem boundary.
- A specified, regression-tested layout pin on the default LanceDB
  path: two collections always resolve to distinct `.lance` table
  directories.
- Documentation that states the layout contract and the honest
  concurrency position (cross-process concurrent writes unverified).

**Non-Goals:**

- Any concurrency guarantee. No claim that cross-collection writes are
  contention-free, in-process or cross-process, without a
  two-process/two-collection write experiment.
- Any change to LanceDB's storage engine or table layout — the
  guarantee documents and pins what LanceDB already does natively.
- Chroma per-collection persist directories, grouping maps, and the
  migration CLI — deferred (see below).
- HTTP Chroma server mode; runtime-mutable grouping; cross-process
  locking; change detection (separate change).

## Decisions

### D1: The LanceDB guarantee is a layout guarantee, not a concurrency guarantee

`{lancedb_uri}/{collection_name}.lance` will be pinned with a regression
test asserting two collections occupy distinct table directories
against a real temporary store. The prior draft's scenario asserting
that concurrent writes to two collections "MUST NOT serialise on a
shared collection-level file lock" is withdrawn: within one process the
orchestration lock serialises them by design, and across processes the
behaviour is unverified.

### D2: Path-component validation at the filesystem boundary

The LanceDB adapter validates collection names before table access:
non-empty, single path component, no absolute paths, separators, `.` or
`..`. Chroma collection names are not filesystem path components in the
current shared-`PersistentClient` layout, so Chroma validation and group
names remain deferred with the Chroma per-directory scope. `lancedb.py`
sits at the 500-line ceiling (497 lines), so validation lands in a
focused helper rather than inline. The resolver never creates directories
itself; creation stays with LanceDB.

### D3: No compose.py changes in this scope

The default path needs no per-collection resolution in the composition
root — one LanceDB store already serves all tables. Name validation
lives at the adapter filesystem boundary. This keeps the change small
and leaves `compose.py` (497 lines) untouched.

## Deferred: Chroma per-collection scope (recorded for a future change)

Deferred until demonstrated Chroma-extra operator demand **and** any
needed contention evidence exist. When taken up:

- Chroma local-mode unmapped collections resolve to
  `{chroma_persist_dir}/{collection_name}/` (one SQLite file per
  independently-written collection), with an explicit static grouping
  map opting collections back into shared directories. Resolution lives
  in `compose.py`; `config/` holds the mapping data.
- The Chroma `_get_client()` lazy flat-default read is replaced by the
  injected resolved directory (missing injection fails clearly).
- A Chroma-only migration (`rag-mcp migrate-storage`) moves flat-layout
  data through the ChromaDB API — export/import with verification,
  staging, atomic swap, resume, conflict abort, rollback — never
  recomputing embeddings, never touching LanceDB stores.
- Mapping changes require explicit re-migration or re-ingest; the
  resolver never moves data automatically.
- The `vectordb-abstraction` "Store selection via configuration"
  requirement gains the per-collection persist-resolution clause and
  scenario (drafted in the 2026-08-22 re-scope; retained in git history
  of this change until then).
- The daemon watcher warning may be split by backend at that point,
  grounded in whatever contention evidence exists then.

## Risks / Trade-offs

- [Spec-only guarantee on LanceDB could rot] → Regression test asserts
  two collections resolve to distinct table paths against a real
  temporary store.
- [LanceDB name validation rejects previously accepted tables] → Rejection
  set is narrow (empty, separators, `.`, `..`, absolute); existing
  documented collection names remain valid.
- [Users assume cross-process safety from layout isolation] → The
  documented contract states explicitly that concurrent multi-process
  writes are unverified and the daemon warning stands.
- [LanceDB adapter at the ceiling] → Validation lands in a focused
  helper; no inline growth; no bundled refactor.

## Migration Plan

1. Default-path (LanceDB) users: nothing. The layout is already in
   place; this change adds validation, pinning tests, and docs.
2. Chroma-extra users: nothing in this change. The deferred scope
   carries any future migration.

## Deferred blockers (explicit)

1. Chroma migration demand: requires actual Chroma-extra operator/data
   demand.
2. Any cross-process contention claim (either backend): requires a
   two-process, two-collection concurrent-write experiment.
