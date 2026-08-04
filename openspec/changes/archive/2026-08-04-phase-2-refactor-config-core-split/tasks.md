## 1. Preparation and dependency declaration

- [x] 1.1 Create branch `git switch -c feat/phase-2-refactor-config-core-split` (requires Phase 1 merged)
- [x] 1.2 Baseline: `uv run pytest -m "not slow" --cov=rag_mcp` — record pass/coverage as the phase gate (**581 passed, 87% coverage**)
- [x] 1.3 Enumerate the full legacy constant surface: grep for `from rag_mcp.config import` across `src/` and `tests/`; freeze the constant list in this file before proceeding

  **Frozen constant surface** (39 constants + 4 registries + 2 resolved values + `Settings` re-export):

  **Provider selection:** `EMBED_PROVIDER`, `METADATA_LLM_PROVIDER`, `LOCAL_BACKEND`, `CLOUD_BACKEND`
  **Provider connection:** `LLAMACPP_EMBED_URL`, `LLAMACPP_EMBED_MODEL`, `LLAMACPP_CHAT_URL`, `LLAMACPP_CHAT_MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_EMBED_MODEL`, `OPENROUTER_LLM_MODEL`, `OLLAMA_BASE_URL`, `EMBED_MODEL_NAME`, `EMBED_BATCH_SIZE`
  **Chroma/storage:** `CHROMA_PERSIST_DIR`, `COLLECTION_NAME`, `CHROMA_SCAN_PAGE_SIZE`
  **Chunking:** `CHUNK_SIZE`, `CHUNK_OVERLAP`, `EMBED_CONCURRENCY`, `MARKDOWN_CHUNK_SIZE`, `MARKDOWN_HEADING_PREPEND`, `MARKDOWN_MIN_CHUNK_FRACTION`
  **Retrieval:** `TOP_K`, `RERANK_ENABLED`, `RERANK_ENABLED_FOR_SEMANTIC`, `HARD_TECHNICAL_THRESHOLD`, `SIMILARITY_THRESHOLD`, `RERANK_FETCH_MULTIPLIER`, `RERANK_MAX_FETCH`, `HYBRID_ENABLED`, `HYBRID_RRF_K`, `HYBRID_SPARSE_BACKEND`
  **PDF reader:** `PDF_READER`, `LITEPARSE_NUM_WORKERS`, `LITEPARSE_OCR_ENABLED`
  **Metadata:** `METADATA_EXTRACTION_MODE`, `METADATA_KEYWORD_RULES`, `OLLAMA_CLASSIFY_MODEL`, `OLLAMA_CLASSIFY_MAX_ATTEMPTS`, `OLLAMA_CLASSIFY_TIMEOUT`
  **Codebase map:** `MAGIKA_BINARY`, `DOC_SIMILARITY_THRESHOLD`, `CODEBASE_MAP_CACHE_DIR`, `CODEBASE_MAP_MAX_FILES`, `CODEBASE_MAP_MAX_DEPTH`
  **Document backend:** `DOCUMENT_BACKEND`, `AZURE_DOC_INTELLIGENCE_ENDPOINT`, `AZURE_DOC_INTELLIGENCE_KEY`, `AZURE_DOC_INTELLIGENCE_MODEL`
  **Static mappings:** `MAGIKA_LABEL_TO_TREESITTER`, `SUPPORTED_EXTENSIONS`
  **Registries (move to `core/providers/`):** `LOCAL_EMBED_PROVIDERS`, `CLOUD_EMBED_PROVIDERS`, `LOCAL_LLM_PROVIDERS`, `CLOUD_LLM_PROVIDERS`
  **Resolved values (runtime probes):** `RESOLVED_HYBRID_SPARSE_BACKEND`, `RESOLVED_PDF_READER`
  **Re-export:** `Settings` (from `llama_index.core`)
- [x] 1.4 Add runtime deps `pydantic-settings` and `PyYAML` via `uv add` (explicit approval per AGENTS.md dependency boundary); add dev dep `import-linter` via `uv add --dev`
- [x] 1.5 Write import-linter contracts: (a) subpackage `settings.py` never imports `config.py`/`compose.py`/`core/*`; (b) outside `core/providers/`, only `compose.py` imports concrete provider modules — imports within `core/providers/` are permitted; (c) `core/` business modules (ingestion, retrieval, metadata, chunking) never import from `core/providers/` or `transports/`

## 2. Structured settings resolver

- [x] 2.1 Create `core/chunking/settings.py` (`ChunkingSettings`: chunk_size, chunk_overlap, active_strategy, drop_small_chunks, min_chunk_tokens) — pure data, no upward imports
- [x] 2.2 Create `core/retrieval/settings.py` (`RetrievalSettings`: top_k, hybrid, reranker_enabled, thresholds, fetch knobs)
- [x] 2.3 Create `core/metadata/settings.py` (`MetadataSettings`: mode, taxonomy, backend knobs)
- [x] 2.4 Create `src/rag_mcp/config/defaults.yaml` with non-secret global defaults (no keys, no absolute paths); declare the `config/` directory as package data in `pyproject.toml` (`[tool.hatch.build.targets.wheel] packages = ["src/rag_mcp"]` plus `[tool.hatch.build.targets.wheel.force-include]` or equivalent for `*.yaml` files)
- [x] 2.5 Rewrite `config.py` as the typed resolver (~150 lines): root `Settings` model composing subpackage models, `settings_customise_sources` layering model defaults < defaults.yaml < env/.env < explicit options, zero construction logic; load YAML via `importlib.resources` so the path resolves correctly in both development (repo root) and installed (site-packages) contexts
- [x] 2.6 Write tests pinning every existing env var's name, parsing semantics (booleans, ints, floats), and default against the new resolver
- [x] 2.7 Write a test that resolves `defaults.yaml` from a temporary working directory (simulates installed-wheel resource loading independent of CWD)

## 3. Provider extraction and composition root

- [x] 3.1 Create `core/providers/common.py` with shared connection config (endpoint, key) used by both embedding and LLM providers
- [x] 3.2 Create `core/providers/embeddings/` with `registry.py` (lazy `"module:attr"` contract), `ollama.py`, `llamacpp.py`, `openrouter.py`
- [x] 3.3 Create `core/providers/llm/` with `registry.py`, `ollama.py`, `llamacpp.py`
- [x] 3.4 Move `_ProviderConfig` and `_build_provider()` logic out of `config.py` into the provider modules; `config.py` must end with zero `_build_*()` methods
- [x] 3.5 Create `compose.py`: reads resolved `Settings`, calls `registry.get(config.embed_provider)(config)` etc., constructs and wires pipeline objects; the ONLY file that instantiates providers
- [x] 3.6 Apply the shared registry contract to `core/chunking/registry.py`, `core/retrieval/registry.py`, `core/metadata/registry.py` (lazy import strings, cached `get()`, `available()`, helpful `KeyError`)
- [x] 3.7 Convert `core/` components to receive dependencies as parameters (no concrete provider imports); wire LlamaIndex `Settings.embed_model` assignment from `compose.py` only

## 4. Legacy constant shim and consumer migration

- [x] 4.1 Add PEP 562 module-level `__getattr__` to the legacy `rag_mcp.config` module resolving each frozen constant (task 1.3) to its structured-settings path with `DeprecationWarning`
- [x] 4.2 Write a test asserting each legacy constant resolves and warns
- [x] 4.3 Migrate `src/` consumers off constant reads to structured settings, file-by-file, running the fast suite after each file
- [x] 4.4 Migrate `tests/` consumers the same way (imports only, no assertion changes)
- [x] 4.5 Verify acceptance: no module-level constant read remains outside `config.py`/`compose.py` (grep gate in CI or a lint test)

## 5. Reranker DI conversion (M3)

- [x] 5.1 Convert `CrossEncoderReranker` from `__new__` singleton to a plain class constructed in `compose.py`; add a process-wide model cache in `core/retrieval/reranker.py` preserving load-once semantics
- [x] 5.2 Remove the independent `load_dotenv()` from the reranker (settings now injected)
- [x] 5.3 Move the `HARD_TECHNICAL_THRESHOLD` ÷30 policy consumption so `core/retrieval/policy.py` reads injected settings
- [x] 5.4 Replace the `CrossEncoderReranker._instance = None` test reset hook with an explicit cache-reset function; update every affected test in the same commit
- [x] 5.5 Regression-test rerank fallback behaviour (transient failure retry, permanent failure graceful fallback) against the reranking spec

## 6. Lint enforcement and acceptance

- [x] 6.1 Enable import-linter in CI; confirm contracts from 1.5 pass
- [x] 6.2 Verify `config.py` ≤ ~200 lines and contains zero construction
- [x] 6.3 Verify `from rag_mcp.config import Settings` works and legacy constants warn
- [x] 6.4 Run `uv run pytest -m "not slow" --cov=rag_mcp` — green at baseline coverage or better
- [x] 6.5 Write ADR 031 (Three-Layer Architecture: Config, Compose, DI — numbered 031 because ADR-028/029/030 landed first); amend ADR-006 (aggregation point) and ADR-025/026 (registry relocation)
- [x] 6.6 Update `docs/guides/configuration.md` for the new resolution order and shim deprecations
- [x] 6.7 Run `openspec validate phase-2-refactor-config-core-split --strict`
- [x] 6.8 Run `graphify update .`
- [x] 6.9 Commit (`refactor:`) and open PR with `gh pr create --base main`
