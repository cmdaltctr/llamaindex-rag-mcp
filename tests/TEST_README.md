# Test Suite — Front Door

This is the front door for the test suite. If you are here to run tests
or add a new one, start here. For the wider testing strategy and
coverage policy, see [`docs/guides/testing.md`](../docs/guides/testing.md).
For the hard rules and non-obvious gotchas, see [`AGENTS.md`](../AGENTS.md).

---

## Quick start

```bash
# Fast suite — no Ollama, no ONNX download, no disk I/O. Run these routinely.
uv run pytest -m "not slow" -v

# With coverage (must stay above the per-module floors below)
uv run pytest -m "not slow" --cov=rag_mcp --cov-report=term-missing

# E2E stdio smoke test (slow — boots a real `uv run rag-mcp` subprocess)
uv run pytest -m slow -v

# Single test file
uv run pytest tests/test_reranker.py -v

# Single test by name
uv run pytest tests/test_reranker.py::TestSigmoidScoring::test_sigmoid_zero -v
```

The fast suite uses mock embeddings and an in-memory ChromaDB client —
no external services needed. If a test fails because Ollama is not
running, the test is wrong; the fast suite must never depend on Ollama.

---

## Coverage floors

Coverage is enforced per-module rather than as a single flat number.
Floors in CI:

| Module type | Floor | Modules |
|-------------|-------|---------|
| Core logic | ≥95% | `ingestion.py`, `retrieval.py`, `reranker.py`, `metadata_extractor.py`, `config.py` |
| MCP wrappers | ≥95% | `server.py` |
| Orchestration | ≥85% | `watcher.py` |
| CLI | ≥85% | `cli.py` |
| **Overall** | **≥90%** | all |

If you add a module, assign it to the appropriate tier and document
exceptions inline. Rationale for the per-tier policy lives in
[`docs/guides/testing.md`](../docs/guides/testing.md) and was renegotiated
during the `make-ingest-path-async` OpenSpec change.

---

## Test files

| File | Tests | Coverage area |
|------|-------|---------------|
| `test_watcher.py` | 39 | File watcher: debounce, hash dedup, throttling, shutdown, error handling, on_deleted |
| `test_reranker.py` | 23 | Sigmoid, ONNX variant, singleton, fallback, mock inference, model loading |
| `test_cli.py` | 93 | CLI validation, formatting, edge cases, delete subcommand |
| `test_metadata_extractor.py` | 40 | Keyword, disabled, custom rules, ollama (JSON parsing, normalisation, hybrid taxonomy), llamaindex (pipeline, fallback, aggregation), unknown mode fallback |
| `test_ingestion.py` | 20 | Path validation, empty dir, list empty, collection routing, metadata attachment, delete functions, upsert |
| `test_retrieval.py` | 17 | Empty store, threshold, rerank flag, threshold scaling, collection search, metadata filter, list collections |
| `test_mcp_tools.py` | 19 | Tool discovery, ingest, search, list, list_collections, collection params, backward compat, delete_documents |
| `test_signal_handling.py` | 13 | SIGINT, shutdown flag, lock recheck |
| `test_ingestion_parallel.py` | 21 | Concurrent ingestion, all-or-nothing semantics |
| `test_async_ingest_responsiveness.py` | — | Responsiveness contract: search returns within 500 ms while ingest is in flight |
| `test_e2e_stdio.py` | 1 | JSON-RPC handshake over stdio subprocess (`@pytest.mark.slow`) |

---

## What `conftest.py` does for you

Three autouse fixtures run before every test. You generally do not need
to think about them — they are why the fast suite has no external
dependencies — but you do need to know about the side effects.

**1. ChromaDB → shared `EphemeralClient`**.
`PersistentClient` and `EphemeralClient` are both replaced with a
single in-memory client. Collections are cleared at the start of each
test. No `chroma_db/` directory is ever created on disk.

**2. `Settings.embed_model` → `MockEmbedding(384)`**.
LlamaIndex's global embedding model is replaced with a deterministic
mock that hashes text. Tests run without Ollama. Note: `config.py`
sets `Settings.embed_model = OllamaEmbedding(...)` at import time, so
the `mcp_server` fixture re-applies the mock after server import. If
you write a test that imports `rag_mcp.server` outside that fixture,
re-apply the mock yourself.

**3. Settings are injected, not patched via `sys.modules`**.
There is no singleton to patch. Tests use the `effective_settings(**overrides)`
conftest factory, or `set_default_effective_settings(...)` for code that reads
the composition-root default. The conftest default deliberately sets
`extraction_mode="disabled"` and `pdf_reader="pypdf"` — the class defaults
would make ingestion tests perform real LLM calls and hang on network timeouts
(CLAUDE.md gotcha 8a).

---

## Gotchas

This is the section that saves you an hour of debugging.

**Reranker singleton.** `CrossEncoderReranker.__new__()` returns one
instance per process. If your test loads or configures the reranker,
reset it in `setup_method` and `teardown_method`:

```python
from rag_mcp.core.retrieval.reranker import reset_model_cache


class TestSomeRerankerThing:
    def setup_method(self):
        reset_model_cache()

    def teardown_method(self):
        reset_model_cache()
```

Otherwise the next test inherits whatever model and config the previous
test set up, and you will spend an hour wondering why mocks are not
being called.

**`EphemeralClient` shares state across instances.** ChromaDB's
`EphemeralClient` instances share an in-memory backend by default. The
autouse fixture clears all collections at the start of each test, but
if you bypass the fixture or create a new `PersistentClient`, data
leaks between tests. Use the shared client through the fixture.

**Settings are injected, not read from the environment.**
There is no module-level constant to patch. Use
`set_default_effective_settings(...)` or the `effective_settings(**overrides)`
conftest factory to control the extraction mode in tests:

```python
def test_keyword_extraction(monkeypatch):
    from rag_mcp.core.settings import (
        EffectiveSettings,
        MetadataBlock,
        set_default_effective_settings,
    )

    set_default_effective_settings(
        EffectiveSettings(metadata=MetadataBlock(extraction_mode="keyword"))
    )
    ...
```

**`@pytest.mark.slow` is excluded by default.** The CI command and the
`Quick start` block above both run `-m "not slow"`. If you mark a test
slow, it is opt-in via `-m slow` or running the file directly. The E2E
stdio test is the canonical slow test — it boots a real subprocess.

**`connected_client` is an `asynccontextmanager`, not a fixture.**
Import it directly:

```python
from conftest import connected_client


async def test_some_mcp_tool(mcp_server):
    async with connected_client(mcp_server) as session:
        result = await session.call_tool("search_documents", {...})
```

**MCP tool handlers must never raise.** They return
`{"status": "error", "message": "..."}` instead. Tests that exercise
error paths assert on the dict, not on a raised exception.

**Tool parameters are backward-compatible.** All MCP tool parameters
are optional with defaults. New parameters added to existing tools
must remain optional. Tests under `test_mcp_tools.py::TestBackwardCompat`
enforce this.

**The `÷30` reranker threshold scaling is empirically calibrated.**
When `rerank=True`, `similarity_threshold` is divided by 30. Do not
change the factor without re-running `experiments/reranker-threshold-calibration-2026-05-12/`.

---

## Adding a new test

**Where it goes.** One file per module-under-test. New module
`rag_mcp/foo.py` → new file `tests/test_foo.py`. Don't bolt unrelated
tests onto an existing file just because the file is open in your
editor.

**Pattern.** Class-based with descriptive method names. Look at
`test_reranker.py::TestSigmoidScoring` or
`test_metadata_extractor.py::TestKeywordExtraction` for the shape.
Async tests use `@pytest.mark.asyncio` (asyncio mode is `auto` in
`pyproject.toml`, so plain `async def test_...` also works).

**Fixtures.** Reusable test data goes under `tests/fixtures/`. The
existing fixtures (`sample.txt`, `sample.md`, `pdf_dir`, `corrupt_dir`,
`dir_with_docs`) are exposed via named fixtures in `conftest.py`. Add
new fixtures the same way: drop the file, add a `@pytest.fixture` in
`conftest.py` returning the path.

**Markers.** Use `@pytest.mark.slow` for any test that boots a
subprocess, hits a real network, or takes more than a few seconds.
Everything else stays in the fast suite.

**Coverage.** Run `uv run pytest -m "not slow" --cov=rag_mcp
--cov-report=term-missing` and check that your new module hits its
floor before pushing.

---

## When tests fail

**Read the failure.** Pytest's diff is usually enough.

**Re-run just the failure with `-x` and `-vv`.** `pytest -x -vv
tests/test_foo.py::TestBar::test_baz` stops on the first fail and
shows full assertion context.

**Suspect the autouse fixtures.** If a test passes alone but fails in
the suite, you are probably leaking state. Most common culprits:
reranker singleton, `EphemeralClient` collections, the
`set_default_effective_settings` default.

**Suspect Ollama.** The fast suite must never call Ollama. If a fast
test connects to Ollama, find the real network call and mock it.

**Slow E2E failure?** It boots `uv run rag-mcp`. If the binary is
broken, the slow test is the canary. Run `uv run rag-mcp` by hand and
see what stderr says.

---

## See also

- [`docs/guides/testing.md`](../docs/guides/testing.md) — wider testing strategy and coverage policy
- [`AGENTS.md`](../AGENTS.md) — non-obvious rules, hard boundaries, and architecture invariants
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — overall contribution loop
- [`pyproject.toml`](../pyproject.toml) — pytest configuration, markers, asyncio mode


## Retrieval quality gate

The committed synthetic corpus has two deliberately narrow regression tiers.

Tier 1 is deterministic and needs no Ollama service. Run its metric and
slow-marked production-path cases with:

```bash
uv run pytest tests/quality/test_metrics.py tests/quality/test_retrieval_quality_tier1.py -m slow --tb=short -q -s
```

Confirm the ordinary selector collects no slow quality case with:

```bash
uv run pytest tests/quality -m "not slow" --collect-only -q
```

Tier 2 requires a running Ollama service with the exact
`qwen3-embedding:0.6b` tag already pulled:

```bash
ollama pull qwen3-embedding:0.6b
uv run pytest tests/quality/test_retrieval_quality_tier2.py -m slow --tb=short -q -s
```

For baseline work, run the Tier 2 command at least three times and preserve each
printed `TIER2_MEASUREMENT` record. Use a second architecture when available.
The test fails, rather than skips, when Ollama is absent, the model tag or
recorded digest differs, a fixture identity differs, or the baseline is invalid
or still pending. The Ollama version, OS, and architecture are recorded as
measurement evidence; the nightly job runs a different pinned Ollama build on a
different platform, and the floor margin absorbs that ranking variation.

This gate detects regressions in dense score conversion, reciprocal rank
fusion, threshold handling, and final ranking over the small fixed corpus. It
does not establish broad embedding quality or detect subtle model drift; those
questions still require the experiments process and production-representative
corpora.
