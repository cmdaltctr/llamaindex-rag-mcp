## 1. Preparation and dependency declaration

- [ ] 1.1 Create branch `git switch -c feat/phase-2-refactor-config-core-split` (requires Phase 1 merged)
- [ ] 1.2 Baseline: `uv run pytest -m "not slow" --cov=rag_mcp` — record pass/coverage as the phase gate
- [ ] 1.3 Enumerate the full legacy constant surface: grep for `from rag_mcp.config import` across `src/` and `tests/`; freeze the constant list in this file before proceeding
- [ ] 1.4 Add runtime deps `pydantic-settings` and `PyYAML` via `uv add` (explicit approval per AGENTS.md dependency boundary); add dev dep `import-linter` via `uv add --dev`
- [ ] 1.5 Write import-linter contracts: (a) subpackage `settings.py` never imports `config.py`/`compose.py`/`core/*`; (b) outside `core/providers/`, only `compose.py` imports concrete provider modules — imports within `core/providers/` are permitted; (c) `core/` business modules (ingestion, retrieval, metadata, chunking) never import from `core/providers/` or `transports/`

## 2. Structured settings resolver

- [ ] 2.1 Create `core/chunking/settings.py` (`ChunkingSettings`: chunk_size, chunk_overlap, active_strategy, drop_small_chunks, min_chunk_tokens) — pure data, no upward imports
- [ ] 2.2 Create `core/retrieval/settings.py` (`RetrievalSettings`: top_k, hybrid, reranker_enabled, thresholds, fetch knobs)
- [ ] 2.3 Create `core/metadata/settings.py` (`MetadataSettings`: mode, taxonomy, backend knobs)
- [ ] 2.4 Create `src/rag_mcp/config/defaults.yaml` with non-secret global defaults (no keys, no absolute paths); declare the `config/` directory as package data in `pyproject.toml` (`[tool.hatch.build.targets.wheel] packages = ["src/rag_mcp"]` plus `[tool.hatch.build.targets.wheel.force-include]` or equivalent for `*.yaml` files)
- [ ] 2.5 Rewrite `config.py` as the typed resolver (~150 lines): root `Settings` model composing subpackage models, `settings_customise_sources` layering model defaults < defaults.yaml < env/.env < explicit options, zero construction logic; load YAML via `importlib.resources` so the path resolves correctly in both development (repo root) and installed (site-packages) contexts
- [ ] 2.6 Write tests pinning every existing env var's name, parsing semantics (booleans, ints, floats), and default against the new resolver
- [ ] 2.7 Write a test that resolves `defaults.yaml` from a temporary working directory (simulates installed-wheel resource loading independent of CWD)

## 3. Provider extraction and composition root

- [ ] 3.1 Create `core/providers/common.py` with shared connection config (endpoint, key) used by both embedding and LLM providers
- [ ] 3.2 Create `core/providers/embeddings/` with `registry.py` (lazy `"module:attr"` contract), `ollama.py`, `llamacpp.py`, `openrouter.py`
- [ ] 3.3 Create `core/providers/llm/` with `registry.py`, `ollama.py`, `llamacpp.py`
- [ ] 3.4 Move `_ProviderConfig` and `_build_provider()` logic out of `config.py` into the provider modules; `config.py` must end with zero `_build_*()` methods
- [ ] 3.5 Create `compose.py`: reads resolved `Settings`, calls `registry.get(config.embed_provider)(config)` etc., constructs and wires pipeline objects; the ONLY file that instantiates providers
- [ ] 3.6 Apply the shared registry contract to `core/chunking/registry.py`, `core/retrieval/registry.py`, `core/metadata/registry.py` (lazy import strings, cached `get()`, `available()`, helpful `KeyError`)
- [ ] 3.7 Convert `core/` components to receive dependencies as parameters (no concrete provider imports); wire LlamaIndex `Settings.embed_model` assignment from `compose.py` only

## 4. Legacy constant shim and consumer migration

- [ ] 4.1 Add PEP 562 module-level `__getattr__` to the legacy `rag_mcp.config` module resolving each frozen constant (task 1.3) to its structured-settings path with `DeprecationWarning`
- [ ] 4.2 Write a test asserting each legacy constant resolves and warns
- [ ] 4.3 Migrate `src/` consumers off constant reads to structured settings, file-by-file, running the fast suite after each file
- [ ] 4.4 Migrate `tests/` consumers the same way (imports only, no assertion changes)
- [ ] 4.5 Verify acceptance: no module-level constant read remains outside `config.py`/`compose.py` (grep gate in CI or a lint test)

## 5. Reranker DI conversion (M3)

- [ ] 5.1 Convert `CrossEncoderReranker` from `__new__` singleton to a plain class constructed in `compose.py`; add a process-wide model cache in `core/retrieval/reranker.py` preserving load-once semantics
- [ ] 5.2 Remove the independent `load_dotenv()` from the reranker (settings now injected)
- [ ] 5.3 Move the `HARD_TECHNICAL_THRESHOLD` ÷30 policy consumption so `core/retrieval/policy.py` reads injected settings
- [ ] 5.4 Replace the `CrossEncoderReranker._instance = None` test reset hook with an explicit cache-reset function; update every affected test in the same commit
- [ ] 5.5 Regression-test rerank fallback behaviour (transient failure retry, permanent failure graceful fallback) against the reranking spec

## 6. Lint enforcement and acceptance

- [ ] 6.1 Enable import-linter in CI; confirm contracts from 1.5 pass
- [ ] 6.2 Verify `config.py` ≤ ~200 lines and contains zero construction
- [ ] 6.3 Verify `from rag_mcp.config import Settings` works and legacy constants warn
- [ ] 6.4 Run `uv run pytest -m "not slow" --cov=rag_mcp` — green at baseline coverage or better
- [ ] 6.5 Write ADR 028 (Three-Layer Architecture: Config, Compose, DI); amend ADR-006 (aggregation point) and ADR-025/026 (registry relocation)
- [ ] 6.6 Update `docs/guides/configuration.md` for the new resolution order and shim deprecations
- [ ] 6.7 Run `openspec validate phase-2-refactor-config-core-split --strict`
- [ ] 6.8 Run `graphify update .`
- [ ] 6.9 Commit (`refactor:`) and open PR with `gh pr create --base main`
