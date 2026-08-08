## Why

The default ingestion path (`METADATA_EXTRACTION_MODE=llamaindex`, `METADATA_LLM_PROVIDER=local`, llama.cpp backend) silently degrades to keyword-mode metadata when the LLM call times out, with only a log WARNING to show for it. On larger documents this means chunks are indexed with regex keyword categories instead of the intended LLM classification, and the caller has no way to know.

Prior work on the `v3` branch (PRs #24 and #22) already fixed the acute cause: the `OpenAILike` timeout keyword bug is gone, the three hardcoded `180.0` timeouts were removed, provider construction routes through the LLM registry with a `timeout=` parameter, and two shared settings now exist — `metadata.classify_timeout` (30s, per-attempt for the direct-chat path) and `metadata.pipeline_timeout` (180s, the longer budget for the llamaindex multi-extractor pipeline). Two gaps remain: the timeouts are shared across all providers, so a slow local box and a fast cloud endpoint cannot be tuned independently; and the degradation itself is still invisible outside the logs. The chunker also still drops resolved settings when calling `extract_metadata_async`.

## What Changes

- **Surface the degradation.** When metadata extraction falls back from the configured LLM-backed mode (`llamaindex`/`local`) to a lower tier, the ingestion result dict SHALL report it: a `metadata_degraded` count at the top level and a per-file marker in `file_details`. The fallback stops being invisible in the tool response.
- **Per-provider timeout overrides for BOTH timeouts.** Add six optional fields on `MetadataSettings` — `{llamacpp,ollama,openrouter}_classify_timeout` and `{llamacpp,ollama,openrouter}_pipeline_timeout` — each `None` by default and falling back to the shared `classify_timeout` / `pipeline_timeout` respectively. Two resolvers map the active provider to its effective classify and pipeline timeout. Each is env-overridable per machine (e.g. `METADATA__LLAMACPP_PIPELINE_TIMEOUT`). A new provider added later needs no timeout field to work — it inherits the shared default until someone tunes it.
- **Wire the resolvers into both consumption paths.** The direct-chat backends (`metadata/llamacpp.py`, `metadata/ollama.py`, the OpenRouter chat path in `metadata/extractor.py`) resolve their classify timeout per provider instead of reading the shared `classify_timeout` directly. The llamaindex pipeline (`metadata/llamaindex.py`) passes the per-provider-resolved pipeline timeout into `build()` instead of the shared `pipeline_timeout`.
- **Fix the settings-drop bug.** `core/ingestion/chunker.py` SHALL forward the resolved `settings` to metadata extraction so profile-level configuration reaches it (invariant #9).

This change builds on the `v3` branch state after PRs #22/#24/#25; it does not re-touch the hardcoded-timeout sites (already removed) and targets `v3`, not `main`.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `metadata-extraction`: the `LlamaIndex MetadataExtractor integration` requirement gains per-provider timeout resolution and a fallback-signalling contract (extraction reports when it degrades rather than only logging).
- `async-ingestion`: the ingestion result dict gains a `metadata_degraded` count and a per-file degradation marker in `file_details`, additively (existing keys unchanged).

## Impact

- **Settings**: `MetadataSettings` (`core/metadata/settings.py`, mirrored in `core/settings.py`) gains six optional timeout fields (three classify + three pipeline). `.env.example` and `config/defaults.yaml` documented.
- **Code**: `core/metadata/_common.py` (two resolver helpers), `core/metadata/llamacpp.py` + `core/metadata/ollama.py` + `core/metadata/extractor.py` (direct-chat classify resolution + degradation signal), `core/metadata/llamaindex.py` (pipeline timeout resolution + degradation signal), `core/ingestion/chunker.py` (forward settings + capture degradation), `core/ingestion/pipeline.py` (aggregate degradation into result dict).
- **Tests**: new tests for both resolvers per provider, degradation surfacing in the result dict, and the chunker settings-forwarding fix. Coverage floors: `core/metadata` and `core/ingestion` are ≥95% tier.
- **Docs**: `docs/guides/metadata-extraction.md`, `docs/guides/configuration.md`, and the provider timeout notes in `docs/guides/providers.md`.
- **No breaking changes**: result keys are additive; all six new settings default to `None` and inherit the existing shared timeouts, preserving current behaviour.
