# Evidence: codebase models, explicit context, and cache owner context

Tasks: 1.2 (codebase part), 4.1 to 4.5. Design: D3, D4, D5.
Base commit: `3ca82a0` on `feat/repair-modular-core-boundaries`. Work is uncommitted.

Run command (from the worktree root, no install):

```bash
PYTHONPATH=src ../llamaindex-rag-mcp-v3/.venv/bin/python -m pytest <tests> -q -p no:cacheprovider
```

## 1.2 Reproduced gaps on unchanged code

Fresh-interpreter import order:

```text
cache first:  ImportError: cannot import name '_get_git_commit_hash' from partially
              initialized module 'omrg.core.codebase.cache' (most likely due to a circular import)
map first:    OK
```

Cache and map defaults: `cache._load_cache` and `cache._save_cache` called
`get_default_effective_settings()` for the cache directory.
`build_codebase_map` called `get_default_effective_settings()` and
`get_default_store()` unconditionally. Neither document-graph call received
the similarity threshold. The cache record had no owner context, so two
stores that share one directory and one commit reused each other's map.

New regressions in `tests/unit/test_codebase_context_repair.py`, run on
unchanged code: **15 failed, 0 passed**.

```text
FAILED test_fresh_import_order_is_independent[cache-first]
FAILED test_fresh_import_order_is_independent[map-first]      (no models module)
FAILED test_models_round_trip_through_cache_serialisers
FAILED test_build_uses_supplied_context_without_defaults      (TypeError: no settings keyword)
FAILED test_store_less_map_has_no_document_communities
FAILED test_both_document_graph_calls_receive_supplied_threshold
FAILED test_two_contexts_use_their_own_cache_directories
FAILED test_mcp_handler_forwards_composed_context             (settings/store not passed)
FAILED test_mcp_handler_settings_failure_returns_error_json
FAILED test_matching_owner_context_reuses_cache
FAILED test_same_directory_different_store_is_a_miss
FAILED test_same_directory_different_map_settings_is_a_miss
FAILED test_unscoped_old_record_is_a_safe_miss
FAILED test_unprovable_store_context_never_reuses
FAILED test_store_data_change_invalidates
```

## Changes

| File | Change |
| --- | --- |
| `src/omrg/core/codebase/models.py` (new) | `FileInventory` and `CodebaseMap`, same fields, defaults, and methods. Data only. |
| `src/omrg/core/codebase/cache.py` | Imports models directly. Adds `build_owner_context`. `_load_cache`/`_save_cache` take keyword `cache_dir` and `owner_context`. No default accessors. |
| `src/omrg/core/codebase/codebase_map.py` | Re-exports the models. `build_codebase_map(path, *, settings, store=None)`. `get_codebase_map_text(path=".", refresh=False, *, settings=None, store=None)`. Threshold goes to both document-graph calls. Cache calls go through the `cache` module (gotcha 8b). Detection fallbacks use the sanctioned `resolve_effective_settings`. |
| `src/omrg/transports/mcp/codebase.py` | Resolves default settings and store inside its `try`, then passes them. Signature, annotations, and error JSON unchanged. A missing composed store gives a store-less map with a warning. |
| `tests/unit/test_codebase_map.py`, `tests/unit/test_codebase_map_integration.py` | Pass explicit settings/store and cache context instead of patching default accessors. |
| `docs/guides/{mcp-tools,configuration,architecture}.md` | Explicit context and safe recomputation. |

## Owner-context design (D5)

The record keeps its filename and its map payload. One new envelope key,
`owner_context`, is added:

```json
{"version": 1,
 "settings": {"magika_binary": "...", "doc_similarity_threshold": 0.85,
              "codebase_map_max_files": 5000, "codebase_map_max_depth": 10,
              "community_algorithm": "louvain", "community_seed": 0},
 "store": null | {"backend": "<module>.<class>", "collection": "documents",
                  "data_version": "<VectorStore.get_data_version token>"}}
```

- The store identity is `VectorStore.get_data_version("documents")`. On LanceDB it holds a persistent dataset epoch (UUID) plus the table version. It differs between stores, survives across processes, and changes when documents change. `cache_identity` is process-local, so it is not used.
- A hit needs the same commit and an equal owner context. A missing, different, or unprovable context is a miss. The old file stays until a successful build replaces it.
- If `get_data_version` returns `None` or raises, `build_owner_context` returns `None`. The cache is then neither read nor written for that call. This applies to Chroma, to an absent `documents` collection, and to LanceDB tables with no epoch yet. Reuse is reduced, and the output stays correct.
- `store=None` is a provable context (`"store": null`), so store-less maps can be cached.
- The cache directory is not in the context. It selects where the record lives.
- Settings values only, never secrets.

## After the fix

| Check | Result |
| --- | --- |
| `tests/unit/test_codebase_context_repair.py` | 15 passed |
| Codebase/cache/graph/community/magika/guard/size set (13 files, below) | 250 passed, 7 skipped |
| `tests/test_mcp_tools.py`, `tests/test_core_coverage_v2.py` `-k "codebase or NeverRaise"` | 4 passed |
| Fresh imports, both orders | `cache-first OK`, `codebase_map-first OK` |
| `ruff check`, `ruff format` on changed files | clean |

The 13-file set: the new regressions plus `tests/unit/test_codebase_map.py`,
`tests/unit/test_codebase_map_integration.py`,
`tests/security/test_codebase_map_boundary.py`, `tests/unit/test_doc_graph.py`,
`tests/unit/test_code_graph.py`, `tests/test_community_baseline.py`,
`tests/test_community_strategies.py`, `tests/test_magika_smoke_guards.py`,
`tests/test_magika_parser_boundaries.py`, `tests/test_coverage_gaps_v2.py`,
`tests/test_no_global_settings_reads.py`, `tests/test_file_size_ceiling.py`.

4.4 preserved behaviour, covered by the existing tests: refresh bypasses the
cache, commit change is a miss, a corrupt file is a miss, a non-Git path
writes no cache, and path-boundary errors stay JSON.

Not in this set: `tests/test_magika_pinned_detection.py`. It fails on the base
commit too, because the `magika` binary is not on `PATH` when the venv is not
activated. This is not caused by this change.

## Mutation checks (each reverted afterwards)

| Mutation | Result |
| --- | --- |
| Cross-link `build_document_graph` loses `threshold=` | threshold regression fails |
| `_load_cache` ignores `owner_context` | 4 owner-context regressions fail |
| Hidden `get_default_store()` fallback put back in the map | store-less and cache-dir regressions fail; `test_no_global_settings_reads` fails on `codebase_map.py` |
| Unprovable store treated as `"store": null` | `test_unprovable_store_context_never_reuses` fails |
| `cache.py` imports models from `codebase_map` (base code) | cache-first import fails (see 1.2) |

## Limits

- The owner-context tests use a store double with `get_data_version`. No real LanceDB dataset was built for this evidence.
- No real vector store, real cache, or `.env` was touched. All caches were under pytest `tmp_path`.
