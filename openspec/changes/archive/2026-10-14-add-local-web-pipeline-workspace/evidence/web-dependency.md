# Optional web dependency group (task 1.2)

Date: 2026-10-13. Approved by the user in this session (web extra, lock update, `uv sync`).

## Change

`pyproject.toml` gains the optional extra:

    web = ["fastapi>=0.143.0", "uvicorn>=0.52.0"]

`uv lock` added one package, `fastapi 0.143.0`. Its dependencies (starlette,
annotated-doc, opentelemetry-api, pydantic, typing-extensions,
typing-inspection) were already in the lock. uvicorn 0.52.1 was already locked
through `mcp`.

Lock side effect: the re-resolution simplified the platform markers on the
`nvidia-*` dependencies of `torch` (the `torch` extra). The old markers were
`(aarch64|x86_64 and linux) or (AMD64 and win32)`, the new markers are
`aarch64 or x86_64`. torch publishes no wheels for the dropped combinations,
so the installed set does not change. `uv lock --check` on the unchanged
integration lock passes, so the rewrite comes from this resolution only.

## Checks

| Check | Result |
|---|---|
| `uv sync --extra web --extra pdf-inspector` in the web worktree | PASS, own `.venv` created |
| `import fastapi, uvicorn` | PASS, fastapi 0.143.0, uvicorn 0.52.1 |
| `import omrg` does not load fastapi | PASS (`'fastapi' in sys.modules` is False) |
| torch absent from base + web venv | PASS |
| `uv pip compile --extra web` contains torch | PASS, 0 torch lines |
| `uv pip compile --extra web --resolution lowest-direct` | PASS: fastapi 0.143.0, uvicorn 0.52.0, starlette 1.8.0 |
| `tests/test_dependency_floors.py` | PASS, 1 passed |

Floor note: fastapi 0.143.0 was released on 2026-10-08. The floor equals the
locked version because the floors test rejects a floor more than one minor
below the lock.
