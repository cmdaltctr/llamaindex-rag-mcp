## 1. Settings models — rename fields and add validator

- [x] 1.1 In `src/rag_mcp/core/metadata/settings.py`, rename
      `ollama_classify_max_attempts` → `classify_max_attempts` and
      `ollama_classify_timeout` → `classify_timeout`. Update the inline comments
      to drop "Ollama" (these govern all three backends).
- [x] 1.2 Add `Field(gt=0)` to `classify_max_attempts` and `classify_timeout` so
      a zero or negative budget cannot skip the classification call and a
      non-positive timeout cannot reach the HTTP client. Rejects rather than
      clamps, so the misconfiguration surfaces. Import `Field` from `pydantic`.
- [x] 1.3 In `src/rag_mcp/core/settings.py` (`MetadataBlock`), rename the same
      two fields and add the same `field_validator` (the runtime block mirrors
      the config-layer model).

## 2. Move shared helpers to `_common.py` and rename

- [x] 2.1 In `src/rag_mcp/core/metadata/_common.py`, add the three shared
      helpers currently in `ollama.py`: `_retry_sleep` (the `asyncio.sleep`
      module-level hook), `_get_classify_max_attempts(resolved)`, and
      `_get_classify_timeout(resolved)`. The two getters are direct returns of
      `resolved.metadata.classify_max_attempts` / `classify_timeout` — no
      `os.getenv`, no floor (moved to the validator in 1.2). Add `import asyncio`
      at the top of `_common.py` for `_retry_sleep`.
- [x] 2.2 In `src/rag_mcp/core/metadata/ollama.py`, delete the three helpers
      (`_get_ollama_max_attempts`, `_get_ollama_timeout`, `_retry_sleep`) and
      their `import asyncio` if no longer needed. Update the import block to
      pull `_get_classify_max_attempts`, `_get_classify_timeout`, `_retry_sleep`
      from `._common` alongside the existing `_normalise_category` etc. Keep the
      `from ._common import _retry_sleep` at **module level** (not function
      level) — `tests/unit/test_provider_config.py` rebinds
      `llamacpp._retry_sleep`, which only works if the name is a module global.
- [x] 2.3 In `src/rag_mcp/core/metadata/__init__.py`, update the PEP 562
      lazy re-export map `_NAMES` (lines ~48-51). The helpers moved to
      `_common.py` and were renamed, so three entries are now stale:
      rename key `_get_ollama_max_attempts` → `_get_classify_max_attempts`
      and repoint its value `.ollama` → `._common`; rename key
      `_get_ollama_timeout` → `_get_classify_timeout` and repoint
      `.ollama` → `._common`; repoint `_retry_sleep` value `.ollama` →
      `._common`. **Gotcha #8b:** without this, `from rag_mcp.core.metadata
      import _retry_sleep` resolves against `.ollama` (which no longer defines
      it) and raises `AttributeError`, and the two `_get_ollama_*` keys dangle.

## 3. Backend modules — update imports and call sites

- [x] 3.1 In `src/rag_mcp/core/metadata/ollama.py`, update the two call sites in
      `_extract_ollama_async` to use the renamed helpers from `_common`. Also
      update the stale env-var references in the docstrings — the helper
      docstrings (lines ~183, ~203) and the `_extract_ollama_async` docstring
      (lines ~232-234) still name `OLLAMA_CLASSIFY_MAX_ATTEMPTS` /
      `OLLAMA_CLASSIFY_TIMEOUT`. Point them at
      `METADATA__CLASSIFY_MAX_ATTEMPTS` / `METADATA__CLASSIFY_TIMEOUT` so no
      `ollama`-scoped env reference survives in the shared path.
- [x] 3.2 In `src/rag_mcp/core/metadata/llamacpp.py`, update the import block
      to pull `_get_classify_max_attempts`, `_get_classify_timeout`, `_retry_sleep`
      from `._common` instead of `.ollama`. Keep `_build_ollama_prompt` and
      `_parse_ollama_json_response` imported from `.ollama` (they stay there).
      Update the two call sites.
- [x] 3.3 In `src/rag_mcp/core/metadata/extractor.py`, update the import block
      inside `_extract_openrouter_chat_async` the same way as 3.2. Update the
      two call sites.

## 4. Provider module — update field reference

- [x] 4.1 In `src/rag_mcp/core/providers/llm/ollama.py` line 21, change
      `settings.metadata.ollama_classify_timeout` →
      `settings.metadata.classify_timeout`.

## 5. defaults.yaml — rename YAML keys

- [x] 5.1 In `src/rag_mcp/config/defaults.yaml` (lines 55-56), rename
      `ollama_classify_max_attempts` → `classify_max_attempts` and
      `ollama_classify_timeout` → `classify_timeout`.

## 6. Legacy tripwire — update targets, add old v2 nested names

- [x] 6.1 In `src/rag_mcp/config/legacy.py`, update the two existing entries to
      point at the new nested names:
      `OLLAMA_CLASSIFY_MAX_ATTEMPTS` → `METADATA__CLASSIFY_MAX_ATTEMPTS` and
      `OLLAMA_CLASSIFY_TIMEOUT` → `METADATA__CLASSIFY_TIMEOUT`.
- [x] 6.2 Add two new entries for the old v2 nested names so an operator
      upgrading from v2.0–v2.2 gets a tripwire message:
      `METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS` → `METADATA__CLASSIFY_MAX_ATTEMPTS`
      and `METADATA__OLLAMA_CLASSIFY_TIMEOUT` → `METADATA__CLASSIFY_TIMEOUT`.
      **Sequencing:** 6.2 and 9.1 must land in the **same commit**. `conftest.py`
      currently sets `METADATA__OLLAMA_CLASSIFY_*`; the moment those names go on
      the tripwire, every test that reaches `ensure_runtime_setup()` raises until
      conftest is renamed. Do not split these across commits.

## 7. .env.example — add the new settings

- [x] 7.1 In `.env.example`, after the `METADATA__EXTRACTION_MODE` block (around
      line 103-104), add commented-out entries for `METADATA__CLASSIFY_MAX_ATTEMPTS`
      and `METADATA__CLASSIFY_TIMEOUT` with inline comments noting they govern all
      three backends.

## 8. Documentation — update guides

- [x] 8.1 In `docs/guides/configuration.md` (lines 234-236), rename the table
      entries: `ollama_classify_max_attempts` → `classify_max_attempts`,
      `ollama_classify_timeout` → `classify_timeout`. Update the "What it does"
      column to note these govern all metadata LLM providers, not just Ollama.
      Leave `ollama_classify_model` as-is.
- [x] 8.2 In `docs/guides/providers.md`, add a short note (near the metadata LLM
      provider section around line 64) that `METADATA__CLASSIFY_MAX_ATTEMPTS` and
      `METADATA__CLASSIFY_TIMEOUT` are shared across all three metadata backends
      (Ollama, llama.cpp, OpenRouter). The model field is per-provider; the retry
      budget and timeout are not.
- [x] 8.3 In `docs/tdr/006-openrouter-structured-outputs-per-endpoint.md`
      (lines ~99-102), add a forward-note — do **not** rewrite the record. TDR-006
      flagged the misleading `ollama_` scope ("`METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS`,
      which despite the name governs all three backends … call
      `_get_ollama_max_attempts`"); this change retires that debt. Append a dated
      note (e.g. "**Update (rename-classify-settings):** this knob is now
      `METADATA__CLASSIFY_MAX_ATTEMPTS` and the helper is `_get_classify_max_attempts`
      in `_common.py`.") so a reader lands on the current name. Leave the original
      prose intact above it.

## 9. Tests — update all references

- [x] 9.1 In `tests/conftest.py` (lines 273-274), rename the env vars to
      `METADATA__CLASSIFY_MAX_ATTEMPTS` and `METADATA__CLASSIFY_TIMEOUT`.
- [x] 9.2 In `tests/test_config_sources_coverage.py`, rewrite
      `TestOllamaKnobResolution` to test the settings-injection path: the
      `_settings()` factory already passes `classify_max_attempts=7,
      classify_timeout=42.0` via `MetadataBlock`. Drop the `os.getenv` tests
      (env override, malformed fallback, floor) — those tested dead code. Keep
      one test asserting the settings value flows through the helper. Add bounds
      tests parametrised over both `MetadataSettings` and `MetadataBlock` × both
      fields, asserting `ValidationError` on zero and negative values.
      Update import paths from `ollama` to `_common`.
- [x] 9.3 In `tests/test_metadata_extractor.py`:
      - Line 41: rename `ollama_classify_max_attempts` → `classify_max_attempts`
        in the `block_kwargs` assignment.
      - **`_retry_sleep` patch targets (gotcha #8b).** The `_no_sleep` helper
        (line ~1535) patches `ollama._retry_sleep` but is called only by
        OpenRouter tests (`TestOpenRouterStructuredOutputDowngrade`). After the
        move, `extractor.py` imports `_retry_sleep` from `_common.py` at function
        level, so the patch target must change from
        `rag_mcp.core.metadata.ollama._retry_sleep` to
        `rag_mcp.core.metadata._common._retry_sleep`. The `TestOllamaRetry`
        fixture (line ~1278) patches `ollama._retry_sleep` directly and stays
        unchanged — `ollama.py` will have its own module-level binding via
        `from ._common import _retry_sleep`, so patching `ollama._retry_sleep`
        still controls the Ollama backend's calls.
      - Update any imports of `_get_classify_*` helpers from `ollama` to
        `_common`.
- [x] 9.4 In `tests/test_settings_resolver.py` (lines 74-75, 140-141), rename
      the env vars and field paths to the new names.
- [x] 9.5 In `tests/test_compose.py` line 38, rename
      `ollama_classify_timeout` → `classify_timeout` in the field-mapping
      assertion.
- [x] 9.6 In `tests/test_coverage_gaps_v2.py`:
      - Line 54: rename `ollama_classify_max_attempts` → `classify_max_attempts`.
      - Line 92: change the `_retry_sleep` patch target from
        `rag_mcp.core.metadata.ollama._retry_sleep` to
        `rag_mcp.core.metadata._common._retry_sleep` (this test calls
        `_extract_openrouter_chat_async` directly, which after the move imports
        `_retry_sleep` from `_common.py` at function level — same gotcha #8b as
        9.3).

- [x] 9.7 In `tests/unit/test_provider_config.py` (lines ~102, ~128), no rename
      is needed — the tests rebind `_llamacpp._retry_sleep = AsyncMock()`, which
      stays valid because `llamacpp.py` keeps a module-level
      `from ._common import _retry_sleep` binding (see 2.2). **Verify** both
      `test_provider_config.py` tests still pass after the move; if they fail,
      the llamacpp import went function-level and must be restored to module
      level. This file was not in the original impact list.

## 10. Verification and close-out

- [x] 10.1 `uv run pytest -m "not slow" --cov=rag_mcp` — confirm `core/metadata`
      holds ≥95% and overall ≥90%.
- [x] 10.2 `uv run lint-imports` — 6/6 contracts kept.
- [x] 10.3 `openspec validate --all --strict`.
- [x] 10.4 Conventional Commits on branch `feat/rename-classify-settings`.
- [x] 10.5 Open the PR against `main`.
- [ ] 10.6 After merge, archive the change (`openspec archive`).
