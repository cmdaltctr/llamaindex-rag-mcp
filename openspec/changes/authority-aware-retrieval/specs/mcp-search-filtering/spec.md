# Spec Delta

## ADDED Requirements

### Requirement: MCP search accepts as_of and returns authority annotations
`search_documents` SHALL accept an optional `as_of: str | None` ISO-8601 date and pass it to `core.retrieval.search`. When the collection's resolved settings have `authority.enabled` true, each returned row SHALL include `authority_status` and `authority_reason`, and the response SHALL include a `conflicts` list (possibly empty). When `authority.enabled` is false, none of these keys SHALL appear and `as_of` SHALL be accepted and ignored with a diagnostics-only note.

#### Scenario: as_of validation error uses the error envelope
- **WHEN** a client calls `search_documents(query="notice period", as_of="last year")`
- **THEN** the tool returns `[{"status": "error", "error_type": "validation", "message": ...}]` and does not raise

#### Scenario: Authority disabled hides authority keys
- **WHEN** the collection is bound to the `codebase` profile and the client passes `as_of="2024-01-01"`
- **THEN** rows contain no `authority_status` key and the response contains no `conflicts` key
