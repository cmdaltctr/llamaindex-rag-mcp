## Why

`transports/mcp.py` is 495 lines against the 500-line ceiling that
`tests/test_file_size_ceiling.py` enforces. The margin is already shaping the
code rather than the code shaping itself: the `search-diagnostics-passthrough-1`
change added one parameter and had to compress the `search_documents` docstring
from twelve lines to six to fit, recorded in commit `dd64bf3`. The next feature
that touches this file faces the same trade with less room, and documentation is
the cheapest thing to cut.

The CLI hit this exact problem and solved it: `transports/cli/` is a package
whose `__init__.py` holds the shared `app` object and whose eight command
modules — benchmark, delete, ingest, install_login_watcher, list, profile,
search, watch — register through a bottom import block. Two helper modules
(`_launchagent.py`, `_report.py`) alongside `__init__.py` complete the
package's eleven files. The MCP transport is the same shape of problem with
the same available answer, and copying a proven in-repo pattern is cheaper
than inventing one.

This is deliberately not urgent. Nothing is broken, five lines is enough for
today, and the right moment to restructure a file is while there is no feature
waiting on it.

## What Changes

- Convert `transports/mcp.py` into the package `transports/mcp/`.
- `__init__.py` keeps the `MCPServer` instance, the shared helpers
  (`_get_reranker`, `_get_profile_resolver`, `_error_detail`, `_error_message`,
  `_log_tool_error`, `_noop_lifespan`), `main()`, and a bottom import block that
  imports each handler **by name**, which both registers its `@mcp.tool`
  decorator and re-exports it at the package root. Importing the modules alone
  would register the tools while breaking every
  `from rag_mcp.transports.mcp import <handler>` import in the suite.
- Move each tool handler to its own module: `ingest.py`, `search.py`,
  `list.py` (both listing tools), `delete.py`, `codebase.py`, `profile.py`.
- Repoint the test patch targets that need to move. Of the 24, 15 move and 9
  stay — the `main()` entry-point tests patch names that `main()` still
  looks up in `__init__.py`, so those must be left alone, and the two
  `patch.object` targets on the `_profile_resolver` module global
  (`tests/test_core_coverage_v2.py`) stay because the global and its accessor
  remain in `__init__.py`. The division is by
  *where the name is looked up*, not by where the function is defined, and the
  same symbol can fall on both sides (`_get_profile_resolver` does). This is the
  bulk of the work and the main risk, not an afterthought.
- Update the four affected `transport-separation` requirements: three name
  `transports/mcp.py` as a file, and the uniform error contract is factually
  wrong today — it says every handler returns an error *dictionary*, but
  `search_documents` returns a one-element list and `get_codebase_map` returns a
  JSON string. Correcting the baseline rather than preserving the inaccuracy
  follows AGENTS.md gotcha 12.

**No behaviour change.** Same seven tools, same names, same signatures, same
annotations, same error envelope, same startup. A caller cannot tell the
difference.

### Explicitly out of scope

- Any change to tool behaviour, parameters, or return shapes.
- The `complete-observable-surface` change's two threads. This change adds no
  fields and removes none.
- Splitting any other file. `lancedb.py` and `codebase_map.py` are both at 499
  lines and have the same pressure, but each is a separate judgement about a
  different module's seams.

### Sequencing

Run this **after** `complete-observable-surface` lands. That change adds a
conformance test which reaches into the code via
`rag_mcp.transports.mcp.search_documents`. The path keeps working through the
package's re-export, but doing the two in either order sequentially avoids
reasoning about both at once. The changes do not otherwise conflict:
`complete-observable-surface` was designed to add no lines to this file.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport-separation`: four requirements change. Three name
  `transports/mcp.py` as a single file and are updated to name the package. The
  thin-transports requirement additionally gains scenarios pinning that the tool
  set stays complete and that handlers stay importable from the package root —
  the two failures this refactor can actually cause. The uniform error contract
  is corrected to describe the error shapes the handlers really return.

## Impact

**Code**

- `src/rag_mcp/transports/mcp.py` deleted; `src/rag_mcp/transports/mcp/`
  created with six tool modules plus `__init__.py`.

**Tests**

- 24 patch targets across four test files are affected:
  `tests/test_mcp_tools.py`, `tests/test_core_coverage_v2.py`,
  `tests/test_cli.py`, `tests/test_async_ingest_responsiveness.py`. By current
  count: `rag_mcp.transports.mcp.search` (11 uses), `mcp.run` (3),
  `compose.ensure_runtime_setup` (2), `_list_documents` (2),
  `_get_profile_resolver` (2), `ingest_path_async` (1), `_get_reranker` (1),
  plus two `patch.object` targets on the `_profile_resolver` module global in
  `tests/test_core_coverage_v2.py`, which stay.
- `tests/conftest.py` imports the `mcp` server object from the module root; the
  package must re-export it so the fixture is unchanged.
- `tests/test_compose.py` runs a subprocess importing `rag_mcp.transports.mcp`
  to prove import does not start the runtime. Must still hold for a package.

**Risks**

The dominant risk is AGENTS.md gotcha 8b: a patch target that names the
re-exporting package instead of the module where the function now lives is a
silent no-op. The test keeps passing while testing nothing. Every moved patch
target must be verified to still bite, not merely to still pass.

The second risk is a tool module nobody imports, which silently vanishes from
the server. `tests/test_mcp_tools.py::test_list_tools_discovers_all_seven`
already guards this by asking the running server what it exposes.

**Not affected**

`core/`, `daemon/`, `integrations/`, `transports/cli/`, `transports/api/`, and
the `rag-mcp` entry point.
