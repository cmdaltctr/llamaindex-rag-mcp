# Graph contracts and admission (tasks 2.1 to 2.5)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, base `489a618`, uncommitted work tree.

Command prefix for every run (v3 `.venv`, no installs):

    PATH=<v3>/.venv/bin:$PATH PYTHONPATH=src PDF_READER=pypdf python -m pytest -q -p no:cacheprovider <files>

## Files

- New package `src/omrg/core/pipelines/`: `models.py`, `ports.py`, `levers.py`, `catalogue.py`, `adapters.py`, `executable.py`, `validation.py`, `topology.py`, `admission.py`, `snapshot.py`, `results.py`, `errors.py`, `__init__.py`. The largest file has 342 lines.
- `src/omrg/__init__.py`: lazy PEP 562 exports of the four graph types.
- `tests/test_engine.py`: the `__all__` expectation now lists the seven public names.
- New tests: `tests/unit/test_pipeline_{support,models,catalogue,preflight,admission,guide}.py`.
- New guide: `docs/guides/pipelines.md`.

## Test-first record

1. Tests written before the implementation. First run:
   `tests/unit/test_pipeline_*.py` gave **5 collection errors** (`ImportError: cannot import name 'READER_STRUCTURED' from 'omrg.core.pipelines'`).
   `tests/test_engine.py::test_public_api_exports_engine_effective_settings_version` gave **1 failed** (old `__all__`).
2. After the implementation: `tests/unit/test_pipeline_*.py` plus the export test gave **98 passed**.
3. Mutation checks. A pytest plugin disabled one guard at a time (scratch script, not in the repository). Each mutation made the named tests fail:

| Guard disabled | Failing tests |
|---|---|
| Cycle detection | `test_cycle_is_rejected` (1 failed, 99 passed) |
| Commit conflict check | `test_conflicting_commits_same_collection`, `test_multiple_commit_destinations_rejected_initially` (2 failed) |
| Embedding identity check | `test_embedding_identity_mismatch_with_equal_dimensions`, `test_embedding_identity_mismatch_for_commit` (2 failed) |
| Executable-text check | `test_executable_parameter_text_rejected`, `test_executable_operation_text_rejected` (2 failed) |
| Port compatibility | `test_incompatible_connection_names_edge`, `test_bypass_type_flows_from_upstream` (2 failed) |
| Lever allow-list | 7 parametrised `test_graph_overrides_outside_allowed_levers` cases (7 failed) |
| Precedence reversed (graph beats node) | `test_node_override_beats_graph_override_beats_profile` (1 failed) |
| Bypass type flow | `test_bypass_type_flows_from_upstream` (1 failed) |

4. Guide test (2.5). A copy of the guide had one issue-code row removed and the cycle example broken. The copied test gave **2 failed, 6 passed** (`test_guide_example[invalid-cycle]`, `test_guide_lists_every_issue_code`). The real guide gives 8 passed.

## Final results

| Command | Result |
|---|---|
| `tests/unit/test_pipeline_admission.py` | 13 passed |
| `tests/unit/test_pipeline_catalogue.py` | 24 passed |
| `tests/unit/test_pipeline_guide.py` | 8 passed |
| `tests/unit/test_pipeline_models.py` | 20 passed |
| `tests/unit/test_pipeline_preflight.py` | 38 passed |
| `tests/unit/test_pipeline_support.py` | 2 passed |
| Above plus `tests/test_engine.py`, `tests/test_file_size_ceiling.py`, `tests/test_no_global_settings_reads.py`, `tests/unit/test_profile_resolver_injection.py` | 215 passed |
| `tests/test_pipeline_import_boundaries.py` (owned by task 1.3) | 13 passed |
| `PYTHONPATH=src lint-imports` | 12 kept, 0 broken (includes `pipeline-runner-independent-of-domains`) |
| `ruff check` and `ruff format` on touched files | All checks passed; formatted |

## Scenario coverage

| Spec scenario | Test |
|---|---|
| Moving a node changes presentation only | `test_layout_change_keeps_execution_identity` |
| Unsupported graph version | `test_unsupported_schema_version_is_rejected`, `test_missing_schema_version_is_rejected` |
| Catalogue drives node configuration; unavailable reason | `test_descriptor_schema_lists_ports_params_and_effects`, `test_catalogue_reports_unavailable_operations_with_reasons` |
| Invalid bypass | `test_disabled_node_without_bypass_rejected`, `test_bypass_cannot_change_port_kind`, `test_bypass_type_flows_from_upstream` |
| Invalid graph does not execute | `test_preflight_runs_no_adapter`, `test_unknown_operation_names_node`, `test_missing_required_input`, `test_cycle_is_rejected` |
| Identity conflict at equal dimensions | `test_embedding_identity_mismatch_with_equal_dimensions` |
| Executable text submitted | `test_executable_parameter_text_rejected`, `test_executable_operation_text_rejected` |
| Conflicting commits | `test_conflicting_commits_same_collection` |
| Dense threshold on fusion score (static guard) | `test_fusion_score_cannot_feed_dense_threshold`, `test_incompatible_connection_names_edge` |
| Inherited profile | `test_omitted_profile_inherits_collection_profile` |
| Explicit graph profile keeps collection tag | `test_explicit_profile_uses_bundle_and_keeps_collection_metadata` |
| Explicit node override records control and source | `test_node_disables_reranker_regardless_of_profile` |
| Settings change during execution | `test_snapshot_is_immutable_and_detached` |
| Unsupported composition override | `test_graph_overrides_outside_allowed_levers`, `test_unsupported_graph_profile` |
| Public exports lazy, no import-time setup | `test_top_level_exports_graph_types`, `test_importing_omrg_does_not_load_pipelines_or_settings` |

## Not in scope here

Engine methods (task 4.3), the runner, events emission and cancellation (4.1, 4.2, 4.4), and index-shaping fingerprints (3.5) are not part of this evidence.
