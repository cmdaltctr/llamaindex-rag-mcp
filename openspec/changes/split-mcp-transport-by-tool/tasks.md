## 1. Baseline — capture what must not change

- [ ] 1.1 Record the current tool inventory: run the MCP server fixture and save
      the seven tool names with their full parameter lists, defaults, and
      annotations to a scratch file for later comparison.
- [ ] 1.2 Record the current fast-suite result line
      (`uv run pytest -m "not slow" -q`) so the post-split count can be compared
      exactly, including skips.
- [ ] 1.3 Record `wc -l src/rag_mcp/transports/mcp.py` (expected 495) and the
      current `git rev-parse HEAD`, so the move can be diffed against a known
      point.
- [ ] 1.4 Confirm `complete-observable-surface` has landed and been archived.
      This change is sequenced after it.

## 2. Create the package skeleton

- [ ] 2.1 Create `src/rag_mcp/transports/mcp/` and move `mcp.py` to
      `mcp/__init__.py` with `git mv`, so history follows the file.
- [ ] 2.2 Run the fast suite. It must pass unchanged — at this point the package
      is behaviourally identical to the module and every patch target still
      resolves.
- [ ] 2.3 Confirm `tests/conftest.py`'s `from rag_mcp.transports.mcp import mcp`
      still works and the `mcp_server` fixture still builds.
- [ ] 2.4 Confirm `tests/test_compose.py::test_import_does_not_initialise_runtime`
      still passes for `rag_mcp.transports.mcp` as a package.

## 3. Move the tools, one module at a time

Move one tool, run the fast suite, fix its patch targets, and only then move the
next. Do not batch these — a single failing suite after one move is diagnosable;
after seven it is not.

- [ ] 3.1 Create `codebase.py` and move `get_codebase_map` into it. Add it to a
      new bottom import block in `__init__.py`. Run the fast suite.
- [ ] 3.2 Create `profile.py` and move `change_collection_profile`. Run the fast
      suite.
- [ ] 3.3 Create `delete.py` and move `delete_documents`. Run the fast suite.
- [ ] 3.4 Create `list.py` and move both `list_indexed_documents` and
      `list_collections`. Repoint the two `_list_documents` patch targets at
      `rag_mcp.transports.mcp.list._list_documents`. Run the fast suite.
- [ ] 3.5 Create `ingest.py` and move `ingest_documents`. Repoint the
      `ingest_path_async` target and any `_get_profile_resolver` target used by
      the ingest tests. Run the fast suite.
- [ ] 3.6 Create `search.py` and move `search_documents`, restoring the fuller
      parameter docstring from commit `dd64bf3`'s parent (design D6). Repoint
      all eleven `search` targets to `rag_mcp.transports.mcp.search.search`.
      Do NOT move the `_get_reranker` target: its only use is
      `test_main_calls_mcp_run`, and `main()` stays in `__init__.py`. Run the
      fast suite.
- [ ] 3.7 Confirm `__init__.py` now contains only the server object, shared
      helpers, `main()`, and the bottom import block, and that the bottom import
      carries `# noqa: E402,F401` with a comment explaining it both registers the
      `@mcp.tool` decorators and re-exports the handlers.
- [ ] 3.8 Confirm the bottom block imports handler NAMES, not modules
      (`from .search import search_documents`, not `from . import search`), per
      design D3a. Module-only imports register the tools but leave
      `from rag_mcp.transports.mcp import search_documents` broken.
- [ ] 3.9 Add a test asserting all seven handler names import from the package
      root and are the same objects the server registered. Confirm it fails if
      the bottom block is reverted to module-only imports.
- [ ] 3.10 Confirm `tests/test_async_ingest_responsiveness.py`'s three
      `from rag_mcp.transports.mcp import search_documents` imports still work
      untouched — they are the existing proof that re-export is required.

## 4. Prove every patch target still bites

This is the step that catches the silent no-op. A patch target that was
repointed wrongly leaves its test passing while asserting nothing.

- [ ] 4.1 For each repointed target, confirm its test asserts the double was
      reached — `assert_called*`, or a sentinel return value that appears in the
      result. Do NOT use the missing-attribute trick: `patch` raises
      `AttributeError` on an unknown name whether or not production code would
      have consulted it, so it cannot distinguish a biting patch from a no-op
      (design D4).
- [ ] 4.2 For any test whose only assertion is "no exception raised", add a call
      assertion or a sentinel before considering its target migrated. Such a
      test cannot otherwise prove its patch bites.
- [ ] 4.3 As a supplementary check on the eleven `search` targets, remove the
      patch entirely and confirm each affected test fails. Restore afterwards.
- [ ] 4.4 Confirm the nine targets expected to stay on the package still bite:
      the `main()` test's `_get_reranker`, `_get_profile_resolver`, `mcp.run`
      and `compose.ensure_runtime_setup`, plus the two `patch.object` targets
      on the `_profile_resolver` module global in
      `tests/test_core_coverage_v2.py`. `test_main_calls_mcp_run` already
      asserts all four were called, so verify rather than rewrite it.
- [ ] 4.5 Re-derive the move/stay inventory from the finished code, counting
      every patch form — string patches, `patch.object`, and
      `monkeypatch.setattr`, not string targets only — and compare it against
      design D2's table (15 move, 9 stay). Record any difference — the table
      is a prediction, not the authority.

## 5. Verify nothing else changed

- [ ] 5.1 Run `tests/test_mcp_tools.py::test_list_tools_discovers_all_seven` and
      confirm it passes. This is the guard against a tool module missing from
      the bottom import block.
- [ ] 5.2 Diff the live tool inventory against the 1.1 baseline: same seven
      names, same parameters, same defaults, same `readOnlyHint` and
      `destructiveHint` annotations.
- [ ] 5.3 Run `uv run pytest -m "not slow" -q` and compare the result line
      against the 1.2 baseline. Counts must match exactly, skips included.
- [ ] 5.4 Run `tests/test_clean_base_tripwire.py` and confirm the skip manifest
      is unchanged.
- [ ] 5.5 Run `tests/test_file_size_ceiling.py` and confirm every new module is
      under the ceiling with real headroom, not just under it.
- [ ] 5.6 Run `uv run lint-imports` to confirm no new boundary violation, and
      confirm no stale `ignore_imports` entry was introduced (gotcha 8c).
- [ ] 5.7 Run `uv run ruff check .` and `uv run ruff format --check .`.
- [ ] 5.8 Start the server for real (`uv run rag-mcp`) and confirm it comes up
      and lists seven tools over stdio.
- [ ] 5.9 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm the
      transports coverage floor still holds.

## 6. Update the record

- [ ] 6.1 Apply the four `transport-separation` requirement deltas at archive
      time: thin transports, the uniform error contract (corrected to describe
      the real per-handler return types), FastMCP lifespan, and agent-facing
      documentation (whose ADR-033 pointer names `transports/mcp.py`).
- [ ] 6.2 Update `CLAUDE.md` invariant 3 to describe `transports/mcp/` as split
      by tool, matching how it already describes `transports/cli/`.
- [ ] 6.3 Grep `docs/` and `openspec/specs/` for remaining `transports/mcp.py`
      references and update each, including the ADR-033 pointer in the
      agent-documentation requirement.
- [ ] 6.4 Update `docs/guides/architecture.md` if it names the MCP transport as
      a single file.
- [ ] 6.5 Run `graphify update .` — the agent-documentation requirement in
      `transport-separation` requires the knowledge graph to be refreshed in the
      same change as a structural move.
- [ ] 6.6 Run `openspec validate --all --strict`.
- [ ] 6.7 Do not write an ADR. This is a module move following an established
      in-repo pattern, not an architectural decision. Write a TDR only if the
      patch-target migration surfaces a genuine trap worth recording.
