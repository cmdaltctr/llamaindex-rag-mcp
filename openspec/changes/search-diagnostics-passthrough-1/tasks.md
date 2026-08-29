## 1. MCP diagnostics passthrough

- [x] 1.1 Add `diagnostics: bool = False` to `search_documents` in
      `src/rag_mcp/transports/mcp.py` and document the parameter.
- [x] 1.2 Pass `diagnostics` to retrieval as
      `include_diagnostics=diagnostics` on every MCP search call.
- [x] 1.3 Preserve the existing exception envelope and
      `ToolAnnotations(read_only_hint=True, destructive_hint=False)` unchanged.
- [x] 1.4 Keep `src/rag_mcp/transports/mcp.py` at or below 500 lines. The
      file is exactly 500 lines today, so compress the `search_documents`
      docstring to free the lines tasks 1.1 and 1.2 add. Verify with
      `tests/test_file_size_ceiling.py`.

## 2. CLI diagnostics passthrough

- [x] 2.1 Add a default-off `--diagnostics` boolean option to
      `src/rag_mcp/transports/cli/search.py` with concise help text.
- [x] 2.2 Pass the CLI value to retrieval as
      `include_diagnostics=diagnostics` on every CLI search call.
- [x] 2.3 Keep JSON serialisation and the fixed-column Rich table unchanged.

## 3. Transport tests

- [x] 3.1 Add an MCP spy test that asserts `diagnostics: true` reaches
      retrieval as `include_diagnostics=True`.
- [x] 3.2 Assert omitted and explicit-false MCP diagnostics both pass
      `include_diagnostics=False`.
- [x] 3.3 Update existing exact MCP search-call expectations for the new
      default keyword argument.
- [x] 3.4 Add CLI JSON tests that assert representative diagnostic keys appear
      with `--diagnostics` and disappear without it.
- [x] 3.5 In each CLI state, assert the boolean passed to
      `include_diagnostics`; do not rely only on stubbed result fields.
- [x] 3.6 Extend CLI help coverage to assert that `--diagnostics` is listed.
- [x] 3.7 Confirm diagnostics requests preserve MCP error envelopes and tool
      annotations through existing or focused regression assertions.

## 4. Documentation and scope checks

- [x] 4.1 Add the `diagnostics` parameter row to
      `docs/guides/mcp-tools.md`, including its default-off behaviour.
- [x] 4.2 Add the `--diagnostics` flag row and a JSON example to
      `docs/guides/cli-reference.md`.
- [x] 4.3 Run the documentation drift check across `docs/guides/` for all MCP
      search parameters and CLI search flags. Correct stale entries.
- [x] 4.4 Confirm this change does not edit core retrieval,
      `transports/api/openapi.yaml`, or baseline OpenSpec specifications.

## 5. Final verification

- [x] 5.1 Review the diff for pure transport passthrough. Confirm neither
      transport computes, renames, nor removes diagnostic fields.
- [ ] 5.2 Run `uv run pytest tests/test_mcp_tools.py tests/test_cli.py
      tests/test_retrieval.py tests/test_rerank_policy.py
      tests/test_file_size_ceiling.py
      --cov=rag_mcp.transports.mcp --cov-report=term-missing
      --cov-fail-under=95`, then run
      `openspec validate "search-diagnostics-passthrough-1" --type change
      --strict`.
