# tests (Python test suite)

Fast tests (`-m "not slow"`) need no Ollama and no disk I/O. Slow tests carry the `slow` marker.

## Where to start

- Read [TEST_README.md](TEST_README.md) first.

## Rules

1. Build settings with the `effective_settings(**overrides)` fixture or `set_default_effective_settings(...)`. Do not undo the conftest defaults (`PDF_READER=pypdf`, `extraction_mode="disabled"`).
2. Patch a name at the module that defines it, not at a re-export.
3. Reranker tests call `reset_model_cache()`. Restore any logging handler or level that a test changes.
4. A new fast test changes `_BASE_EXECUTED` in `test_clean_base_tripwire.py`. A new slow test changes `_BASE_DESELECTED`. Update the count with a dated comment.
5. Parallel runs use `--dist loadfile`. Do not pass `--dist load`.
6. Chroma tests skip without the `chroma` extra. CI runs them in the chroma-extra job.

## Links

- [Root AGENTS.md](../AGENTS.md)
- [Testing guide](../docs/guides/testing.md)
