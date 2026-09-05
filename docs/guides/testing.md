# Testing

## Running tests

```bash
# The fast suite. Run this routinely.
uv run pytest -m "not slow" -v

# With coverage
uv run pytest -m "not slow" --cov=omrg --cov-report=term-missing

# The slow end-to-end test (starts a real server over stdio)
uv run pytest -m slow -v

# One file
uv run pytest tests/test_reranker.py -v
```

The fast suite runs in about 80 seconds. It uses mock embeddings and an
in-memory database, so it needs no Ollama, no llama.cpp, no network, and
downloads nothing.

There is also an architecture check that is not part of pytest:

```bash
uv run lint-imports
```

That verifies the module boundaries. It must pass before you commit.

---

## The one thing to know: inject, don't patch

This is the biggest change from older versions of this codebase, and knowing it
will save you an afternoon.

**There is no settings singleton.** You cannot patch `config.settings`, because
it does not exist. Core functions receive a frozen `EffectiveSettings` object as
an argument.

So instead of patching a global, build settings and pass them in:

```python
def test_top_k_is_honoured(effective_settings):
    settings = effective_settings(top_k=20)
    results = search("query", effective_settings=settings)
    assert len(results) <= 20
```

`effective_settings` is a factory fixture in `conftest.py`. It accepts flat or
dotted names:

```python
effective_settings(top_k=20)  # routed to retrieval.top_k
effective_settings(**{"retrieval.top_k": 20})  # the same thing
effective_settings(chroma_persist_dir="/tmp/x")  # a top-level field
```

An unknown name raises `TypeError` rather than being ignored. That is
deliberate: silently dropped overrides were making tests pass for the wrong
reason.

### When the code reads the default instead

Some code reads the composition root's default rather than taking a parameter —
the vector store, the PDF factory, the Magika wrapper. For those, install a
default:

```python
from omrg.core.settings import EffectiveSettings, set_default_effective_settings

set_default_effective_settings(EffectiveSettings(chroma_scan_page_size=1))
```

`conftest.py` installs one before every test and clears it afterwards, so
nothing leaks between tests.

---

## Patch the module that owns the function

If a function moved, its patch target moved too. Patching the module that
re-exports it does nothing at all.

| Function                                             | Lives in                       |
| ---------------------------------------------------- | ------------------------------ |
| `_is_magika_available`                               | `omrg.integrations.magika`  |
| `_get_git_commit_hash`, `_load_cache`, `_save_cache` | `omrg.core.codebase.cache`  |
| `format_codebase_map`                                | `omrg.core.codebase.format` |
| `Observer`                                           | `omrg.daemon.runner`        |
| `search`, `_list_documents`                          | `omrg.transports.mcp`       |

---

## Gotchas

**Reset the reranker model cache.** Tests touching the reranker must call
`reset_model_cache()` in setup and teardown. The model is cached process-wide,
so a leftover instance leaks into the next test.

**Pin the PDF reader.** Tests need `pdf_reader="pypdf"`. The packaged default
is `pdf_inspector`, and `auto` probes for LiteParse. Each reader emits
different document boundaries, so only `pypdf` keeps tests deterministic. The
conftest default already sets this.

**Metadata extraction is off in tests.** The conftest default sets
`extraction_mode="disabled"`. The real default is `llamaindex`, which would make
every ingestion test call a live LLM and hang on network timeouts.

**Database state can leak.** The conftest fixture clears collections between
tests. Build your own client and bypass it, and the cleanup is yours.

**Do not write timing assertions.** `assert elapsed < 0.5` measures how busy the
machine is, not whether the code is correct. Assert the property instead — for
instance, that a concurrent search finishes _while an ingest is still
deliberately paused on an Event_. If the loop were blocked it could not finish
at all. See `tests/test_async_ingest_responsiveness.py`, where converting the
stopwatch assertions exposed two tests that had been passing while measuring
nothing.

---

## Coverage floors

Enforced per tier, not as one flat number.

| Tier          | Floor | What it covers                                                                                                                                           |
| ------------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core + MCP    | 95%   | `core/ingestion`, `core/retrieval`, `core/metadata`, `core/chunking`, `core/vectordb`, `core/profiles`, `core/settings.py`, `config/`, `transports/mcp/` |
| Orchestration | 85%   | `daemon/`, `transports/cli/`                                                                                                                             |
| Overall       | 90%   | everything                                                                                                                                               |

```bash
uv run pytest -m "not slow" --cov=omrg
```

Nothing is excluded. The old exclusion list covered compatibility shims, which
no longer exist.

---

## Tests that guard the architecture

These fail when a structural rule is broken. If one fails, the fix is usually in
the source, not the test.

| Test                                       | What it catches                                                                  |
| ------------------------------------------ | -------------------------------------------------------------------------------- |
| `test_no_global_settings_reads.py`         | A `core/` module importing the settings singleton                                |
| `test_file_size_ceiling.py`                | Any file over 500 lines                                                          |
| `test_no_module_level_strategy_imports.py` | A dispatcher importing a strategy directly instead of going through the registry |
| `test_registry_contract.py`                | A registry that eagerly imports its strategies, or a broken import string        |
| `test_contract_coverage.py`                | A package covered by no import-linter contract                                   |
| `test_config_no_legacy_surface.py`         | The v1 config surface creeping back                                              |

One more that surprises people: `lint-imports` fails when a _suppression_
becomes unnecessary. Fix a boundary violation, forget to delete its exception,
and the build tells you. That is how every temporary exception from the v2 work
got removed. See [ADR-037](../adr/037-architecture-v2-conformance.md).

---

## Cloud storage tests

Three test files cover the cloud backend and experiment storage. All run in
the fast suite.

- `tests/test_chroma_cloud.py` — mode and credential validation, the
  factory's constructor arguments, secret redaction, embedding-identity
  enforcement, local/cloud parity, and the chromadb import boundary.
- `tests/test_chroma_cloud_smoke.py` — fake cloud-operation failures that
  verify the manual smoke script redacts secrets from operation and cleanup logs.
- `tests/test_experiment_storage.py` — deterministic collection naming,
  the experiment storage config, and a runner migration guard that scans
  the six calibration harnesses for direct chromadb usage.

All cloud tests use fakes. No test contacts Chroma Cloud. The opt-in smoke
check (`scripts/chroma_cloud_smoke.py`) is manual-only and never runs in CI.

---

## Writing a new test

- Put it in `tests/`, named `test_*.py`.
- Use the `effective_settings` fixture rather than patching anything.
- Mark it `@pytest.mark.slow` if it needs a real model, a network call, or more
  than a second or two.
- Async tests need no decorator; `asyncio_mode` is set in `pyproject.toml`.

Before committing:

```bash
uv run pytest -m "not slow" --cov=omrg
uv run lint-imports
```
