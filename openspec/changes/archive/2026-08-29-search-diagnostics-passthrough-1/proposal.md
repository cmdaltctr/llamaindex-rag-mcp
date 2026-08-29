## Why

Core retrieval already computes optional per-result diagnostics, but neither
public transport lets callers request them. `search()` accepts
`include_diagnostics=False` (`src/rag_mcp/core/retrieval/pipeline.py:117-126`),
preserves rank diagnostics when requested (`pipeline.py:271,283`), attaches
policy and effective sparse-backend details (`pipeline.py:347-365`), and strips
internal fields by default (`pipeline.py:367-368`).

The MCP signature and call omit this flag
(`src/rag_mcp/transports/mcp.py:178-186,230-241`). The CLI does the same
(`src/rag_mcp/transports/cli/search.py:21-42,59-67`). A transport-only
passthrough will expose the existing evidence without changing retrieval.

## Context and sequencing

The `-1` suffix marks this as the first of three ordered changes. Implement and
land this change before the two later changes in that sequence.

## What Changes

- Add `diagnostics: bool = False` to the MCP `search_documents` tool. Pass it
  unchanged to `search(include_diagnostics=diagnostics)`.
- Add `--diagnostics` to `rag-mcp search`. Pass it through identically.
- Keep diagnostics disabled by default so MCP client context remains lean.
- Preserve the MCP never-raise error contract and its existing read-only tool
  annotations.
- Keep both transports as thin wrappers. No diagnostic logic moves into either
  transport.
- Reuse the current CLI output paths. JSON already serialises all returned
  fields (`src/rag_mcp/transports/cli/search.py:86-88`), while the Rich table
  reads fixed public keys (`cli/search.py:90-103`).
- Add transport tests for enabled and disabled passthrough states. The existing
  spy pattern demonstrates direct keyword assertion
  (`tests/test_experiment_14_harness.py:217-225`). Core tests already cover both
  flag states (`tests/test_retrieval.py:423-438,438-474` and
  `tests/test_rerank_policy.py:305-342`).
- Update the MCP tools guide and CLI reference.
- Record the future REST/OpenAPI parity question in `design.md`. Do not change
  the REST contract in this change.

## Capabilities

### New Capabilities

- `search-diagnostics-surface`: Defines opt-in MCP and CLI access to the
  existing retrieval diagnostics, including default-off behaviour and
  transport passthrough guarantees.

### Modified Capabilities

- None.

## Impact

**Code**

- `src/rag_mcp/transports/mcp.py`
- `src/rag_mcp/transports/cli/search.py`
- No changes under `src/rag_mcp/core/retrieval/`.

**Tests**

- MCP handler spy coverage in the existing MCP transport tests.
- CLI JSON coverage for `--diagnostics` enabled and omitted.
- Preserve the 95% coverage floor for `transports/mcp`.

**Documentation**

- `docs/guides/mcp-tools.md`
- `docs/guides/cli-reference.md`

**Dependencies and data**

- No new dependency, configuration, migration, or stored-data change.

**Out of scope**

- Changing diagnostic content or defaults.
- Adding diagnostic fields.
- Changing retrieval behaviour or reranker behaviour.
- Changing `transports/api/openapi.yaml` or adding a REST runtime.
