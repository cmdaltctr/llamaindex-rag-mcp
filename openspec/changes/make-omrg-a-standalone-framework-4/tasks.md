# Tasks: make-omrg-a-standalone-framework-4

Land after changes 1–3. Group 1 is a content-neutral rename and must be its
own commit. Groups 2–5 are the behavioural work.

## 1. Rename to omrg — one commit, no behaviour change

- [ ] 1.1 `git mv src/rag_mcp src/omrg`.
- [ ] 1.2 Rewrite live `rag_mcp` imports and path references across `src/`,
  `tests/`, `experiments/`, `scripts/`, `.github/workflows`, `codecov.yml`,
  `.coderabbit.yaml`, `.env.example`, contribution docs and active guides.
  Preserve released changelogs, ADR/TDR decisions and archived OpenSpec as
  historical records.
- [ ] 1.3 Update `pyproject.toml`: `project.name` → `omrg`, console-script
  entry points, coverage `source`/`omit` paths, and every import-linter
  contract module name. Regenerate `uv.lock`. Retain `rag-mcp` as a deprecated
  one-major console alias unless the same change migrates all legacy
  LaunchAgent ProgramArguments.
- [ ] 1.4 Update `[tool.semantic_release] version_toml` if the path changed.
- [ ] 1.5 `uv sync && uv run pytest -m "not slow"` — green.
- [ ] 1.6 `uv run lint-imports` — green, no stale ignores.
- [ ] 1.7 Prove the commit is content-neutral: compare the tree hash against
  the pre-rename ref with import lines normalised. A diff beyond import paths
  and packaging metadata means something else was changed — fix before merge.
- [ ] 1.8 Commit alone, with no behavioural change bundled in.

## 2. Public API surface

- [ ] 2.1 Write `src/omrg/__init__.py` exporting `Engine`,
  `EffectiveSettings`, stable result/error types and `__version__`, with an
  explicit `__all__`. Keep ingest/search/answer as explicit Engine methods;
  do not create a module-level default engine.
- [ ] 2.2 Keep imports inside `__init__` lazy (PEP 562 `__getattr__`, the
  pattern already used by `core/ingestion` and `core/retrieval`) so importing
  the package constructs nothing.
- [ ] 2.3 Add a test asserting import of `omrg` resolves no settings,
  constructs no provider/store/model, and mutates no global.
- [ ] 2.4 Add a test asserting the package imports cleanly with no optional
  extras installed, and that using an absent capability raises an actionable
  error naming the extra.
- [ ] 2.5 Replace `__version__` with `importlib.metadata.version("omrg")`.
- [ ] 2.6 Add a test asserting `__version__` equals the distribution metadata
  version — it must fail if a literal is reintroduced.

## 3. The Engine

- [ ] 3.1 Add `src/omrg/engine.py` with
  `Engine(effective_settings: EffectiveSettings)` and
  `Engine.from_environment()` delegating to the composition root. Resolve
  store/embedder/reranker/profile state at construction; resolve optional
  answer completion lazily on `answer()`.
- [ ] 3.2 `Engine` construction MUST NOT call `set_default_store`,
  `set_default_effective_settings`, or assign the LlamaIndex global.
- [ ] 3.3 Add async `ingest` delegating only to `ingest_path_async`, sync
  `search`/listing/deletion methods, and async `answer`, all delegating to the
  existing core operations with the engine's dependencies injected.
- [ ] 3.4 Add an explicit store lifecycle/ownership contract and `close()`
  that releases only engine-owned handles/caches. Shared keyed model artefacts
  remain alive while another Engine references them; test closing A leaves B
  functional.
- [ ] 3.5 Construction failure must name the offending setting and leave no
  partially initialised engine.
- [ ] 3.6 Move the query-embedding LRU cache from module level to engine-owned
  state, keeping the `(query, model_name)` key.

## 4. Engine-scoped embedding

- [ ] 4.1 Add an `embed_model` parameter to `retrieval/dense.py::_embed_query`
  and its callers; remove the `Settings.embed_model` read.
- [ ] 4.2 Add an `embed_model` parameter to
  `ingestion/replacement.py::_embed_missing_nodes`; remove the global read.
- [ ] 4.3 Add an `embed_model` parameter to `write_nodes` on the `VectorStore`
  ABC and both adapters; remove the global read.
- [ ] 4.4 Pass the engine's embedder from `search()` and `ingest_path_async()`
  down to those three seams.
- [ ] 4.5 Change `source_state.py::_runtime_embedding_identity()` to
  fingerprint the injected embedder. Do NOT bump
  `_INDEX_IDENTITY_SCHEMA` — the value must be identical for a
  single-engine process so existing collections do not reprocess.
- [ ] 4.6 Add a test asserting a single-engine process produces an unchanged
  `source_index_identity` for a byte-identical source.
- [ ] 4.7 Add the decisive full-path test: set the LlamaIndex global embedder
  to a throwing sentinel, construct two engines with distinguishable
  embedders, ingest/search both collections, and assert every vector/query
  came from its Engine. This fails if any direct-Engine seam still reads the
  global.
- [ ] 4.8 Add a test interleaving two engines' ingest and search operations,
  asserting no operation observes the other's model.
- [ ] 4.9 Confirm the embedding-identity guard still rejects a mismatched
  collection.

## 5. Server startup path

- [ ] 5.1 Keep the composition root as the sole `get_settings()` caller;
  reimplement `ensure_runtime_setup()` and `Engine.from_environment()` through
  one root factory that builds/installs the default Engine. Assign the
  LlamaIndex global only for the legacy transport startup path.
- [ ] 5.2 Confirm MCP, CLI and watcher behaviour; add an upgrade test that
  discovers `com.rag-mcp.watch.*` plists and rewrites their absolute command,
  or prove the one-major `rag-mcp` console alias prevents dead/duplicate
  watchers while preserving existing labels and log paths.
- [ ] 5.3 Add a test asserting a directly-constructed engine works without
  `ensure_runtime_setup()` having been called.
- [ ] 5.4 Confirm startup remains fail-fast on invalid provider, store or
  strategy names.

## 6. Settings-resolution boundary

- [ ] 6.1 Confirm the composition root remains the sole production
  `get_settings()` call site and `Engine.from_environment()` delegates to it.
- [ ] 6.2 Add a test asserting an engine built from explicit settings never
  calls `get_settings()` and reads no environment variable.
- [ ] 6.3 Update the `test_no_global_settings_reads` guard to match the
  narrowed rule.

## 7. Validation and documentation

- [ ] 7.1 `uv run pytest -m "not slow" --cov=omrg` — green, coverage floors
  held.
- [ ] 7.2 `uv run lint-imports` — green, no new ignores.
- [ ] 7.3 Re-run Tier 1 and Tier 2 quality gates; results MUST be unchanged,
  since no retrieval behaviour changed. A difference means an embedder seam
  was wired wrongly.
- [ ] 7.4 `openspec validate make-omrg-a-standalone-framework-4 --strict`.
- [ ] 7.5 Extend `test_docs_references.py` with a curated live-surface gate for
  stale `rag_mcp` paths. Exclude released changelogs, ADR/TDR history and
  `openspec/changes/archive/**`; do not rewrite historical provenance.
- [ ] 7.6 Rewrite `README.md` around library usage first, transports second.
- [ ] 7.7 Update `AGENTS.md`: package name, module paths, and the retired
  process-scoped embedding invariant.
- [ ] 7.8 Add a `docs/guides/library-usage.md` covering `Engine`, explicit
  settings, two-engine usage and `close()`.
- [ ] 7.9 CHANGELOG entry stating plainly: import path and distribution
  changed, stored data did not.
- [ ] 7.10 Write ADR: "omrg is a framework; MCP is a transport" recording D1,
  D2, D3 and D7.
- [ ] 7.11 Supersede ADR-047 decision 7 with an ADR recording engine-scoped
  embedding, linking back to the original.
- [ ] 7.12 Confirm `.github/workflows/ci.yml`, `codecov.yml`,
  `.coderabbit.yaml`, root configuration and the regenerated lockfile contain
  the new live paths, and that `lancedb.py` remains at or below 500 lines after
  change 2.
