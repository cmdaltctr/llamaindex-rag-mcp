# TDR-009: Dead TYPE_CHECKING imports in provider modules

**Date:** 2026-08-13
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** pyright | providers | imports | settings

## Context

Six provider modules imported `Settings` from a path that does not exist.
The imports were inside `TYPE_CHECKING` blocks. Python never ran them.
The application and its tests therefore continued to work.

The affected modules are the llama.cpp, Ollama, and OpenRouter builders in
`core/providers/embeddings/` and `core/providers/llm/`.

### Root Cause Analysis (if debugging-driven)

A depth-three relative import was copied into depth-four modules on
2026-08-04. In these modules, `from ...config import Settings` resolves to
`rag_mcp.core.config`. That module does not exist. Four dots resolve to
`rag_mcp.config`, which contains `Settings`.

`core/providers/common.py` is one package level shallower. Its three-dot
import is correct and remains unchanged.

## Decision

Change the six imports to `from ....config import Settings`.

Configure pyright to use the project uv environment:

```toml
[tool.pyright]
venvPath = "."
venv = ".venv"
```

Correct the `caplog` fixture annotation in `tests/test_compose.py` to
`pytest.LogCaptureFixture`.

Do not add pyright to CI or pre-commit in this change. The repository baseline
still has unrelated diagnostics.

## Consequences

### Positive

- Pyright resolves `Settings` in all six provider builders.
- Editors use the uv environment and avoid false missing-import reports.
- The provider check reports only unavailable optional provider extras.
- The `caplog` annotation exposes its supported logging methods to pyright.

### Negative

- Pyright remains a local verification tool until a separate baseline-reduction change adds a gate.

### Neutral

- Runtime behaviour does not change.
- `common.py` keeps its correct three-dot import.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Add pyright to CI now | The current repository baseline would fail the gate. |
| Change other pyright diagnostics | They are outside this defect scope. |
| Change `common.py` | Its relative import resolves correctly. |

## How to Recognise / Handle This Again

1. Run `pyright src/rag_mcp/core/providers`.
2. Check each relative import against the module package depth.
3. Run the config-import audit from this change.
4. Keep `TYPE_CHECKING` import paths valid. They affect static analysis.

## Revisit Triggers

- A future change adds pyright to CI or pre-commit.
- The project removes the legacy `Settings` model.
- Provider modules move to a different package depth.

## References

- `AGENTS.md` — settings injection invariant
- `docs/adr/031-config-composition-root-split.md`
- `src/rag_mcp/core/providers/common.py`
- `pyproject.toml` — pyright configuration
- `tests/test_compose.py` — logging fixture annotation
