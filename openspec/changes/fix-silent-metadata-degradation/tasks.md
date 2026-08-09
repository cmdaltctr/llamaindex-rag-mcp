## 1. Settings: six per-provider timeout overrides

- [x] 1.1 Add `{llamacpp,ollama,openrouter}_classify_timeout_override` and `{llamacpp,ollama,openrouter}_pipeline_timeout_override` to `MetadataSettings` in `core/metadata/settings.py`, all `float | None = Field(default=None, gt=0)`, with docstring comments.
- [x] 1.2 Mirror the six fields into the `MetadataSettings` block in `core/settings.py` with identical defaults and validators.
- [x] 1.3 Extend the settings round-trip/parity test to assert the two models declare the same fields and defaults (fails if one drifts).
- [x] 1.4 Document the six vars in `.env.example` and `config/defaults.yaml` (nested `metadata.*`), noting each falls back to the shared `classify_timeout`/`pipeline_timeout`.

## 2. Timeout resolution helpers

- [x] 2.1 Add `_resolve_classify_timeout(resolved, provider)` and `_resolve_pipeline_timeout(resolved, provider)` to `core/metadata/_common.py`: return the provider-specific override if set, else the matching shared timeout.
- [x] 2.2 Unit tests for both resolvers: override honoured per provider; `None` falls back to the shared value; unknown provider name falls back to shared.

## 3. Wire resolvers into both consumption paths

- [x] 3.1 Direct-chat classify: switch `core/metadata/llamacpp.py` and `core/metadata/ollama.py` from `_get_classify_timeout(resolved)` to `_resolve_classify_timeout(resolved, "<its provider>")`; do the same for the OpenRouter chat path in `core/metadata/openrouter.py` (the standalone module the chat path actually lives in; `core/metadata/extractor.py` is dispatch-only).
- [x] 3.2 Pipeline: in `core/metadata/llamaindex.py`, pass `_resolve_pipeline_timeout(resolved, backend)` into `build()` instead of `resolved.metadata.pipeline_timeout`, reusing the `backend` already computed for registry lookup.
- [x] 3.3 Retire `_get_classify_timeout` if no caller remains (delete only if unused).
- [x] 3.4 Tests: with `LLAMACPP_PIPELINE_TIMEOUT` set, the llamaindex llama.cpp provider is built with that value; with `LLAMACPP_CLASSIFY_TIMEOUT` set, the direct-chat httpx client uses it; unset in both cases falls back to the shared values; openrouter unset uses the shared values.

## 4. Surface metadata degradation

- [x] 4.1 Add `extract_metadata_with_status_async(file_text, file_name, settings) -> tuple[dict, bool]` in `core/metadata/extractor.py`. It runs the existing dispatch and reports `degraded=True` when the configured mode is LLM-backed (`llamaindex`/`local`) but the result came from a lower tier. Keep `extract_metadata_async` as the dict-only public entry.
- [x] 4.2 Set the fallback flag at each abandon point: the `ImportError` and `except Exception` branches in `core/metadata/llamaindex.py`, and the exhausted-retry `uncategorised` fallback in the `local`/openrouter path. Thread it up to the wrapper. Implemented via a `contextvars.ContextVar` side channel (`_signal_degraded()` / `_degradation_flag` in `_common.py`) — a backend cannot know whether it was reached as the primary mode or as a fallback, so it only reports "no real classification happened"; the wrapper applies the configured-mode detection rule.
- [x] 4.3 In `core/ingestion/chunker.py`, call the status variant, forward the resolved `settings` (fixes the settings-drop bug at `chunker.py:168`), keep the dict for nodes, and return/record the degraded flag to the pipeline. Implemented via a `_ChunkResult(list)` subclass carrying a `metadata_degraded` attribute, so every existing caller that treats the return value as a plain list of nodes is unaffected.
- [x] 4.4 In `core/ingestion/pipeline.py`, aggregate degradation: add top-level `metadata_degraded` (int) to the `ok` result, and set `metadata_degraded: true` on affected `file_details` entries via `make_file_detail` (extend it to accept the marker).
- [x] 4.5 Tests: no degradation → `metadata_degraded == 0` and no per-file marker; one file times out → count `1` and exactly that entry marked; successful configured-mode extraction raises no signal; metadata dict written to chunks keeps `category` and gains no `_degraded` key.

## 5. Verification and docs

- [x] 5.1 Confirm each new test FAILS when its fix is reverted (override ignored, settings dropped, flag suppressed). Also verified the settings-parity test (1.3) fails when a field is removed from one model.
- [x] 5.2 Update `docs/guides/metadata-extraction.md` (degradation reporting + per-provider timeouts), `docs/guides/configuration.md` (six new vars + fallback behaviour), and the timeout notes in `docs/guides/providers.md`.
- [x] 5.3 Run `uv run pytest -m "not slow" --cov=rag_mcp`, `uv run lint-imports`, and `openspec validate fix-silent-metadata-degradation --strict`. All green.

## 6. Discovered during implementation (not in the original task list)

- [x] 6.1 `METADATA__OLLAMA_CLASSIFY_TIMEOUT` collided with an existing retired-name tripwire entry in `config/legacy.py` (`_RETIRED_ENV_VARS`), left over from `rename-classify-settings`. Reclaiming the name would silently change semantics for operators who had it set (their timeout would apply only to ollama instead of all backends). All six override fields use an `_override` suffix (e.g. `ollama_classify_timeout_override`) to avoid the collision entirely; the tripwire stays active.
