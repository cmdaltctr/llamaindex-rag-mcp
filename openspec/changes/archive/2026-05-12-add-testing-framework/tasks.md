## 1. Infrastructure Setup

- [x] 1.1 Add dev dependencies: `uv add --dev pytest pytest-asyncio pytest-cov`
- [x] 1.2 Add `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` and
      `testpaths = ["tests"]` to `pyproject.toml`
- [x] 1.3 Add `[tool.coverage.run]` with `source = ["rag_mcp"]` to
      `pyproject.toml`
- [x] 1.4 Create `tests/conftest.py` with:
  - `monkeypatch` fixture to replace `chromadb.PersistentClient` with
    `chromadb.EphemeralClient` on module import
  - FastMCP server instance fixture (imports `rag_mcp.server.mcp`)
  - Optional `@pytest.fixture` for configuring a temp ChromaDB dir
- [x] 1.5 Create `tests/fixtures/sample.txt` with known content (e.g.,
      "The capital of France is Paris. The capital of Germany is Berlin.
      The capital of Italy is Rome.")
- [x] 1.6 Create `tests/fixtures/sample.md` with same content in markdown
      format (headings + paragraphs)
- [x] 1.7 Create `tests/fixtures/empty.txt` (zero-byte file for edge case)
- [x] 1.8 Create `tests/fixtures/dir_with_docs/` with two small `.txt` files
      for recursive directory ingestion test
- [x] 1.9 Verify `uv run pytest` discovers no tests (empty pass, no errors)

## 2. Unit Tests

- [x] 2.1 Create `tests/test_reranker.py` with tests for:
  - `_sigmoid(0.0)` → 0.5, `_sigmoid(10.0)` → near 1.0, `_sigmoid(-10.0)` → near 0.0
  - `_sigmoid` monotonicity — `a > b` implies `_sigmoid(a) > _sigmoid(b)`
  - `_select_onnx_variant()` returns ARM64 variant when `platform.machine()`
    is `arm64` or `aarch64` (mock `platform.machine`)
  - `_select_onnx_variant()` returns generic `model.onnx` for `x86_64`
  - `CrossEncoderReranker()` singleton — two calls return same object
  - `rerank()` with empty results → returns empty list
  - `rerank()` graceful fallback when `_loaded` is `False` → returns
    originals with `_reranked=False`, truncated to `top_k`
  - `rerank()` with mocked ONNX session → scores normalised to 0–1 range,
    results sorted descending, `_reranked=True`
- [x] 2.2 Create `tests/test_ingestion.py` with tests for:
  - `ingest_path("/nonexistent")` → `{"status": "error", ...}`
  - `ingest_path` with unsupported `.xyz` extension → error with "unsupported"
  - `ingest_path` on empty directory → `{"status": "ok", "files_indexed": 0}`
  - `list_documents()` returns `[]` when no collection exists
  - (tests that require Ollama are skipped via `pytest.skip` when
    `OLLAMA_BASE_URL` is unreachable)

## 3. Integration Tests

- [x] 3.1 Create `tests/test_mcp_tools.py` with tests for:
  - `list_tools()` discovers `ingest_documents`, `search_documents`,
    `list_indexed_documents`
  - `ingest_documents` with `tests/fixtures/` directory → returns
    `status: ok` and `files_indexed > 0`
  - `search_documents` after ingest returns results with correct shape
    (`score`, `source`, `text`, `reranked` keys)
  - `list_indexed_documents` after ingest returns non-empty list
  - `search_documents` with missing `query` parameter returns error
- [x] 3.2 Create `tests/test_retrieval.py` with tests for:
  - `search_documents` on empty store returns `[]`
  - `search_documents` with `similarity_threshold=0.99` filters all results
  - `search_documents` without rerank sets `reranked: false` on all results
  - `search_documents` with `rerank=True` propagates `reranked` flag
    correctly (tests the code path; actual reranker may fall back if
    model not loaded)

## 4. End-to-End Smoke Test

- [x] 4.1 Create `tests/test_e2e_stdio.py` with:
  - One test decorated `@pytest.mark.slow` that spawns `uv run rag-mcp`
    as a subprocess, performs MCP `initialize` and `tools/list` handshake
    over stdio, and asserts the three tool names are present
  - Verify the test is skipped when `-m slow` is not passed

## 5. Verification

- [x] 5.1 Run `uv run pytest tests/ -v` — all tests pass (30/30)
- [x] 5.2 Run `uv run pytest tests/ --cov=rag_mcp --cov-report=term-missing`
      — coverage report shows 92% overall
- [x] 5.3 Verify no `chroma_db/` directory is created on disk after test run
- [x] 5.4 Run `uv run pytest tests/ -m "not slow"` — slow test skipped
      (30 pass, 1 deselected, 2.68s)
- [x] 5.5 Run `uv run pytest tests/ -m slow` — stdio smoke test runs and passes
- [x] 5.6 Update `AGENTS.md` testing section to reflect `uv run pytest` command
- [x] 5.7 Update `AGENTS.md` dependency notes to list dev dependencies
