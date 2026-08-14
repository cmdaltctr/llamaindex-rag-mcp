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
group directory name, loaded via the nested settings convention (env var
JSON or defaults source, exact encoding in tasks). The default rule needs
no table entry: unmapped collection → own subdirectory.

Resolution lives in `compose.py`, using dispatch over configured data (a
`dict.get` plus the default rule) — no `if/elif` over collection names, no
registry needed for a pure lookup. `config/` holds the data; `compose.py`
holds the resolution; consistent with the config-composition-root
invariant. `ChromaVectorStore` construction receives the resolved
directory, and the lazy flat-default read inside `_get_client()` is
retired for the production path.

Filesystem-as-registry (the LlamaIndex trick): a group directory that does
not exist is created on first use; listing the parent directory enumerates
all storage locations. No sidecar state file exists in this option.

### D3: Migration = file moves, not re-embedding

A Chroma `persist_dir` directory is self-contained (SQLite + supporting
files). Migrating a collection from the flat layout to its own
subdirectory is a directory move/rename, performed by a small CLI command
(`rag-mcp migrate-storage` or a documented manual step — tasks decide) on
a stopped server. No embedding recomputation. Rollback is the reverse
move. Collections the operator elects not to migrate are simply re-ingested
into fresh directories; with `add-ingestion-change-detection` landed, the
first re-ingest into a fresh directory is also the last full one.

### D4: Empty/absent directories never create collections implicitly

Directory creation happens lazily on first write via Chroma's own
`PersistentClient(path=...)` behaviour (it creates the path). The resolver
returns a path; it does not touch the filesystem. This keeps resolution
pure and testable without disk I/O.

## Risks / Trade-offs

- [BREAKING: existing collections invisible under the new default layout]
  → One-time migration command (D3) + clear release notes; the flat
  directory remains readable by pointing a group mapping at it for
  transition periods.
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

1. Ship with a transition default: if the flat `./chroma_db` directory
   contains collections and no per-collection subdirectory exists yet,
   the operator runs the migration command once (server stopped), which
   moves each collection's data to its resolved subdirectory.
2. Rollback: move directories back (or remap via a group entry pointing
   at the original flat directory) and revert the commit.
3. Re-ingest is always a functional alternative to migration (see D3).

## Open Questions

None blocking. The env-var encoding of the mapping table (JSON dict vs
repeated vars) is decided during implementation per ergonomics; either
satisfies the spec.
