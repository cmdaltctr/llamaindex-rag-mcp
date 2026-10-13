# Evidence: metadata store ownership (design D2)

Scope: tasks 1.2 (taxonomy part), 3.1 (metadata half), 3.2, 3.3, 3.4 and 3.5.

Worktree: `llamaindex-rag-mcp-v3-feat-repair-modular-core-boundaries`, branch
`feat/repair-modular-core-boundaries`, base commit `3ca82a0`. Date 2026-10-13.

Interpreter (no install, no `.venv` in the worktree):

```bash
cd <worktree>
PYTHONPATH=src /Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3/.venv/bin/python \
  -m pytest <tests> -q -p no:cacheprovider
```

All tests use a fake `httpx.AsyncClient` that records each prompt. No model,
network, Ollama, llama.cpp or OpenRouter call is made. Stores are in-memory
doubles or temporary LanceDB directories.

## 1.2 Reproduction on unchanged code

A probe built the shared prompt with a poisoned process-default store
installed, then with no default store:

```text
WARNING:omrg.core.metadata._common:Failed to query vector store for existing categories:
  No default vector store has been composed yet. ... — classification will use seed categories only
poisoned default leaks into prompt: True
absent default prompt built (warning above): True
```

So the prompt read the process default (`get_default_store()` in
`taxonomy._gather_existing_categories`). A poisoned default leaked its labels.
An absent default gave a swallowed warning and seed-only labels, also for
Engine ingestion that owns a different store.

## Regression tests

New file `tests/test_metadata_store_ownership.py` (38 test cases). Each case
runs twice through the `default_store` fixture: once with **no** default store
(the accessor raises) and once with a **poisoned** default that records access
and offers `poison_label`. Every case asserts the poisoned store was never
called, so a swallowed lookup cannot pass.

| Test | Task | Proves |
|---|---|---|
| `test_supplied_store_labels_reach_prompt` (ollama, llamacpp, openrouter) | 3.2, 3.4 | Labels from **all** collections of the supplied store reach each shared-prompt provider; `None` rows and rows without `category` are skipped; labels are normalised; seeds merge. |
| `test_disjoint_stores_interleaved` | 3.2 | Four concurrent classifications over two disjoint stores and two seed sets. Each prompt holds exactly its own labels and seeds. |
| `test_two_engines_interleaved_ingestion_prompts` (A-first, B-first) | 3.2 | Two Engines over separate LanceDB stores (`scan_page_size=1`, so every label is on its own page). Round two ingests into a new collection; each prompt must hold its own round-one label from the other collection and not the other Engine's label. Uses the chunker forwarding from agent A. |
| `test_standalone_without_store_is_seed_only` (3 providers) | 3.3 | No store gives seeds plus `uncategorised` only, no WARNING, `degraded=False`, no default lookup. |
| `test_supplied_store_failure_warns_and_uses_seeds` | 3.3 | A failing supplied store keeps the existing WARNING and seed fallback; the result shape is unchanged and `degraded=False`. |
| `test_collection_failure_keeps_healthy_siblings` | 3.3 | One unreadable collection is skipped; a healthy sibling still contributes. |
| `test_retry_budget_and_degradation_with_store` (3 providers) | 3.3 | With `classify_max_attempts=3` and a failing backend: exactly 3 attempts, each prompt holds the owning label, the prompt is built once, the fallback shape is unchanged and `degraded=True`. |
| `test_llamaindex_import_fallback_forwards_store` | 3.4 | Missing LLM package: the local fallback prompt holds the owning label. |
| `test_llamaindex_pipeline_fallback_forwards_store` | 3.4 | Pipeline failure: the local fallback prompt holds the owning label. |
| `test_registered_strategies_accept_keyword_only_store` | 3.1 | Every registered strategy and both entry points keep positional `file_name, settings` and add keyword-only `store=None`. |
| `test_custom_strategy_receives_store_through_dispatch` | 3.1 | A custom strategy installed in the registry receives the same store object through production dispatch. |
| `test_modes_without_lookup_ignore_store` (keyword, disabled) | 3.1 | These modes accept a store, never read it, and give the same result as without one. |

## Before the fix (tests written first)

```text
38 failed in 1.14s
  33  TypeError: extract_metadata_with_status_async() got an unexpected keyword argument 'store'
   4  assert 0 == 2   (Engine test: ingestion failed on the same TypeError, so no prompts)
   1  KeyError: 'store' (signature test)
```

The chunker already forwarded `store=` (agent A), so the unchanged metadata
entry points rejected the keyword. The mutation check below shows the
prompt-content failures the tests catch once the keyword exists.

## Fix

- `taxonomy._gather_existing_categories(*, store=None)`: scans the supplied
  store only. `None` returns `[]` with no warning. The `get_default_store` and
  `resolve_effective_settings` imports were removed. `_get_seed_categories`
  now requires resolved settings.
- `ollama._build_ollama_prompt(text, settings, *, store=None)`: the shared
  prompt for Ollama, llama.cpp and OpenRouter forwards the store.
- All registered strategies (`keyword`, `ollama`, `llamacpp`, `openrouter`,
  `llamaindex`) accept keyword-only `store=None`. Both `llamaindex` fallback
  paths forward it to `_dispatch_local_extraction(..., store=store)`.
- `extractor`: `extract_metadata_async`, `extract_metadata_with_status_async`
  and `_dispatch_local_extraction` accept and forward `store`. Optional
  settings still resolve at these documented entry points only.
- Backends keep their existing `resolve_effective_settings(settings)` call,
  because they remain directly callable with positional optional settings.
  Production dispatch always passes resolved settings.

## After the fix

```text
tests/test_metadata_store_ownership.py                       38 passed
metadata files (extractor, degradation, timeout, provider_config, ownership)
                                                             203 passed, 5 skipped
wider set (28 metadata/chunking/ingestion files + document_registry_dispatch,
no_global_settings_reads, engine_isolation, registry_contract,
file_size_ceiling), -m "not slow"                            552 passed, 34 skipped
```

The 5 skips in the metadata files are Chroma-only tests (`chromadb` is not
installed in this interpreter). They were migrated to pass the store
explicitly but were not executed here.

`ruff check` and `ruff format --check` pass on all changed metadata source and
test files.

## Mutation check

Each mutation was applied to the fixed code, the ownership file was run, then
the file was restored from a scratch copy (`diff -q` confirmed).

| Mutation | Result |
|---|---|
| M1: taxonomy ignores the supplied store and uses a swallowed `get_default_store()` lookup | 32 failed, 6 passed. Engine test fails on prompt contents, e.g. `assert 'zenith_topic' in {'ai', ..., 'poison_label', ...}` |
| M2: LlamaIndex fallback drops `store=store` | 4 failed (both fallback tests × both default modes) |
| M3: shared prompt builder drops `store=store` | 26 failed |
| Restored | 38 passed |

## Signature-sensitive doubles updated (3.5)

Test doubles now accept `*, store=None` explicitly. No signature inspection or
name-based branching was added to production code.

- `tests/test_metadata_extractor.py`: `_fake_ollama` (×3), `_failing_ollama`,
  `fake_extract_llamaindex_async` (×2). Taxonomy tests now pass the store
  (`_gather_existing_categories(store=...)`, `_build_ollama_prompt(..., store=...)`,
  `extract_metadata_async(..., store=...)`) and seed tests pass settings
  explicitly, instead of installing a process default.
- `tests/test_metadata_degradation.py`: `_fake_ollama` (×2), `_fake_llamaindex`,
  `_degrading_llamaindex`, `_degrading_ollama`.
- `tests/test_metadata_timeout_resolution.py`: `_fake_dispatch`.
- `tests/unit/test_provider_config.py`: dispatch assertions now expect
  `store=None`.

Guide: `docs/guides/metadata-extraction.md`, new section "Existing categories
and the owning store".

## Open points

- The Chroma-specific category tests were not run (no `chromadb` here). Run
  them in the chroma-extra CI job.
- Backends still call `resolve_effective_settings` for direct callers that
  omit settings. If agent D's guard treats that call as a leaf default read in
  backends, move resolution out of the backends and update their direct-call
  tests.
