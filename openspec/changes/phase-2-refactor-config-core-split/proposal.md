## Why

`config.py` currently does two jobs at once: it holds settings AND constructs provider objects (`_build_provider()`, `_ProviderConfig`), and it exposes settings as bare module-level constants (`TOP_K`, `CHUNK_SIZE`, `RERANK_ENABLED`, `EMBED_MODEL`, …) consumed across every module and most of the ~30 test files. This makes it the single most imported and most fragile module in the codebase. This is Phase 2 of the five-phase refactor (`docs/brainstorm/refactor-proposal/PROPOSAL.md` §8): split configuration (declarative resolution) from construction (a composition root), convert the constant surface to a structured `Settings` object, and extract the provider registry into `core/providers/`. This phase carries the highest risk of the five because of the constant-import blast radius (H4) — it gets its own shim strategy and lint enforcement.

## What Changes

- Slim `config.py` from 572 to ~150 lines: a typed Pydantic `Settings` resolver that aggregates subpackage model defaults, `config/defaults.yaml`, environment overrides — and performs ZERO object construction (ADR-006 amended: single source of truth for resolved values, not a monolith).
- Create `compose.py` as the composition root — the ONLY place runtime objects (providers, pipeline components) are constructed and wired. Named `compose.py` (not `core.py`) to avoid visual collision with the `core/` package.
- Extract the provider registry from `config.py` into `core/providers/`: `common.py` (shared connection config), `embeddings/` (`registry.py`, `ollama.py`, `llamacpp.py`, `openrouter.py`), `llm/` (`registry.py`, `ollama.py`, `llamacpp.py`). Interface unchanged (ADR-025/026 amended: physical relocation only).
- Add per-subpackage `settings.py` files (chunking, retrieval, metadata) declaring Pydantic models of their knobs and defaults — pure data, no upward imports.
- Define the shared registry contract for all strategy folders: `registry.py` as `Dict[str, str]` mapping names to lazy `"module:attr"` import strings, resolved and cached on first `get()`, with a helpful `KeyError` listing available names (PROPOSAL §4.4).
- **Constant-import shim (H4):** the old `config` module gains a PEP 562 module-level `__getattr__` resolving legacy constant reads (`TOP_K`, `CHUNK_SIZE`, `RERANK_ENABLED`, `EMBED_MODEL`, …) to the structured settings with a `DeprecationWarning`. Acceptance requires that no module-level constant read remains outside `config.py`/`compose.py`.
- **Reranker DI conversion (M3):** convert `CrossEncoderReranker`'s `__new__` singleton and module-level `RERANK_MODEL` to a compose-constructed instance with process-wide model caching; remove the independent `load_dotenv()` once settings are injected; either preserve the `_instance = None` test reset hook or deliberately retire it and update every affected test.
- Add `import-linter` to dev dependencies and CI: contracts enforce that subpackage `settings.py` files never import upward (`config.py`, `compose.py`, or any `core/` module).
- Add `config/defaults.yaml` for non-secret global defaults. YAML never contains secrets, keys, or machine-specific paths.
- **New runtime dependencies (requires approval):** `pydantic-settings` and `PyYAML` declared deliberately (PROPOSAL §4.3 dependency decision).
- New ADR 028: Three-Layer Architecture (Config, Compose, DI).

## Capabilities

### New Capabilities

- `config-composition-root`: The three-layer configuration architecture — typed settings resolution in `config.py`, object construction in `compose.py`, dependency injection elsewhere — plus the registry contract, the legacy-constant deprecation shim, and the import-boundary lint rules that keep the layers honest.

### Modified Capabilities

- `inference-backend`: Provider construction moves physically from `config.py` to `core/providers/` and `compose.py`; the provider registry interface and resolution behaviour are unchanged (ADR-025/026 relocation).
- `reranking`: The reranker changes from an import-time `__new__` singleton to a compose-constructed, process-cached instance; rerank scoring behaviour and model identity are unchanged.

## Impact

- **Code**: `config.py` (572 → ~150 lines), new `compose.py`, new `core/providers/` tree, new `settings.py` in each Phase 1 subpackage, reranker singleton converted to DI.
- **Tests**: most of the ~30 test files import config constants; the PEP 562 shim keeps them working during migration, and consumers are migrated off constant reads as part of acceptance. Reranker tests either keep the `_instance = None` reset hook or are updated deliberately.
- **Dependencies**: NEW runtime deps `pydantic-settings` + `PyYAML` (approval required); NEW dev dep `import-linter`.
- **ADRs**: 006 amended (aggregation point), 025/026 amended (relocation); new ADR 028.
- **Risk**: **High** — touches the most-imported module and converts the entire config surface. Phase 4 depends on this phase's resolver and MUST NOT begin until Phase 2 lands.
