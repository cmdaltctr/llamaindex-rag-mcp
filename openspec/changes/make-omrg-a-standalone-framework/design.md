# Design: make-omrg-a-standalone-framework

## Context

Verified against `v3` at `c9d2906`.

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
- `core/ingestion/source_state.py::_runtime_embedding_identity()` fingerprints
  `LlamaIndexSettings.embed_model` into `source_index_identity`.
- `settings-dependency-injection` currently requires `compose.py` to be the
  only `get_settings()` caller.
- Import-linter contracts in `pyproject.toml` name `rag_mcp.*` modules
  extensively, with `unmatched_ignore_imports_alerting = "error"` on most.
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

## Decisions

### D1: The rename lands as its own commit, before the behavioural work

`git mv src/rag_mcp src/omrg`, then a mechanical import rewrite, then the
`pyproject.toml` updates (name, scripts, import-linter module names, coverage
paths, semantic-release config). One commit, no behaviour change, `pytest`
green on both sides.

The behavioural work in D2–D4 lands after. This matters for bisect: a rename
touching nearly every file, mixed with a composition change, produces a commit
where a regression cannot be attributed. Separating them costs nothing.

The tree-hash check from the project's own known-workarounds applies — a
rename commit must change paths, never content beyond the import lines.

### D2: `Engine` is a constructed object; the module-level API is a thin wrapper

```
omrg.Engine(settings=None)      # resolves env when settings is None
engine.ingest(path, collection=...)
engine.search(query, collection=..., ...)
engine.answer(question, collection=...)   # after change 3
engine.close()
```

The engine holds the resolved settings, the vector store, the embedder, the
reranker, the profile resolver and the answer LLM. It is the thing that
`compose` builds today, made explicit and given a lifetime.

Alternatives considered:

- *Module-level functions with an implicit default engine* — friendlier for
  one-liners, but it reintroduces exactly the process-global the change
  exists to remove. A default engine may be offered later as sugar over an
  explicit one, never as the only path.
- *A `Settings`-carrying context manager instead of an object* — hides the
  lifetime rather than naming it, and makes two concurrent engines awkward.

`close()` is explicit rather than relying on garbage collection: LanceDB
connections and ONNX sessions are real resources, and the BM25 cache holds
strong references to store instances (noted in ADR-047).

### D3: The embedder is injected through the seams that read the global today

`core/` currently reaches `LlamaIndexSettings.embed_model` in three places.
Each becomes a parameter supplied by the engine:

| Site | Today | After |
| --- | --- | --- |
| `retrieval/dense.py::_embed_query` | reads the global | takes `embed_model` |
| `ingestion/replacement.py::_embed_missing_nodes` | reads the global | takes `embed_model` |
| `vectordb/*.py::write_nodes` | reads the global | takes `embed_model` |

The LlamaIndex global is still assigned by the server startup path, because
LlamaIndex internals used elsewhere (the metadata `IngestionPipeline`, the
`VectorStoreIndex` adapter) consult it. The difference is that `core/` no
longer *depends* on it: an engine passes its own embedder explicitly, so two
engines produce correct vectors regardless of what the global happens to hold.

This is the load-bearing decision of the change. Without it, "engine-scoped
embedding" is a claim the runtime cannot honour, and ADR-047 decision 7 stands.

The query-embedding LRU cache is already keyed by `(query, model_name)`, so it
stays correct under interleaving; it moves from a module-level cache to an
engine-owned one so two engines with same-named models cannot share entries.

### D4: `_runtime_embedding_identity()` fingerprints the injected embedder

It currently inspects `LlamaIndexSettings.embed_model`. It takes the engine's
embedder instead. Same fields, same hash shape, no change to
`_INDEX_IDENTITY_SCHEMA` — the value is identical for a single-engine process,
so existing collections do not reprocess as a result of this change.

This is deliberate: change 1 already forces a reprocess for its own reasons.
This change must not force a second one.

### D5: `ensure_runtime_setup()` is reimplemented, not removed

It becomes: build the default engine from the environment, install it as the
process default, assign the LlamaIndex global for the library internals that
still need it. The MCP server, CLI and watcher keep calling it and keep
working unchanged.

Removing it would turn a surface change into a transport change across three
entry points for no benefit. Keeping it as *a* caller of the engine, rather
than *the* composition mechanism, is the whole point.

### D6: `__version__` comes from installed metadata

`importlib.metadata.version("omrg")`, with a test asserting it equals the
distribution version. No second update site for semantic-release, and the
1.8.0-versus-2.2.0 drift becomes unrepresentable.

### D7: No shim, and the break is stated loudly

`rag_mcp` disappears. The project's own precedent is clean breaks on majors,
this lands on the breaking branch, and a shim for a package with no external
consumers would be dead code from the day it shipped.

The CHANGELOG entry and release notes must say plainly: the import path
changed, the distribution changed, stored data did not.

## Risks

| Risk | Mitigation |
| --- | --- |
| The rename's mechanical rewrite silently changes content | Land it as a content-neutral commit; verify with a tree-hash comparison against the pre-rename ref, per the project's known-workaround for history rebuilds |
| Import-linter contracts break en masse on the rename | They are module-name strings; update them in the same commit and require `lint-imports` green before merge |
| An `Engine` API invites a second, divergent code path | The engine builds the same objects `compose` builds today; `ensure_runtime_setup` becomes a caller of it, so there is one construction path, not two |
| Injected embedder missed at one seam, leaving a hidden global read | Add a test that constructs two engines with distinguishable embedders and asserts each collection's vectors came from the right one — it fails if any seam still reads the global |
| Two engines exhaust memory (two stores, two ONNX sessions) | `close()` is explicit; the reranker's model cache is already keyed by `(backend, model_id)` and shared safely |
| Docs and ADRs reference `rag_mcp` in dozens of places | The existing `test_docs_references.py` gate covers documentation drift; extend it to fail on `rag_mcp` after the rename |
