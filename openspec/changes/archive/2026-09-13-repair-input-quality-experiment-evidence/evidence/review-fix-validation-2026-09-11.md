# Review-fix validation at b222823 (2026-09-11)

## Scope lock

- Worktree: `/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3-feat-repair-input-quality-experiment-evidence`
- Branch: `feat/repair-input-quality-experiment-evidence`
- Revision: `b22282366cc5e5a983e07e43d2fdd9c742684735`
- `uv.lock` unchanged; `uv run --no-sync` against the existing environment.
- Dependency action: none.
- Environment: OpenAI-like adapter absent, Qwen3-Embedding-4B tokenizer cache present, historical ground truth present (verified 2026-09-11).

This run validates the review-amendment code fixes (`047dedb`..`cc88a13`) at their own HEAD. The prior green run at `23389f7` predates the review amendment and is retained as provenance; it does not validate these fixes.

## Targeted subsets (task 8.6 explicit items)

Command:

```sh
uv run --no-sync pytest \
  tests/test_ocr_routing_gate.py \
  tests/test_ocr_identity_reingestion.py \
  tests/test_ocr_routing_seam.py \
  tests/test_ocr_diagnostics_metadata.py \
  tests/test_ocr_error_boundary.py \
  tests/test_ocr_worker_import_boundary.py \
  tests/test_experiment_summary_safety.py \
  tests/test_exp26_verdict_validity.py \
  tests/test_exp27_verdict_validity.py \
  tests/test_no_module_level_strategy_imports.py \
  tests/test_contract_coverage.py \
  tests/test_lancedb_import_site.py \
  -m "not slow" -q -rs
```

Result: **174 passed, 0 skipped, 0 failed in 23.83 s**.

Covers: OCR/identity routing and reingestion, routing seam, diagnostics metadata, error boundary, worker import boundary, experiment summary safety, exp 26/27 verdict validity, no module-level strategy imports, contract coverage, LanceDB import site.

## Static checks

- `uv run --no-sync ruff check tests/test_clean_base_tripwire.py` — All checks passed.
- `uv run --no-sync ruff format --check tests/test_clean_base_tripwire.py` — 1 file already formatted.
- `uv run --no-sync openspec validate --all --strict` — 53 passed, 0 failed.

## Full fast-suite branch coverage

Command:

```sh
uv run --no-sync pytest -m "not slow" -q --cov=omrg --cov-branch
```

Result at `b222823`: **2863 passed, 131 skipped, 19 deselected, 0 failed in 597.65 s (0:09:57)**.

The 2863 executed count = 2858 (the tripwire's own subprocess count, which ignores `test_clean_base_tripwire.py`) + 5 (the tripwire module's own test cases). The tripwire `test_base_skip_manifest_is_exact` passed inside this run, validating the 2858/131/19 pin against its own subprocess recount at this revision.

### Coverage tiers

| Tier | Required | Branch coverage | Result |
| --- | ---: | ---: | --- |
| Core + MCP | 95% | 90% (6,716 stmt, 553 missed; 2,066 branches, 191 partial) | FAIL |
| Orchestration | 85% | 93% (1,285 stmt, 78 missed; 362 branches, 30 partial) | PASS |
| Overall | 90% | 91% (9,665 stmt, 754 missed; 2,860 branches, 279 partial) | PASS |

## Coverage exception

The Core+MCP tier sits at 90%, below its 95% floor. This is a slight regression
from the 91% recorded at `23389f7`; the review amendment added core code
(`ocr_routing.py`, `ocr_policy.py`, identity schema 5) whose new branches are
not fully exercised. The exception remains unresolved and visible; no
unrelated coverage fix was attempted, per the change non-goals. The prior
recorded measurement at `23389f7` used the identical command and
configuration.

## Boundary

No paid run, OCR execution, index rebuild, production routing change, default
promotion, commit or push occurred. Historical plans, raw results and
preserved indexes remain untouched. This record validates the review fixes at
their own revision; it does not authorise any further change.
