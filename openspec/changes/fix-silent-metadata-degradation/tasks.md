## 1. Settings: six per-provider timeout overrides

- [ ] 1.1 Add `{llamacpp,ollama,openrouter}_classify_timeout` and `{llamacpp,ollama,openrouter}_pipeline_timeout` to `MetadataSettings` in `core/metadata/settings.py`, all `float | None = Field(default=None, gt=0)`, with docstring comments.
- [ ] 1.2 Mirror the six fields into the `MetadataSettings` block in `core/settings.py` with identical defaults and validators.
- [ ] 1.3 Extend the settings round-trip/parity test to assert the two models declare the same fields and defaults (fails if one drifts).
- [ ] 1.4 Document the six vars in `.env.example` and `config/defaults.yaml` (nested `metadata.*`), noting each falls back to the shared `classify_timeout`/`pipeline_timeout`.

## 2. Timeout resolution helpers

- [ ] 2.1 Add `_resolve_classify_timeout(resolved, provider)` and `_resolve_pipeline_timeout(resolved, provider)` to `core/metadata/_common.py`: return the provider-specific override if set, else the matching shared timeout.
- [ ] 2.2 Unit tests for both resolvers: override honoured per provider; `None` falls back to the shared value; unknown provider name falls back to shared.

## 3. Wire resolvers into both consumption paths

- [ ] 3.1 Direct-chat classify: switch `core/metadata/llamacpp.py` and `core/metadata/ollama.py` from `_get_classify_timeout(resolved)` to `_resolve_classify_timeout(resolved, "<its provider>")`; do the same for the OpenRouter chat path in `core/metadata/extractor.py`.
- [ ] 3.2 Pipeline: in `core/metadata/llamaindex.py`, pass `_resolve_pipeline_timeout(resolved, backend)` into `build()` instead of `resolved.metadata.pipeline_timeout`, reusing the `backend` already computed for registry lookup.
- [ ] 3.3 Retire `_get_classify_timeout` if no caller remains (delete only if unused).
- [ ] 3.4 Tests: with `LLAMACPP_PIPELINE_TIMEOUT` set, the llamaindex llama.cpp provider is built with that value; with `LLAMACPP_CLASSIFY_TIMEOUT` set, the direct-chat httpx client uses it; unset in both cases falls back to the shared values; openrouter unset uses the shared values.

## 4. Surface metadata degradation

- [ ] 4.1 Add `extract_metadata_with_status_async(file_text, file_name, settings) -> tuple[dict, bool]` in `core/metadata/extractor.py`. It runs the existing dispatch and reports `degraded=True` when the configured mode is LLM-backed (`llamaindex`/`local`) but the result came from a lower tier. Keep `extract_metadata_async` as the dict-only public entry.
- [ ] 4.2 Set the fallback flag at each abandon point: the `ImportError` and `except Exception` branches in `core/metadata/llamaindex.py`, and the exhausted-retry `uncategorised` fallback in the `local`/openrouter path. Thread it up to the wrapper.
- [ ] 4.3 In `core/ingestion/chunker.py`, call the status variant, forward the resolved `settings` (fixes the settings-drop bug at `chunker.py:168`), keep the dict for nodes, and return/record the degraded flag to the pipeline.
- [ ] 4.4 In `core/ingestion/pipeline.py`, aggregate degradation: add top-level `metadata_degraded` (int) to the `ok` result, and set `metadata_degraded: true` on affected `file_details` entries via `make_file_detail` (extend it to accept the marker).
- [ ] 4.5 Tests: no degradation → `metadata_degraded == 0` and no per-file marker; one file times out → count `1` and exactly that entry marked; successful configured-mode extraction raises no signal; metadata dict written to chunks keeps `category` and gains no `_degraded` key.

## 5. Verification and docs

- [ ] 5.1 Confirm each new test FAILS when its fix is reverted (override ignored, settings dropped, flag suppressed).
- [ ] 5.2 Update `docs/guides/metadata-extraction.md` (degradation reporting + per-provider timeouts), `docs/guides/configuration.md` (six new vars + fallback behaviour), and the timeout notes in `docs/guides/providers.md`.
- [ ] 5.3 Run `uv run pytest -m "not slow" --cov=rag_mcp`, `uv run lint-imports`, and `openspec validate fix-silent-metadata-degradation --strict`. All green.
