# ADR-031: Three-Layer Architecture — Config, Compose, DI

**Date:** 2026-08-04
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `phase-2-refactor-config-core-split`
**Amends:** ADR-006 (aggregation point), ADR-025, ADR-026 (registry relocation)
**Phase:** 2 of 5 (`docs/brainstorm/refactor-proposal/PROPOSAL.md`)

## Context

Before this change, `config.py` (572 lines) did two unrelated jobs at once. It
held every setting as a bare module-level constant, and it also constructed
runtime objects: `_build_provider()` and the `_ProviderConfig` machinery built
embedding models, LLMs, and rerankers, and the module mutated LlamaIndex's
global `Settings.embed_model` at import time.

This made `config.py` the single most-imported and most-fragile module in the
codebase. Every business module imported constants from it, and roughly thirty
test files reached in for the same names. There was no `Settings` class — just
module globals — so the module could be reasoned about neither as pure data
nor as a construction site. Adding a provider meant editing the same file that
every consumer depended on, and any import-time construction side effect
propagated to every test that touched the import graph.

Phase 2 of the five-phase refactor splits declarative resolution from
construction. It carries the highest risk of the five phases because the
constant-import surface touches every module and most tests; the mitigation
strategy (a PEP 562 shim plus lint-enforced layering) is the substance of this
ADR.

## Decision

Adopt a three-layer architecture for configuration and wiring. The layers are
separated by file and enforced mechanically by `import-linter` (a new dev
dependency) so the boundaries cannot drift by convention alone.

### Layer 1 — `config/` typed resolver (pure data, zero construction)

`config.py` becomes a thin facade over a package. A typed Pydantic `Settings`
class composes per-subpackage settings models
(`core/chunking/settings.py`, `core/retrieval/settings.py`,
`core/metadata/settings.py`) through multiple inheritance, so each knob's
default lives next to the code that consumes it. The resolver performs parsing
and validation only — it builds no providers, mutates no LlamaIndex globals,
and exposes no constructed objects. Resolution layers sources as a precedence
chain:

```
subpackage model field defaults (lowest)
  → config/defaults.yaml (shipped as package data via importlib.resources)
    → environment variables / .env
      → explicit instantiation args (highest)
```

A PEP 562 module-level `__getattr__` shim resolves the legacy bare constants
(`TOP_K`, `CHUNK_SIZE`, `RERANK_ENABLED`, `EMBED_MODEL`, …) by reading from the
`Settings` singleton, emitting a `DeprecationWarning` on each access. The shim
exists so external and experiment code keeps working during migration; the
acceptance criterion forbids any remaining constant read inside the main tree
outside `config.py` and `compose.py`. The shim is removed in v2.0.0.

### Layer 2 — `compose.py` composition root (the only construction site)

`compose.py` is the single module permitted to construct provider and pipeline
objects. It owns `build_embed_model`, `build_llm_model`, and `build_reranker`;
it resolves the lazy registries against `Settings`; and it wires LlamaIndex's
global `Settings.embed_model` through `ensure_runtime_setup()`. No other module
imports a concrete provider class. This centralises every import-time side
effect in one testable place that can be fully mocked.

### Layer 3 — dependency injection everywhere else

Business modules (`core/ingestion`, `core/retrieval`, `core/metadata`,
`core/chunking`) receive their dependencies as parameters. They never import
concrete provider classes and never reach into `config` for a constructed
object. `core/retrieval/policy.py`, for example, now reads injected settings
(`settings.rerank_enabled`, …) at call time instead of re-reading the config
module.

### Lazy `"module:attr"` registries

The provider registry is extracted from `config.py` into `core/providers/`
(`common.py` for shared connection config, plus `embeddings/` and `llm/`
subpackages). Every registry is a lazy `Dict[str, str]` mapping a name to a
`"module:attr"` import string, resolved and cached on first `get()`, with a
`KeyError` that lists the available names. The same lazy contract now lives in
`core/chunking/registry.py`, `core/retrieval/registry.py`, and
`core/metadata/registry.py`. Importing a registry never imports a strategy
module, so a missing optional dependency degrades to "strategy unavailable"
rather than breaking startup.

### Reranker converted to DI

`core/retrieval/reranker.py`'s `CrossEncoderReranker` changes from a `__new__`
singleton to a plain class that receives its model ID. It is constructed in
`compose.py` (`build_reranker`). A process-wide `_MODEL_CACHE` dict keyed by
model ID preserves the load-once semantics the singleton gave us. The
independent `load_dotenv()` call (the old circular-import workaround, gotcha
#4) is removed because settings are now injected. The `_instance = None` test
reset hook is replaced by an explicit `reset_model_cache()` function; affected
tests were updated in the same change.

### import-linter as the boundary enforcer

`import-linter` joins the dev dependencies and runs in CI (`lint-imports`).
Three contracts in `pyproject.toml` `[tool.importlinter]` make the layering
mechanical:

1. **`settings-models-are-pure-data`** — subpackage `settings.py` modules
   import nothing upward (no `config`, no `compose`, no `core/` business).
2. **`providers-constructed-only-in-compose`** — outside `core/providers/`,
   only `compose.py` imports concrete provider modules.
3. **`core-business-avoids-providers-transports`** — `core/` business modules
   do not import from `core/providers/` or from `transports/`.

Strategy subpackage `__init__.py` files (chunking, retrieval, metadata,
ingestion) were made lazy (PEP 562 `__getattr__`) to break a config↔core import
cycle and to align with the lazy-registry design.

## Consequences

### Positive

- `config` can be reasoned about as pure data: parsing, defaults, and
  validation with no hidden object construction or import-time side effects.
- Construction is centralised in `compose.py`, so it is testable with mocks
  and every import-time side effect lives in one auditable place.
- Adding a provider now costs one file plus one registry line — no edit to
  either `config` or any consuming module.
- Subpackage settings models keep each knob's default beside the code that
  owns it, so the source of truth for a default no longer lives in a distant
  monolith.
- Import cycles are structurally prevented by the lint contracts rather than
  policed by convention, which had already drifted once (the original
  config-construction coupling).
- The lazy registry contract lets a missing optional dependency degrade to
  "strategy unavailable" instead of crashing at import.

### Negative

- One-time migration cost for the constant surface. The PEP 562 shim bridges
  external and experiment code, but every internal consumer had to move to the
  structured `settings` object file-by-file with the suite green at each step.
- Two files (`config` and `compose`) where there used to be one. Developers
  must internalise the layering. The cost is mitigated by `import-linter`
  failing the build when the layers are crossed.
- The PEP 562 shim emits a `DeprecationWarning` on each legacy constant access,
  which is noisy in logs until consumers migrate. The shim is removed in
  v2.0.0, so the debt is bounded.
- The legacy `Settings` name changed meaning: `from rag_mcp.config import
  Settings` now yields the pydantic resolver model, not the LlamaIndex global.
  Because it is a real module attribute, the PEP 562 shim cannot intercept it
  or warn. Consumers needing the LlamaIndex global must import
  `from llama_index.core import Settings` and trigger runtime setup via
  `rag_mcp.compose` (or `server`/`cli`). In-repo experiment scripts were
  migrated; third-party or experimental code importing `Settings` from
  `rag_mcp.config` or `rag_mcp.ingestion` must be updated.

### Neutral

- The resolver ships an extension point for a `ProfileYamlSettingsSource` that
  Phase 4 will slot into the precedence chain between `defaults.yaml` and the
  environment sources. Phase 2 does not activate profiles; it only avoids
  precluding them.
- `pydantic-settings` and `PyYAML` become direct runtime dependencies. Pydantic
  was already transitive, but the config boundary depends on its public API and
  now declares it.
- The environment-variable interface is unchanged: every name, default, and
  parsing semantic is preserved. The refactor moves where values are read, not
  what values mean.

> **Update (silent-failure-audit-and-guards, 2026-08-11):** the composition
> root's failure semantics tightened. `ensure_runtime_setup()` now lets
> construction failures (missing optional dependency, missing credentials,
> failed embedding-model build) propagate instead of warn-and-continue, so a
> bad configuration raises at import time — `rag-mcp --help` and every other
> command fail loudly rather than running on a degraded store. This was
> accepted deliberately: `VECTOR_STORE`'s unknown-value check already raised
> through the same import-time path (ADR-034), the retired-env-var tripwire
> (`config/legacy.py`) had already established "loud failure over silent
> misconfiguration", and a stderr traceback with a non-zero exit is the whole
> point of ADR-029. Full rationale in the archived change's `design.md`
> (decision D5).

## Alternatives Considered

| Option | Rejected Because |
| ------ | ---------------- |
| **Single `core.py` doing both resolution and construction** | Construction inside the settings module is exactly the coupling this change removes. The name `core.py` also visually collides with the `core/` package directory (design D1). |
| **Rewrite every constant consumer in one commit (no shim)** | The diff would be too large to review safely, and a single bad merge would break the whole tree at once. The shim lets migration proceed file-by-file with the suite green at each step (design D2). |
| **Leave the bare constants forever** | Defeats the structured-settings goal. The constant surface is what made `config.py` fragile in the first place. |
| **Eager registry of live callables** | One missing optional dependency would break the whole registry import. Lazy `"module:attr"` strings defer the import to first `get()`, so a missing dependency in an *unselected* strategy degrades gracefully — only the strategy this deployment actually selects gets imported at startup, and a missing dependency there now fails loudly instead (see the 2026-08-11 update above) (design D3). |
| **Keep the reranker singleton** | The singleton's `__new__` and independent `load_dotenv()` existed only to dodge the config-construction coupling. Once construction moves to `compose.py`, DI with a process-wide model cache achieves the same load-once semantics without the workaround (design D4). |
| **Convention-based boundaries (status quo)** | Convention had already drifted once. Lint makes the boundaries mechanical and fails CI on violation, so the layering cannot quietly rot (design D5). |

## References

- Design doc: [`openspec/changes/phase-2-refactor-config-core-split/design.md`](../../openspec/changes/phase-2-refactor-config-core-split/design.md) (decisions D1–D6)
- Proposal: [`openspec/changes/phase-2-refactor-config-core-split/proposal.md`](../../openspec/changes/phase-2-refactor-config-core-split/proposal.md)
- Refactor proposal: [`docs/brainstorm/refactor-proposal/PROPOSAL.md`](../brainstorm/refactor-proposal/PROPOSAL.md) (§4, §8)
- [ADR-006](./006-config-as-single-source-of-truth.md) — Config as Single Source of Truth (amended: aggregation point moves to `compose.py`)
- [ADR-025](./025-pluggable-inference-backend.md) — Pluggable Inference Backend (amended: registry relocated to `core/providers/`)
- [ADR-026](./026-provider-registry-and-openrouter.md) — Provider Registry Pattern (amended: registry relocated to `core/providers/`)
- [ADR-020](./020-use-liteparse-as-pdf-reader.md) — factory/lazy-load discipline the registries generalise
- `src/rag_mcp/config/` — typed resolver and PEP 562 shim
- `src/rag_mcp/compose.py` — composition root
- `src/rag_mcp/core/providers/` — lazy provider registries
- `src/rag_mcp/core/retrieval/reranker.py` — DI reranker with process-wide model cache
- [`docs/guides/configuration.md`](../guides/configuration.md) — resolution order and deprecated-constant guidance
