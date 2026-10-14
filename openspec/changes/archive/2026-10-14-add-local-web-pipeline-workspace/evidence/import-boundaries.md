# Evidence: task 1.3, executable import boundaries

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, base commit `489a618`, uncommitted working tree.
Tools: v3 virtual environment, import-linter 2.13, grimp 3.15. No installs.

Command prefix for all runs:

```bash
cd <worktree> && PATH=/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3/.venv/bin:$PATH PYTHONPATH=src
```

## Changes

`pyproject.toml`, `[tool.importlinter]` only:

1. `core-business-avoids-providers-transports` now lists `omrg.core.pipelines` and `omrg.core.workspace` as sources. No ignore entry.
2. New contract `pipeline-runner-independent-of-domains`. Source `omrg.core.pipelines`. Forbids `omrg.core.ingestion`, `omrg.core.retrieval`, `omrg.core.answer`, `omrg.core.providers`, `omrg.transports`, `subprocess`, `sqlite3`, `fastapi`, `starlette`, `uvicorn`, `marimo`.
3. New contract `workspace-services-independent-of-domains-and-web`. Source `omrg.core.workspace`. Forbids `omrg.core.ingestion`, `omrg.core.retrieval`, `omrg.core.answer`, `omrg.transports`, `subprocess`, `sqlite3`, `fastapi`, `starlette`, `uvicorn`, `marimo`.
4. New contract `core-never-imports-transports`. Source `omrg.core` (all of it, including `core.providers` and domain graph adapters). Forbids `omrg.transports`.
5. New contract `core-free-of-web-notebook-and-sqlite-runtimes`. Source `omrg.core`. Forbids `fastapi`, `starlette`, `uvicorn`, `marimo`, `sqlite3`.

All new contracts set `unmatched_ignore_imports_alerting = "error"` and have no `ignore_imports`.

The standard-library SQLite adapter (`src/omrg/integrations/workspace_sqlite/`) is covered by the existing `integrations-are-leaves` contract. It forbids `omrg.core`, `omrg.transports`, and `omrg.daemon`.

`subprocess` and `sqlite3` are forbidden for the workspace package as well as the runner. The spec says workspace services receive persistence and process control from composition, so direct imports there are a violation.

New test: `tests/test_pipeline_import_boundaries.py`.

## Result 1: real tree passes

`lint-imports --no-cache` on the worktree:

```text
Analyzed 278 files, 1274 dependencies.
settings-models-are-pure-data KEPT
providers-constructed-only-in-compose KEPT
core-business-avoids-providers-transports KEPT
community-strategies-independent-of-consumers KEPT
pipeline-runner-independent-of-domains KEPT
workspace-services-independent-of-domains-and-web KEPT
core-never-imports-transports KEPT
core-free-of-web-notebook-and-sqlite-runtimes KEPT
chromadb-confined-to-vectordb KEPT
lancedb-confined-to-vectordb KEPT
config-is-leaf KEPT
integrations-are-leaves KEPT
Contracts: 12 kept, 0 broken.
```

Before this change the same command gave `Contracts: 8 kept, 0 broken.`

## Result 2: intentional violations fail (real-tree copy)

Method: copy `src/omrg` and `pyproject.toml` into the session scratchpad. Add three throwaway modules to the copy only. Run `lint-imports --no-cache` with the real contract set. No file owned by another agent was changed.

- `core/pipelines/zz_violation.py` imports every module the runner contract forbids.
- `core/workspace/zz_violation.py` imports `subprocess`, `sqlite3`, `fastapi`, `marimo`, ingestion, retrieval, answer, and `omrg.transports`.
- `core/providers/zz_violation.py` imports `omrg.transports.mcp` and `uvicorn`.

Output, exit code 1:

```text
Analyzed 285 files, 1295 dependencies.
core-business-avoids-providers-transports BROKEN
pipeline-runner-independent-of-domains BROKEN
workspace-services-independent-of-domains-and-web BROKEN
core-never-imports-transports BROKEN
core-free-of-web-notebook-and-sqlite-runtimes BROKEN
Contracts: 7 kept, 5 broken.
```

Each edge was named, for example:

```text
- omrg.core.pipelines.zz_violation -> subprocess (l.1)
- omrg.core.pipelines.zz_violation -> sqlite3 (l.2)
- omrg.core.pipelines.zz_violation -> fastapi (l.3)
- omrg.core.pipelines.zz_violation -> marimo (l.6)
- omrg.core.pipelines.zz_violation -> omrg.core.ingestion.pipeline (l.7)
- omrg.core.pipelines.zz_violation -> omrg.core.retrieval (l.8)
- omrg.core.pipelines.zz_violation -> omrg.core.answer.synthesis (l.9)
- omrg.core.pipelines.zz_violation -> omrg.core.providers.embeddings (l.10)
- omrg.core.pipelines.zz_violation -> omrg.transports (l.11)
- omrg.core.providers.zz_violation -> omrg.transports.mcp (l.1)
- omrg.core.providers.zz_violation -> uvicorn (l.2)
```

Control: the same copy with the three modules removed gave `Contracts: 12 kept, 0 broken.` (exit 0).

`core.providers -> omrg.transports` was not covered before this change. The new `core-never-imports-transports` contract catches it.

An earlier probe confirmed that indirect chains are reported. A runner import of `omrg.core.ingestion`, which imports `sqlite3` and `subprocess`, broke the `sqlite3` and `subprocess` rules through the two-step chain.

## Result 3: boundary tests pass and fail when weakened

```bash
python -m pytest -q -p no:cacheprovider tests/test_pipeline_import_boundaries.py tests/test_contract_coverage.py
# 42 passed
```

`tests/test_contract_coverage.py` includes `omrg.core.pipelines` and `omrg.core.workspace` as covered packages.

The new test builds a temporary `omrg` tree per contract, imports every forbidden module on purpose, and runs `lint-imports` against that contract copied from `pyproject.toml`. It expects a broken contract that names each `violator -> module` edge. The same tree without the imports must give `1 kept, 0 broken`. The test also pins the minimum forbidden set and checks for no ignore entries.

Mutation checks. Each ran a copy of the test against a changed copy of `pyproject.toml` in the scratchpad:

| Mutation | Result |
|---|---|
| None (control) | 13 passed |
| Remove `marimo` from the runner contract | 1 failed: `test_contract_is_declared_strictly[pipeline-runner-independent-of-domains]` |
| Add an `ignore_imports` entry to the workspace contract | 1 failed: `test_contract_is_declared_strictly[workspace-services-independent-of-domains-and-web]` |
| Remove `omrg.core.pipelines` from the business contract | 1 failed: `test_business_contract_covers_new_packages` |
| Test writes no violating import | 4 failed: every `test_each_forbidden_import_breaks_contract[...]` case |

`ruff check` and `ruff format --check` pass on the new test file.

## Not done here

- Domain graph adapters do not exist yet. When task 3.8 adds them, the core-wide contracts already apply. Sibling-domain independence for adapters needs a contract once their module names are known.
- `tests/test_no_global_settings_reads.py` was not changed. Task 3.8 owns the adapter leaf list.
- `./scripts/local_ci.sh` and the full suite were not run.
