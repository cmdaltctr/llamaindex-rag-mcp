## Why

`compose.py::_resolve_active_strategies` silently `continue`s when a configured strategy name is absent from the registry. The function's stated purpose is to "fail fast on a bad import string", but it only validates names that ARE in the registry — a typo in `CHUNKING__STRATEGY_FALLBACK` or `METADATA__EXTRACTION_MODE` passes through silently and fails at query time instead.

The `silent-failure-audit-and-guards` change sharpened the inconsistency: after §6, the `embeddings` and `llm` entries in that same loop are pre-validated and raise at settings resolution, while `chunking.strategy_fallback` and `metadata.extraction_mode` have no validation anywhere and still silently `continue` on a typo.

The reason this was deferred from `silent-failure-audit-and-guards` is that "not in the registry" does not mean "invalid": `METADATA__EXTRACTION_MODE=local` is a documented, valid value that is absent from the metadata registry (registered names are `keyword`, `ollama`, `llamacpp`, `llamaindex`, `openrouter`) because that mode is dispatched inline. A naive raise-on-unregistered would break a supported configuration.

## What Changes

- Separate genuinely-inline-dispatched modes from typos in `METADATA__EXTRACTION_MODE` and `CHUNKING__STRATEGY_FALLBACK`.
- For `METADATA__EXTRACTION_MODE`: the accepted set is `disabled`, `keyword`, `local`, `llamaindex`, `ollama`, `llamacpp`, `openrouter`. Values not in this set raise at settings resolution. This is pure-data validation — the accepted set is a static literal, so it stays in `config/` without importing any `core/` registry.
- For `CHUNKING__STRATEGY_FALLBACK`: validate against the chunking registry's available names **in `compose.py`**, not in `config/`. The `config/` package is a leaf that cannot import `core/` business logic (architecture invariant #1), so registry membership is checked at startup in `_resolve_active_strategies` before the silent `continue` fires. A name not in the registry raises at startup.
- Update `_resolve_active_strategies` to remove the silent `continue` for names that should have been pre-validated, or document why the `continue` remains for specific inline-dispatched values.

## Impact

- **Code**: `src/rag_mcp/config/__init__.py` (pure-data validation for `METADATA__EXTRACTION_MODE` only), `src/rag_mcp/compose.py` (`_resolve_active_strategies` — chunking registry membership check at startup).
- **Tests**: new tests for unrecognised `METADATA__EXTRACTION_MODE` raising at settings resolution; new tests for unrecognised `CHUNKING__STRATEGY_FALLBACK` raising at startup in `compose.py`.
- **Breaking**: a deployment with a typo in `CHUNKING__STRATEGY_FALLBACK` or `METADATA__EXTRACTION_MODE` (currently silently ignored) will fail startup.

## Filed by

`silent-failure-audit-and-guards` §8.6. This change is the follow-up; it is not implemented by that change.
