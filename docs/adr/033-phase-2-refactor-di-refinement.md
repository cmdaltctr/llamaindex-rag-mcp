# ADR-033: Phase 2 Refactor — DI Refinement (Inject Constructed Objects, Resolve Settings at Call Time)

**Date:** 2026-08-04
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `phase-2-refactor-config-core-split` (review follow-ups)
**Follows:** [ADR-031](./031-three-layer-config-compose-di.md)
**Phase:** 2 of 5 (`docs/brainstorm/refactor-proposal/PROPOSAL.md`)

## Context

ADR-031 (Phase 2) established the three-layer architecture: a typed settings
resolver (`config/`), a composition root (`compose.py`), and dependency
injection elsewhere. Its Layer 3 wording stated that business modules
"receive their dependencies as parameters". Reviewing the merged
implementation against that wording surfaced three gaps:

1. **The production path constructed a pipeline object outside the
   composition root.** `core/retrieval/pipeline.py::search()` instantiated
   `CrossEncoderReranker()` directly when the caller did not pass one, and
   `server.py` never passed one — so `compose.build_reranker()` existed but
   was exercised only by tests. The spec scenario "all instantiation MUST
   occur in `compose.py`" was therefore not met by the live call path.
2. **Settings knobs were snapshotted at import time in places.** Defaults
   like `hybrid: bool = settings.hybrid_enabled` (in `search()` and
   `search_documents()`) and `RERANK_MODEL = settings.rerank_model` (in
   `reranker.py`) were evaluated once at module/definition import. A
   post-import patch of `settings.hybrid_enabled` or `settings.rerank_model`
   was silently ignored — inconsistent with `top_k`/`similarity_threshold`,
   which already resolved from the singleton at call time via a `None`
   sentinel.
3. **The legacy `Settings` name changed meaning.** Pre-refactor,
   `from rag_mcp.config import Settings` returned LlamaIndex's global
   settings object. Post-refactor it returns the pydantic resolver model. As
   a real module attribute it bypasses the PEP 562 shim, so no
   `DeprecationWarning` fires and experiment/third-party code using
   `Settings.embed_model` breaks (fixed in the follow-ups by re-exporting
   LlamaIndex's `Settings` from the `rag_mcp.ingestion` shim and importing
   `rag_mcp.compose` for runtime setup).

## Decision

Refine the Phase 2 DI contract into an explicit two-part rule, applied across
the follow-up commits and enforced going forward:

**Part 1 — constructed objects are injected; never constructed in business
modules.** The composition root builds every provider and pipeline object.
`server.py` constructs the reranker once via `compose.build_reranker()` and
injects it into every `search()` call. `core/retrieval/pipeline.py` keeps a
`reranker: CrossEncoderReranker | None = None` parameter; its internal
`CrossEncoderReranker()` construction remains only as a defensive fallback
for direct library callers (process-wide cache means the fallback cannot
re-load the model). `build_reranker()` is therefore live in the production
path, not dead test-only code.

**Part 2 — settings knobs are read from the resolved singleton at call time,
never snapshotted at import or definition time.** Every consumer-facing
default (`top_k`, `similarity_threshold`, `hybrid`, `rerank_model`) resolves
from `settings` at the moment it is needed:

- `search()` and `search_documents()` accept `None` for optional knobs and
  resolve them from `settings` inside the call body.
- `CrossEncoderReranker.__init__` and `_select_onnx_variant` read
  `settings.rerank_model` at construction/call time; the module-level
  `RERANK_MODEL` alias survives only as a legacy export for the compat shim.
- Tests therefore patch singleton attributes
  (`monkeypatch.setattr(settings, "rerank_model", ...)`) rather than
  module-level constants or import-time snapshots.

**Part 3 — the legacy `Settings` name is preserved for the LlamaIndex
global.** `rag_mcp.config.Settings` is the pydantic resolver model (the new
source of truth). `rag_mcp.ingestion.Settings` re-exports
`llama_index.core.Settings` so pre-refactor consumer semantics
(`Settings.embed_model`) keep working. The `config-composition-root` spec
scenario was amended to state the contract as implemented: constructed
objects injected, settings read from the singleton at call time.

## Consequences

### Positive

- The spec's "compose.py is the single construction site" holds in the live
  path: every provider and the reranker are built by the composition root.
- A post-import settings change is honoured everywhere, so tests and runtime
  reconfiguration behave consistently across knobs.
- The process-wide model cache and lazy provider registries mean the injected
  construction adds no startup cost and no model re-loading.
- `rag_mcp.ingestion` retains the legacy `Settings` meaning, so experiment
  code keeps working while the shim window is open (removed in v2.0.0).

### Negative

- The DI contract is weaker than full parameter injection: settings are still
  read from a mutable process-wide singleton rather than passed in. Tests
  that need a distinct configuration must patch the singleton and restore it
  (the `conftest.py` `_isolate_env` fixture does this) rather than passing a
  fresh `Settings` instance.
- `search()` still contains a defensive `CrossEncoderReranker()` fallback, so
  the composition root is the intended — but not the only — construction site
  unless the fallback is removed in a later phase.
- The `hybrid` default changed from a visible `bool` (in the function
  signature) to `None`, which is a subtle API-visible change for callers
  introspecting signatures.

### Neutral

- The spec wording was adjusted to match the implemented contract rather than
  forcing full parameter injection — a deliberate trade-off to avoid churning
  every call site and test for marginal benefit.
- The `Settings` semantic split (pydantic resolver vs LlamaIndex global) is
  documented in ADR-031 and here so the v2.0.0 removal window is predictable.

## Alternatives Considered

| Option | Rejected Because |
|--------|------------------|
| **Full constructor injection of a `Settings` object into every pipeline entry point** | Every call site, MCP tool signature, and test would need to thread a `Settings` argument; the singleton is value-stable for consumers and the knobs are read-only, so the churn outweighed the testability gain. |
| **Keep import-time/definition-time default snapshots** | Inconsistent with `top_k`/`similarity_threshold` (call-time) and silently ignored post-import patches — the exact class of subtle breakage the Phase 2 review flagged. |
| **Remove the `CrossEncoderReranker()` fallback from `search()`** | Direct library callers (experiments, scripts) would need to construct and pass a reranker themselves; the process-wide cache makes the fallback behaviourally identical, so keeping it costs nothing. Deferred to a later phase. |
| **Leave `rag_mcp.config.Settings` shadowing the legacy name with no shim** | Breaks the documented compat guarantee for experiment/third-party code with no `DeprecationWarning` — fixed by re-exporting the LlamaIndex global from `rag_mcp.ingestion` instead. |

## References

- [ADR-031](./031-three-layer-config-compose-di.md) — Three-Layer Architecture — Config, Compose, DI (the parent decision; negative consequences updated)
- PR #13 review follow-up commit `aa32ad0` — implementation of this refinement
- `src/rag_mcp/server.py` — `compose.build_reranker()` wired into `search_documents()`
- `src/rag_mcp/core/retrieval/pipeline.py` — `search()` `None`-sentinel call-time resolution
- `src/rag_mcp/core/retrieval/reranker.py` — `settings.rerank_model` read at construction time
- `src/rag_mcp/ingestion.py` — legacy `Settings` (LlamaIndex global) re-export
- `openspec/changes/phase-2-refactor-config-core-split/specs/config-composition-root/spec.md` — amended "Components receive dependencies" scenario
