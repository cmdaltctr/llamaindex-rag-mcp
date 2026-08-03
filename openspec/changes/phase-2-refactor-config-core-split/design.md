## Context

Phase 2 of the five-phase refactor (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §4, §8). Today's `config.py` (572 lines) both holds settings and constructs providers, and exposes settings as bare module-level constants consumed everywhere. There is no `Settings` class — `config.py` mutates LlamaIndex's global `Settings.embed_model` and exports constants. Phase 2 introduces the three-layer stack (typed config / composition root / DI). This is the highest-risk phase: the constant-import surface (H4) touches every module and most test files. Phase 4 depends on this phase's resolver.

## Goals / Non-Goals

**Goals:**

- `config.py` slimmed to ~150 lines of typed resolution; zero construction.
- `compose.py` as the single construction site.
- Provider registry extracted to `core/providers/` with the shared lazy registry contract.
- Subpackage `settings.py` models as pure data, enforced by import-linter.
- Legacy constant reads keep working via a PEP 562 shim while consumers migrate.
- Reranker converted to compose-constructed DI with process-wide model caching.

**Non-Goals:**

- No profiles or `config/profiles/*.yaml` bundles (Phase 4) — though the resolver is designed so a `ProfileYamlSettingsSource` can slot into the precedence chain between `defaults.yaml` and environment sources in Phase 4 without rewriting the resolver. Phase 2 ships the extension point; Phase 4 activates it.
- No `VectorStore` ABC (Phase 3).
- No transport moves (Phase 5).
- No env var renames or default changes.
- No removal of compat shims (all shims die together in v2.0.0).

## Decisions

### D1: Three-layer stack, not two

Configuration resolution (`config.py`) and object construction (`compose.py`) are separate files. Alternative considered: a single `core.py` doing both — rejected because construction logic inside the settings module is exactly today's coupling, and the name `core.py` visually collides with the `core/` package directory (PROPOSAL §5.2 naming note).

### D2: PEP 562 `__getattr__` shim for the constant surface

The legacy `config` module gains a module-level `__getattr__` mapping each legacy constant name to its structured-settings path, emitting `DeprecationWarning`. This lets every existing consumer keep working while consumers are migrated file-by-file. Acceptance forbids any remaining constant read outside `config.py`/`compose.py` — the shim is for third-party/experiment code, not the main tree. Alternatives considered: (a) rewrite all consumers in one commit — rejected, diff too large to review safely; (b) leave constants forever — rejected, defeats the structured-settings goal.

### D3: Lazy `"module:attr"` registries

All registries store import strings, resolved on first `get()` and cached (PROPOSAL §4.4). Importing a registry never imports strategy modules. This keeps startup fast and lets a missing optional dependency degrade to "strategy unavailable" per ADR-020/ADR-024 discipline. Alternative considered: eager registration of live callables — rejected because one missing optional dep would break the whole registry import.

### D4: Reranker DI with process-wide model cache

`CrossEncoderReranker` becomes a normal class constructed in `compose.py`; a module-level model cache in `core/retrieval/reranker.py` preserves load-once semantics. The independent `load_dotenv()` (gotcha #4) is removed because settings are now injected — the circular-import risk that motivated it no longer exists. The `_instance = None` test reset hook is replaced by an explicit cache-reset function and affected tests are updated in the same change.

### D5: import-linter as the boundary enforcer

`import-linter` joins dev dependencies and CI with contracts: (1) subpackage `settings.py` modules import nothing upward; (2) outside `core/providers/`, only `compose.py` imports concrete provider modules — imports within `core/providers/` (e.g. provider modules importing `common.py`, registries resolving provider modules) are permitted; (3) `core/` business modules (ingestion, retrieval, metadata, chunking) do not import from `core/providers/` or from `transports/`. Convention-based boundaries (today's approach) have already drifted once (the config-construction coupling); lint makes them mechanical.

### D6: New dependencies are deliberate

`pydantic-settings` and `PyYAML` are added as direct runtime dependencies (PROPOSAL §4.3 dependency decision). `pydantic` may already be transitive, but the config boundary depends on its public API and must declare it.

## Risks / Trade-offs

- Constant-import migration breaks consumers (H4, High/High) → PEP 562 shim + acceptance criterion forbidding remaining constant reads; migration done file-by-file with the suite green at each step.
- Reranker DI conversion breaks model loading (M3) → process-wide cache preserves load-once; reset hook replaced explicitly and tests updated in the same change; fallback-to-unreranked behaviour (spec: reranking) is regression-tested.
- Circular imports introduced by settings models → pure-data rule enforced by import-linter in CI.
- Structured `Settings` changes behaviour subtly (e.g. env parsing of booleans) → every env var's parsing semantics are pinned by tests before and after migration; D6 keeps the env interface byte-identical.
- Phase 2 stalls leaving a half-converted config → the shim means both worlds work simultaneously; a stalled Phase 2 is ugly, not broken.

## Migration Plan

1. Add `pydantic-settings`, `PyYAML`, dev `import-linter`; write the contracts and watch them fail (guard test).
2. Create subpackage `settings.py` models + root `Settings` resolver + `config/defaults.yaml`.
3. Create `core/providers/` with lazy registries; create `compose.py`.
4. Add the PEP 562 shim to the legacy `config` module.
5. Migrate consumers off constant reads, file-by-file, suite green at each step.
6. Convert the reranker to DI; update affected tests.
7. Enable import-linter in CI. Rollback: branch revert; the shim makes partial states functional.

## Open Questions

- Exact set of legacy constants covered by the shim — enumerate from a `grep` of constant imports during task 1 and freeze the list in the tasks.
