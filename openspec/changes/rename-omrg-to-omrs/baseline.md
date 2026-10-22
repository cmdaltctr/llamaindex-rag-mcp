# Baseline before the rename

Measured on 2026-10-22 in the worktree `llamaindex-rag-mcp-feat-rename-omrg-to-omrs`
at commit `8f0d18e` (branch `feat/rename-omrg-to-omrs`, forked from `v4`).

## `./scripts/local_ci.sh`

Result: **passed** (exit 0), 7 min 43 s wall time.

| Step | Result |
| --- | --- |
| ruff check, ruff format --check | pass |
| `uv run lint-imports` | 21 contracts kept, 0 broken |
| `openspec validate --all --strict` | 84 passed, 0 failed |
| OpenAPI contract | valid |
| Default install torch-free | OK |
| Fast suite (parallel) | 7484 passed, 152 skipped, 197 s |
| Clean-base tripwire | 5 passed, 223 s |
| Web gates (`npm ci`, lint, typecheck, test, build) | 145 test files, 1750 tests passed |
| Wheel contains web assets | OK |
| pyright (advisory) | findings are advisory, same as CI |

## Tripwire pins (`tests/test_clean_base_tripwire.py`)

- `_BASE_EXECUTED = 7491`
- `_BASE_DESELECTED = 21`

The rename must leave both values unchanged, except for tests that this change
adds on purpose (the guard test, the startup-check tests, the migrate tests and
the LanceDB key test). Added tests raise `_BASE_EXECUTED` by their count and
nothing else.

## Release name check

- 2026-10-22: `omrs` returns 404 on PyPI (free). `omrg` also returns 404.
- Re-check `omrs` just before the first release and record the date here.

## Owner backup (task 1.6)

`/Users/aizat/Development/DATA/omrg/backups/pre-omrs-rename-2026-10-22/`
holds copies of `~/.omrg` and `~/.config/omrg` (171 files, SHA-256 manifest
inside). Local only. `workspace.db` passed `PRAGMA integrity_check` after the copy.
