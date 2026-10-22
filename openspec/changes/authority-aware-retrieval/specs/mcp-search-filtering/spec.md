# Spec Delta

## ADDED Requirements

### Requirement: MCP search accepts as_of and returns per-row authority annotations
`search_documents` SHALL accept an optional `as_of: str | None` ISO-8601 date and pass it to the Engine search. When the authority stage runs for the collection, each returned row SHALL include `authority_status`, `authority_reason` and `authority_conflicts`. The handler SHALL keep returning `list[dict]` and SHALL NOT add a top-level envelope. When the stage does not run, none of these keys SHALL appear and `as_of` SHALL have no effect.

#### Scenario: as_of validation error uses the error envelope
- **WHEN** a client calls `search_documents(query="notice period", as_of="last year")`
- **THEN** the tool returns `[{"status": "error", "error_type": "validation", "message": ...}]` and does not raise

#### Scenario: Conflicts are carried on the rows
- **WHEN** the authority stage runs and two returned rows are in unresolved conflict
- **THEN** the response is a list of row dicts, both rows are `unresolved_conflict`, and each row's `authority_conflicts` names the other row

#### Scenario: Authority disabled hides authority keys
- **WHEN** the collection is bound to the `codebase` profile and the client passes `as_of="2024-01-01"`
- **THEN** no row contains `authority_status`, `authority_reason` or `authority_conflicts`, and the rows equal those returned without `as_of`
