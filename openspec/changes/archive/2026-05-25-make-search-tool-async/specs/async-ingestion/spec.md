## MODIFIED Requirements

### Requirement: Event loop responsiveness during ingest
When ingestion runs inside the MCP server's event loop, the loop SHALL remain able to service other tool calls. A concurrent MCP `search` request issued while a long ingest is in flight SHALL receive a response without waiting for the ingest to complete. MCP search SHALL not execute blocking embedding or ChromaDB retrieval work directly on the event-loop thread.

#### Scenario: Search responds during in-flight ingest
- **WHEN** an `ingest_path_async("/large/folder")` task is in progress
- **AND** an MCP client issues a `search(query="x", top_k=5)` call
- **THEN** the search SHALL return its result within 500 ms
- **THEN** the ingest SHALL continue to run uninterrupted to completion

#### Scenario: Search offloads synchronous retrieval
- **WHEN** `search_documents(...)` is called via MCP
- **THEN** the MCP handler SHALL be asynchronous
- **THEN** synchronous retrieval work SHALL be offloaded from the event-loop thread

#### Scenario: Multiple MCP tool calls interleave during ingest
- **WHEN** an ingest is in progress
- **AND** the MCP client issues `list_collections` and `search` calls in sequence
- **THEN** both calls SHALL return without waiting for ingest to finish
- **THEN** the result of each tool call SHALL be correct (no torn reads of ChromaDB state)
