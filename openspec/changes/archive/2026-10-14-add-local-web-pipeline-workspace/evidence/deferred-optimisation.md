# Deferred optimisation check (task 9.4)

Date: 2026-10-13. Lead session, web worktree, base `489a618`.

## Search

Pattern (case-insensitive): `optimi[sz](e|er|ation)|autotun|device-aware|quick.{0,3}standard`.

| Scope | Result |
|---|---|
| Files changed since `489a618` under `src/`, `web/src/`, `plugins/` | 0 matches |
| Untracked new files under `src/`, `web/src/`, `plugins/` | 0 matches |
| Whole `src/omrg` | Only older matches: LanceDB `table.optimize()`, Leiden optimiser seed, profile YAML comments ("Optimised for ..."), the existing `omrg benchmark` command and ingestion metrics docstring. None was added by this change. |

## Dependencies

- `pyproject.toml` diff since `489a618` adds only the `web` extra (`fastapi`, `uvicorn`).
- `web/package.json` has no optimisation, benchmark or tuning package.

## Endpoints and controls

- No optimisation route in the runtime routers or `openapi.yaml`.
- No optimisation view or button in `web/src` (navigation: Canvas, Library, Search, Ask, Runs, Experiments, Settings).

## Later-change notes kept

- `design.md` D12 and `proposal.md` keep **Quick**, **Standard** and **Full**.
- ADR-075 Consequences (Neutral) now names the three modes and states that this change adds no optimiser code, endpoint, control or dependency.

Result: PASS. Re-run this search in task 9.2 after the frontend tasks finish.
