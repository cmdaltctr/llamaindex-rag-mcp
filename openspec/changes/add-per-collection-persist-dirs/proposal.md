# Proposal: add-per-collection-persist-dirs

> **Re-scoped 2026-08-22** for the post-ADR-049 storage topology: LanceDB
> is the default vector store; Chroma is the opt-in `chroma` extra. The
> original (pre-ADR-049) proposal treated the Chroma `PersistentClient`
> shared-SQLite layout as the production default; that premise is gone.
> The rewrite keeps what still matters and drops what the topology change
> dissolved.

## Why

Running several stdio MCP clients at once (an OpenCode instance and a
Claude instance, each spawning its own server subprocess) is the normal,
supported pattern. The storage layer — not the transport — decides whether
those processes contend.

On the default LanceDB path each collection is already its own `.lance`
directory under `LANCEDB_URI`, so cross-collection write contention does
not exist by construction (qualified for concurrency by Experiment 19).
But nothing in the specs guarantees that layout, and collection names
cross into filesystem paths without a stated safety contract.

On the opt-in Chroma path the original problem stands in full:
`chromadb.PersistentClient` keeps every collection in one shared SQLite
file inside `chroma_persist_dir`, so two agents ingesting to *different*
collections still contend on one file-level write lock. The watcher
already warns about this (`transports/cli/watch.py`).

## What Changes

- **LanceDB (default): specify and guarantee the native layout.** The
  per-collection isolation of `{lancedb_uri}/{collection_name}.lance`
  becomes a specified contract with regression tests pinning it, so a
  future adapter change cannot silently co-locate collections.
- **Path-component safety, both backends.** Collection names become
  filesystem path components on both paths; names MUST be validated as
  non-empty single path components (no separators, `.`, `..`, absolute
  paths) before any store operation touches disk.
- **Chroma (opt-in extra): per-collection persist directories.** When
  `VECTOR_STORE=chroma` runs in local mode, each unmapped collection
  resolves to `{chroma_persist_dir}/{collection_name}/` — one SQLite file
  per independently-written collection. An explicit static grouping map
  opts collections back into shared directories where co-location is
  wanted. Resolution lives in `compose.py`; `config/` holds the mapping
  data.
- **Chroma-only migration.** Existing flat-layout Chroma data moves once
  through a Chroma-API export/import command (`rag-mcp
  migrate-storage`), copying IDs, embeddings, documents and metadata
  without recomputing embeddings. Default-path users (LanceDB) have no
  migration step; legacy Chroma directories at the old default location
  remain governed by the ADR-049 fail-closed legacy guard.
- **Watcher warning accuracy.** The daemon warning is split by backend:
  same-collection concurrent writes contend on both backends;
  different-collection writes contend only under Chroma co-location.

Not in scope: HTTP Chroma server mode, transport-layer changes,
cross-process locking, runtime-mutable grouping (recorded as the Option 2
follow-up in the original design, unchanged).

## Capabilities

### New Capabilities

- `collection-storage-layout`: how a collection name resolves to on-disk
  storage per backend — the LanceDB native-layout guarantee, path-safety
  validation, the Chroma per-collection rule with opt-in grouping, and
  the Chroma-only migration contract.

### Modified Capabilities

- `vectordb-abstraction`: "Store selection via configuration" gains the
  constraint that the persist location for an operation is resolved per
  collection at the composition root (per-backend rules from
  `collection-storage-layout`), never read as one flat global default
  inside the store.

## Impact

- **Code**: `compose.py` (per-collection resolution + directory-keyed
  store provider for Chroma local mode), `config/` + `core/settings.py`
  (grouping-map setting), `core/vectordb/chroma.py` (injected resolved
  directory), `core/vectordb/lancedb.py` (name validation at the
  filesystem boundary), `daemon/watcher.py` (split warning).
- **On-disk data**: LanceDB users — none. Chroma-extra local users —
  one-time migration or re-ingest.
- **Dependencies**: none new. `chroma` remains an optional extra.
- **Contracts**: MCP tool surface unchanged; every tool already passes
  `collection: str` per call.
