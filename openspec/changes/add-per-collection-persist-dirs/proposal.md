# Proposal: add-per-collection-persist-dirs

> **Re-scoped twice.** First on 2026-08-22 for the post-ADR-049 storage
> topology (LanceDB default, Chroma opt-in extra). Then on 2026-08-26
> after a static review against v3 corrected two factual errors in the
> re-scope and split the remaining work into a small default-path scope
> plus a deferred Chroma scope gated on operator demand and contention
> evidence.

## Why

Running several stdio MCP clients at once (an OpenCode instance and a
Claude instance, each spawning its own server subprocess) is the normal,
supported pattern. The storage layer — not the transport — decides whether
those processes contend.

Three distinct layers decide that, and they must not be conflated:

1. **Process-level orchestration lock.** Ingestion mutations inside one
   process run under a process-global lock (`write_lock` in
   `core/ingestion/_state.py`, acquired by `replacement.py`'s commit
   section). It serialises store mutations across *all* collections in
   that process. It is not a per-collection lock, and it is invisible to
   other processes.
2. **Backend physical layout.** On the default LanceDB path each
   collection is its own `.lance` table directory under `LANCEDB_URI`.
   Distinct table directories remove *shared-storage* coupling between
   collections; they say nothing by themselves about cross-process write
   safety.
3. **Backend/filesystem locking across processes.** Whether two separate
   operating-system processes can safely write two different LanceDB
   collections concurrently is a property of LanceDB's file locking. It
   is **unverified**: no experiment has exercised two concurrent writers.
   Experiment 19 (campaign `19-lancedb-lifecycle-qualification`, gate
   G13) qualified a concurrent *read* on one populated collection while
   an ingestion into a *second* collection was in flight — one writer,
   one reader. It did not qualify concurrent writes, so this proposal
   makes no contention-free claim for LanceDB cross-collection writes.

What the default path lacks today is not new storage machinery but a
stated contract: nothing in the specs guarantees the per-table layout,
and collection names cross into filesystem paths without a stated safety
contract.

## What Changes (this change: default-path scope)

- **Path-component safety, both adapters.** Collection names become
  filesystem path components; names MUST be validated as non-empty
  single path components (no separators, `.`, `..`, absolute paths)
  before any store operation touches disk. Applies at both adapters'
  filesystem boundaries.
- **LanceDB (default): specify and pin the native layout.** The
  per-collection isolation of `{lancedb_uri}/{collection_name}.lance`
  becomes a specified contract with regression tests pinning it, so a
  future adapter change cannot silently co-locate collections. This is
  a layout guarantee only — no concurrency guarantee is claimed.
- **Documentation.** The layout and safety contract is documented per
  backend, including the honest statement that cross-process concurrent
  writes are unverified.

## Deferred scope (recorded, not built by this change)

The original re-scope bundled a Chroma-side programme: per-collection
persist directories under `chroma_persist_dir`, a static grouping map,
per-collection resolution in `compose.py`, and a
backup/export/staging/swap/resume/rollback migration CLI
(`rag-mcp migrate-storage`). That programme is **deferred** until both
of these hold:

1. Demonstrated demand from real Chroma-extra operators with data worth
   migrating (the `chroma` extra is opt-in and isolated).
2. Contention evidence: for any cross-process contention claim, a
   two-process, two-collection concurrent-write experiment on the
   relevant backend.

When taken up, the deferred scope would amend the
`vectordb-abstraction` "Store selection via configuration" requirement
(per-collection persist resolution at the composition root; no
self-read flat global default) and extend `collection-storage-layout`
with the Chroma per-directory, grouping, and migration requirements.

Not in scope in any phase: HTTP Chroma server mode, transport-layer
changes, cross-process locking, runtime-mutable grouping.

## Capabilities

### New Capabilities

- `collection-storage-layout`: how a collection name resolves to on-disk
  storage per backend — path-safety validation and the LanceDB
  native-layout guarantee (default-path scope of this change).

### Modified Capabilities

- None. The `vectordb-abstraction` amendment belongs to the deferred
  Chroma scope.

## Impact

- **Code**: `core/vectordb/lancedb.py` (name validation at the
  filesystem boundary; also validated in the Chroma adapter for
  symmetry), plus tests. `lancedb.py` (497 lines) and `chroma.py` (499
  lines) sit at the 500-line ceiling — validation logic lands via a
  small shared helper or focused module, not inline growth, and no
  broad refactor accompanies it.
- **On-disk data**: none. No migration, no layout change on any backend.
- **Dependencies**: none new. `chroma` remains an optional extra.
- **Contracts**: MCP tool surface unchanged.

## Watcher warning

The current daemon warning — that two processes do not share the
internal write lock — remains accurate under the corrected concurrency
picture and is left unchanged. The previously proposed backend-split
warning rested on the withdrawn contention-free claim; if the deferred
Chroma scope lands, revisit the wording then.
