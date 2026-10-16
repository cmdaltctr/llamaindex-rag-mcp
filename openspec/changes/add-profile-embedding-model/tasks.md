# Tasks

Start these tasks after `organise-backend-folders` has landed and `unify-profiles-and-pipelines` is applied. The first moves the backend files to the paths below. The second adds the `profiles` table, `core/profiles/catalogue.py`, `engine_profiles.py` and `GET /v1/profiles`. Start group 9 after `feat/studio-canvas-layout`, `clarify-canvas-steps` and `studio-profiles-gallery` merge.

Test-first rule for each task that changes behaviour: write the test, run it, see it fail on the current code, then write the code and see it pass.

Line ceiling: `src/omrg/engine.py` has 498 lines and `src/omrg/core/vectordb/lancedb/store.py` has 500. Put new code in the new or mixin modules named below. `uv run pytest tests/test_file_size_ceiling.py` must pass after each group.

## 1. Decision record

- [ ] 1.1 Write `docs/adr/081-per-profile-embedding-models.md` with status Proposed. ADR-080 belongs to `unify-profiles-and-pipelines`; stop and report if 081 is taken. Record D1 to D9 of design.md, the user's approval of the feature, and the safety rules: one model per collection, lock on stamp or rows, binding refusal, check before save, llama.cpp list check. State that it narrows the CLAUDE.md rule "Ask before mixing embedding models" and does not remove it. Verify that `docs/adr/ADR_README.md` lists the new ADR.

## 2. Provider builders accept a model name

- [ ] 2.1 Write `tests/unit/test_embedding_provider_model_override.py`. For `ollama`, `llamacpp` and `openrouter`, assert that `build(settings, model="m2")` returns an embedder with `model_name == "m2"` and keeps the URL, key and batch size from `settings`. Assert that `build(settings)` keeps today's model. Run it and see it fail.
- [ ] 2.2 Add the keyword `model: str | None = None` to `build` in `src/omrg/core/providers/embeddings/{ollama,llamacpp,openrouter}.py`. Verify that the test from 2.1 passes and `tests/unit/test_openrouter_embedding.py` still passes.

## 3. Stores check and stamp the identity they receive

- [ ] 3.1 Add tests to `tests/test_embedding_write_contract.py` for both ChromaDB and LanceDB: a store composed with model A writes into a new collection with `embedding_identity` of model B and the stamp names model B; a write with model B into a collection stamped A fails before mutation, no row persists and the generation does not advance; a write without `embedding_identity` keeps today's rule; a malformed vector diagnostic names model B. Run them and see them fail.
- [ ] 3.2 Add tests to `tests/test_vectordb_contract.py`: `query_dense` and LanceDB `query_native_sparse` with `embedding_identity` of model B accept a collection stamped B on a store composed with A, and refuse a collection stamped A. Run them and see them fail.
- [ ] 3.3 Add the optional `identity` argument to the guard methods in `src/omrg/core/vectordb/identity.py` (`IdentityGuardMixin`) and `src/omrg/core/vectordb/lancedb/meta.py` (`_reject_conflicting_identity`, `_check_or_stamp_identity`, `_guard_query_identity`, `_flush_after_write`). Verify with the tests from 3.1 and 3.2.
- [ ] 3.4 Add the keyword `embedding_identity: EmbeddingIdentity | None = None` to `write_nodes`, `query_dense` and `query_native_sparse` in `src/omrg/core/vectordb/base.py`, `chroma/store.py`, `lancedb/store.py` and `lancedb/fts.py`, and pass it to the guards and the Chroma validator diagnostic. Keep `upsert_precomputed` unchanged. Verify that tests 3.1 and 3.2 pass and `lancedb/store.py` stays at or under 500 lines.

## 4. Retrieval and answer use a supplied identity and a model-aware cache

- [ ] 4.1 Add tests to `tests/test_query_embedding_cache.py`: one query against two identities with equal `model_name` embeds twice; one query against one identity on two collections embeds once; the cache stays bounded. Run them and see them fail.
- [ ] 4.2 Change `_embed_query` in `src/omrg/core/retrieval/dense.py` so that the cache key is `(prepared_query, provider, model)` when an identity is supplied, and keep `(prepared_query, model_name)` otherwise. Pass `embedding_identity` from `_dense_query_rows` to `store.query_dense`. Verify with test 4.1 and `tests/test_query_embedding_instruction.py`.
- [ ] 4.3 Add the keyword `embedding_identity` to `search` in `src/omrg/core/retrieval/pipeline.py`, to `src/omrg/core/retrieval/native_sparse.py`, to `answer` in `src/omrg/core/answer/pipeline.py` and to `src/omrg/core/answer/retriever.py`, and pass it to the dense and native sparse calls. Write a test in `tests/unit/test_retrieval_embedding_identity.py` that a fake store receives the identity on both paths; see it fail first. Verify that `src/omrg/core/retrieval/pipeline.py` stays under 500 lines.

## 5. Ingestion writes with a supplied identity

- [ ] 5.1 Write `tests/unit/test_ingestion_embedding_identity.py`: `ingest_path_async(..., embedding_identity=B)` reaches `store.write_nodes` with identity B through `commit_prepared_source`. Run it and see it fail.
- [ ] 5.2 Add the keyword `embedding_identity` to `ingest_path_async` (`src/omrg/core/ingestion/pipeline.py`), `IngestionContext` and `build_ingestion_context` (`sources.py`), `replace_source_nodes_async` (`replacement.py`) and `commit_prepared_source` (`commit.py`), following the `embed_model` path. Verify with test 5.1 and `uv run pytest tests/test_ingestion_stage3_runtime_identity.py tests/test_embedding_norm_guard.py`.

## 6. Engine embedder set and per-collection routing

- [ ] 6.1 Write `tests/unit/test_engine_embedders.py`: the host key returns the host embedder; one (provider, model) pair builds once and returns the same instance; concurrent `get` calls from threads build once; `release()` clears the set. Run it and see it fail.
- [ ] 6.2 Create `src/omrg/engine_embedders.py` with `EngineEmbedders` (dict keyed by (provider, model), `threading.Lock`, injected factory, host entry first, `release()`). Verify with test 6.1.
- [ ] 6.3 Add the embedder factory to `src/omrg/compose_engine.py` (`embed_registry.get(provider)(settings, model=model)`) and pass it and the concrete host identity (`embedding_identity_from_settings`) to `Engine`. Verify that `tests/test_engine.py` and the import-linter contracts pass (`uv run lint-imports`).
- [ ] 6.4 Write `tests/unit/test_engine_profile_embedding.py` with a fake resolver and two fake embedders: a collection whose profile names model B gets queries embedded by B and not by the host model A (`search` and `answer`); `ingest` writes with identity B; a collection without a choice uses A; two Engines with the same choice use different instances; closing one Engine leaves the other's embedders in place. Run it and see it fail.
- [ ] 6.5 Add `embedding_choice(collection)` to the profile resolver (`src/omrg/core/profiles/resolver.py`) and an `embedding` field to the user profile record in `src/omrg/core/profiles/catalogue.py`. Built-in profiles, a missing tag and an empty choice return `None`. Add a resolver test in `tests/unit/test_profile_embedding_choice.py` first and see it fail.
- [ ] 6.6 Add `Engine._embedding_for(collection)` and use it in `ingest`, `search`, `answer` and `_graph_host`. Call `release()` in `close()`. Keep `engine.py` at or under 500 lines by moving helper code into `engine_embedders.py`. Verify with test 6.4.
- [ ] 6.7 Write tests in `tests/unit/test_engine_pipelines_isolation.py` (or a new `tests/unit/test_graph_profile_embedding.py`): preflight accepts a collection stamped B when the run's profile uses B and the host uses A; preflight refuses a collection stamped A for a profile using B and names both models; `retrieve.dense` and `commit.source` use identity B. Run them and see them fail.
- [ ] 6.8 In `src/omrg/compose_pipelines.py`, build `EmbeddingRef` from the concrete identity in `host_embedding`, compare stamps with that identity in `StoreCollectionView`, and add the `embedding_identity` resource in `build_graph_host`. Add `EMBEDDING_IDENTITY_RESOURCE` to `src/omrg/core/ingestion/graph_adapters_values.py` and read it in `graph_adapters.py` (`commit.source`) and `graph_adapters_retrieve.py` (`retrieve.dense`). Verify with test 6.7 and `uv run pytest tests/unit/test_engine_pipelines*.py`.
- [ ] 6.9 Write a test in `tests/unit/test_pipeline_preflight.py` that a graph override of `embed_model` reports "Set the model on the profile's Embed step"; see it fail. Add the hint for `embed_model` and `embed_provider` in `lever_error` (`src/omrg/core/pipelines/levers.py`). Verify the test passes.
- [ ] 6.10 Update `docs/guides/configuration.md`: replace the paragraph that says one model applies to the whole process (lines 267-272) with the per-profile rule, the lock rule and the server default. Update `docs/guides/pipelines.md`: the Embed step uses the profile's model, and graphs cannot set it. Verify with `grep -n "whole server process" docs/guides/configuration.md` returning nothing.

## 7. Profile storage, lock rule and binding rule

- [ ] 7.1 Write `tests/unit/test_profile_embedding_lock.py` for `collection_embedding_state`, `blocking_collections` and `binding_refusal`: empty unstamped allows; stamped with rows blocks; stamped with no rows blocks; rows without a stamp block with "not recorded"; a request equal to the stamp allows; binding refuses a different stamp; binding to rows without a stamp is allowed only for the server default; each refusal lists the collection, provider, model and chunk count. Use ChromaDB and LanceDB stores. Run it and see it fail.
- [ ] 7.2 Create `src/omrg/core/profiles/embedding_lock.py` with the three functions. Verify with test 7.1.
- [ ] 7.3 Write a schema test in `tests/unit/test_workspace_migrations.py`: version 4 adds `embed_provider`, `embed_model` and `embed_dimensions` to `profiles`; the CHECK refuses a provider without a model; existing rows read as server default; the migration makes a backup. Run it and see it fail.
- [ ] 7.4 Append the version 4 migration to `SCHEMA_MIGRATIONS` in `src/omrg/integrations/workspace_sqlite/schema.py`. Add read and write of the three fields in `src/omrg/integrations/workspace_sqlite/profiles.py` and the repository interface in `src/omrg/core/workspace/repository.py`. Copy the choice when a profile is duplicated. Verify with test 7.3 and the duplicate test from `unify-profiles-and-pipelines`.
- [ ] 7.5 Write tests in `tests/test_web_profile_embedding.py` for `PATCH /v1/collections/{collection}/profile`: the preview and the confirm step return 409 `embedding_mismatch` that names both models when the target profile's model differs from the stamp, and the tag does not change. Run them and see them fail.
- [ ] 7.6 Call `binding_refusal` in `change_collection_profile` (`src/omrg/transports/api/routes/admin.py`) before the preview and before `apply_profile_change`. Verify with test 7.5.

## 8. Check model and the embedding API

- [ ] 8.1 Write `tests/unit/test_check_embedding_model.py` with fake embedders and a fake llama.cpp model list: a 1024-value unit vector passes and reports 1024; a llama.cpp name that the server does not list fails before the probe and lists the served names; a probe error fails with the error text and the API key removed; a vector of length 1.4 fails when the norm guard is on; a missing extra names the extra; an unknown provider is refused. Run it and see it fail.
- [ ] 8.2 Add `check_embedding_model(provider, model)` to the composition root (in `src/omrg/compose_engine.py` or a new `src/omrg/compose_embedding.py` if `compose.py` would pass 500 lines). Use a throwaway embedder and `engine.redact` for errors. Verify with test 8.1.
- [ ] 8.3 Extend `tests/test_web_profile_embedding.py`: `GET /v1/embedding-providers` lists registered providers with availability and the server default; `POST /v1/embedding-providers/{provider}/check` returns `{ok, dimensions, norm, reason}`; `PUT /v1/profiles/{id}/embedding` saves an unlocked change with the checked size, returns 409 `embedding_locked` with the blocking collections, returns 422 when the check fails, returns 400 for a built-in profile, and allows a change back to the stamped model; `GET /v1/profiles` items include `embedding` and `embedding_lock`. Run them and see them fail.
- [ ] 8.4 Create `src/omrg/transports/api/routes/embedding.py` with the three routes (`ReadScope` for the list, `ManageScope` and `admitted(runtime)` for check and save) and register it in `src/omrg/transports/api/app.py`. Add `embedding` and `embedding_lock` to the profile list items. Verify with test 8.3.
- [ ] 8.5 Write a test that a stamp written after the model check but before the row save makes the save return 409; see it fail. Run the model check first without a lock, then hold the process-wide ingestion `write_lock` (`src/omrg/core/ingestion/_state.py:18`) only while the save runs the lock check and writes the row. Verify the test passes.
- [ ] 8.6 Add the three operations, the new profile fields and the two 409 shapes to `src/omrg/transports/api/openapi.yaml`. Verify with `uv run pytest tests/test_openapi_conformance.py`.
- [ ] 8.7 Add the new routes to `docs/guides/web-workspace.md` (API section) and the "Check model" behaviour to `docs/guides/configuration.md`. Verify that the documented request bodies match `openapi.yaml`.

## 9. Web Embed step

- [ ] 9.1 Write `web/src/api/embedding.test.ts` for `listEmbeddingProviders`, `checkEmbeddingModel` and `saveProfileEmbedding`, including the 409 and 422 shapes. Run `cd web && npm test -- embedding` and see it fail.
- [ ] 9.2 Create `web/src/api/embedding.ts` and the query and mutation hooks in `web/src/api/queries.ts` and `web/src/api/mutations.ts`. Invalidate the profile queries after a save. Verify with test 9.1.
- [ ] 9.3 Write `web/src/studio/EmbeddingModelSection.test.tsx`: a built-in profile shows the server default as read-only text; an unlocked user profile shows the provider select, the model field, "Check model" and the checked vector size; a locked profile shows exactly "Locked: papers already holds vectors made with nomic-embed-text. Create a new collection to use another model." and no controls; a not-recorded lock shows the "not recorded" text; a 409 on save shows the lock text. Run it and see it fail.
- [ ] 9.4 Create `web/src/studio/EmbeddingModelSection.tsx` and render it from `NodeInspector.tsx` (the "Step settings" section) for `embed.chunks` when the canvas shows a profile. Give the card line from `clarify-canvas-steps` the profile's effective model. Follow the `omrg-design` skill for controls. Verify with test 9.3, `npx tsc --noEmit` and `npx eslint src/studio src/api`.
- [ ] 9.5 Update `docs/guides/web-workspace.md` (Studio section) with the Embed step model control and the lock text. Verify that the text matches the component strings.

## 10. Specs and final verification

- [ ] 10.1 Run `uv run pytest tests/unit/test_embedding_provider_model_override.py tests/test_embedding_write_contract.py tests/test_vectordb_contract.py tests/test_query_embedding_cache.py tests/unit/test_engine_embedders.py tests/unit/test_engine_profile_embedding.py tests/unit/test_profile_embedding_lock.py tests/unit/test_check_embedding_model.py tests/test_web_profile_embedding.py tests/test_engine_isolation.py -v` and confirm that all pass.
- [ ] 10.2 Run `./scripts/local_ci.sh` (parallel fast suite, then the tripwire) and confirm that it passes, including `tests/test_file_size_ceiling.py` and the import-linter contracts.
- [ ] 10.3 Run `cd web && npm test && npx tsc --noEmit && npx eslint .` and confirm that all pass.
- [ ] 10.4 Run `openspec validate add-profile-embedding-model --strict`. Verify that it passes, and that the MODIFIED blocks for `engine-scoped-composition` and `query-embedding-cache` still match the baseline requirement names in `openspec/specs/`.
- [ ] 10.5 Change the ADR from task 1.1 to Accepted after the user reviews the result. Verify that `docs/adr/ADR_README.md` shows the new status.
