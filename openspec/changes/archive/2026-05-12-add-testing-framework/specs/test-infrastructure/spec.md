## ADDED Requirements

### Requirement: pytest configuration in pyproject.toml

The project SHALL include `[tool.pytest.ini_options]` and `[tool.coverage.run]`
sections in `pyproject.toml` so that `uv run pytest` discovers and runs all
tests without needing a separate `pytest.ini` or `setup.cfg` file.

#### Scenario: pytest discovers all test modules

- **WHEN** the developer runs `uv run pytest` in the project root
- **THEN** all `test_*.py` modules under `tests/` SHALL be discovered and executed

#### Scenario: asyncio mode is auto for FastMCP Client

- **GIVEN** a test uses `async def` with the in-memory FastMCP `Client`
- **WHEN** the test is executed
- **THEN** pytest SHALL auto-detect the async test and run it with the asyncio
  event loop without requiring `@pytest.mark.asyncio` decorators

#### Scenario: coverage reports source line coverage

- **WHEN** the developer runs `uv run pytest tests/ --cov=rag_mcp --cov-report=term-missing`
- **THEN** a terminal report SHALL show line coverage percentages for all
  modules in `src/rag_mcp/`

### Requirement: ChromaDB EphemeralClient patch in conftest

The test suite SHALL replace `chromadb.PersistentClient` with
`chromadb.EphemeralClient` globally so that all tests use an in-memory vector
store that leaves no disk artifacts and provides test isolation.

#### Scenario: tests do not write to chroma_db directory

- **GIVEN** `conftest.py` applies the monkeypatch to replace `PersistentClient`
  with `EphemeralClient`
- **WHEN** any test calls `ingest_path()` or `search()`
- **THEN** no directory named `chroma_db` SHALL be created on disk
- **AND** tests SHALL work without a running Ollama server (embedding calls
  may need separate mocking or be skipped)

#### Scenario: each test gets a fresh vector store

- **GIVEN** Test A indexes a document into ChromaDB
- **WHEN** Test B runs a search query
- **THEN** Test B SHALL NOT see documents indexed by Test A (fresh state per test)

### Requirement: FastMCP in-memory client fixture

The test suite SHALL provide a pytest fixture that returns the real
`rag_mcp.server.mcp` FastMCP instance so that integration tests can call tools
through the in-memory `Client` transport.

#### Scenario: tools are discoverable via in-memory client

- **GIVEN** the FastMCP instance fixture
- **WHEN** a test creates `Client(server_instance)` and calls `list_tools()`
- **THEN** the returned list SHALL include `ingest_documents`, `search_documents`,
  and `list_indexed_documents`

#### Scenario: tool calls return structured data

- **GIVEN** the FastMCP instance fixture and documents indexed
- **WHEN** a test calls `call_tool("search_documents", {"query": "capital"})`
- **THEN** the result SHALL contain a list of dicts with `score`, `source`,
  `text`, and `reranked` keys

### Requirement: test fixture documents

The test suite SHALL include small synthetic document fixtures in
`tests/fixtures/` that are version-controlled so integration tests have
deterministic, known-good content for ingestion and search verification.

#### Scenario: synthetic fixture files exist

- **GIVEN** the project is checked out
- **WHEN** the developer lists `tests/fixtures/`
- **THEN** at least `sample.txt` and `sample.md` SHALL be present with known text
  content (e.g., sentences about capitals of countries)

#### Scenario: fixture content is searchable

- **GIVEN** `sample.txt` contains the text "The capital of France is Paris"
- **WHEN** a test indexes it and searches for "capital of France"
- **THEN** the top result SHALL contain "Paris" in the text field
