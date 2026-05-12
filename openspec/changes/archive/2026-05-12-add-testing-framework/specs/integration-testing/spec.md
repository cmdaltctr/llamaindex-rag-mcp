## ADDED Requirements

### Requirement: ingest-search-list round-trip

The system SHALL be tested end-to-end through the in-memory FastMCP Client to
verify that documents can be ingested, searched, and listed correctly.

#### Scenario: ingest then search finds the document

- **GIVEN** synthetic test fixtures in `tests/fixtures/`
- **WHEN** `ingest_documents` is called with the fixtures directory
- **THEN** the response SHALL contain `"status": "ok"` and `files_indexed > 0`
- **AND** subsequent `search_documents` with a relevant query SHALL return results

#### Scenario: list shows indexed document count

- **GIVEN** at least one document has been indexed
- **WHEN** `list_indexed_documents` is called
- **THEN** the return SHALL be a non-empty list with `source` and `chunks` keys
  for each entry

#### Scenario: search on empty store returns empty list

- **GIVEN** no documents have been indexed
- **WHEN** `search_documents` is called with any query
- **THEN** an empty list `[]` SHALL be returned

### Requirement: similarity threshold filtering

The `search_documents` tool SHALL be tested to verify that the
`similarity_threshold` parameter correctly filters low-confidence results.

#### Scenario: high threshold filters all results

- **GIVEN** documents are indexed
- **WHEN** `search_documents` is called with `similarity_threshold=0.99`
- **THEN** an empty list MAY be returned (no result meets the threshold)

#### Scenario: default threshold includes all results

- **GIVEN** documents are indexed
- **WHEN** `search_documents` is called without a threshold parameter
- **THEN** all retrieved results SHALL be returned (no filtering)

### Requirement: rerank flag propagation

The `search_documents` tool SHALL be tested to verify the `reranked` flag
correctly reflects whether cross-encoder re-scoring was applied.

#### Scenario: default search sets reranked to false

- **GIVEN** documents are indexed
- **WHEN** `search_documents` is called without the `rerank` parameter
- **THEN** every returned result SHALL have `"reranked": false`

#### Scenario: rerank enabled sets reranked flag on success

- **GIVEN** documents are indexed
- **AND** the ONNX reranker model is available (or gracefully managed)
- **WHEN** `search_documents` is called with `rerank=True`
- **THEN** the `reranked` flag in each result SHALL reflect whether the reranker
  was successfully applied

### Requirement: tool parameter validation

The MCP server SHALL validate tool parameters through FastMCP's built-in schema
validation, and invalid inputs SHALL return error responses.

#### Scenario: missing required parameter returns error

- **WHEN** `search_documents` is called without the required `query` argument
- **THEN** the call SHALL return an error (via FastMCP schema validation)

### Requirement: end-to-end stdio smoke test

The project SHALL include one end-to-end test that launches the server as a
subprocess over stdio transport, performs the MCP handshake, and verifies tool
discovery.

#### Scenario: server starts over stdio and lists tools

- **WHEN** the server is launched as `uv run rag-mcp`
- **AND** an MCP client sends `initialize` and `tools/list` requests over stdio
- **THEN** the response SHALL list `ingest_documents`, `search_documents`, and
  `list_indexed_documents` as available tools

#### Scenario: stdio test is marked slow and skipped by default

- **GIVEN** the stdio test is decorated with `@pytest.mark.slow`
- **WHEN** `uv run pytest` is run without the `-m slow` flag
- **THEN** the stdio test SHALL be skipped, not failed
