## Why

The current provider naming (`ollama`, `llamacpp`, `openrouter`) exposes implementation details to users and doesn't scale. Users think in terms of "local vs cloud", not which specific server binary they're running. The naming also creates confusion — `OLLAMA_CLASSIFY_MODEL` has no `LLAMACPP_CLASSIFY_MODEL` equivalent, and mixing providers requires knowing three different sets of env var prefixes. A two-tier `local`/`cloud` category with a sub-provider (`LOCAL_BACKEND`, `CLOUD_BACKEND`) simplifies the mental model while preserving mix-and-match flexibility.

## What Changes

- **BREAKING**: `EMBED_PROVIDER` accepts `local` or `cloud` (was `ollama`, `llamacpp`, `openrouter`). Default: `local`.
- **BREAKING**: `METADATA_LLM_PROVIDER` accepts `local` or `cloud` (was `ollama`, `llamacpp`, `openrouter`). Default: `local`.
- **NEW**: `LOCAL_BACKEND=llamacpp|ollama` env var (default: `llamacpp`) — selects the local implementation when `EMBED_PROVIDER=local` or `METADATA_LLM_PROVIDER=local`.
- **NEW**: `CLOUD_BACKEND=openrouter` env var (default: `openrouter`) — selects the cloud implementation. Extensible to future cloud providers.
- **BREAKING**: `EMBED_PROVIDER=ollama`, `EMBED_PROVIDER=llamacpp`, `EMBED_PROVIDER=openrouter` are no longer valid values. Users must migrate to `EMBED_PROVIDER=local` + `LOCAL_BACKEND=ollama` (or `llamacpp`), or `EMBED_PROVIDER=cloud` + `CLOUD_BACKEND=openrouter`.
- The provider registry in `config.py` is restructured: `LOCAL_EMBED_PROVIDERS`, `CLOUD_EMBED_PROVIDERS`, `LOCAL_LLM_PROVIDERS`, `CLOUD_LLM_PROVIDERS` replace the flat `EMBED_PROVIDERS`/`LLM_PROVIDERS` dicts.
- `_build_provider()` resolves the category → sub-provider → registry entry → dynamic import chain.
- `metadata_extractor.py` dispatch logic checks `local`/`cloud` instead of `ollama`/`llamacpp`/`openrouter`.
- All documentation, `.env.example`, tests, and ADR-026 updated to the new naming.

## Capabilities

### New Capabilities

_None — this is a rename/restructure of existing functionality._

### Modified Capabilities

- `inference-backend`: Provider selection changes from flat names (`ollama`/`llamacpp`/`openrouter`) to category + sub-provider (`local`/`cloud` + `LOCAL_BACKEND`/`CLOUD_BACKEND`). All scenarios updated.
- `cloud-embed-providers`: OpenRouter is now selected via `EMBED_PROVIDER=cloud` + `CLOUD_BACKEND=openrouter` instead of `EMBED_PROVIDER=openrouter`. Registry structure changes to nested dicts.

## Impact

- **`src/rag_mcp/config.py`** — registry restructure, `_build_provider()` changes, new `LOCAL_BACKEND`/`CLOUD_BACKEND` env vars
- **`src/rag_mcp/metadata_extractor.py`** — dispatch logic for `local`/`cloud` instead of provider-specific names
- **`.env.example`** — all provider env vars restructured
- **`tests/conftest.py`** — test provider setup updated
- **`tests/unit/test_provider_config.py`** — all provider tests rewritten
- **`tests/test_metadata_extractor.py`** — provider references updated
- **`docs/guides/providers.md`**, **`configuration.md`**, **`architecture.md`**, **`metadata-extraction.md`**, **`getting-started.md`** — full documentation update
- **`docs/adr/026-provider-registry-and-openrouter.md`** — ADR updated to reflect new naming
- **`README.md`** — quick install and provider sections updated
- **`openspec/specs/inference-backend/spec.md`** and **`openspec/specs/cloud-embed-providers/spec.md`** — spec requirements updated
