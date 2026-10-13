# Fresh fast-suite coverage evidence

## Scope lock

- Worktree: `/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3-feat-improve-rag-input-quality-5`
- Git root: `/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3-feat-improve-rag-input-quality-5`
- Branch: `feat/improve-rag-input-quality-5`
- Revision: `afe151e93dd9b79e18618811dc15e35c6a96b16d`
- `uv.lock` SHA-256: `51ca3e37fc38db371a4d42335d4edbad6b82d926e4e2fe2a640316231afb5a33`
- Dependency action: none. The run used the existing environment with `--no-sync`.

## Test isolation review

`docs/guides/testing.md` states that the fast suite uses mock embeddings and an in-memory database. It needs no model server, network, or downloads.

`tests/conftest.py` supplies deterministic provider values, autouse environment isolation, tmp-path LanceDB storage, mock embeddings, disabled metadata extraction, and the `pypdf` reader. This supports tests independent of the real `.env`. This audit did not read `.env`.

## Command and result

```sh
uv run --no-sync pytest -m 'not slow' -q --cov=omrg --cov-branch
```

Fresh result: **FAILED** after 547.84 seconds.

- 1 failed
- 2,809 passed
- 131 skipped
- 19 deselected
- 2,026 warnings

Failure emitted by the suite:

```text
FAILED tests/test_clean_base_tripwire.py::test_base_skip_manifest_is_exact
AssertionError: base executed count drifted: 2805
assert 2805 == 2774
```

## Branch coverage

| Tier | Required | Fresh branch coverage | Result |
| --- | ---: | ---: | --- |
| Core + MCP | 95% | 90.65% (6,389/7,048) | FAIL |
| Orchestration | 85% | 93.20% (1,535/1,647) | PASS |
| Overall | 90% | 90.68% (11,355/12,522) | PASS |

The Core + MCP calculation covers 94 files. It includes 5,007/5,430 lines and 1,382/1,618 branches. The orchestration tier covers 17 files. Overall coverage includes 8,908/9,662 lines and 2,447/2,860 branches.

## Coverage artefacts

- `.coverage` is ignored by `.gitignore:59`.
- `htmlcov/` is ignored by `.gitignore:60`.
- Fresh JSON: `htmlcov/fast-fast-suite-coverage.json` SHA-256 `bdf13508772ad41ea294f68b5f11c6dd5f2e9e826cac88588c7b69bbda01e5ec`.
- Fresh XML: `htmlcov/fast-fast-suite-coverage.xml` SHA-256 `5cf731d4a35e9d764387d0328e797deaad814285f77043803bf0c173304054bc`.

## Read-only comparison and attribution limit

`git diff origin/v3...HEAD -- src/omrg/core/vectordb/` produced no paths or diff.

No earlier comparable coverage run exists in this evidence set. An empty vectordb diff cannot attribute aggregate suite counts, coverage, warnings, or the tripwire failure to a pre-existing condition. This record makes no such attribution.

No source, frozen/input/index, or `.env` file was edited. This evidence file is the only intended tracked change from this run.

## Fresh green measurement at 23389f7 (2026-09-10, repair resume session)

Command: `uv run --no-sync pytest -m 'not slow' -q --cov=omrg --cov-branch`

- Revision: `23389f7552d3425e2712817e3c7242c4794bb6db` (worktree `feat/repair-input-quality-experiment-evidence`), after the tripwire executed-count re-baseline 2,774 → 2,816 (documented in the change evidence).
- Result: **2,821 passed, 131 skipped, 19 deselected, 0 failed in 551.82 s**.
- Overall branch coverage: **91%**. Orchestration tier: **94%**. Core+MCP tier: **91%** (below its 95% floor; exception unresolved and unchanged in disposition).
- Lock provenance: `uv run --no-sync` against the existing environment; no dependency change.
- The earlier `afe151e` measurement in this file used the identical command and configuration, so both revisions are on file; no further earlier-revision run is required for attribution. The suite is green at `23389f7`.
