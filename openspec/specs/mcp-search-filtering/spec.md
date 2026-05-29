## Purpose

Define MCP search metadata filtering and error-envelope behaviour so clients
can restrict retrieval by stored metadata without receiving raw ChromaDB or
retrieval exceptions.

## Requirements

### Requirement: MCP search metadata filtering
The system SHALL allow MCP clients to pass an optional `metadata_filter` parameter to `search_documents`. When provided, the filter SHALL be passed to retrieval as a ChromaDB-compatible `where` clause and applied before returning results.

#### Scenario: Search filters by category
- **WHEN** `search_documents(query="retrieval", metadata_filter={"category": "ai"})` is called
- **THEN** retrieval SHALL apply the filter before result assembly
- **THEN** every successful returned chunk SHALL have metadata compatible with `category == "ai"`

#### Scenario: Search without filter remains unchanged
- **WHEN** `search_documents(query="retrieval")` is called without `metadata_filter`
- **THEN** retrieval SHALL use the existing unfiltered search path
- **THEN** successful result dictionaries SHALL keep their existing fields

### Requirement: MCP search error envelope
The system SHALL catch retrieval errors inside the MCP `search_documents` handler and return an explicit error response instead of raising raw exceptions from the handler. The handler's declared return type SHALL remain `list[dict]` on every path, including failures. On a caught exception, the handler SHALL return a one-element list whose sole entry is an error dict with the exact keys `status`, `error_type`, and `message`, where `error_type` is one of `"validation"`, `"retrieval"`, or `"internal"`.

#### Scenario: Invalid metadata filter
- **WHEN** `search_documents` receives a metadata filter rejected by ChromaDB
- **THEN** the MCP handler SHALL return a list containing exactly one dict
- **THEN** that dict SHALL contain `status: "error"`, `error_type: "validation"`, and a human-readable `message`
- **THEN** the MCP handler SHALL NOT raise the ChromaDB exception directly

#### Scenario: ChromaDB query failure
- **WHEN** the underlying ChromaDB query raises during retrieval
- **THEN** the handler SHALL return a one-element list containing `status: "error"`, `error_type: "retrieval"`, and a human-readable `message`
- **THEN** the handler SHALL NOT raise the underlying exception

#### Scenario: Successful response shape is unchanged
- **WHEN** `search_documents` succeeds
- **THEN** the returned list SHALL contain zero or more result dicts with the existing field set (`score`, `source`, `page_label`, `text`, `metadata`, `reranked`)
- **THEN** no result dict SHALL contain a `status` key
