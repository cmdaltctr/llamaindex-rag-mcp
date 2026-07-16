## 1. Config.py — registry restructure

- [x] 1.1 Replace flat `EMBED_PROVIDERS` dict with `LOCAL_EMBED_PROVIDERS` and `CLOUD_EMBED_PROVIDERS` nested dicts
- [x] 1.2 Replace flat `LLM_PROVIDERS` dict with `LOCAL_LLM_PROVIDERS` and `CLOUD_LLM_PROVIDERS` nested dicts
- [x] 1.3 Update `_build_provider()` to accept `(category, sub_provider)` and resolve from nested registries
- [x] 1.4 Add `LOCAL_BACKEND` env var (default: `llamacpp`) with validation and fallback
- [x] 1.5 Add `CLOUD_BACKEND` env var (default: `openrouter`) with validation and fallback
- [x] 1.6 Change `EMBED_PROVIDER` default to `local`, valid values: `local|cloud`
- [x] 1.7 Change `METADATA_LLM_PROVIDER` default to `local`, valid values: `local|cloud`
- [x] 1.8 Update `Settings.embed_model = _build_provider(...)` call to pass category + sub-provider
- [x] 1.9 Update `EMBED_MODEL` validation — only required when `EMBED_PROVIDER=local` and `LOCAL_BACKEND=ollama`

## 2. Metadata extractor — dispatch logic

- [x] 2.1 Update imports: replace `METADATA_LLM_PROVIDER` check from `ollama`/`llamacpp`/`openrouter` to `local`/`cloud`
- [x] 2.2 Add `LOCAL_BACKEND` import from config
- [x] 2.3 Update `_dispatch_local_extraction` to check `METADATA_LLM_PROVIDER == "local"` then dispatch by `LOCAL_BACKEND`
- [x] 2.4 Update `_dispatch_local_extraction` to check `METADATA_LLM_PROVIDER == "cloud"` then dispatch by `CLOUD_BACKEND`
- [x] 2.5 Update `_extract_llamaindex_async` LLM construction to resolve via category + sub-provider

## 3. .env.example

- [x] 3.1 Replace `EMBED_PROVIDER=llamacpp` with `EMBED_PROVIDER=local`
- [x] 3.2 Replace `METADATA_LLM_PROVIDER=llamacpp` with `METADATA_LLM_PROVIDER=local`
- [x] 3.3 Add `LOCAL_BACKEND=llamacpp` with comment explaining ollama alternative
- [x] 3.4 Add `CLOUD_BACKEND=openrouter` (commented out, for cloud users)
- [x] 3.5 Update metadata extraction section comments to reference provider-specific model env vars via sub-provider

## 4. Tests

- [x] 4.1 Update `conftest.py` — set `EMBED_PROVIDER=local`, `LOCAL_BACKEND=ollama`, `METADATA_LLM_PROVIDER=local` at module load and in `_isolate_env`
- [x] 4.2 Rewrite `test_provider_config.py` — test `local`/`cloud` categories, `LOCAL_BACKEND`/`CLOUD_BACKEND` sub-providers, defaults, fallbacks
- [x] 4.3 Update `test_metadata_extractor.py` — replace provider-specific references with `local`/`cloud` + `LOCAL_BACKEND`
- [x] 4.4 Run full test suite and fix any remaining failures

## 5. Documentation

- [x] 5.1 Update `docs/guides/providers.md` — restructure around `local`/`cloud` + sub-providers
- [x] 5.2 Update `docs/guides/configuration.md` — provider selection table with new env vars
- [x] 5.3 Update `docs/guides/architecture.md` — provider table and registry description
- [x] 5.4 Update `docs/guides/metadata-extraction.md` — provider references
- [x] 5.5 Update `docs/guides/getting-started.md` — default provider reference
- [x] 5.6 Update `README.md` — quick install, badge, provider sections
- [x] 5.7 Update `docs/adr/026-provider-registry-and-openrouter.md` — full ADR rewrite for local/cloud naming

## 6. OpenSpec specs

- [x] 6.1 Verify `openspec validate --all --strict` passes
