# Proposal: add-per-collection-persist-dirs

## Why

The server uses `chromadb.PersistentClient` — an embedded SQLite-backed
store. Two processes writing to the same `persist_dir` (for example an
OpenCode instance and a Claude Code instance each spawning their own stdio
MCP subprocess) risk SQLite "database is locked" errors during concurrent
ingestion. The lock is file-level, not collection-level: all collections
created via `get_or_create_collection(name)` inside one shared
`chroma_persist_dir` live in the same SQLite file, so "agent A ingests to
collection X, agent B ingests to collection Y" does not avoid contention
when X and Y share the directory. Concurrent reads/searches are fine; only
concurrent writers contend. This risk is already acknowledged in the codebase
(`transports/cli/watch.py` warns "two processes do not share the internal
write lock"). Running multiple stdio clients is itself the normal, supported
pattern — the fix belongs at the storage layer, not the transport layer.

Related but orthogonal: `add-ingestion-change-detection` reduces how often
writers contend (skipped files perform zero ChromaDB writes; the hash lookup
is a read) but does not eliminate concurrent-write contention for
simultaneous ingests of different files. The two changes share no code
coupling — change detection hashes are scoped to `(file_path, collection)`
inside a collection, so it works identically whether collections share one
SQLite file or each get their own directory. If a collection later moves to
a new persist dir, that store has no stored hashes and re-ingests once —
the legacy-chunks scenario already covered by that change's spec delta.

## What Changes

- Default per-collection isolation: when no explicit mapping exists, each
  collection resolves to its own persist directory
  (`{chroma_db_dir}/{collection_name}` by default), giving each collection
  its own SQLite file and eliminating cross-collection write lock
  contention with no HTTP server and no change to stdio transport.
- Opt-in grouping: an explicit mapping table assigns collections to shared
  persist directories (for example `journal_a` and `journal_b` both into a
  `journals` directory), for callers who want them co-located.
- The resolver lives in `config/` (single source of truth for settings
  data, no business logic) with `compose.py` performing resolution and
  wiring — same registry-dispatch pattern as the reranker-per-profile
  setting, no `if/elif` over collection names.
- `ChromaVectorStore.__init__(persist_dir=...)`
  (`core/vectordb/chroma.py`) already accepts a per-instance override; the
  change routes construction through the resolved directory rather than
  the flat global default.
- **BREAKING (behavioural, with migration path)**: collections previously
  living in the shared flat `./chroma_db` directory are not visible under
  the new default directory layout. A one-time migration (or documented
  re-ingest) moves or rebuilds them. The existing
  `chroma_persist_dir` setting remains honoured as the parent root.

Not in scope: an HTTP Chroma server mode, transport-layer changes,
cross-process locking, and change detection itself (covered by
`add-ingestion-change-detection`).

**Cloud evolution (deferred, recorded):** this change keeps the embedded
`PersistentClient` model. The per-collection layout does not lock out a
future move to a Chroma server or managed cloud deployment — the swap
happens at the single construction seam in `compose.py`
(`PersistentClient(path=...)` → `HttpClient(host=..., port=...)`), already
pinned by the `vectordb-abstraction` "persist directory arrives resolved"
contract. The ADR for this change SHALL record the cloud-evolution path so
the decision is deliberate, not accidental.

## Capabilities

### New Capabilities

- `collection-storage-layout`: defines how a collection name resolves to a
  persist directory — the default-isolated rule, the opt-in grouping table,
  and the migration/compatibility contract for existing flat-layout data.

### Modified Capabilities

- `vectordb-abstraction`: the "ChromaDB as first implementation" and "Store
  selection via configuration" requirements gain the constraint that the
  store's persist directory is resolved per collection through the
  composition root rather than read as one flat global default inside the
  store.

## Impact

- **Code**: `config/` (new resolver data — mapping table plus default rule),
  `compose.py` (resolution + store construction wiring), 
  `core/vectordb/chroma.py` (lazy default read replaced by injected,
  already-resolved directory), `core/settings.py` + `config/__init__.py`
  (new settings fields: grouping map, parent dir semantics).
- **Contracts**: MCP tool surface unchanged (every tool already takes
  `collection: str` per call); storage layout on disk changes.
- **On-disk data**: existing `./chroma_db` collections require a one-time
  migration or re-ingest; document the exact steps.
- **Dependencies**: none new.
- **Resolved design question — the middle path**: the grouping table is
  **static configuration** (`.env`/`defaults.yaml`) now, with a
  **runtime-mutable grouping tool (Option 2) as a named additive follow-up
  change** when agent-driven collection creation actually demands it. The
  layout contract — "a collection name resolves to a persist directory,
  resolved at the composition root" — is identical under both, so nothing
  built now is discarded when Option 2 lands. Prior art: LlamaIndex — with
  10+ vector store integrations — uses static construction-time layout
  everywhere and implements no runtime grouping mutation; its
  `from_namespaced_persist_dir` discovers namespaces from the filesystem
  (directory listing as registry), the trick this change borrows for the
  default rule.
- **ADR future work**: the ADR for this change SHALL record three deferred
  paths: (1) Option 2 — runtime-mutable grouping via an MCP tool writing a
  state file, additive on top of this layout contract, triggered when the
  agentic retrieval loop starts creating collections dynamically;
  (2) the agentic retrieval loop itself — multi-query fan-out,
  self-correcting retrieval, per-session namespaces — which is where RAG
  quality work lives and is the workload that eventually justifies
  Option 2; (3) cloud evolution — swapping `PersistentClient` for
  `HttpClient` (self-hosted `chroma run` or managed cloud) at the single
  `compose.py` construction seam. Recording them makes the deferral
  deliberate rather than accidental.
