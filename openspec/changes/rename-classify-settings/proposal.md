## Why

The metadata classification retry budget and per-attempt timeout are named
`ollama_classify_max_attempts` and `ollama_classify_timeout`, but they govern all
three LLM backends (Ollama, llama.cpp, OpenRouter), not just Ollama. The name is
undiscoverable for two of three backends, and a 30 s timeout tuned for a local
model is applied unchanged to the OpenRouter cloud API. Separately, the call-time
`os.getenv` override path in `_get_ollama_max_attempts` / `_get_ollama_timeout`
reads pre-v2 flat env names that are on the startup tripwire — the branch is dead
in production, reachable only by tests that bypass `ensure_runtime_setup()`.
Neither setting appears in `.env.example`.

These three issues were raised as deferred task group 7 in the
`structured-outputs-metadata-classification` change (PR #20 review) and are
tracked there as 7.1, 7.2, and 7.3.

## What Changes

- **BREAKING** Rename `ollama_classify_max_attempts` → `classify_max_attempts`
  across `MetadataSettings`, `MetadataBlock`, `defaults.yaml`, and all consumers.
  The nested env var becomes `METADATA__CLASSIFY_MAX_ATTEMPTS`.
- **BREAKING** Rename `ollama_classify_timeout` → `classify_timeout` in the same
  locations. The nested env var becomes `METADATA__CLASSIFY_TIMEOUT`.
- Add the old v2 nested names (`METADATA__OLLAMA_CLASSIFY_MAX_ATTEMPTS`,
  `METADATA__OLLAMA_CLASSIFY_TIMEOUT`) to the legacy tripwire
  (`_LEGACY_FLAT_ENV_VARS`) so an operator who upgrades and still has the old
  name set gets a clear migration message instead of a silent ignore. The pre-v2
  flat names (`OLLAMA_CLASSIFY_MAX_ATTEMPTS`, `OLLAMA_CLASSIFY_TIMEOUT`) are
  already on the tripwire; their target updates to the new nested name.
- Drop the `os.getenv` lookups from `_get_ollama_max_attempts` and
  `_get_ollama_timeout`. The settings are already injected via
  `resolved.metadata.*`; the nested env override is read by pydantic-settings
  natively at resolution time. The call-time re-read was a pre-v2 pattern that
  ADR-037 retired.
- Move the `max(1, value)` floor for `classify_max_attempts` from the call-time
  helper to a `field_validator` on `MetadataSettings` and `MetadataBlock`, so the
  guarantee holds regardless of how the value enters the system (env, YAML,
  programmatic).
- Add `METADATA__CLASSIFY_MAX_ATTEMPTS` and `METADATA__CLASSIFY_TIMEOUT` to
  `.env.example` with inline comments.
- Move `_get_classify_max_attempts`, `_get_classify_timeout`, and `_retry_sleep`
  from `ollama.py` to `_common.py` where the other shared helpers already live
  (`_normalise_category`, `_truncate_keywords`, etc.). After the rename, these
  helpers are no longer Ollama-specific, so a new backend should not have to
  import them from `ollama.py`. This completes the neutral naming — no `ollama`
  reference remains in the shared path.
- Update `docs/guides/configuration.md` (rename table entries, note shared scope)
  and `docs/guides/providers.md` (note that retry budget and timeout are shared
  across all metadata LLM providers, not per-provider).
- Update all test references (conftest, `test_config_sources_coverage.py`,
  `test_metadata_extractor.py`, `test_settings_resolver.py`, `test_compose.py`,
  `test_coverage_gaps_v2.py`).

`ollama_classify_model` is NOT renamed — it is genuinely Ollama-specific (each
backend has its own model field: `ollama_classify_model`, `llamacpp_chat_model`,
`openrouter_llm_model`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — this is a pure rename and dead-code removal. The spec refers to the retry
budget generically ("the system SHALL retry within configured limits",
"the configured retry budget") without naming the knob, so no spec-level
behaviour changes. `skip_specs: true` is set in `.openspec.yaml`.

## Impact

**Code**
- `src/rag_mcp/core/metadata/settings.py` — rename fields, add validator.
- `src/rag_mcp/core/settings.py` (`MetadataBlock`) — rename fields, add validator.
- `src/rag_mcp/core/metadata/_common.py` — receives the renamed helpers and
  `_retry_sleep` from `ollama.py`.
- `src/rag_mcp/core/metadata/ollama.py` — drop helpers (moved to `_common.py`),
  update imports, call sites, and docstrings (stale `OLLAMA_CLASSIFY_*` env refs).
- `src/rag_mcp/core/metadata/__init__.py` — update the PEP 562 lazy `_NAMES`
  re-export map: rename the two `_get_ollama_*` keys and repoint all three moved
  helpers (`_get_classify_max_attempts`, `_get_classify_timeout`, `_retry_sleep`)
  from `.ollama` to `._common`. A stale entry raises `AttributeError` on lazy
  import (gotcha #8b).
- `src/rag_mcp/core/metadata/llamacpp.py` — update imports (from `_common.py`).
- `src/rag_mcp/core/metadata/extractor.py` — update imports (from `_common.py`).
- `src/rag_mcp/core/providers/llm/ollama.py` — update field reference.
- `src/rag_mcp/config/defaults.yaml` — rename YAML keys.
- `src/rag_mcp/config/legacy.py` — update tripwire targets, add old v2 nested
  names.

**Tests**
- `tests/conftest.py` — update env var names.
- `tests/test_config_sources_coverage.py` — rewrite `TestOllamaKnobResolution` to
  test the settings-injection path instead of the dead `os.getenv` path.
- `tests/test_metadata_extractor.py` — update field name and import paths.
- `tests/test_settings_resolver.py` — update env var and field names.
- `tests/test_compose.py` — update field mapping.
- `tests/test_coverage_gaps_v2.py` — update field name.
- `tests/unit/test_provider_config.py` — no rename; verify the two
  `_llamacpp._retry_sleep = AsyncMock()` rebinds still pass after the helper
  move (they rely on llamacpp keeping a module-level `_retry_sleep` binding).

**Documentation**
- `docs/guides/configuration.md` — rename table entries, note shared scope.
- `docs/guides/providers.md` — note retry budget and timeout are shared across
  all metadata LLM providers.
- `docs/tdr/006-openrouter-structured-outputs-per-endpoint.md` — append a dated
  forward-note (original prose intact) pointing readers at the new
  `METADATA__CLASSIFY_MAX_ATTEMPTS` name; TDR-006 explicitly flagged the
  misleading `ollama_` scope this change retires.
- Historical records `docs/adr/015` and `docs/adr/037` reference the old names
  but are left **unchanged** — ADRs are immutable decision records.

**Configuration**
- `.env.example` — add the two new settings with comments.

**Not affected**
- Dependencies, public API, MCP tool contracts, retrieval, ingestion, chunking,
  spec requirements, coverage tiers.
- `ollama_classify_model` — stays as-is (genuinely Ollama-specific).
