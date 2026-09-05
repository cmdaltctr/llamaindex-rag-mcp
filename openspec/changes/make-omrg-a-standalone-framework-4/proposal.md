# Make omrg a standalone framework

## Why

This project was built as an MCP server in v1 and carried that shape into v2.
The name says so, the package exports say so, and the startup path says so.
But MCP is one transport. The CLI is another, a watcher daemon is a third, and
an HTTP API is coming. The retrieval engine underneath is not an MCP feature —
it is the product.

The architecture already reflects that, and it is enforced rather than
intended: `core/` never imports `transports/`, import-linter proves it in CI,
`lancedb` and `chromadb` are confined to their adapters, every strategy
resolves through a registry, and the CLI, the MCP server, the watcher daemon
and the test suite drives `core/` directly. That is the expensive half of
being a framework and it is done.

The packaging is what has not caught up.

**There is no operational public API.** `src/rag_mcp/__init__.py` contains a
docstring and an importable version string, but exports no engine or
operation. A library user's entry point today is:
import `compose`, call `ensure_runtime_setup()`, then call `search()` with
eight keyword arguments.

**Composition is a process-global side effect.** `ensure_runtime_setup()`
installs three process defaults and a setup flag — LlamaIndex's global
`embed_model`, the default vector store, the default `EffectiveSettings`, and
`_runtime_setup_done` — after first-call settings resolution also initialises
the config cache. That is a correct server startup sequence and a
hostile library API. Two engines cannot coexist in one process, and a caller
cannot construct one from settings they hold in hand rather than in the
environment.

**One embedding model per process.** `EMBEDDING_PROVIDER_SCOPE = "process"`,
recorded in ADR-047 decision 7 as a deliberate limit while LlamaIndex's
`Settings.embed_model` stays global. For a server that is fine. For a
framework indexing two collections on different embedding models, it is a
ceiling — and it is the reason per-collection profiles cannot override the
provider.

**The version is already lying.** `rag_mcp.__version__` reports `1.8.0`;
`pyproject.toml` says `2.2.0`. semantic-release only updates
`version_toml = ["pyproject.toml:project.version"]`, so the package attribute
has drifted since v1.8 and nobody noticed because nothing imports it. The
moment `__version__` is public API, it misreports.

**And the name asserts two things that are false.** `llamaindex-` implies an
affiliation that does not exist and binds the identity to a dependency the
`VectorStore` ABC was explicitly built to outgrow. `-mcp` says the transport
is the product.

Now, because v3 is already the breaking-change branch. A rename and an entry
point change after v3 ships costs a deprecation cycle; before it ships, they
cost a line in `pyproject.toml` and a mechanical import rewrite.

## What Changes

- The project is renamed to **`omrg`** — distribution and import name both.
  `src/rag_mcp/` becomes `src/omrg/`. No compatibility shim, following the
  project's own precedent: the v1 top-level shims were deleted outright in
  v2.0.0 rather than carried.
- `omrg/__init__.py` becomes a real public API centred on `Engine`,
  `EffectiveSettings` and stable result types. Ingest, search and answer are
  explicit Engine methods; no module-level default engine is introduced.
- A new engine object owns its providers, store, reranker and settings for
  its lifetime. The composition root keeps constructing them — a
  `compose.build_engine()` factory resolves settings, builds the
  dependencies and returns an Engine — so no process-global state is
  mutated and the composition-root invariant is preserved. Two engines with
  different configurations coexist in one process.
- Embedding-provider selection becomes engine-scoped rather than
  process-scoped, retiring ADR-047 decision 7. Different engines may target
  different collections/providers; profile-driven routing within one Engine
  remains a separate decision.
- `ensure_runtime_setup()` remains, reimplemented as the server startup path
  that delegates environment resolution to the composition root and installs
  a default engine. Existing transports keep working. The Python import break
  has no shim; `rag-mcp` is retained as a deprecated console alias for one
  major so installed watchers keep working, and the watcher installer keeps
  its existing `com.rag-mcp.watch.*` labels, log paths and command resolution
  for that compatibility period. No plist migration is performed in this
  change.
- `__version__` is single-sourced from installed package metadata, so it
  cannot drift again.

Not in scope: the HTTP runtime, authentication, tenancy and streaming — those
are scaffolded as a separate change and deliberately deferred until the
deployment target is chosen. No retrieval, ingestion or scoring behaviour
changes here; this is a surface and lifetime change, not a pipeline change.

## Capabilities

### New Capabilities

- `public-library-api`: the exported surface, its stability contract, the
  package identity, and version single-sourcing.
- `engine-scoped-composition`: an engine object owning its own providers,
  store and settings, with no process-global mutation and no shared state
  between engines.

### Modified Capabilities

- `vectordb-abstraction`: embedding-provider swappability becomes engine
  scoped rather than process scoped.
- `settings-dependency-injection`: `get_settings()` remains the environment
  resolution path, but an engine constructed from caller-supplied settings
  reaches it never.
- `query-embedding-cache`: the cache ownership moves from process-local to
  engine-local. Behavioural guarantees (keyed by `(query, model_name)`,
  bounded LRU, shared between filtered and unfiltered search within one
  engine) are preserved; entries are never shared between engines.

## Impact

- **Breaking.** Every import path changes, the distribution name changes, and
  the console-script entry points change. This is a v3 major.
- **No data migration.** Stored collections, vectors, metadata and lineage are
  untouched. An index built under `rag-mcp` is readable by `omrg`.
- Code: every module under `src/`, every test import, the import-linter
  contract module names, `pyproject.toml` (name, scripts, semantic-release,
  coverage paths, contracts), and all documentation.
- Live docs/config: `AGENTS.md`, `README.md`, guides, CI, Codecov,
  CodeRabbit, lockfile and release metadata. Released changelogs, ADR/TDR
  decisions and archived OpenSpec remain historical records; new migration
  notes link old and new paths without rewriting provenance.
- Risk concentration: the rename is mechanical but touches roughly every file.
  It should land as its own commit, separate from the behavioural changes in
  this change, so a bisect can distinguish them.
