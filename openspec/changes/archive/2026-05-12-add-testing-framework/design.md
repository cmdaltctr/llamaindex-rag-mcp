## Context

The `llamaindex-rag-mcp` project has 566 lines of production code across four
modules — ingestion, retrieval, reranker, and server — with zero automated
tests. Two completed OpenSpec changes shipped non-trivial features (cross-encoder
reranker, sigmoid normalisation, singleton recovery logic) verified only by
manual inspection. Every refactor, dependency upgrade, or new feature carries
undetected regression risk.

**Constraints:**
- Tests must run without Ollama (no guaranteed embedding server in CI)
- Tests must run without downloading the 23 MB ONNX reranker model on every run
- Tests must be fast enough for pre-commit hooks (ideally <5 seconds)
- No new runtime dependencies; dev dependencies only

## Goals / Non-Goals

**Goals:**
- Cover all pure functions with unit tests (`_sigmoid`, `_select_onnx_variant`,
  `ingest_path` validation, `list_documents` edge cases)
- Verify the `CrossEncoderReranker` singleton pattern, graceful fallback, and
  score normalisation
- Verify ingest → search → list round-trip through real ChromaDB (in-memory)
  and real FastMCP tool routing (in-memory Client)
- One end-to-end stdio smoke test to catch transport-level regressions
- Provide `uv run pytest` single-command test execution with coverage support

**Non-Goals:**
- RAG evaluation metrics (DeepEval, Tonic Validate, RAGAS) — this is retrieval
  testing, not generation quality testing
- Testing anything that requires a running Ollama server (embedding calls are
  skipped or mocked)
- Real ONNX model inference in unit tests (already covered by fallback path)
- CI/CD pipeline configuration (`.github/workflows/`) — that is a separate
  change
- 100% line coverage (the goal is meaningful coverage of all distinct code
  paths, not metric-chasing)

## Decisions

### 1. ChromaDB: EphemeralClient via monkeypatch (not PersistentClient with tempdir)

**Chosen:** Replace `chromadb.PersistentClient` with `chromadb.EphemeralClient`
in `conftest.py` using pytest's `monkeypatch` fixture.

**Rationale:**
- EphemeralClient stores everything in memory — zero disk I/O, test-isolated,
  and supported by the chromadb API without mocking
- Eliminates tempdir cleanup, directory collisions, and leftover state
- Tests that want to specifically test persistence can override the fixture
  with a tempdir approach

**Alternative considered:** Tempfile + PersistentClient. Rejected because it
leaves files on disk, requires cleanup, and isn't meaningfully different from
EphemeralClient for our use case.

### 2. FastMCP tests: in-memory Client (not subprocess spawning)

**Chosen:** Use FastMCP's built-in `Client(server_instance)` which creates an
in-memory transport.

**Rationale:**
- Tests actual tool routing, JSON serialisation/deserialisation, parameter
  validation — everything except the stdio pipe
- Starts instantly (no subprocess overhead)
- Synchronous call semantics for test assertions
- Single stdio smoke test catches transport-level issues

**Alternative considered:** Every test spawning a subprocess. Rejected because
it's 100x slower, fragile across platforms, and adds no value beyond what
in-memory transport already covers.

### 3. ONNX reranker: test fallback path first, mock internals for signal path

**Chosen:** All tests default to exercising the graceful fallback path (where
`_loaded` is `False`), which is always available. One test optionally mocks
`InferenceSession.run()` and `AutoTokenizer` to verify sigmoid normalisation
of raw logits.

**Rationale:**
- The fallback path is the most critical code path (it must never crash)
- Mocking onnxruntime internals is fragile (API changes, provider differences)
- The real model loading is acceptable in CI (singleton, loads once per test
  suite, ~23 MB download on first run)
- The project's AGENTS.md explicitly states "no PyTorch at runtime" — mocking
  lets us verify this constraint without actually downloading the model

**Alternative considered:** Always download the real model. Rejected because it
adds a HuggingFace network dependency to every test run and CI environment.

### 4. Test data: synthetic fixtures (not real project documents)

**Chosen:** Create small `.txt` and `.md` files in `tests/fixtures/` with
known, deterministic content. Optionally supplement with one real project
directory for a realistic integration sanity check.

**Rationale:**
- Deterministic — test assertions work against known text (e.g., "The capital
  of France is Paris")
- No binary bloat — `.txt`/`.md` files are a few KB each
- Reproducible — content is version-controlled in the repo
- The optional real-project test can be marked `slow` and skipped in CI

**Alternative considered:** Use real PDFs/DOCXs. Rejected — binary bloat, slow
to parse, non-deterministic metadata, and add no test value over plain text.

### 5. Test runner: pytest + pytest-asyncio (no unittest)

**Chosen:** pytest with `asyncio_mode = "auto"` in `pyproject.toml`.

**Rationale:**
- FastMCP's `Client` is async; pytest-asyncio is the standard async test
  framework
- `asyncio_mode = "auto"` means no decorators needed — any `async def` test
  function works
- pytest is already present as a transitive dependency (FastMCP pulls it in)

**Alternative considered:** Standard `unittest`. Rejected because it has no
built-in async support and no `monkeypatch` equivalent.

## Risks / Trade-offs

| Risk                                                                              | Mitigation                                                                                        |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| **EphemeralClient API divergence** — ChromaDB may change EphemeralClient behaviour | Use only the public `collection.get()`, `collection.count()`, `collection.get_or_create()` API that |
|                                                                                   | both clients share. Add a PersistentClient smoke test if needed.                                  |
| **Mocking ONNX inference may mask real bugs**                                        | Keep mocks minimal (one test). The fast-path test can be run manually.                           |
| **Synthetic fixtures don't catch real-world edge cases**                               | Add one optional marked-slow test with a real project directory (like `openspec/` docs).             |
| **Ollama dependency blocks full integration test**                                  | Tests that require Ollama are skipped if `OLLAMA_BASE_URL` is unreachable. Document how to run    |
|                                                                                   | them with a real Ollama instance.                                                                 |
| **pytest-asyncio auto mode breaks sync tests**                                      | Not possible — auto mode only activates for `async def` tests; `def` tests run synchronously.        |

## Open Questions

1. **CI environment** — Do we set up `uv run pytest` in a GitHub Actions
   workflow now, or defer CI config to a separate change?
   *Default assumption: defer CI to a separate change (`add-ci-pipeline`).*

2. **Coverage target** — Should we enforce a minimum coverage percentage
   (`--cov-fail-under=N`), or treat coverage as informational only?
   *Default assumption: informational only for this change; enforce a target
   once we have baseline data.*

3. **Real project test data** — Which local project directory should serve as
   the optional integration smoke test? Candidates: `openspec/` (this project's
   own specs), `scopus-mcp/`, or `src/rag_mcp/` (self-referential code search).
   *Default assumption: `openspec/` since it's already part of this repo.*
