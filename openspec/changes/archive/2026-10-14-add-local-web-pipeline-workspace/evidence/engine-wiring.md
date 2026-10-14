# Engine wiring (task 4.3)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree.

Command prefix for every run:

    PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider <files>

## Files

| File | Lines | Change |
|---|---|---|
| `src/omrg/engine.py` | 483 | New `resolve_settings`, `validate_pipeline`, `run_pipeline`; `close()` refuses during a graph run; helpers `_graph_host`, `_get_answer_llm`, `_resolver`. `answer()` now uses `_get_answer_llm` (same behaviour). |
| `src/omrg/compose_pipelines.py` (new) | 447 | Catalogue composition, `HostContext`, profile source, request limits, run plan, run lock and leases. |
| `src/omrg/compose_engine.py` | 195 | No change. |
| `tests/test_engine.py` | | Method-set expectation only. |
| `tests/unit/test_engine_pipelines{,_isolation,_ingestion,_support}.py` (new) | 312, 149, 108, 282 | 26 tests and one strict `xfail`. The support module holds no tests. |

## Public interface

```python
Engine.resolve_settings(collection: str | None = None) -> EffectiveSettings
Engine.validate_pipeline(
    definition: PipelineDefinition | Mapping[str, Any],
    *,
    inputs: Mapping[str, Any] | None = None,
    collection: str | None = None,
) -> AdmissionSnapshot | PreflightReport
async Engine.run_pipeline(
    definition: PipelineDefinition | Mapping[str, Any] | AdmissionSnapshot,
    *,
    inputs: Mapping[str, Any] | None = None,
    on_event: EventSink | None = None,
    cancellation: CancellationToken | None = None,
) -> PipelineResult
```

- `validate_pipeline` with `inputs` admits the graph and returns the frozen `AdmissionSnapshot`. Without `inputs` it returns the draft `PreflightReport`. Both raise `PipelineValidationError` and have no side effects.
- `run_pipeline` also accepts an `AdmissionSnapshot` from `validate_pipeline` (then omit `inputs`). The run service can therefore admit once and run the admitted snapshot.
- `resolve_settings(None)` uses `settings.collection_name`. It uses the Engine's own resolver, else the Engine settings.

## Composition decisions

1. The catalogue is built on the first validation or run and kept per Engine. `build_operation_catalogue()` calls `register_ingestion_operations`, `register_retrieval_operations` and `register_answer_operations`. All three imports are hard imports.
2. `HostContext`: capabilities `store`, `embedder`, `reranker`, `ocr` (reason text when absent); `embedding = EmbeddingRef(settings.embed_provider, embedder.model_name)`; default collection = `collection` argument or `settings.collection_name`.
3. `StoreCollectionView` reads the identity stamp from collection metadata. Stamps use the store vocabulary (`llamacpp`), and the host identity uses the settings vocabulary (`local`). The view compares a stamp with the store's own write identity. A match returns the host identity. A different stamp returns the stamp, so preflight reports `embedding_identity_mismatch`. A store without an identity reports no stamp.
4. Profiles: `ResolverProfileSource` over the Engine's resolver. An Engine without a resolver uses `FixedProfileSource`: every collection gets the Engine settings, and a named graph profile fails with `profile_resolution_failed` and corrective actions. The draft check (no inputs) also checks a named profile.
5. Resources: `store`, `embedder`, `reranker`, `ocr`, `answer_llm` (zero-argument callable that builds and caches `Engine._answer_llm`, shared with `Engine.answer`), `verify_llm` (callable of the answer block, one judge per block, cached per Engine). `None` resources are omitted. Without an answer factory, `answer_llm` is absent and the adapter gives the no-provider result.
6. Request limits: when an enabled node has an `answer` output, the `answer()` limits apply: query inputs at most 4096 characters, `retrieval.top_k` 1 to 100 on node parameters and graph overrides, `expand_window` 0 to 10. The constants come from `core/answer/pipeline.py`. Retrieval-only graphs keep the search limits, as `Engine.search` does.
7. Run plan (from the snapshot, not in the runner): when a node uses an ingestion operation, the plan adds `ingestion_shape(snapshot, catalogue)` as resource `ingestion_shape`, the unit split on the one `source.discover` node, and `ocr`. The Engine's OCR client is used when present. Otherwise, when a node's settings enable `ocr_fallback_enabled`, the run builds one client with `capabilities.build_ocr_routes` (the `ingest_path_async` rule) and closes it after the run.
8. Leases: `EnginePipelines.active_runs` counts runs that hold or wait for the lock. One `asyncio.Lock` per Engine serialises runs. `close()` raises `RuntimeError` while `active_runs > 0`; the Engine stays usable. A caller `RunCancellation` is used as given; another token becomes the parent; no token gives a new `RunCancellation`.

## Test-first record

1. Tests written first (`test_engine_pipelines.py`, `test_engine_pipelines_isolation.py`, method-set test). First run: **23 failed** (`AttributeError`: no `validate_pipeline`, `run_pipeline`, `resolve_settings`; method set mismatch).
2. After the implementation: **62 passed, 1 xfailed** (with `tests/test_engine.py`).
3. The ingestion test file was added after the coordinator's update. Its red state comes from the mutations below.
4. Mutation checks. A scratch script changed one line, ran the three new test files, restored the file and compared SHA-256:

| Mutation | Result | Failing tests |
|---|---|---|
| No unit split | 2 failed, 24 passed | ingestion parity, OCR plan |
| No `ingestion_shape` resource | 1 failed | ingestion parity |
| No run lock | 1 failed | `test_runs_on_one_engine_are_serialised` |
| No close guard | 1 failed | `test_close_during_a_run_fails_and_keeps_the_engine_usable` |
| Answer model built eagerly | 4 failed | validation side effects, two lazy-answer tests, query limit |
| No request limits | 2 failed | query length, top-k limits |
| One catalogue shared by all Engines | 1 failed | `test_two_engines_run_concurrently_and_stay_isolated` |
| No collection identity view | 1 failed | `test_embedding_identity_mismatch_is_rejected` |
| Judge not cached | 1 failed | `test_verify_resource_builds_each_judge_once` |

## Scenario coverage

| Requirement or task check | Test |
|---|---|
| Documented method set | `tests/test_engine.py::test_engine_public_method_surface_is_exactly_documented` |
| Validation before side effects | `test_validation_has_no_side_effects`, `test_invalid_run_input_raises_before_side_effects` |
| Invalid graph names node | `test_invalid_graph_names_the_node`, `test_unavailable_reranker_is_a_capability_issue` |
| Identity at equal dimensions | `test_embedding_identity_mismatch_is_rejected` |
| Explicit Engine lacks named profile | `test_explicit_engine_cannot_load_named_profile` |
| Valid graph executes | `test_retrieval_graph_runs_on_the_engine_store` |
| Answering remains lazy | `test_retrieval_graph_never_builds_answer_models`, `test_empty_evidence_answer_graph_never_builds_answer_models`, `test_answer_model_is_built_once_and_shared_with_engine_answer` |
| Answer request limits | `test_answer_query_length_limit`, `test_answer_top_k_limit_on_node_and_graph_override`, `test_retrieval_graph_keeps_search_limits` |
| Two-Engine isolation, other Engine disposed | `test_two_engines_run_concurrently_and_stay_isolated` (barrier proves both runs are in the store at once) |
| Runs serialised per Engine | `test_runs_on_one_engine_are_serialised` |
| Close during an active run | `test_close_during_a_run_fails_and_keeps_the_engine_usable` |
| Leases released on failure | `test_failed_run_releases_its_lease` |
| Cancellation is run scoped | `test_caller_cancellation_is_run_scoped` |
| Poisoned process defaults | `test_poisoned_process_defaults_are_never_read` |
| Ingestion graph equals `Engine.ingest` | `test_ingestion_graph_writes_the_same_rows_as_engine_ingest` (temporary LanceDB, parity fixtures) |
| Run-owned OCR client | `test_ingestion_run_builds_and_closes_its_own_ocr_client` |
| `resolve_settings` | `test_resolve_settings_uses_the_engine_resolver` |

## Final results

| Command | Result |
|---|---|
| The three new test files | 26 passed, 1 xfailed |
| Above plus `test_engine.py`, `test_engine_isolation.py`, `test_file_size_ceiling.py`, `test_no_global_settings_reads.py`, `test_pipeline_import_boundaries.py`, `unit/test_pipeline_guide.py` | 161 passed, 1 xfailed |
| Wider set: compose, answer compose, all `unit/test_pipeline_*`, retrieval, answer and ingestion graph adapter tests, profile resolver injection | 519 passed, 3 skipped, 1 xfailed, 1 failed (`test_clean_base_tripwire.py::test_base_skip_manifest_is_exact`) |
| `PYTHONPATH=src lint-imports` | 15 kept, 0 broken |
| `ruff check`, `ruff format --check` on owned files | Pass |

The tripwire test runs the whole base suite in a subprocess. It reported 2 failures. Both are `tests/test_strategy_registration_inventory.py` (the `architecture.md` inventory lacks `integrations/workspace_sqlite`, task 3.7). This task adds no integration module. `retrieval-adapters.md` records the same 2 failures before this task.

## Defect found: answer adapters do not accept assembled context

`context.assemble` outputs a `ContextBundle`. `answer.prepare_evidence` and `answer.synthesise` iterate the value as rows, so a real retrieval-to-answer graph fails with `TypeError: 'ContextBundle' object is not iterable`. A graph input cannot feed the answer chain either: preflight requires chunk lineage. The strict `xfail` test `test_answer_chain_accepts_assembled_context_without_a_bridge` records the defect. The two lazy-answer chain tests use a test-only bridge (`bridge_context_bundle`) that passes `bundle.public_rows()`.

Fix (owner of `core/answer/graph_adapters.py`): accept a value with `public_rows()` in `prepare_evidence` input handling. Then remove the bridge and the `xfail` marker.

## Open points

1. `request_limit_issues` imports `_QUERY_MAX_CHARS`, `_TOP_K_MAX`, `_EXPAND_WINDOW_MAX` from `core/answer/pipeline.py`. Consider public names.
2. `run_cancellation` comes from `omrg.core.pipelines.cancellation`. It is not in the package `__init__`.
3. An admitted snapshot passed to `run_pipeline` is not checked against the Engine that admitted it. Pass only snapshots from the same Engine.
4. Graph-adapter modules are not yet in `_GUARDED_LEAVES` (task 3.8). `compose_pipelines.py` is a composition-root module.
