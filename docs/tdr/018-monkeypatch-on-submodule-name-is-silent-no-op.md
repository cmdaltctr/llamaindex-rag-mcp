# TDR-018: `monkeypatch.setattr` on a submodule name is a silent no-op

**Date:** 2026-08-31
**Status:** Accepted
**Deciders:** Aizat
**Tags:** testing | mcp | transport

## Context

When `transports/mcp.py` was split into `transports/mcp/` (change
`split-mcp-transport-by-tool`), the `search` function moved from
`transports/mcp/__init__.py` to `transports/mcp/search.py`. Two tests patched
it via `monkeypatch.setattr(server, "search", mock)` where `server` was the
`rag_mcp.transports.mcp` package.

After the split, `server.search` is the **submodule** `transports/mcp/search`,
not the `search` function. `monkeypatch.setattr` happily overwrote the
submodule attribute on the package object, but the handler in `search.py`
looks up `search` in its own module namespace — so the patch never reached the
production code path. The test ran against the real `search` function and
passed for the wrong reason (or failed with an unrelated error).

### Root Cause Analysis

The design inventory (D2) predicted 15 patch targets to move and 9 to stay.
It counted string patches (`patch("rag_mcp.transports.mcp.search.search")`)
but missed two `monkeypatch.setattr(server, "search", ...)` calls that
referenced the function by its package-level attribute, not by a dotted string.
These were silent no-ops because:

1. `server.search` resolved to the submodule (a valid attribute), so
   `setattr` succeeded without error.
2. The handler's `search(...)` call resolves `search` from its own module's
   globals, not the package's.
3. No test asserted the mock was _called_ — one asserted only that the result
   was non-empty (the real `search` returned results), the other asserted
   reranker fallback behaviour that held regardless.

## Decision

Patch targets must follow the function to its new module namespace, using a
dotted string or a module object that owns the function as a real attribute:

```python
# Correct — patches the function in its own module
monkeypatch.setattr("rag_mcp.transports.mcp.search.search", mock)
# or
import rag_mcp.transports.mcp.search as search_mod

monkeypatch.setattr(search_mod, "search", mock)
```

Never patch a function via the package root after a split, even if the name
still resolves there — it resolves to the submodule, not the function.

## Consequences

### Positive

- The two missed targets were caught by the supplementary check (task 4.3:
  remove patches and confirm tests fail) before the change was archived.
- A new test (`test_all_handlers_importable_from_package_root`) guards the
  re-export invariant going forward.

### Negative

- The D2 inventory under-counted by 2. The "15 move, 9 stay" prediction was
  really "17 move, 9 stay" — the two `monkeypatch.setattr` calls were missed
  because they used an object reference, not a dotted string.

### Neutral

- The clean-base tripwire's executed count was bumped from 1986 to 1988 to
  account for the new re-export test.

## How to Recognise / Handle This Again

1. **Symptom**: a test passes after a module split but the mock's
   `assert_called` fails, or the test exercises the real function instead of
   the double.
2. **Diagnostic**: grep for `monkeypatch.setattr(<module_alias>, "<name>"`
   where `<name>` is also a submodule of `<module_alias>`. The attribute
   resolves to the submodule, not a function inside it.
3. **Recovery**: repoint the patch to the submodule that owns the function:
   `monkeypatch.setattr("...module.submodule.function", mock)`.

## Revisit Triggers

- Another transport or core module is split into a package.
- A new `monkeypatch.setattr` target is added that references a package-level
  name.

## References

- Change: `openspec/changes/split-mcp-transport-by-tool/`
- Gotcha 8b: "Patch targets follow the function, not the re-export"
  (`AGENTS.md`)
- Affected tests: `tests/test_hybrid_retrieval.py:156`,
  `tests/test_retrieval.py:172`
