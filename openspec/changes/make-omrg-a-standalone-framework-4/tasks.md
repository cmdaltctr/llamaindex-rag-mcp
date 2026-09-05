# Tasks: make-omrg-a-standalone-framework-4

Land after changes 1–3. Group 1 is the isolated mechanical rename and must be
its own commit. Groups 2–6 implement the API and lifetime behaviour. Group 7
validates and documents the completed change.

## 1. Rename to omrg — one commit, no behaviour change

- [x] 1.1 `git mv src/rag_mcp src/omrg`.
- [x] 1.2 Rewrite live `rag_mcp` imports and path references across `src/`,
  `tests/`, `experiments/`, `scripts/`, `.github/workflows`, `codecov.yml`,
  `.coderabbit.yaml`, `.env.example`, contribution docs and active guides.
  Preserve released changelogs, ADR/TDR decisions and archived OpenSpec as
  historical records.
- [x] 1.3 Update `pyproject.toml`: `project.name` → `omrg`, console-script
  entry points (keep `rag-mcp` as the deprecated one-major alias), coverage
  `source`/`omit` paths, every import-linter contract module name, the
  `[tool.hatch.build.targets.wheel]` `packages` list and every
  force-include source/destination package path. Regenerate `uv.lock`.
- [x] 1.4 Update `[tool.semantic_release] version_toml` if the path changed.
- [x] 1.5 Update every path-based test guard that names `src/rag_mcp`
  (including `tests/test_file_size_ceiling.py` and
  `tests/test_no_global_settings_reads.py`), and make each guard assert its
  configured source root exists so a stale path cannot pass vacuously.
- [x] 1.6 Verify packaged YAML resources resolve from an installed wheel
  (`config/defaults.yaml`, `config/profiles/*.yaml` via the updated Hatch
  force-includes).
- [x] 1.7 `uv sync && uv run pytest -m "not slow"` — green.
- [x] 1.8 `uv run lint-imports` — green, no stale ignores.
- [x] 1.9 Prove the commit is content-neutral per design D1: compare the tree
  hash against the pre-rename ref after normalising exactly the permitted
  substitutions (package/module paths, filesystem and packaging paths,
  command/distribution references, import-string registry entries). A diff
  beyond that permitted set means something else was changed — fix before
  merge.
- [x] 1.10 Commit alone, with no behavioural change bundled in.

## 2. Public API surface

- [x] 2.1 Write `src/omrg/__init__.py` exporting exactly `Engine`,
  `EffectiveSettings` and `__version__` with an explicit `__all__`. Do not
  export registries, adapters, builders or convenience helpers. Do not
  create a module-level default engine.
- [x] 2.2 Keep imports inside `__init__` lazy (PEP 562 `__getattr__`, the
  pattern already used by `core/ingestion` and `core/retrieval`) so importing
  the package constructs nothing.
- [x] 2.3 Add a test asserting import of `omrg` resolves no settings,
  constructs no provider/store/model, and mutates no global.
- [x] 2.4 Add a test asserting the package imports cleanly with no optional
  extras installed, and that using an absent capability raises an actionable
  error naming the extra.
- [x] 2.5 Add a test asserting the Engine's public method set is exactly the
  documented surface (async `ingest`, sync `search`, async `answer`, sync
  `list_collections`, sync `delete_collection`, sync `close`) with the
  existing `dict`/`list[dict]` result shapes and existing core exceptions —
  no new result/error DTO classes.
- [x] 2.6 Replace `__version__` with `importlib.metadata.version("omrg")`.
- [x] 2.7 Add a test asserting `__version__` equals the distribution metadata
  version — it must fail if a literal is reintroduced.

## 3. The Engine

- [x] 3.1 Add `compose.build_engine()` as the single construction path: it
  resolves `Settings`, constructs embedder/store/reranker/profile resolver,
  derives `EffectiveSettings`, and returns an `Engine` that owns those
  dependencies. `Engine(effective_settings, *, store, embed_model, ...)`
  accepts already-composed dependencies and constructs nothing itself —
  `compose.py` remains the sole construction root. Resolve optional answer
  completion lazily on `answer()`.
- [x] 3.2 `Engine` construction — direct or via `Engine.from_environment()`
  — MUST NOT call `set_default_store`, `set_default_effective_settings`, or
  assign the LlamaIndex global. `from_environment()` delegates to
  `compose.build_engine()` and stays side-effect-free.
- [x] 3.3 Add the Engine operations per the public surface (2.5), all
  delegating to the existing core operations with the engine's dependencies
  injected.
- [x] 3.4 Add `VectorStore.close()` with a safe default no-op on the ABC and
  backend-specific release where supported; implement both adapters. Add
  `Engine.close()`: close the owned store, release the engine-owned caches,
  evict only the BM25 cache entries in this engine's stores' identity
  namespace, and never touch process-wide ingestion coordination state
  (`_state.py`). Test closing A leaves B functional.
- [x] 3.5 Construction failure must name the offending setting and leave no
  partially initialised engine.
- [x] 3.6 Move the query-embedding LRU cache from module level to
  engine-owned state, keeping the `(query, model_name)` key, per the
  `query-embedding-cache` delta spec: shared between filtered/unfiltered
  search within one engine, never between engines, released on `close()`.

## 4. Engine-scoped embedding and stores

- [x] 4.1 Add an `embed_model` parameter to `retrieval/dense.py::_embed_query`
  and its callers; remove the `Settings.embed_model` read.
- [x] 4.2 Add an `embed_model` parameter to
  `ingestion/replacement.py::_embed_missing_nodes`; remove the global read.
- [x] 4.3 Add an `embed_model` parameter to `write_nodes` on the `VectorStore`
  ABC and both adapters; remove the global read.
- [x] 4.4 Add an injected `store: VectorStore | None` parameter to
  `ingest_path_async()` (replacing the unconditional `get_default_store()`
  at `pipeline.py:185`) and pass the engine-owned store through the full
  ingestion path, including source replacement. Direct-Engine ingestion MUST
  NOT call `get_default_store()`. Pass the engine's embedder from `search()`
  and `ingest_path_async()` down to the three embedder seams.
- [x] 4.5 Make the scan page size an instance field on both stores,
  supplied from construction-time settings; `_default_page_size()` MUST use
  the instance value, never `get_default_effective_settings()`. Resolve the
  LanceDB connection URI and Chroma persist directory at construction the
  same way, removing their process-default fallbacks.
- [x] 4.6 Change `source_state.py::_runtime_embedding_identity()` to
  fingerprint the injected embedder. Do NOT bump
  `_INDEX_IDENTITY_SCHEMA` — the value must be identical for a
  single-engine process so existing collections do not reprocess.
- [x] 4.7 Add a test comparing the old/global and new/injected identity
  calculations using the same embedder fixture, proving byte-identical
  `source_index_identity` before the old path is removed.
- [ ] 4.8 Add the decisive full-path test: with no process-default store and
  no process-default effective settings installed, and the LlamaIndex global
  embedder set to a throwing sentinel, construct two engines with
  distinguishable embedders and run ingest, dense search, hybrid/BM25
  retrieval, and listing/paged reads on both. Assert every vector/query came
  from its engine and no path fell back to a process default. This fails if
  any direct-Engine seam still reads a global.
- [ ] 4.9 Add a test interleaving two engines' ingest and search operations,
  asserting no operation observes the other's model.
- [x] 4.10 Confirm both embedding-identity guards still reject a mismatched
  collection: source-level `source_index_identity` and collection-level
  `EmbeddingIdentity`.

## 5. Server startup path

- [x] 5.1 Split building from installing: `compose.build_engine()` resolves
  and constructs with no global installation; `ensure_runtime_setup()` calls
  the builder, then installs the result as the process default (default
  store, default effective settings) and assigns the LlamaIndex global only
  for legacy transport compatibility.
- [x] 5.2 Confirm MCP, CLI and watcher behaviour unchanged. Keep the
  `rag-mcp` one-major console alias: the installer continues resolving
  `rag-mcp`, keeps `com.rag-mcp.watch.*` labels and
  `~/Library/Logs/rag-mcp/` log paths, and detects existing matching agents
  without creating duplicates. No plist migration in this change.
- [x] 5.3 Add a test asserting a directly-constructed engine works without
  `ensure_runtime_setup()` having been called (covered fully by 4.8).
- [x] 5.4 Confirm startup remains fail-fast on invalid provider, store or
  strategy names.

## 6. Settings-resolution boundary

- [x] 6.1 Remove the direct `get_settings()` call from
  `transports/cli/install_login_watcher.py::_contention_warning()` — pass the
  already-resolved adapter name in, obtained through the composition-root
  surface.
- [x] 6.2 Confirm `compose.build_engine()` is the sole environment-resolution
  entry point and `Engine.from_environment()` delegates to it.
- [x] 6.3 Add a test asserting an engine built from explicit dependencies
  and settings never calls `get_settings()` and reads no environment
  variable.
- [x] 6.4 Widen the `test_no_global_settings_reads` guard to scan the full
  production package, permitting only `compose.py` and its sanctioned
  composition-root sibling `compose_answer.py`.

## 7. Validation and documentation

- [x] 7.1 `uv run pytest -m "not slow" --cov=omrg` — green, coverage floors
  held.
- [x] 7.2 `uv run lint-imports` — green, no new ignores.
- [x] 7.3 Re-run Tier 1 and Tier 2 quality gates; results MUST be unchanged,
  since no retrieval behaviour changed. A difference means an embedder seam
  was wired wrongly.
- [ ] 7.4 `openspec validate make-omrg-a-standalone-framework-4 --strict`.
- [x] 7.5 Extend `test_docs_references.py` with a curated live-surface gate for
  stale `rag_mcp` paths. Exclude released changelogs, ADR/TDR history and
  `openspec/changes/archive/**`; do not rewrite historical provenance.
- [x] 7.6 Rewrite `README.md` around library usage first, transports second.
- [x] 7.7 Update `AGENTS.md`: package name, module paths, and the retired
  process-scoped embedding invariant.
- [x] 7.8 Update the package `description` and other live release metadata
  that still describe the project solely as a "LlamaIndex RAG MCP server".
  Keep this prose change out of the content-neutral Group 1 commit.
- [x] 7.9 Add a `docs/guides/library-usage.md` covering `Engine`, explicit
  settings, two-engine usage and `close()`.
- [x] 7.10 CHANGELOG entry stating plainly: import path and distribution
  changed, stored data did not.
- [x] 7.11 Write ADR: "omrg is a framework; MCP is a transport" recording
  D1, D2, D3, D5 and D7.
- [x] 7.12 Supersede ADR-047 decision 7 with an ADR recording engine-scoped
  embedding, linking back to the original.
- [x] 7.13 Confirm `.github/workflows/ci.yml`, `codecov.yml`,
  `.coderabbit.yaml`, root configuration and the regenerated lockfile contain
  the new live paths, and that `lancedb.py` remains at or below 500 lines
  after change 2.
