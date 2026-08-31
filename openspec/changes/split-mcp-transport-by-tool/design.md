## Context

`transports/cli/` already solves this problem in this repository. Its
`__init__.py` defines the shared `app` object and shared display helpers, then
ends with:

```python
# Importing these modules registers their ``@app.command()`` decorators.
from . import (  # noqa: E402,F401
    benchmark,
    delete,
    ingest,
    install_login_watcher,
    list,
    profile,
    search,
    watch,
)
```

Each command module does `from . import app` (plus whichever helpers it needs)
and decorates. The import sits at the bottom with a `noqa` because it runs for
its side effect after `app` exists. The MCP transport needs exactly this shape,
substituting `mcp` for `app` and `@mcp.tool` for `@app.command()`.

The current `mcp.py` holds, in order: the module docstring listing all seven
tools, imports, `load_dotenv()`, two lazily-built module globals with their
accessors, three error helpers, the lifespan stub, the `MCPServer` construction,
seven decorated tool handlers, and `main()`.

Twenty-four test patch targets name symbols inside `rag_mcp.transports.mcp`.
AGENTS.md gotcha 8b states the governing rule: patch targets follow the
function, not the re-export. That rule was written after this exact class of
mistake bit the ADR-037 splits.

## Goals / Non-Goals

**Goals:**

- Restore working room in the MCP transport before a feature needs it.
- Keep the seven tools byte-identical in behaviour, name, signature, defaults,
  and annotations.
- Move every affected patch target so it still bites, and prove it still bites.
- Follow the CLI's established split rather than inventing a second pattern.

**Non-Goals:**

- Changing any tool's behaviour, parameters, or output.
- Splitting `lancedb.py` or `codebase_map.py`, both also at 499 lines.
- Introducing a shared base class, handler registry, or abstraction over the
  tools. Seven independent functions is the correct amount of structure.
- Reducing the total line count. The work redistributes lines; it does not
  delete them.

## Decisions

### D1 — Package layout mirrors `transports/cli/`

```
transports/mcp/
  __init__.py    server object, shared helpers, main(), bottom tool imports
  ingest.py      ingest_documents
  search.py      search_documents
  list.py        list_indexed_documents, list_collections
  delete.py      delete_documents
  codebase.py    get_codebase_map
  profile.py     change_collection_profile
```

The two listing tools share `list.py` because they are the same concern at two
granularities and neither is large. Everything else is one tool per module.

The layout also adds one level of package nesting, so the handlers' imports
are rewritten rather than moved verbatim. The current `from .. import compose`
(`mcp.py` line 31) would resolve to `rag_mcp.transports.compose`, which does
not exist, from inside `transports/mcp/*.py`; tool modules need `from ...
import compose`, or `from . import compose` to bind the name `__init__.py`
already imports. Each tool module imports the core symbols it calls directly —
`search.py` does `from ...core.retrieval import search`. That direct binding
is what makes the repointed patch targets in D2 and D3 name the namespace the
handler actually consults.

**Alternative rejected:** a flat `_tools.py` holding all seven. It would satisfy
the ceiling today by moving the problem one file sideways, and would not match
the CLI pattern a reader already knows.

### D2 — Shared helpers stay defined in `__init__.py`, but their patch targets still move

`_get_reranker`, `_get_profile_resolver`, `_error_detail`, `_error_message`,
`_log_tool_error`, and `_noop_lifespan` are used by several tools and are part
of the transport's shared surface, exactly like the CLI's `console`,
`_sanitise_display_name`, and `_print_ollama_error`. They stay defined in
`__init__.py`, and tool modules import them with `from . import ...` as the CLI
modules do.

**That does not keep their patch targets stable.** `from . import
_get_profile_resolver` binds the name in the tool module's namespace at import
time. Patching `rag_mcp.transports.mcp._get_profile_resolver` afterwards
rebinds the package attribute, which the tool module never consults again. The
patch becomes a no-op — gotcha 8b, in the direction that is easy to miss
because the symbol genuinely still lives where the old target names it.

So the rule for the migration is "patch where the name is looked up", not
"patch where the function is defined" — and crucially, **the same symbol has
different lookup sites in different tests.** `_get_profile_resolver` is looked
up in four places in the current file (ingest, search, profile, and `main()`),
so where each of its patch targets goes depends on which call site that test
drives.

Verified inventory, by the test that owns each target:

| Target | Owning test | After the split |
|---|---|---|
| `.search` (11) | search tool tests | `.search.search` — **moves** |
| `._list_documents` (2) | listing tool tests | `.list._list_documents` — **moves** |
| `.ingest_path_async` (1) | ingest tool test | `.ingest.ingest_path_async` — **moves** |
| `._get_profile_resolver` (1 of 2) | `test_ingest_documents_returns_lazy_setup_error` | `.ingest._get_profile_resolver` — **moves** |
| `._get_profile_resolver` (1 of 2) | `test_main_calls_mcp_run` | **stays** — `main()` is in `__init__.py` |
| `._get_reranker` (1) | `test_main_calls_mcp_run` | **stays** — same reason |
| `.mcp.run` (3) | main entry-point tests | **stays** |
| `.compose.ensure_runtime_setup` (2) | main entry-point tests | **stays** |
| `.search_documents.<attr>` (0) | none — the dotted `rag_mcp.transports.mcp.search_documents` path appears once, as a code comment at `tests/test_mcp_tools.py:1018`, not a patch target | not a target; the re-export (D3a) is still required by the three `from rag_mcp.transports.mcp import search_documents` imports at `tests/test_async_ingest_responsiveness.py:55, 134, 235` |
| `_profile_resolver` global via `patch.object` (`tests/test_core_coverage_v2.py:176`) | `test_ingest_reports_invalid_profile_tag` | **stays** — patches the module global that `_get_profile_resolver()` reads at call time; the global and accessor remain in `__init__.py` |
| `_profile_resolver` global via `patch.object` (`tests/test_core_coverage_v2.py:188`) | `test_search_reports_invalid_profile_tag` | **stays** — same reason |

Fifteen move, nine stay. The inventory must be gathered in all patch forms —
string patches, `patch.object`, and `monkeypatch.setattr` — because a
string-only grep misses the two `patch.object` globals; the existing
`monkeypatch.setattr` example is `tests/test_async_ingest_responsiveness.py:148`,
already counted among the eleven `search` targets. An earlier draft of this
table sent `_get_reranker` to `.search`, treated both `_get_profile_resolver`
targets alike, and counted a code comment as a stay; all three were wrong,
because the single `_get_reranker` patch belongs to the `main()` test where the
lookup stays in `__init__.py`. The table is confirmed by D4, not trusted.

### D3a — Handlers are re-exported, not merely imported

`from . import search` executes the module, so the `@mcp.tool` decorator runs
and the tool registers. It does **not** bind `search_documents` on the package.
`from rag_mcp.transports.mcp import search_documents` — which
`tests/test_async_ingest_responsiveness.py:55` does, and which the
`complete-observable-surface` conformance test also does — would then fail with
`ImportError`.

The bottom block therefore imports the handler names, not the modules:

```python
# Registers each @mcp.tool decorator and re-exports the handler.
from .codebase import get_codebase_map  # noqa: E402,F401
from .delete import delete_documents  # noqa: E402,F401
from .ingest import ingest_documents  # noqa: E402,F401
from .list import list_collections, list_indexed_documents  # noqa: E402,F401
from .profile import change_collection_profile  # noqa: E402,F401
from .search import search_documents  # noqa: E402,F401
```

One line per module does both jobs: importing the name executes the module (so
the decorator registers the tool) and binds the handler at the package root (so
every existing import keeps working). A dedicated test asserts all seven names
import from the package root.

**Alternative considered:** have tool modules call helpers through a module
reference (`from .. import mcp as _pkg`, then `_pkg._get_profile_resolver()`),
which would keep every helper patch target on the package. Rejected because it
diverges from the CLI pattern for the sole benefit of not editing test files,
and it makes the call sites noisier for every future reader in exchange for a
one-off migration cost.

### D3 — The patch-target migration is the deliverable, not a chore

`patch("rag_mcp.transports.mcp.search")` currently replaces the `search` name in
the module where `search_documents` looks it up. After the split,
`search_documents` lives in `transports/mcp/search.py` and looks up `search`
there. Patching the package name would replace a re-exported alias that the
handler never consults: the patch does nothing, the real `search` runs, and the
test either fails confusingly or passes while asserting nothing.

Eleven of the twenty-four targets are this one symbol.

The migration therefore has two steps per target, not one:

1. Repoint it at the module where the function now lives.
2. Prove it still bites — the patched double must be observably reached, not
   merely absent of error.

Step 2 is satisfied by the assertions the tests already make (`mock_search`
call assertions, returned sentinel values). Where a test only asserts "no
exception", the migration must add an assertion that the double was called, or
the target is unverifiable.

### D4 — Prove each patch bites by asserting the double was reached

An earlier draft proposed pointing each target at a non-existent attribute and
confirming the test errors. **That proves nothing.** `unittest.mock.patch`
resolves its target eagerly and raises `AttributeError` when the name does not
exist, regardless of whether production code would ever have consulted it. The
test errors either way, so the check cannot distinguish a patch that bites from
one that is a silent no-op.

The real question is whether the *patched double is reached*, and only the test
body can answer it:

1. **Prefer a call assertion.** `mock.assert_called_once()` — or
   `assert_called_once_with(...)` — fails when the double is never reached,
   which is exactly the no-op case. `test_main_calls_mcp_run` already works this
   way and needs no change.
2. **Otherwise use a sentinel return.** Make the double return a value the real
   implementation could not produce, and assert that value appears in the
   result. If the real function ran instead, the sentinel is absent.
3. **A test asserting only "no exception raised" cannot be verified**, and must
   gain one of the two above before its target is considered migrated.

The migration is complete for a target when its test would fail if the patch
were removed entirely — not merely when the suite is green.

**Cross-check:** temporarily removing a patch decorator and confirming the test
fails is a valid supplementary check, and is cheap for the eleven `search`
targets since they share a symbol. It is a supplement to the call assertion,
not a substitute for it.

This follows the repository's own rule that a test which passes regardless of
implementation is worse than no test.

### D5 — Tool registration is proven by the server, not by imports

`test_list_tools_discovers_all_seven` asks the running `MCPServer` what it
exposes. That is the only assertion that catches the characteristic failure of
this refactor — a tool module missing from the bottom import block, so its
decorator never runs and the tool silently disappears.

The spec delta adds a scenario pinning this so it survives as a requirement
rather than an incidental test.

**No new test is needed for it.** The existing one already asserts the count and
would fail on a missing tool. The task list verifies it runs rather than adding
a duplicate.

### D6 — Docstring is restored, not carried forward compressed

`search_documents`'s parameter documentation was compressed to fit the ceiling.
Once the handler lives in its own module the pressure is gone, so the fuller
description is restored from `dd64bf3`'s parent. This is the point of the
exercise, and skipping it would leave the ceiling still shaping the prose.

## Risks / Trade-offs

**Silent no-op patches are the whole risk.** Everything else here is mechanical.
D3 and D4 exist entirely to address it, and the task list front-loads the
verification rather than trailing it.

**Circular imports.** Tool modules import `mcp` from the package; the package
imports tool modules at the bottom. This works because the bottom import runs
after `mcp` exists, which is precisely why the CLI's equivalent import carries
`# noqa: E402`. A tool module that imports from the package at module scope
*above* its own decorator is fine; one that is imported *before* `mcp` is
constructed is not. The bottom placement is load-bearing, not stylistic.

**Import-time behaviour must not change.** `test_compose.py` spawns a subprocess
importing `rag_mcp.transports.mcp` and asserts the runtime does not initialise.
Converting a module to a package adds `__init__.py` execution, and the bottom
imports now execute seven more modules at import time. None of them may call
`compose` at module scope. They already do not, but the constraint becomes
easier to violate after the split, so the existing test is the guard.

**A larger diff than the behaviour change deserves.** Roughly 500 lines move and
15 of the 24 test patch targets change, for zero user-visible difference. Reviewing it as a
behaviour diff would be misleading; it should be reviewed as a move, with the
test-target migration read line by line and the rest read for "did anything
change other than location".

**Line count moves, it does not shrink.** `__init__.py` lands around 170 lines
and each tool module between 40 and 70. If a future tool needs 200 lines, this
buys room but does not remove the ceiling. That is the intent.
