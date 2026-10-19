# Experiment contexts (task 8.5)

Design D10 and spec `notebook-plugins` ("Experiment writes stay in approved experiment workspaces").

## Files

| File | Lines | Job |
|---|---|---|
| `src/omrg/core/experiments/__init__.py` | 39 | Public exports. |
| `src/omrg/core/experiments/contexts.py` | 368 | `ExperimentRegistry`, `ExperimentContext` (approval record), path checks, leases, revocation. |
| `src/omrg/core/experiments/admission.py` | 151 | `BackendIdentity`, `check_credential_target`, `check_experiment_snapshot`. |
| `src/omrg/core/experiments/errors.py` | 51 | `ExperimentPathError`, `ExperimentAdmissionError` (stable `code`, `to_dict()`). |
| `src/omrg/compose_experiments.py` | 324 | `ExperimentEngines`: one Engine per context, admission, execution, shutdown. |
| `tests/unit/test_experiment_contexts.py` | 333 | Core rules (33 tests). |
| `tests/unit/test_experiment_contexts_engines.py` | 386 | Composition with tmp_path LanceDB stores (15 tests). |
| `tests/unit/test_experiment_contexts_support.py` | 69 | Explicit `Settings`, recording Engine builder. No tests. |

`core/experiments` is pure. It imports only `core.pipelines.catalogue` (for `EffectClass`) and the standard library. It starts no process, opens no database and imports no web package.

## Behaviour

### Registration and path checks

- The operator gives approved roots to `ExperimentRegistry` (each root must be an existing directory, else `root_not_approved`).
- `register(workspace, name=, actions=, store_backend=, declared_factors=)` returns an `ExperimentContext` with an opaque id `exp_<16 hex>`. The id names no path.
- Rejections (all `ExperimentPathError.code`): `not_absolute`, `traversal` (any `..` part), `not_found`, `not_a_directory`, `is_root`, `outside_root`, `symlink_escape` (a link below a root that resolves outside it, or a linked `output` directory), `overlaps_context` (same or nested workspace as an active context), `action_unknown`, `store_unknown`, `store_not_declared`.
- A link that stays below the root registers its real directory.
- Actions: `read` and `ingest`. Default is both. `ingest` permits `SOURCE_COMMIT` nodes.
- Store backend: `lancedb` by default. Another backend (`chroma`, local only) needs `declared_factors=["store"]`.
- `context.record()` gives the approval record: id, name, root, workspace, output directory, backend, factors, actions, `approved_at`, `revoked_at`, `status`.

### Engine per context

- `ExperimentEngines(registry, base_settings, build_engine=None)`. The default builder is `compose.build_engine(settings)` (explicit settings route). Callers pass the base `Settings`. Nothing reads a settings singleton or a process default.
- `experiment_settings(base, context)` copies the base settings and moves only the store location to `<workspace>/output/<backend>` (`lancedb_uri`, or `chroma_persist_dir` with `chroma_mode="local"`).
- `engine(context_id)` builds once and caches. It checks containment again before and after it creates `output/`, so a link planted after registration cannot move the store (`symlink_escape`, nothing created outside).
- Each Engine has its own embedder (`EMBEDDING_PROVIDER_SCOPE = "engine"`). The LlamaIndex global embedder is not changed.
- `identity(context_id)` and `live_backend_identity(settings)` return `BackendIdentity`: `context_id`, `store_kind`, canonical `store_path`, `embedding_provider`, `embedding_model`, and `index_identity` (16-hex SHA-256 of those fields). `provenance()` is the record that runs store with their outputs.

### Admission guard

`ExperimentEngines.admit(context_id, definition, inputs=, bound_context=, session=)` runs these steps in this order:

1. `check_credential_target`: refuses before any Engine build or lease.
2. `registry.acquire`: refuses an unknown or revoked context.
3. `engine.validate_pipeline(definition, inputs=...)`: no side effects.
4. `check_experiment_snapshot`: the Engine store must be this context's store below `output/`, and each enabled `SOURCE_COMMIT` node needs the `ingest` action and a destination collection.

Any failure releases the lease and raises. Success returns `ExperimentAdmission(context, engine, snapshot, identity, lease)`.

| Code | When |
|---|---|
| `live_library_target` | Experiment credential selects the live library (no context id). |
| `experiment_scope_mismatch` | Experiment credential selects another context. |
| `experiment_credential_required` | Unbound bearer credential selects an experiment context. |
| `experiment_context_unknown` | Unknown id. |
| `experiment_context_revoked` | Revoked context (at admission or at execution start). |
| `action_not_permitted` | Commit node in a read-only context. |
| `commit_outside_context` | Engine store not below this context's `output/`, or commit without a destination. |

Read-only graphs (no enabled `SOURCE_COMMIT`) are admitted for a context with the `read` action.

### Leases, revocation and shutdown

- `execute(admission)` checks again that the context is active, runs `engine.run_pipeline(snapshot)`, and releases the lease in all cases. `run(...)` is `admit` plus `execute`.
- Revocation semantics. New admissions fail with `experiment_context_revoked`. A job that was admitted but has not started fails at `execute` with the same code, before the Engine runs. A run that already started is not stopped: it finishes. To stop it, use the existing run-service cancel (`RunService.cancel(run_id)`, `POST /v1/runs/{run_id}/cancel`), which follows the runner's cancellation rules.
- The context Engine closes when the context is revoked and its last lease is released (registry idle listener).
- `close()` refuses with `RuntimeError` naming busy contexts while any lease is held; nothing closes. After the leases are released, it closes every Engine.

## Test-first record

1. Tests written first. Command: `PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/test_experiment_contexts.py tests/unit/test_experiment_contexts_engines.py`. Result: **2 errors during collection** (`omrg.core.experiments` and `omrg.compose_experiments` missing).
2. After `core/experiments`: core file **33 passed**.
3. After `compose_experiments.py`: **46 passed**. After two added tests (link swap, queued revocation): **48 passed**.

## Mutation checks

Script `scratchpad/exp85/mutate.py` changed one line, ran both test files, restored the file and compared SHA-256.

| Mutation | Result | Failing tests |
|---|---|---|
| M1 No credential check in `admit` | 1 failed | `test_bound_credential_cannot_use_another_context` |
| M2 No `ingest` action check | 3 failed | commit-needs-ingest, read-only context, lease release |
| M3 No store containment check | 1 failed | `test_commit_into_a_store_outside_the_context_is_rejected` |
| M4 No containment recheck at build | 0 failed at first; added `test_workspace_swapped_for_a_link_creates_nothing_outside`; then 1 failed | link swap test |
| M5 Store left at live location | 4 failed | ingestion location, isolation, declared factor, production builder |
| M6 Lease kept on rejection | 2 failed, 2 errors | lease release, read-only context |
| M7 No close on idle | 1 failed | revocation in-flight test |
| M8 No Engine cache | 2 failed | isolation, lease release |
| M9 No linked `output` check | 2 failed | registration and build link tests |
| M10 No overlap check | 1 failed | `test_overlapping_workspaces_are_rejected` |
| M11 Revocation ignored | 2 failed, 1 error | revocation tests |
| M12 No active check in `execute` | 1 failed | `test_queued_job_fails_when_its_context_is_revoked_before_execution` |

## Final results

| Command | Result |
|---|---|
| Both experiment test files | 48 passed |
| Plus `tests/test_file_size_ceiling.py`, `tests/test_no_global_settings_reads.py`, `tests/test_contract_coverage.py` | 151 passed |
| Regression: `tests/test_engine.py`, `tests/test_pipeline_import_boundaries.py`, `tests/unit/test_engine_pipelines{,_isolation,_ingestion}.py` with the above (`-m "not slow"`) | 229 passed (before the `execute` split; experiment files rerun after) |
| Branch coverage (owned modules, `COVERAGE_FILE` in scratchpad) | 97 % (`admission.py` 100 %, `compose_experiments.py` 99 %, `contexts.py` 95 %) |
| `PYTHONPATH=src .venv/bin/lint-imports` | 16 kept, 0 broken |
| `ruff format`, `ruff check` on owned files | Pass |

## Proposed import-linter contract (not made; `pyproject.toml` not owned)

`omrg.core.experiments` is covered today only through the `omrg.core` contracts. Proposed:

```toml
[[tool.importlinter.contracts]]
name = "experiment-contexts-stay-pure"
type = "forbidden"
source_modules = ["omrg.core.experiments"]
forbidden_modules = [
    "omrg.compose", "omrg.engine",
    "omrg.core.ingestion", "omrg.core.retrieval", "omrg.core.answer", "omrg.core.providers",
    "omrg.core.vectordb", "omrg.core.workspace", "omrg.core.plugins",
    "omrg.transports", "omrg.integrations",
    "subprocess", "socket", "signal", "sqlite3", "fastapi", "starlette", "uvicorn", "marimo",
]
unmatched_ignore_imports_alerting = "error"
```

Also add `"omrg.core.experiments"` to `core-business-avoids-providers-transports`. Trial with a scratch config: KEPT. With a temporary `import subprocess` in `errors.py`: BROKEN (file restored).

## Transport wiring needed (not made; `transports/api/*` and `security.py` not owned)

1. **Credential binding (`security.py`).** Add `experiment_context: str | None = None` to `_BearerEntry`, `IssuedBearer` and `Principal`. `issue_bearer(scopes, label, experiment_context=None)` stores it. `authenticate_bearer` copies it to the principal. `list_bearers` shows it. Issue a bound credential only for an active context (`registry.require_active`). Revoking a context does not revoke the credential, but every later admission fails with `experiment_context_revoked`.
2. **Runtime.** Build `experiment_registry(approved_roots)` and `ExperimentEngines(registry, settings)` in the lifespan. Approved roots come from a new `--experiment-root` option (repeatable), never from a request. Call `experiments.close()` after the run service shuts down and before `engine.close()`. The transport cannot call `get_settings()` (`tests/test_no_global_settings_reads.py`). To get the base `Settings`, either (a) add a small `experiment_base_settings()` to `compose_engine.py`, next to `configured_vector_store()`, or (b) add `compose_experiments.py` to `_PERMITTED_PATHS` and give `ExperimentEngines` a `from_environment(registry)` constructor.
3. **Routes (session only, scope `manage`):**
   - `POST /v1/experiments` `{workspace, name, actions?, store_backend?, declared_factors?}` gives 201 with `context.record()` and `identity(...).provenance()`. `ExperimentPathError` gives 400 with `to_dict()`.
   - `GET /v1/experiments` lists records. `GET /v1/experiments/{context_id}` gives one record plus identity.
   - `DELETE /v1/experiments/{context_id}` revokes and gives the record.
   - `POST /v1/credentials` accepts optional `experiment_context`.
4. **Run submission.** `POST /v1/runs` accepts optional `experiment_context`. The admitter calls `experiments.admit(context_id, revision["document"], inputs=..., bound_context=principal.experiment_context, session=principal.kind == "session")` and keeps the `ExperimentAdmission` as the job payload. For a request with no `experiment_context`, the admitter calls `check_credential_target(bound_context=principal.experiment_context, target_context=None, session=...)` first, so a bound credential never reaches the live Engine. The executor calls `await experiments.execute(admission, on_event=..., cancellation=...)`. Record `admission.provenance()` (context id, graph identity, backend and index identity) in the run's resource identities. Map `ExperimentAdmissionError` to 403 and `to_dict()`, before any side effect. The admitter needs the principal; today `RunAdmitter.__call__` receives only revision and inputs, so the submit route must pass it (for example a per-call context like `RunAdmitter.task`).
5. **Trust text.** The Experiments view states that notebook Python has the user's filesystem and network permissions.

## Open points

1. **Read-only graphs on the live library with an experiment credential are refused** (`live_library_target`). The spec requires refusal only for mutation. I chose the stricter rule because a credential bound to one experiment should not reach the live library. To allow live reads, permit `target_context=None` when the snapshot has no enabled `SOURCE_COMMIT` node.
2. **Registry state is per launch, in memory**, like bearer credentials. Approval records do not survive a restart. To keep them, persist `context.record()` through the workspace repository (owner of `integrations/workspace_sqlite`).
3. **Chroma as a declared factor** is composed (settings only); no test builds a Chroma Engine because the `chroma` extra is optional.
