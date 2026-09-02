# TDR-020: Permanent `sys.modules` eviction in laziness tests poisons later real imports

**Date:** 2026-09-01
**Status:** Accepted
**Deciders:** Aizat
**Tags:** testing | pdf | imports

## Context

`tests/unit/test_pdf_inspector_reader.py::test_adapter_module_imports_pdf_inspector_lazily`
asserts that importing `rag_mcp.integrations.pdf.pdf_inspector` does not import
the optional `pdf_inspector` package. To make that assertion meaningful, the
test removed `pdf_inspector` from `sys.modules` before importing the adapter.

The original implementation used a bare `sys.modules.pop("pdf_inspector", None)`
— a permanent eviction. The test passed in isolation for months because no
other test in the file imported the real package.

During change `fix-embedding-and-structure-fidelity-1` (PR #79), new
real-reader tests were added to the same suite. The whole-file run started
failing with a `NameError` raised from inside `pdf_inspector`'s own package
`__init__` — in library code the change never touched.

### Root Cause Analysis

`sys.modules.pop("pdf_inspector")` removes only the top-level entry. The
package's submodules (for example the cached `pdf_inspector.pdf_inspector`)
stay in `sys.modules`, now parentless. The next real `import pdf_inspector`
re-executes the package `__init__` against that stale submodule cache; the
half-initialised import raises `NameError` inside the package's own
initialisation. Any test that imports the real package afterwards inherits
the poison, and the failure points at the wrong file.

Symptom-to-cause distance is the trap: the failing test is healthy; an
earlier test in the same process broke it.

## Decision

Laziness tests must evict through `monkeypatch.delitem`, never a bare `pop`:

```python
# Correct — teardown restores the sys.modules entry automatically
monkeypatch.delitem(sys.modules, "pdf_inspector", raising=False)

importlib.import_module("rag_mcp.integrations.pdf.pdf_inspector")

assert "pdf_inspector" not in sys.modules
```

`raising=False` keeps the test valid when the package was never imported.
The restoring variant landed in commit `312be9e` with an in-test comment
explaining the failure mode.

## Consequences

### Positive

- Laziness tests are now order-independent: real-reader tests can run before,
  after, or interleaved with them in one pytest process.
- The failure mode is documented at the point a future author is most likely
  to copy from.

### Negative

- None identified. The restoring eviction is strictly more correct.

### Neutral

- The clean-base tripwire count moved when the new real-reader tests were
  added (see TDR-018's note on the same pin mechanism).

## How to Recognise / Handle This Again

1. **Symptom**: a `NameError` or `ImportError` raised from inside a third-party
   package's `__init__`, in a test that only imports it; passes alone, fails
   in a full-suite or full-file run.
2. **Diagnostic**: `grep -rn "sys.modules.pop" tests/` — every hit inside a
   laziness test is a suspect. Check whether the same suite also contains
   tests that import the real package.
3. **Recovery**: replace the `pop` with
   `monkeypatch.delitem(sys.modules, "<package>", raising=False)`. If the
   poison is already in a live interpreter, start a fresh process.

## Revisit Triggers

- A new laziness test is written for another optional dependency (the Azure
  and LiteParse adapters are candidates).
- pytest config changes test ordering (randomisation, `-p xdist`).

## References

- Change: `openspec/changes/archive/2026-09-01-fix-embedding-and-structure-fidelity-1/`
- Fix commit: `312be9e` (stage B, PR #79)
- Related: TDR-018 (another silent test-infrastructure landmine)
- Affected test: `tests/unit/test_pdf_inspector_reader.py`
