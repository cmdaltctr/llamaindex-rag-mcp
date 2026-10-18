# Design

## Context

See proposal.md, Why. This section lists only the facts that shape the approach.

**Embedder today.** `compose.build_embed_model(settings)` resolves the provider and calls the registry builder (`src/omrg/compose.py:49-66`). `build_engine` calls it once and gives the result to `Engine` (`src/omrg/compose_engine.py:122,148-152`). The Engine passes that one embedder to `ingest_path_async`, `search`, `answer` and the graph host (`src/omrg/engine.py:162,201,267,444`). The graph step `embed.chunks` reads it as the `embedder` resource (`src/omrg/core/ingestion/graph_adapters.py:320`). Each provider builder reads its model from one `Settings` field: `embed_model` (Ollama), `llamacpp_embed_model`, `openrouter_embed_model` (`src/omrg/core/providers/embeddings/{ollama,llamacpp,openrouter}.py`). The registry lists providers only (`registry.py:75-77`). No model catalogue exists.

**Identity today.** Paths below use the folders of `organise-backend-folders`, which lands first; line numbers are from before the move. The store gets one `EmbeddingIdentity` at construction (`src/omrg/core/vectordb/chroma/store.py:476`, `embedding_identity_from_settings` in `identity.py:47-76`). The write path checks and stamps with it (`identity.py:233-241`; Chroma `chroma/store.py:204`; LanceDB `lancedb/store.py:225`, stamp after the write in `lancedb/meta.py` `_flush_after_write`). The query paths refuse a different stamp (`chroma/store.py:277`, `lancedb/store.py:346`, `lancedb/fts.py:175`). Graph preflight compares the host identity with each bound collection's stamp (`src/omrg/core/pipelines/validation.py:226-243`). `StoreCollectionView.embedding_identity` hides the provider alias problem: it returns the host reference when the stamp equals the store identity (`src/omrg/compose_pipelines.py:98-112`), because `host_embedding` uses `settings.embed_provider`, which can be the alias `local` (`compose_pipelines.py:74-79`). The dense graph step builds its reference the same way (`src/omrg/core/retrieval/graph_adapters_retrieve.py:157-159`).

**Query side today.** Every query embedding goes through `_embed_query` in `src/omrg/core/retrieval/dense.py:64-109`. The Engine cache key is `(prepared_query, model_name)` (`dense.py:95`). Callers: `core/retrieval/pipeline.py:76,308` (direct search), `core/answer/retriever.py` (answer, through `search`), and `graph_adapters_retrieve.py:170-181` (graph `retrieve.dense`, no cache). Native sparse queries call `store.query_native_sparse` (`core/retrieval/native_sparse.py:60`), which also runs the identity guard on LanceDB.

**Vector size today.** Both stores report the fixed size through `get_collection_dimension` (`chroma/store.py:167-173`, `lancedb/store.py:189-195`). The write contract refuses a batch whose size differs (`openspec/specs/embedding-write-contract`). A ChromaDB collection keeps its size after all rows are deleted. A LanceDB table keeps its Arrow vector width in the schema.

**Constraints.** `engine.py` has 498 lines and the ceiling is 500 (`tests/test_file_size_ceiling.py`). Providers are built only in `compose` (import-linter contract `providers-constructed-only-in-compose`, `pyproject.toml:205`). Settings are injected (ADR-037). `EMBEDDING_PROVIDER_SCOPE = "engine"` (`compose.py:36`). `unify-profiles-and-pipelines` adds the `profiles` table (workspace schema version 3), `core/profiles/catalogue.py`, `engine_profiles.py` and `transports/api/routes/profiles.py`, and runs user profiles through their slot graphs.

## Goals / Non-Goals

**Goals:**

- One embedding model per collection, chosen by the collection's profile, used by every operation on that collection.
- Fail closed. A model that differs from a collection's stamp never writes to it and never queries it.
- A plain explanation in the web app when the model is locked.

**Non-Goals:**

- A catalogue or picker of embedding models. Listing Ollama models is recorded as later work.
- Moving existing vectors to another model. The user creates a new collection and ingests again.
- Per-profile provider URLs or API keys. Connection settings stay in `.env`.
- MCP or CLI commands to change a profile's model.
- Changing `upsert_precomputed` (experiment harnesses). It keeps the store identity for its guard.

## Decisions

### D1. The model choice is a profile column, not a graph lever

Add three nullable columns to `profiles`: `embed_provider`, `embed_model`, `embed_dimensions`. A CHECK keeps provider and model both set or both empty. Empty means "server default". The `profiles` row is the single place; the Embed step reads and writes it through the API. `_HOST_OWNED_EXACT` (`levers.py:86-104`) stays unchanged, so graphs still cannot set `embed_model` or `embed_provider`. The host-owned message (`levers.py:131-136`) gets a hint for these two paths: "Set the model on the profile's Embed step."

- *Alternative: a node parameter on `embed.chunks`.* Rejected. Ingest and search must use the same model, and a node parameter lives in one slot graph only.
- *Alternative: pin the server default into every new user profile.* Rejected for now. It needs the host model at migration time, which the SQL migration does not know. An empty choice keeps today's built-in behaviour: an `.env` change makes stamped collections fail closed with the mismatch message.

### D2. Built-in profiles always use the server default

Built-in YAML gets no model field. `PUT /v1/profiles/documents/embedding` returns 400 with "Duplicate the profile to choose another model."

### D3. The identity is `EmbeddingIdentity`, carried beside the embedder

The pair (provider, model) uses the existing `EmbeddingIdentity` with `index_identity=None`. The provider is always concrete (`ollama`, `llamacpp`, `openrouter`), never the alias `local` or `cloud`. The Engine resolves one pair per operation and passes the embedder and its identity down the same call chain that `embed_model` uses today. The new keyword is `embedding_identity`. It reaches `store.write_nodes`, `store.query_dense` and `store.query_native_sparse`.

- *Alternative: put the choice into `EffectiveSettings`.* Rejected. `EffectiveSettings` is frozen and shared by many readers. Under `unify-profiles-and-pipelines` D8, slot graphs resolve settings from the base built-in profile, so the overlay would be lost in graph runs.
- *Alternative: a store view per identity (shallow copy with another `_identity`).* Rejected. It splits the BM25 cache identity (`base.py:24-27`), can open a second ChromaDB client on the same path, and hides the routing.

### D4. Stores check and stamp the identity they receive

The guard methods take an optional identity. When the call supplies one, it replaces the composed `_identity` for that call (`identity.py:233-265`, `lancedb/meta.py:207-252`). When the call supplies none, today's behaviour stays. Chroma `write_nodes` also uses it for the validator diagnostic (`chroma/store.py:191-194`). LanceDB stamps it after the write. Only `write_nodes`, `query_dense` and `query_native_sparse` change.

### D5. The Engine owns an embedder set keyed by (provider, model)

A new module `src/omrg/engine_embedders.py` holds `EngineEmbedders`. It holds a dict from (provider, model) to embedder, a `threading.Lock` (ingest calls embedders from worker threads), the host identity, and a factory from `compose`. The host embedder is the first entry, so the host key returns the same instance as today. Other entries are built on first use. `Engine.close()` calls `release()`, which clears the dict, as ADR-061 requires for the host embedder. The set has no size limit, because entries exist only for models that profiles name.

The factory lives in `compose_engine.py`: `lambda provider, model: embed_registry.get(provider)(settings, model=model)`. Each provider `build` gets a keyword `model: str | None = None`. When it is set, it replaces the `Settings` model field. URLs, keys and batch size still come from `Settings`.

- *Alternative: a process-wide cache.* Rejected. `engine-scoped-composition` requires that two Engines never share embedders.
- *Alternative: copy `Settings` with the model field replaced.* Rejected. It needs a provider-to-field map in a third place (`identity.py:70-74` and `core/providers/common.py:24-35` already hold one).

### D6. The Engine resolves the identity from the collection's profile

`Engine._embedding_for(collection)` asks the profile resolver for the choice. The resolver reads the collection's profile tag. A built-in profile, a missing tag or an empty choice returns `None`, and the Engine uses the host identity. A user profile with a choice returns that identity from the catalogue (`core/profiles/catalogue.py`, from `unify-profiles-and-pipelines` D11). `ingest`, `search`, `answer` and `_graph_host(collection)` all call it. This keeps the rule in one place, also when a transport calls the direct path for a user-profile collection.

`_graph_host` puts the chosen embedder in the `embedder` resource and adds an `embedding_identity` resource. `host_embedding` builds `EmbeddingRef` from the concrete identity. `StoreCollectionView` compares stamps with that identity, which removes the alias workaround. `retrieve.dense` and `commit.source` read the `embedding_identity` resource instead of `context.settings.embed_provider`.

### D7. Lock and binding checks are pure functions in `core/profiles/embedding_lock.py`

`collection_embedding_state(store, name)` returns the stamp (from `get_collection_metadata`, which both stores support) and the row count. `blocking_collections(states, requested)` returns the collections that block a change. A collection blocks when it has rows or a stamp, and its stamp does not equal the requested identity. Rows without a stamp always block, because the store stamps an unstamped collection on its next write (`identity.py:238-240`), and that would mix vectors. `binding_refusal(state, profile_identity, host_identity)` applies the binding rule. These functions do not use `StoreCollectionView`, because that view reports no stamp when the store has no identity (`compose_pipelines.py:103-105`).

`PUT /v1/profiles/{profile_id}/embedding` runs the model check first, without a lock, because the probe is a network call. It then holds the process-wide ingestion `write_lock` (`src/omrg/core/ingestion/_state.py:18`) while it runs the lock check and writes the row. Every store write takes that lock (`commit.py:194`), so no new stamp can appear between the lock check and the save. `PATCH /v1/collections/{collection}/profile` runs `binding_refusal` in the preview and again in the confirm step, before `apply_profile_change`. A separate function keeps this change away from the edits that `unify-profiles-and-pipelines` makes to `core/profiles/contract.py`.

### D8. "Check model" embeds one probe text

`compose.check_embedding_model(provider, model)` is the composition-root surface (transports may not call `get_settings()`). It:

1. Refuses an unregistered provider (404) and reports a missing extra from the registry `ImportError` (`registry.py:51-63`).
2. For `llamacpp` only, reads `GET {LLAMACPP_EMBED_URL}/models` and requires an `id` equal to the model name or to its file name. llama-server ignores the `model` field of an embedding request, so without this check two names could produce the same vectors under different stamps.
3. Builds a throwaway embedder (not added to the Engine set), embeds `"OMRG model check"`, and measures size and L2 length.
4. Fails when the length is outside `EMBEDDING__NORM_TOLERANCE` and the norm guard is on, because ingestion would refuse these vectors (`openspec/specs/embedding-norm-guard`).

Errors pass through `engine.redact`. The route uses `ManageScope` and `admitted(runtime)`, like `testConnection` (`transports/api/routes/connections.py:43-55`). Save runs the same check, so a client cannot skip it.

- *Alternative: check membership for every provider.* Rejected. Ollama and OpenRouter honour the name and fail at the probe. The OpenRouter model list does not clearly cover embedding models.

### D9. A new vector size reaches only collections without vectors

The lock rule already allows a change only when each bound collection has no stamp and no rows. The first write then fixes the size and the stamp. `embed_dimensions` stores the size from the last passing check, so the web can show "Vector size: 768".

### D10. API shape

- `GET /v1/embedding-providers` returns `{providers: [{name, available, reason}], server_default: {provider, model}}`.
- `POST /v1/embedding-providers/{provider}/check` with `{model}` returns `{ok, dimensions, norm, reason}`.
- `PUT /v1/profiles/{profile_id}/embedding` with `{provider, model}` or `{provider: null, model: null}` returns the profile. A lock refusal is 409 with `error_type: "embedding_locked"` and `collections: [{collection, provider, model, chunk_count}]`. A failed check is 422 with the reason.
- `GET /v1/profiles` items gain `embedding: {provider, model, source, dimensions}` and `embedding_lock: {locked, collections}`. `source` is `profile` or `server_default`.
- `PATCH /v1/collections/{collection}/profile` gains a 409 with `error_type: "embedding_mismatch"`.

The three new routes go in `src/omrg/transports/api/routes/embedding.py`, so `routes/admin.py` and the new `routes/profiles.py` do not grow.

### D11. Web: one section in the Embed step inspector

A new `web/src/studio/EmbeddingModelSection.tsx` renders inside `NodeInspector.tsx` when the node operation is `embed.chunks` and the canvas shows a profile. It reads the profile from the profile query that `studio-profiles-gallery` adds. It shows read-only text for built-ins, the lock text when `embedding_lock.locked` is true, and otherwise a provider select, a model field, "Check model", the result and "Save model". The lock text names the first blocking collection: "Locked: <collection> already holds vectors made with <model>. Create a new collection to use another model." When the model is not recorded, the text is: "Locked: <collection> already holds vectors, but the model that made them is not recorded. Create a new collection to use another model." `clarify-canvas-steps` owns the card line "Model: …". For a user profile, this change gives that line the profile's effective model instead of the host model. The section sits in the panel section "Step settings" (renamed from "Node settings" by `studio-profiles-gallery`).

### D12. Spec placement

- `embedding-write-contract`: one MODIFIED requirement ("Shared structural embedding validation") and one ADDED requirement. This change owns the capability.
- `profile-embedding-model`: new capability.
- `query-embedding-cache`: one MODIFIED requirement. "Query embedding cache reduces repeat Ollama calls" now states the full key, `(embedding_provider, embedding_model, prepared_query)`, in one text. The three model scenarios move into it, and the earlier ADDED requirement "Two embedding models never share a cache entry" is gone, because it repeated the key.
- `engine-scoped-composition`: one MODIFIED requirement and one ADDED requirement. "Embedding-provider selection is engine scoped" keeps its full baseline text and every scenario. Only the last line of the scenario "Different engines may target different providers" changes: it said "profile-driven provider routing inside one Engine SHALL remain out of scope", and now points to the ADDED requirement "One Engine routes embedding models by collection profile".

No other active change modifies `query-embedding-cache` or `engine-scoped-composition` (checked in `openspec/changes/*/specs/` on 2026-10-16), so this change can modify them.

- Alternative: ADDED requirements only, with the out-of-scope line deleted by hand at archive time. Rejected: the main spec would contradict this change until archive, and a hand edit can be forgotten.
- Alternative: keep the cache key in an ADDED requirement beside the old one. Rejected: two texts would state two different keys.

### D13. Order and decision record

This change lands after `organise-backend-folders` and `unify-profiles-and-pipelines`. Backend paths therefore use the new folders: `core/vectordb/chroma/store.py`, `core/vectordb/lancedb/store.py`, `core/vectordb/lancedb/meta.py`, `core/vectordb/lancedb/fts.py` and `transports/api/routes/`. The decision record is ADR-081. `unify-profiles-and-pipelines` takes ADR-080. No other change in this group plans an ADR.

## Risks / Trade-offs

- [An ingest that started before the change has already embedded with the old model. It writes and stamps the old model after the save.] → The `write_lock` stops a stamp between check and save, but it cannot stop this later write. Every later operation then fails closed with the mismatch message, so no vectors mix. Recovery: set the profile's model back to the stamped model on the Embed step. The lock rule allows a change back to the stamped model, so this takes one save. To use the new model, create a new collection and ingest into it.
- [The operator changes `EMBED_*` in `.env`. Collections whose profile uses the server default stop working.] → This is today's behaviour for built-in profiles. The mismatch message names both models. Recovery: restore the earlier `EMBED_*` values and restart. The guide tells users to choose an explicit model in a user profile to avoid it.
- [llama-server serves one model. A profile that names another llama.cpp model fails the check.] → This is the intended safety result. The reason lists the names that the server serves. Router mode servers that list several models pass.
- [Two embedders stay in memory per extra model.] → Remote providers hold only HTTP clients. The Engine releases them on close.
- [A crash between a LanceDB write and its post-write stamp leaves rows without a stamp.] → The lock rule treats rows without a stamp as locked, with "not recorded".
- [More keyword plumbing through ingestion and retrieval.] → The new keyword follows the existing `embed_model` path one for one. The default `None` keeps every current caller unchanged.
- [`engine.py` is at 498 lines.] → Embedder code goes to `engine_embedders.py`. The Engine keeps only one call per operation.

## Migration Plan

1. Workspace schema version 4 adds the three nullable columns. Existing profiles get empty values, which means "server default". The existing migration code backs up the database first.
2. No vector data changes. No re-ingest is needed.
3. Rollback: version 3 code refuses a version 4 database (`schema.py:211-214`). Restore the `*.v3-to-v4.*.bak` file that the migration made (`schema.py:175-185`). Collections stamped by a profile model then fail closed under the server default until the user creates a new collection or restores the version 4 code.

## Open Questions

None. The earlier questions are decisions in D12: this change modifies the `engine-scoped-composition` and `query-embedding-cache` requirements directly. The race between a running ingest and a model change stays a recorded risk with its recovery step (Risks, first item).
