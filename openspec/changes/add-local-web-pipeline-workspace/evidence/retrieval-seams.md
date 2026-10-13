# Evidence: task 3.1 retrieval seams

Date: 2026-10-13. Worktree: `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace`, branch `feat/add-local-web-pipeline-workspace`.

Test command prefix (v3 venv, no installs):

```bash
PATH=/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3/.venv/bin:$PATH PYTHONPATH=src PDF_READER=pypdf python -m pytest -q -p no:cacheprovider <files>
```

## What changed

| File | Change |
|---|---|
| `src/omrg/core/retrieval/operations.py` (new, 323 lines) | Shared seams for lever defaults, rerank policy, candidate sizing, dense eligibility, reranker call, success rule, dense fallback decision, score threshold and ordering. |
| `src/omrg/core/retrieval/pipeline.py` (484 to 474 lines) | `search()` and `_hybrid_query_rows()` call the seams through `ops.<name>`. Signature, defaults, return shape and diagnostics are unchanged. `RERANK_SCORE_KIND` stays importable from `pipeline`. |
| `tests/fixtures/pipeline_parity/retrieval/{corpus.json,cases.json,harness.py}` (new) | 15 recorded parity cases and a reusable harness. |
| `tests/unit/test_retrieval_seams.py` (new) | 37 seam tests. |
| `tests/unit/test_retrieval_seams_parity.py` (new) | Parity test over all recorded cases. |

The ÷30 transform and the candidate-pool formula stay in `policy.py`. `operations.py` calls them and holds no second copy. The fallback re-query still calls `pipeline._hybrid_query_rows`, so existing monkeypatch targets (`_hybrid_query_rows`, `_sparse_bm25_query`, `_selected_sparse_backend`, `assemble`) keep working. Sparse and native-fallback behaviour in `sparse_dispatch.py` is untouched.

## Seam functions (for task 3.2 graph adapters)

All take settings and rows explicitly. None reads a process default.

```python
RERANK_SCORE_KIND = "reranker_sigmoid_v1"
SearchLevers(top_k: int, hybrid: bool, similarity_threshold: float)            # frozen
RerankOutcome(rows: list[dict], backend: str | None, failure_reason: str | None)  # frozen
resolve_search_levers(settings, *, top_k=None, hybrid=None, similarity_threshold=None) -> SearchLevers
resolve_rerank_decision(rerank, query, settings, *, caller_settings=None, technical_fraction=None) -> tuple[bool, str]
size_candidate_pool(top_k, rerank, collection_count, settings, *, fetch_k_override=None) -> int
first_stage_dense_threshold(similarity_threshold, *, rerank) -> float
apply_dense_eligibility(dense_rows, sparse_rows, dense_threshold) -> tuple[list[dict], list[dict]]
run_reranker(query, rows, *, top_k, settings, reranker=None, timing_report=None) -> RerankOutcome
rerank_succeeded(rerank, rows) -> bool
needs_dense_fallback(*, rerank, hybrid, succeeded, similarity_threshold) -> bool
apply_score_threshold(rows, similarity_threshold, *, succeeded, hybrid) -> tuple[list[dict], str]
rank_and_truncate(rows, top_k) -> list[dict]
```

## Parity fixtures

`cases.json` was recorded from `search()` on a `git archive` export of commit `489a618` `src/` (the pre-extraction retrieval package; no retrieval commits since `3ca82a0`). The recorder ran outside the worktree source, so the "before" result does not depend on the new code.

Cases cover: dense without rerank, dense rerank success (÷30), dense rerank failure (undivided threshold), hybrid dense eligibility, hybrid without threshold (tie order of `a` and `e`), hybrid rerank success, hybrid rerank failure with fallback re-query, hybrid rerank failure without threshold, `fetch_k` override, profile settings enable rerank, semantic policy disable (technical query) and enable, settings-filled levers, public result shape, empty collection.

Hand checks against the recorded values:

1. `hybrid_no_rerank_dense_eligibility`: `b` = 1/62 + 1/61 = 0.032522; `c` = 1/63 + 1/62 = 0.032002; `a` = 1/61 = 0.016393. Rows `d`, `e`, `f` are ineligible.
2. `dense_rerank_success_div30`: threshold 0.3/30 = 0.01 keeps `d` (0.02) and `e` (0.012) and drops `f` (0.001).
3. `fetch_k_override_pool`: only `a` and `b` reach the reranker.

## Test outcomes

| Step | Command files | Result |
|---|---|---|
| Baseline before any change | 21 retrieval files (hybrid, rerank policy, fetch pool, retrieval, timing, LM-free, native sparse, assembly x2, lineage, audit regressions, norm guard, query cache, query instruction, sparse freshness, profiles, registry contract, strategy inventory, global-settings guard, file-size ceiling, engine) | 475 passed, 12 skipped |
| Parity before extraction (worktree code) | `tests/unit/test_retrieval_seams_parity.py` | 16 passed |
| Parity before extraction (HEAD `src/` export, final fixtures) | same, `PYTHONPATH=<export>/src` | 16 passed |
| Seam tests before implementation | `tests/unit/test_retrieval_seams.py` | collection error: `operations` module missing (expected fail) |
| Seams + parity after extraction | both new files | 53 passed |
| Same 21 retrieval files after extraction | as baseline | 472 passed, 3 failed, 12 skipped |
| Wider run after extraction | 21 files + reranker backend, answer core, MCP tools, CLI, OpenAPI, no-torch, profile resolver, codebase context, new files | 805 passed, 3 failed, 17 skipped |
| `ruff check`, `ruff format --check` | touched files | clean |
| `lint-imports` | whole package | 8 kept, 0 broken |

The 3 failures come from other agents' concurrent work in the same worktree. They are not caused by this task:

1. `test_strategy_registration_inventory.py::test_integration_inventory_table_matches_disk` and `::test_integration_inventory_marker_count_agrees`: the new `omrg.integrations.workspace_sqlite` package is not yet in the `architecture.md` inventory table.
2. `test_engine.py::test_public_api_exports_engine_effective_settings_version`: the edited test expects `PipelineDefinition` and related exports that `omrg.__init__` does not yet export.

## Mutation checks (tests fail when the rule breaks)

Each mutation was applied to a file this task owns, run, then restored byte for byte.

| Mutation | Failing tests |
|---|---|
| `policy._effective_threshold` divides by 20 instead of 30 | `test_successful_rerank_divides_threshold_by_thirty`, parity `dense_rerank_success_div30`, parity `hybrid_rerank_success_div30` |
| `apply_dense_eligibility` returns rows unfiltered | seam eligibility test, parity `hybrid_no_rerank_dense_eligibility`, `hybrid_rerank_failure_fallback`, `settings_defaults_fill_levers` |
| `needs_dense_fallback` always `False` | seam truth-table case, parity `hybrid_rerank_failure_fallback` |

## Boundary checks in the seam tests

1. `search()` calls every seam in order (spy test).
2. `pipeline.py` has no reference to `_effective_threshold`, `_resolve_fetch_k` or `_resolve_rerank_policy`.
3. `operations.py` passes the default-accessor AST scan from `tests/test_no_global_settings_reads.py`.
4. All seams run with poisoned `get_default_effective_settings`, `resolve_effective_settings` and `get_default_store`.
5. Importing `operations` in a fresh interpreter loads no `dense`, `sparse`, `native_sparse`, `fusion`, `reranker`, `reranker_torch` or `backend` module.
