## Why

The RAG MCP server has zero automated tests. Two OpenSpec changes
(`add-advanced-rag-features`, `fix-reranker-production-quality`) shipped
production code — including a cross-encoder reranker with sigmoid normalisation,
singleton recovery, and platform-aware ONNX variant selection — all verified
only by manual inspection. This is unsustainable: every refactor, dependency
upgrade, or new feature carries regression risk we cannot automatically detect.

## What Changes

- Install **pytest** and **pytest-asyncio** as dev dependencies; add
  `[tool.pytest.ini_options]` and `[tool.coverage.run]` sections to
  `pyproject.toml`
- Create **`tests/conftest.py`** with shared fixtures:
  - Monkeypatch to replace `PersistentClient` with `EphemeralClient` (in-memory
    ChromaDB for fast, isolated tests)
  - FastMCP server instance fixture for in-memory tool testing
- Create **`tests/fixtures/`** with small synthetic `.txt` and `.md` files for
  deterministic ingestion and search tests
- Write **unit tests** (`test_reranker.py`, `test_ingestion.py`) covering:
  `_sigmoid()` edge cases, `_select_onnx_variant()` platform logic,
  `CrossEncoderReranker` singleton + graceful fallback, path validation,
  unsupported extensions, empty directory handling
- Write **integration tests** (`test_mcp_tools.py`, `test_retrieval.py`)
  covering: ingest → search → list round-trip, `similarity_threshold` filtering,
  `rerank` flag propagation, tool parameter validation
- Write **one end-to-end smoke test** (`test_e2e_stdio.py`) launching the
  server as a subprocess over stdio (marked `slow`, skipped by default)
- Optionally use a real small local project (`openspec/` or `src/rag_mcp/`) for
  a realistic integration sanity check

## Capabilities

### New Capabilities

- `test-infrastructure`: pytest configuration, conftest fixtures (ChromaDB
  ephemeral patch, FastMCP client fixture), coverage reporting, test fixture
  documents
- `unit-testing`: Tests for all pure functions with no external dependencies:
  `_sigmoid()`, `_select_onnx_variant()`, `CrossEncoderReranker` fallback and
  singleton, `ingest_path()` validation logic
- `integration-testing`: Tests that wire components together through real
  ChromaDB (EphemeralClient) and real FastMCP tool routing (in-memory Client),
  verifying ingest → search → list round-trips, threshold filtering, and
  rerank flag behaviour

### Modified Capabilities

<!-- No existing spec requirements change — tests verify existing behaviour. -->

## Impact

- **New dependency**: `pytest`, `pytest-asyncio`, `pytest-cov` (dev only)
- **New directory**: `tests/` with `conftest.py`, test modules, and `fixtures/`
- **`pyproject.toml`**: Add `[tool.pytest.ini_options]` and `[tool.coverage.run]`
  sections
- **Backward compatibility**: None — tests are additive
- **Running tests**: `uv run pytest tests/ -v`
- **Running with coverage**: `uv run pytest tests/ --cov=rag_mcp --cov-report=term-missing`
