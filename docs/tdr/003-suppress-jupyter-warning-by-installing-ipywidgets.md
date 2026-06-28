# TDR-003: Suppress Jupyter warning by installing ipywidgets as dev dependency

**Date:** 2026-06-28
**Status:** Accepted
**Deciders:** Muhammad Aizat Bin Md Hawari
**Tags:** rich | ipywidgets | warnings | dev-dependencies

## Context

Running the RAG MCP server or experiment scripts produces a `UserWarning` from
the `rich` library:

```
.venv/lib/python3.12/site-packages/rich/live.py:260: UserWarning:
    install "ipywidgets" for Jupyter support
    warnings.warn('install "ipywidgets" for Jupyter support')
```

`rich` (a transitive dependency via `chromadb` / `llamaindex`) checks for
Jupyter/ipython at import time in `rich.live.Live`. When `ipywidgets` is not
installed, it emits this warning and falls back to plain terminal output.

### Root Cause Analysis

The warning is emitted by `rich` at import time when it detects an interactive
environment context. It is not an error — execution continues with a text
fallback. The project does not run inside Jupyter, but `rich`'s detection logic
triggers regardless when certain code paths are imported.

## Decision

Install `ipywidgets` as a **dev dependency** to silence the warning and enable
rich Jupyter rendering if experiment notebooks are ever used:

```bash
uv add --dev ipywidgets
```

## Consequences

### Positive

- No more `UserWarning` noise in server logs and experiment output
- Jupyter notebook support available for experiment prototyping if needed

### Negative

- Adds ~15 transitive dev-only packages (ipykernel, matplotlib-inline, etc.)
- Slightly larger dev environment footprint

### Neutral

- Runtime behaviour unchanged — `ipywidgets` is dev-only, not shipped to users

## Alternatives Considered

| Option                                                        | Rejected Because                                                                                        |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Suppress warning via `warnings.filterwarnings` in `config.py` | Hides the signal rather than addressing the root cause; adds code to a core module for a cosmetic issue |
| Ignore the warning entirely                                   | Persistent noise in logs makes it harder to spot real warnings                                          |

## How to Recognise / Handle This Again

1. **Symptom:** `UserWarning: install "ipywidgets" for Jupyter support` in logs
2. **Diagnostic:** Check if `ipywidgets` is in dev dependencies: `uv tree --dev | grep ipywidgets`
3. **Recovery:** `uv add --dev ipywidgets`

## Revisit Triggers

- `rich` removes the Jupyter detection check in a future major version
- `ipywidgets` becomes incompatible with the Python version in use
- Project explicitly decides never to use Jupyter notebooks (could then switch to `warnings.filterwarnings` instead)

## References

- `rich` source: `.venv/lib/python3.12/site-packages/rich/live.py:260`
- `pyproject.toml` (dev dependencies section)
