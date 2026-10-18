# Proposal

## Why

Today one Engine has one embedding model. `compose.build_embed_model` builds it once (`src/omrg/compose.py:49`, `src/omrg/compose_engine.py:122`). Every ingest, search, answer and graph run then uses that model (`src/omrg/engine.py:162,201,267,444`). A user profile cannot choose a different model.

The user wants each user profile to choose its embedding model on the Embed step. The model must stay locked once a collection that uses the profile holds vectors, because vectors from two models must never mix in one collection. The repository rule says "Ask before mixing embedding models (ChromaDB locks dims)". The user has asked for this feature. This change keeps one model per collection and makes the safety rules explicit.

This change depends on `unify-profiles-and-pipelines`. That change adds the user profile record and `GET /v1/profiles` with `used_by`. This change also lands after `organise-backend-folders`, so its backend paths use the new folders (`core/vectordb/chroma/`, `core/vectordb/lancedb/`, `transports/api/routes/`).

## What Changes

- A user profile stores an embedding choice: a provider from the provider registry and a model name. An empty choice means "server default" (the `EMBED_*` settings). Built-in profiles (`documents`, `codebase`) always use the server default. Graph node parameters and graph overrides still cannot set the model (`src/omrg/core/pipelines/levers.py:86-104` stays unchanged).
- The Engine keeps a small set of embedders, one for each (provider, model) pair. The server default embedder is the first entry. The Engine builds other entries on first use and releases all of them when it closes. Two Engines never share an entry.
- Every operation on a collection uses the model of the collection's profile. This covers ingest, search, answer, graph runs and graph preflight. Queries are embedded with the collection's model, not the server model.
- The store stamps and checks the identity of the embedder that the operation uses. Today it uses one identity that it gets at construction (`src/omrg/core/vectordb/chroma/store.py:476`).
- The query embedding cache key includes the provider and the model.
- Lock rule: the API refuses a model change when a bound collection holds vectors (it has a stamp, or it has rows). The refusal names each collection and the model that made its vectors. A change back to the stamped model is allowed.
- Binding rule: the API refuses to bind a profile to a collection when the collection's stamp names another model.
- "Check model": the API embeds a short probe text with the chosen model. It records the vector size and checks that the vector has unit length. For llama.cpp it first confirms that the server lists the model, because llama.cpp ignores the model name that a request sends.
- Web: the Embed step shows the model. It shows a provider list, a model field and a "Check model" button when the model can change. When the model is locked, it shows: "Locked: <collection> already holds vectors made with <model>. Create a new collection to use another model."
- New routes: `GET /v1/embedding-providers`, `POST /v1/embedding-providers/{provider}/check`, `PUT /v1/profiles/{profile_id}/embedding`.
- ADR-081 records the decision and the safety rules. `unify-profiles-and-pipelines` takes ADR-080.

## Capabilities

### New Capabilities

- `profile-embedding-model`: how a profile chooses its embedding model, how every operation on a collection uses that model, the lock and binding rules, the "Check model" probe, the Engine's embedder set, and the Embed step display.

### Modified Capabilities

- `embedding-write-contract`: "Shared structural embedding validation" changes. `write_nodes` uses the identity of the embedder that produced the batch, not only the identity the store got at construction. One ADDED requirement: the write stamp follows the embedder used.
- `query-embedding-cache`: one MODIFIED requirement. "Query embedding cache reduces repeat Ollama calls" states the full cache key (provider, model, prepared query) in one text, so two models never share an entry, also when their model names are equal.
- `engine-scoped-composition`: one MODIFIED requirement and one ADDED requirement. "Embedding-provider selection is engine scoped" drops the line that kept profile-driven routing inside one Engine out of scope. The ADDED requirement says that one Engine routes embedding models by collection profile.

## Impact

- **Python code:** `src/omrg/engine.py` (at 498 lines, so embedder code moves to a new `src/omrg/engine_embedders.py`), `src/omrg/compose.py`, `src/omrg/compose_engine.py`, `src/omrg/compose_pipelines.py`, `src/omrg/core/providers/embeddings/{ollama,llamacpp,openrouter}.py`, `src/omrg/core/vectordb/{identity,base}.py`, `src/omrg/core/vectordb/chroma/store.py`, `src/omrg/core/vectordb/lancedb/{store,meta,fts}.py`, `src/omrg/core/ingestion/{pipeline,sources,replacement,commit,graph_adapters}.py`, `src/omrg/core/retrieval/{pipeline,dense,native_sparse,graph_adapters_retrieve}.py`, `src/omrg/core/answer/{pipeline,retriever}.py`, `src/omrg/core/profiles/` (new `embedding_lock.py`, and the `catalogue.py` that `unify-profiles-and-pipelines` adds), `src/omrg/integrations/workspace_sqlite/{schema,profiles}.py` (schema version 4 adds three nullable columns to the `profiles` table).
- **API:** three new routes in a new `src/omrg/transports/api/routes/embedding.py`. `GET /v1/profiles` items get `embedding` and `embedding_lock` fields. `PATCH /v1/collections/{collection}/profile` can return a new 409 refusal. `src/omrg/transports/api/openapi.yaml` changes.
- **Web:** the Embed step inspector in `web/src/studio/` and a new `web/src/api/embedding.ts`. The web tasks start after `feat/studio-canvas-layout` merges.
- **Docs:** `docs/guides/configuration.md` (the section that says one model per process is stale), `docs/guides/pipelines.md`, a new ADR in `docs/adr/`.
- **No new dependencies.** MCP and CLI tools do not get new commands.
