# Evidence: task 3.2 retrieval graph adapters

Date: 2026-10-13. Worktree `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace`, branch `feat/add-local-web-pipeline-workspace`. No commits, no installs.

Command prefix:

```bash
cd <worktree> && PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider <files>
```

## What changed

| File | Change |
|---|---|
| `src/omrg/core/retrieval/graph_adapters.py` (new, 271 lines) | RRF, rerank, threshold/top-k and context adapters. `register_retrieval_operations(catalogue)`. |
| `src/omrg/core/retrieval/graph_adapters_retrieve.py` (new, 214 lines) | Query preparation, dense and sparse adapters. |
| `src/omrg/core/retrieval/graph_adapters_catalogue.py` (new, 203 lines) | Parameter models and the seven `OperationDescriptor`s. One `register()` line each. |
| `src/omrg/core/retrieval/graph_adapters_values.py` (new, 194 lines) | Port types and frozen port values: `PreparedQuery`, `RankedEvidence`, `ContextBundle`. |
| `src/omrg/core/retrieval/sparse_dispatch.py` (additive) | New `sparse_policy_runner(backend, *, native=None, bm25=None)`. It is now the only place that maps a backend name to a sparse runner. |
| `src/omrg/core/retrieval/pipeline.py` (one statement) | `_hybrid_query_rows` calls `sparse_policy_runner(backend, native=_native_sparse_query, bm25=_sparse_bm25_query)`. It passes its own references, so existing monkeypatch targets and the source-reading test stay valid. `search()` behaviour is unchanged. |
| `tests/unit/test_retrieval_graph_adapters{,_parity,_support}.py` (new) | 49 tests. |

## Operations

| Operation id | Effect | Ports (in → out) | Notes |
|---|---|---|---|
| `retrieve.prepare_query` | read_only | `query` text → `query` prepared | Calls `resolve_search_levers`, `resolve_rerank_decision(caller_settings=settings)`, `store.count`, `size_candidate_pool`. Levers: `top_k`, `similarity_threshold`, `rerank`. Also `fetch_k`, `metadata_filter`, `collection`. |
| `retrieve.dense` | model_call | `query` → `evidence` (`dense_similarity_v1`, embedding identity) | Calls `registry.get("dense")` with the injected embedder and the embedding block settings. |
| `retrieve.sparse` | read_only | `query` → `evidence` (`sparse_rank_v1`) | Calls `sparse_policy_runner(settings.retrieval.hybrid_sparse_backend)`. A native-to-BM25 degradation is `NodeOutput.fallback`; the summary names the backend that ran. |
| `combine.rrf` | pure | `ranked` (MANY) → `evidence` (`rrf_v1`) | `apply_dense_eligibility(first_stage_dense_threshold(...))`, then `registry.get("fusion")`, then the `fetch_k` cut. Keeps both branch rankings for the fallback. Lever `rrf_k`. |
| `select.rerank` | model_call | `evidence` → `evidence` (rerank, dense or rrf) | Bypass declared. Calls `run_reranker` on row copies. A failure is `NodeOutput.fallback` with the reranker's reason. Lever `enabled`. |
| `select.threshold` | pure | `evidence` (dense, rrf, rerank) → `evidence` | `needs_dense_fallback`, `apply_score_threshold`, `rank_and_truncate`. On fallback it re-fuses the kept branch rankings with the dense threshold before fusion. |
| `context.assemble` | read_only | `evidence` → `context` | Calls `assemble` (lineage expansion and overlap merge). `ContextBundle.public_rows()` uses `pipeline._strip_internal_result_fields`. |

No adapter holds a second copy of ranking, RRF, the ÷30 transform, eligibility, candidate sizing or filtering. Each rule is a call to `operations.py`, `policy.py` (through `operations`), `fusion.py` (through the registry) or `assembly.py`.

## Test-first record

1. Before implementation: all three test files failed at collection with `ModuleNotFoundError: No module named 'omrg.core.retrieval.graph_adapters'`.
2. After implementation: 49 passed.

## Parity with search()

`test_graph_chain_matches_search` runs all 15 recorded cases through `search(include_diagnostics=True)`, `search(include_diagnostics=False)` and the hand-chained adapters. It compares:

1. `ContextBundle.public_rows()` equals the public `search()` rows exactly (shape, text, scores, lineage fields).
2. `id`, `source`, `score`, `score_kind`, `reranked`, `dense_score`, `dense_score_kind`, `dense_rank`, `sparse_rank`, `fused_rank`, in order.
3. `threshold_score_kind`, `rerank_reason` and `rerank_backend` in the select summary equal the `search()` diagnostics.

`test_graph_chain_matches_recorded_expectation` also compares the 13 argument-settings cases with the values recorded before task 3.1.

Graphs always receive explicit settings, as `Engine.search()` does. The two `policy_default_*` cases were recorded with the process default, so the parity test runs both paths with those settings passed explicitly.

## Mutation checks

Each mutation changed one owned file, ran the two test files, and restored the file. A SHA-256 check confirmed each restore.

| Mutation | Failing tests |
|---|---|
| Select never re-applies the dense gate after a failed rerank | 3 (parity `hybrid_rerank_failure_fallback` x2, fallback outcome) |
| RRF skips dense eligibility | 4 (parity `hybrid_no_rerank_dense_eligibility`, `settings_defaults_fill_levers`, x2) |
| Failed rerank labelled as reranker scores | 6 |
| Rerank failure not reported as a fallback | 2 |
| Score-kind guard removed | 1 (`test_threshold_refuses_rank_only_evidence`) |
| Assembly skipped | 1 (lineage merge test) |
| Dense drops the injected embedder | 1 (poisoned-defaults test) |
| Prepare ignores explicit settings in the rerank policy | 4 |
| Rerank changes upstream rows | 1 (fan-out isolation test) |
| Sparse fallback not reported | 1 |

## Other checks

| Check | Result |
|---|---|
| Poisoned `get_default_effective_settings`, `resolve_effective_settings`, `get_default_store` (both modules), `build_reranker_from_settings`, `llama_index Settings.embed_model` | Full hybrid chain with rerank runs. |
| Accessor-guard AST scan (`_scan_default_accessors`) on `graph_adapters*.py` | No hits. |
| Fresh interpreter import of `graph_adapters` | Loads none of `dense`, `sparse`, `native_sparse`, `reranker`, `reranker_torch`, `fusion`. |
| Preflight of the canonical hybrid graph, with and without the reranker node enabled | Valid. Sparse evidence wired to `select.threshold` gives `incompatible_ports`. |
| `ruff check`, `ruff format --check` on changed files | Pass. |
| `PYTHONPATH=src .venv/bin/lint-imports` | 12 kept, 0 broken. |

Regression run (`-m "not slow"`): 21 retrieval, engine, profile, boundary and size files, plus the seam and adapter tests. Result: 603 passed, 31 skipped, 3 failed. The 3 failures come from other agents' files in the same worktree:

1. `test_file_size_ceiling.py`: `core/workspace/service.py` has 517 lines.
2. `test_strategy_registration_inventory.py` (2 tests): `integrations/workspace_sqlite` is not in the `architecture.md` inventory table.

`tests/test_precalibration_audit_regressions.py::test_hybrid_sparse_path_accepts_the_query_metadata_filter` (the source-reading test) passes.

## Deviations and open points

1. New score kind `sparse_rank_v1` (`SCORE_KIND_SPARSE_RANK`, in `graph_adapters_values`). Sparse rows carry rank order only and no score. The provisional fixture labels sparse output `native_fts_v1`, but a BM25 or fallen-back ranking must not be labelled native. Decide whether to move the constant into `omrg.core.pipelines.ports`.
2. Operation ids: `retrieve.prepare_query` and `select.threshold` are new. The guide's provisional `select.dense_threshold` is not registered; `select.threshold` is score-kind-aware instead.
3. The hybrid lever is resolved into `PreparedQuery.hybrid`, but the graph shape decides whether a sparse branch runs.
4. RRF takes at most one dense and one other ranking (the registered fusion has two inputs). More inputs raise a clear `ValueError`.
5. Dense eligibility keeps the `search()` rule: with a dense threshold above 0 and no rerank, a sparse row needs a qualifying dense row. A sparse-only fusion with a threshold therefore returns no rows.
6. The rerank decision lives in `retrieve.prepare_query`, because it sizes the pool and decides the dense gate. `select.rerank` with `enabled=false` skips inference; `select.threshold` then restores the dense gate exactly as for a failed rerank.
7. Dense embedding identity at run time is `EmbeddingRef(settings.embed_provider, embedder.model_name)`. Composition must build `HostContext.embedding` with the same rule.
8. Cancellation raises `asyncio.CancelledError` at safe boundaries. Task 4.4 may replace this with a runner-owned signal.
9. Task 3.8 still must add the four `graph_adapters*.py` modules to `_GUARDED_LEAVES` (file not owned here). The AST scan already passes on them.
