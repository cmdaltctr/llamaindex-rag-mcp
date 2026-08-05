## Why

The five-phase refactor (ADR-032 … ADR-036) shipped, but a conformance audit
against the agreed target — `docs/brainstorm/refactor-proposal/PROPOSAL.md` and
`architecture-diagrams.md` — found the implemented tree does not match it. The
strategy registries the whole design rests on are dead code with zero production
consumers; `config/__init__.py` imports business logic and is 576 lines against a
~150-line target (4 lines *longer* than the 572-line v1 monolith it replaced);
`core/` reads a mutable process-wide settings global in 21 places instead of
receiving injected settings; ChromaDB leaks outside its abstraction; a circular
import exists purely to keep a test monkeypatch alive; three v1 modules were
never relocated; and 15 deprecated shims plus a ~55-entry legacy alias table are
still shipping. Several ADRs assert conformance that the code does not have.

Shipping a v2.0.0 that claims this architecture while the audit findings stand
would make the ADR record dishonest. This change closes every finding, deletes
the v1 surface, and adds machine enforcement so the gaps cannot silently reopen.

## What Changes

**Registries become the real dispatch mechanism (F1, F9)**
- `core/ingestion/chunker.py`, `core/metadata/extractor.py`, and
  `core/retrieval/pipeline.py` resolve strategies through their `registry.get()`
  instead of eager top-level imports and if/elif chains.
- Every registry gains the documented `register(name, import_path)` helper and
  hides the raw `REGISTRY` dict behind `get()` / `available()`.

**Settings are injected, not read from a global (F4, F6)** — **BREAKING**
- A frozen `EffectiveSettings` is threaded through `search()` and
  `ingest_path_async()` and down into every `core/` module and `integrations/`
  module, per PROPOSAL §6.3.1.
- All 21 `from ...config import settings` reads inside `core/` and
  `integrations/` are removed, along with the import-time snapshots at
  `core/ingestion/chunker.py:23` and `core/ingestion/_state.py:22`.
- The `settings = get_settings()` module-level singleton at
  `config/__init__.py:460` is deleted; `compose.py` becomes the only caller of
  `get_settings()`.

**Configuration schema becomes nested (F7, F8)** — **BREAKING, no back-compat**
- `Settings` moves from flat multiple inheritance
  (`config/__init__.py:186`) to nested composition (`chunking:`, `ingestion:`,
  `retrieval:`, `metadata:`) with `env_nested_delimiter="__"`, per PROPOSAL
  §4.3. A new `IngestionSettings` block takes `embed_concurrency` and
  `embed_batch_size` out of `ChunkingSettings`, where they never belonged
  (design.md D10) — done now because the breaking rename is already being paid
  for, and deferring would buy a second break later.
- Unknown configuration cannot be silently dropped: the four subpackage models
  set `extra="forbid"` (catching typos and unenumerated nested keys), and a
  startup tripwire catches the pre-v2 flat names that structurally never reach
  a subpackage model (design.md D9).
- `config/defaults.yaml` and all three `config/profiles/*.yaml` are rewritten
  into the nested schema, per PROPOSAL §6.2. This change ships the migrated
  YAML; it is not left as a user step.
- Subpackage env var names change (`TOP_K` → `RETRIEVAL__TOP_K`,
  `CHUNK_SIZE` → `CHUNKING__CHUNK_SIZE`, …). No flat-key fallback, no
  `DeprecationWarning` path. `.env.example` and the configuration guide are
  rewritten.
- `config/__init__.py` drops to ~150 lines: the PEP 562 alias table
  (`:497-576`) is deleted, and `resolve_sparse_backend()` (`:385`) and
  `resolve_pdf_reader()` (`:412`) move to `compose.py`.

**`config` stops depending on `core` (F3)**
- `config/__init__.py:395`'s `from ..core.retrieval.sparse import
  _detect_native_sparse_capability` is removed with the functions that used it.

**ChromaDB stops leaking (F2)**
- `src/rag_mcp/codebase_map.py:476-478`'s direct `chromadb.PersistentClient(...)`
  is replaced by the injected `VectorStore`, honouring ADR-034 and
  `core/vectordb/chroma.py:9`.

**Circular import removed (F5)**
- `integrations/magika.py:81`'s `import rag_mcp.codebase_map as _cbm` is
  deleted; the test monkeypatch target moves to `integrations/magika.py`.

**Unmigrated v1 modules relocated (Category B, F10, F11)** — **BREAKING**
- `codebase_map.py` and `code_graph.py` → `core/codebase/`;
  `doc_graph.py` → `core/documents/`, per PROPOSAL §5.1. This removes
  `core/ingestion/pipeline.py:97`'s upward import into a top-level module.
- `MAGIKA_LABEL_TO_TREESITTER` and `SUPPORTED_EXTENSIONS` move from
  `config/__init__.py:478,488` next to their consumers.
- The five files over the 500-line ceiling (`code_graph.py` 690,
  `codebase_map.py` 663, `config/__init__.py` 576, `doc_graph.py` 562,
  `daemon/watcher.py` 550) are split under 500.

**All v1 compatibility surface deleted (Category A)** — **BREAKING**
- The 15 shim modules (`server.py`, `cli.py`, `watcher.py`, `azure_reader.py`,
  `ingestion.py`, `retrieval.py`, `metadata_extractor.py`, `reranker.py`,
  `sparse_retriever.py`, and the six files under `readers/`) are removed,
  overriding PROPOSAL §11 Decision 2's grace period. Archived
  `experiments/*/run_eval.py` scripts that import them are historical artefacts,
  are not run in CI, and are **not** repaired.
- The coverage `omit` list for shims is removed from `pyproject.toml`.

**Machine enforcement (enforcement gap)**
- New import-linter contracts cover ChromaDB confinement, `config` → `core`,
  the Magika/codebase cycle, and extend the business-layer contract to
  `core.vectordb`, `core.profiles`, `core.providers`, `daemon`, and
  `integrations`.
- A test asserts the 500-line ceiling across `src/rag_mcp/`.

**Documentation truth-up**
- Corrections to ADR-032 (registry dispatch claim), ADR-033 (no-snapshot claim;
  `src/rag_mcp/server.py` reference), ADR-034 ("never through ChromaDB APIs
  directly"), ADR-036 (§1 import-linter coverage claim; §3 Magika extraction
  claim), PROPOSAL §8 Phase 2 ("572 → ~150 lines"), and PROPOSAL §12.
- New **ADR-037** recording this conformance change and the v2.0.0 break.

**Release**: ships as `refactor!:` → **v2.0.0 major**.

## Capabilities

### New Capabilities
- `architecture-boundary-enforcement`: machine-enforced module boundaries —
  import-linter contracts for ChromaDB confinement, config/core direction,
  acyclic integrations, and full `core/`+`daemon`+`integrations` coverage; the
  500-line file ceiling as an executable check; and the `core/codebase/` +
  `core/documents/` subsystem placement that removes core's upward imports.
- `settings-dependency-injection`: an immutable `EffectiveSettings` threaded
  through core operations as a parameter, replacing every process-wide settings
  global read and import-time snapshot inside `core/` and `integrations/`.

### Modified Capabilities
- `config-composition-root`: nested `Settings` composition with
  `env_nested_delimiter`, revised resolution precedence over nested YAML,
  registries as the sole dispatch mechanism with a `register()` helper, removal
  of the legacy constant shim, relocation of runtime capability probing to
  `compose.py`, and the deliberate break of the flat env var interface.
- `modular-core-extraction`: removal of the backward-compatible import shim
  requirement, and extension of the 500-line ceiling from `core/` to the whole
  package.
- `profiles-dual-use-case`: profile bundles expressed as nested
  `retrieval:`/`chunking:`/`metadata:` blocks validated against the nested
  Pydantic models, and Tier-2 levers delivered as an `EffectiveSettings`
  parameter rather than resolved against a global.
- `vectordb-abstraction`: ChromaDB confined to `core/vectordb/chroma.py`, with
  no `import chromadb` anywhere else in production code.
- `transport-separation`: agent-facing documentation and the ADR record updated
  to the post-conformance tree, including the corrections to stale claims.

## Impact

**Code** — `src/rag_mcp/config/__init__.py`, `compose.py`, all of
`core/ingestion/`, `core/retrieval/`, `core/metadata/`, `core/chunking/`,
`core/vectordb/`, `core/profiles/`, `integrations/`, `daemon/watcher.py`,
`transports/mcp.py`, `transports/cli/`; new `core/codebase/` and
`core/documents/` packages; deletion of 15 modules and the `readers/` package.

**Configuration** — every `CHUNKING__*`, `RETRIEVAL__*`, `METADATA__*` env var
is renamed; `config/defaults.yaml` and all three profile bundles are rewritten;
`.env.example` is regenerated. Existing `.env` files stop supplying subpackage
values silently defaulted — the migration note in `design.md` is mandatory
reading for upgraders.

**Data** — none. No ChromaDB migration; existing `output/chroma_*` collections
and their profile metadata tags keep working.

**Public surface** — MCP tool names/signatures and CLI subcommands are
unchanged. Python import paths under `rag_mcp.*` v1 names are removed.

**Tooling** — `pyproject.toml` import-linter contracts extended, coverage
`omit` list trimmed, `python-semantic-release` produces v2.0.0.

**Verification** — `uv run pytest -m "not slow" --cov=rag_mcp` at the AGENTS.md
floors (Core+MCP ≥95%, Orchestration ≥85%, Overall ≥90%), `uv run lint-imports`
green against the new contracts, `openspec validate --all --strict` clean.
