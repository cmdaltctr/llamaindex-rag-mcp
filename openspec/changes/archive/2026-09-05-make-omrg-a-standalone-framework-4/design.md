# Design: make-omrg-a-standalone-framework-4

## Context

Verified against `v3` at `4585972`.

- `src/rag_mcp/__init__.py` contains a docstring and
  `__version__ = "1.8.0"`. `pyproject.toml` declares `version = "2.2.0"`, and
  `[tool.semantic_release] version_toml = ["pyproject.toml:project.version"]`
  updates only the TOML value. The literal has drifted since v1.8.
- `compose.ensure_runtime_setup()` mutates four process-global things:
  `LlamaIndexSettings.embed_model`, the default vector store via
  `set_default_store`, the default effective settings via
  `set_default_effective_settings`, and the `_runtime_setup_done` flag.
- `EMBEDDING_PROVIDER_SCOPE = "process"` (`compose.py:36`), recorded as
  ADR-047 decision 7 and specified in `vectordb-abstraction` under
  "Embedding-provider swappability scope is explicit".
- `core/` reads its embedder through the LlamaIndex global in three places:
  `core/retrieval/dense.py` (`Settings.embed_model.get_query_embedding`),
  `core/ingestion/replacement.py` (`_embed_missing_nodes`), and
  `core/vectordb/lancedb.py` / `chroma.py` (`write_nodes`). Each is the seam
  that must take an injected embedder instead.
- Embedding is not the only global seam. The stores themselves read process
  defaults during operation: both `_default_page_size()` implementations
  (`lancedb.py`, `chroma.py`, invoked by `PagedReadMixin` whenever a page size
  is omitted) call `get_default_effective_settings().chroma_scan_page_size`;
  `lancedb.py::_get_connection` falls back to the process-default
  `lancedb_uri`; `chroma.py` falls back to the process-default
  `chroma_persist_dir`. An engine with its own store can therefore still read
  process-default settings mid-operation.
- `core/ingestion/pipeline.py::ingest_path_async` has no store parameter and
  calls `get_default_store()` unconditionally (`pipeline.py:185`). Retrieval
  is already better: `search()` accepts an injected store.
- `core/ingestion/source_state.py::_runtime_embedding_identity()` fingerprints
  `LlamaIndexSettings.embed_model` into `source_index_identity`.
- `BM25SparseRetriever._cache` is a class-level dict keyed by
  `(store_identity, collection)` — process-scoped derivative state ADR-047
  itself lists as a lifecycle limitation.
- `VectorStore` (base.py) has no `close()` or lifecycle method, so disposal
  cannot be expressed backend-neutrally today.
- The `settings-dependency-injection` spec requires `compose.py` to be the
  sole production `get_settings()` caller, and the `test_no_global_settings_reads`
  guard enforces this only for `core/` and `integrations/`. The current source
  has one violation outside that scope:
  `transports/cli/install_login_watcher.py::_contention_warning()` calls
  `get_settings()` to inspect the selected store. (`compose_answer.py` also
  calls `get_settings()`, but it is a sanctioned composition-root sibling
  re-exported by `compose.py`, per its own docstring.)
- Import-linter contracts in `pyproject.toml` name `rag_mcp.*` modules
  extensively, with `unmatched_ignore_imports_alerting = "error"` on most.
- Path-based test guards hard-code `src/rag_mcp`
  (`tests/test_file_size_ceiling.py`, `tests/test_no_global_settings_reads.py`);
  after the rename they could pass vacuously unless they assert the source
  root exists.
- Precedent for clean breaks: the v1 top-level shims were deleted outright in
  v2.0.0 rather than carried.

## Goals / Non-Goals

**Goals**

- A public API a consumer can use without importing private modules.
- Composition that a caller owns, with no process-global side effects.
- Two engines with different embedding models coexisting in one process.
- A package identity that does not assert an affiliation or a transport.
- A version that cannot drift.

**Non-Goals**

- HTTP runtime, authentication, tenancy, streaming — scaffolded separately and
  deferred until the deployment target is chosen.
- Any change to retrieval, ranking, chunking, scoring or storage behaviour.
- Async-native public API. The existing sync/async split is preserved as-is;
  changing it is a separate concern.
- A `rag_mcp` compatibility shim.
- Making process-wide ingestion coordination primitives (the write lock,
  embed semaphores, shutdown event in `core/ingestion/_state.py`)
  engine-scoped. They are coordination, not configuration or provider
  ownership, and stay process-scoped.

## Decisions

### D1: The rename lands as its own commit, before the behavioural work

`git mv src/rag_mcp src/omrg`, then a mechanical import rewrite, then the
`pyproject.toml` updates (name, scripts, Hatch wheel packages and
force-includes, coverage paths, import-linter module names, semantic-release
config). One commit, no behaviour change, `pytest` green on both sides.

The behavioural work in D2–D4 lands after. This matters for bisect: a rename
touching nearly every file, mixed with a composition change, produces a commit
where a regression cannot be attributed. Separating them costs nothing.

The commit is content-neutral in this precise sense: it performs only the
mechanical identity substitutions the rename requires — `rag_mcp` → `omrg`
package/module paths, `src/rag_mcp` → `src/omrg` filesystem and packaging
paths, selected `rag-mcp` → `omrg` command/distribution references,
import-string registry entries, and the packaging/workflow/coverage/
import-linter configuration lines that name them. No algorithmic, structural
or behavioural code changes, no prose redesign. Verification compares the tree
hash against the pre-rename ref after normalising exactly those permitted
substitutions (not merely import lines — the permitted set is broader, as
listed above). A diff beyond the permitted set means something else was
changed — fix before merge.

### D2: `compose` constructs; `Engine` owns and operates

`compose.py` remains the object-construction root, exactly as the
`config-composition-root` spec requires: it is the only module that
instantiates providers, stores and pipeline objects. The engine does not
become a second construction root. Construction functions in `compose.py`
resolve settings, build the embedder/store/reranker/profile resolver, and
return an Engine that owns those dependencies and their lifetime.

The constructor contract is explicit. `EffectiveSettings` deliberately
excludes construction-time values — the composition spec forbids copying
Chroma Cloud credentials into it, and it carries no `chroma_mode`,
`chroma_cloud_*` or `vector_store_provenance`. So an Engine cannot be built
from `EffectiveSettings` alone, and must not be:

```
compose.build_engine(settings=None) -> Engine
    # resolves Settings from the environment (sole get_settings() caller),
    # constructs store/embedder/reranker, derives EffectiveSettings,
    # returns an Engine owning them. No process-global installation.

Engine(effective_settings, *, store, embed_model, reranker=None, ...)
    # owns already-composed dependencies. Does not construct providers.

Engine.from_environment()
    # thin classmethod delegating to compose.build_engine().
    # Side-effect-free: it never installs process globals.
```

Direct construction (`Engine(...)`) receives already-composed dependencies.
`Engine.from_environment()` delegates to `compose.build_engine()`. Only the
legacy server startup path (`ensure_runtime_setup()`) installs process
defaults, and it does so by calling the same builder and then installing the
result. One construction path, two installation policies.

The public operation surface on Engine is deliberately small and mirrors the
existing core signatures (return shapes stay the existing plain `dict` /
`list[dict]`; no new result or exception DTO classes are introduced — errors
propagate as the existing core exceptions, e.g. `ValueError` for invalid
configuration and `ImportError` for missing extras):

- `async ingest(path, *, collection_name="documents", chunk_size=None,
  chunk_overlap=None, progress_callback=None) -> dict`
- `search(query, *, collection_name="documents", ...retrieval overrides as in
  core.search...) -> list[dict]`
- `async answer(question, *, collection_name="documents", ...) -> dict`
  (completion resolved lazily)
- `list_collections() -> list[str]`, `delete_collection(name) -> None`
- `close() -> None`

Alternatives considered:

- *Module-level functions with an implicit default engine* — friendlier for
  one-liners, but it reintroduces exactly the process-global the change
  exists to remove. A default engine may be offered later as sugar over an
  explicit one, never as the only path.
- *A `Settings`-carrying context manager instead of an object* — hides the
  lifetime rather than naming it, and makes two concurrent engines awkward.
- *`Engine(effective_settings)` resolving its own providers* — contradicts
  the composition-root invariant and cannot work for Chroma Cloud without
  smuggling credentials into `EffectiveSettings`.

### D3: The embedder and store are injected through every seam that reads a global today

`core/` reaches `LlamaIndexSettings.embed_model` in three places, and the
stores read process-default settings in three more. Each becomes
engine-supplied state:

| Site | Today | After |
| --- | --- | --- |
| `retrieval/dense.py::_embed_query` | reads the global | takes `embed_model` |
| `ingestion/replacement.py::_embed_missing_nodes` | reads the global | takes `embed_model` |
| `vectordb/*.py::write_nodes` | reads the global | takes `embed_model` |
| `ingestion/pipeline.py::ingest_path_async` | `get_default_store()` unconditionally | accepts an injected store; the direct-Engine path never calls `get_default_store()` |
| `lancedb.py` / `chroma.py` `_default_page_size()` | reads process-default settings | uses an instance field supplied at construction |
| `lancedb.py::_get_connection` URI fallback, `chroma.py` persist-dir fallback | reads process-default settings | resolved at construction from construction-time settings |

The LlamaIndex global may still be assigned by the legacy server startup path,
but every operation reachable through a directly constructed Engine must pass
its embedder through all LlamaIndex internals it uses or avoid the
global-dependent adapter. A full-path sentinel test sets the global to a
throwing model and interleaves two engines; construction alone is not proof.

This is the load-bearing decision of the change. Without it, "engine-scoped
embedding" is a claim the runtime cannot honour, and ADR-047 decision 7 stands.

The query-embedding LRU cache is already keyed by `(query, model_name)`, so it
stays correct under interleaving; it moves from a module-level cache to an
engine-owned one so two engines with same-named models cannot share entries.
This modifies the `query-embedding-cache` capability and carries its own
delta spec.

The BM25 sparse cache (`BM25SparseRetriever._cache`) stays keyed by
`(store_identity, collection)` but gains targeted eviction (D9) so closing an
engine releases its own entries without clearing another engine's.

### D4: `_runtime_embedding_identity()` fingerprints the injected embedder

It currently inspects `LlamaIndexSettings.embed_model`. It takes the engine's
embedder instead. Same fields (`class` = `module.qualname`, `model` = first
available selector), same serialisation shape, and no change to
`_INDEX_IDENTITY_SCHEMA` (currently 3): preserve the schema version delivered
by change 1. The value is identical for a single-engine process, so existing
collections do not reprocess a second time.

This is deliberate: change 1 already forces a reprocess for its own reasons.
This change must not force a second one. The equivalence test (task 4.7)
compares the old/global calculation against the new/injected calculation
using the same embedder fixture before the old path is removed.

Two related-but-separate identity guards must both stay compatible: the
source-level `source_index_identity` in `source_state.py`, and the
collection-level `EmbeddingIdentity` enforced by the store adapters.

### D5: `ensure_runtime_setup()` is reimplemented, not removed

It becomes: call `compose.build_engine()`, then install the result as the
process default (default store, default effective settings) and assign the
LlamaIndex global for the legacy transport startup path. The builder itself
never installs anything; the installer never constructs directly.
`Engine.from_environment()` delegates to the builder only and is
side-effect-free. The MCP server, CLI and watcher keep calling
`ensure_runtime_setup()` and keep working unchanged.

Removing it would turn a surface change into a transport change across three
entry points for no benefit. Keeping it as *a* caller of the engine, rather
than *the* composition mechanism, is the whole point.

### D6: `__version__` comes from installed metadata

`importlib.metadata.version("omrg")`, with a test asserting it equals the
distribution version. No second update site for semantic-release, and the
1.8.0-versus-2.2.0 drift becomes unrepresentable.

### D7: No Python import shim; keep the installed command surface via a one-major alias

`rag_mcp` disappears as a Python import. The break is declared as a major and
ships with a migration guide. That does not justify breaking already-installed
LaunchAgents. The chosen strategy, decided now rather than left open:

- `omrg` becomes the primary console command.
- `rag-mcp` is retained as a deprecated console alias for one major, so
  installed LaunchAgents keep working and no plist migration routine is
  written in this change.
- The watcher installer keeps resolving the `rag-mcp` alias, keeps the
  existing `com.rag-mcp.watch.*` label scheme, and keeps the
  `~/Library/Logs/rag-mcp/` log paths during the compatibility period. It
  detects existing matching agents and never creates a duplicate under a new
  label.
- Migrating the installer surfaces (labels, log paths, resolved command) to
  `omrg` is deferred to the change that removes the alias.

The CHANGELOG entry and release notes must say plainly: the import path
changed, the distribution changed, stored data did not.

### D8: Mechanical coverage includes repository controls

The content-neutral rename covers `.github/workflows`, `codecov.yml`,
`.coderabbit.yaml`, `.env.example`, contribution docs, lockfile regeneration,
coverage paths, Hatch wheel/package-data configuration and every
import-linter string. Path-based test guards (`test_file_size_ceiling.py`,
`test_no_global_settings_reads.py`) are updated in the same commit and made
to assert their configured source root exists, so a stale `src/rag_mcp` path
cannot pass vacuously. The stale-reference gate uses a curated live-surface
allowlist; it does not rewrite history. Implement change 4 only from the
integrated changes 1–3 HEAD, and keep `lancedb.py` within 500 lines after
change 2's adapter seam.

### D9: Disposal is backend-neutral and additive

`VectorStore` gains a `close()` lifecycle method with a safe default no-op
implementation on the ABC, so an Engine can express disposal against the
abstraction; each adapter implements backend-specific release where the
backend supports it. `Engine.close()`:

- closes its owned store via `VectorStore.close()`;
- releases engine-owned caches (the query-embedding LRU is dropped entirely);
- evicts only the BM25 cache entries in its own stores' identity namespace —
  never another engine's entries;
- does not touch the process-wide ingestion coordination primitives
  (`_state.py` write lock, embed semaphores, shutdown event) — in
  particular it MUST NOT set the global shutdown event.

Immutable model artefacts (the reranker's keyed model cache) remain shared
and stay alive while another engine references them. Closing engine A leaves
engine B functional.

## Risks

| Risk | Mitigation |
| --- | --- |
| The rename's mechanical rewrite silently changes content | Land it as a content-neutral commit per D1's permitted-substitution list; verify with a rename-aware normalised tree-hash comparison against the pre-rename ref |
| Import-linter contracts break en masse on the rename | They are module-name strings; update them in the same commit and require `lint-imports` green before merge |
| Path-based guards pass vacuously after the rename | Task 1.x makes every path-based guard assert its configured source root exists |
| An `Engine` API invites a second, divergent code path | `compose.build_engine()` is the single construction path; `ensure_runtime_setup` becomes an installer over it, so there is one construction path, not two |
| Injected embedder or store missed at one seam, leaving a hidden global read | Full-path tests run with no process default installed and a throwing LlamaIndex global, covering ingest, dense search, hybrid/BM25 iteration and paged listing (task 4.8) |
| Two engines exhaust memory (two stores, two ONNX sessions) | `close()` is explicit; the reranker's model cache is already keyed by `(backend, model_id)` and shared safely |
| Closing one engine breaks another | `close()` is scoped per D9: own store namespace eviction only, shared artefacts untouched; tested with two engines |
| Public API surface locks in mistakes | The initial surface is deliberately minimal (D2); dictionary result shapes are documented as the v3 contract rather than inventing DTOs under time pressure |
| Live and historical records reference `rag_mcp` | Gate active code/config/docs only; preserve released changelogs, ADR/TDR decisions and archived OpenSpec as historical provenance, with a migration guide for current users |
