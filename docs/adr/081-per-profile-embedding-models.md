# ADR-081: Per-Profile Embedding Models

- **Date:** 2026-10-17
- **Status:** Accepted (2026-10-18, after review)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-051](051-fail-closed-embedding-write-contract.md) (write contract), [ADR-053](053-embedding-norm-guard.md) (norm guard), [ADR-061](061-engine-scoped-embedding-provider.md) (engine-scoped embedder), [ADR-080](080-profiles-own-pipelines.md) (profiles own pipelines)
- **Change:** `openspec/changes/add-profile-embedding-model/` (design D1 to D13)

## Context

One embedder served the whole Engine. Its model came from `.env`. Every
collection used it. A user could not choose a model for one use case, such as a
larger model for papers, without changing the model for all collections.

The stores already refuse a vector from a model other than the one stamped on a
collection. The CLAUDE.md rule "Ask before mixing embedding models" exists
because ChromaDB and LanceDB fix the vector size per collection.

## Decision

The user approved this feature on 2026-10-16.

1. **The model is a profile column (D1, D2).** The workspace `profiles` table
   (schema version 4) gains `embed_provider`, `embed_model` and
   `embed_dimensions`. Empty means "server default". Built-in profiles always
   use the server default. Graph levers still cannot set the model.
2. **The identity travels with the embedder (D3, D4).** The pair
   (provider, model) is an `EmbeddingIdentity`. `write_nodes`, `query_dense`
   and `query_native_sparse` take an optional `embedding_identity` that
   replaces the composed identity for that call.
3. **The Engine owns an embedder set keyed by (provider, model) (D5, D6).**
   `Engine._embedding_for(collection)` asks the profile resolver. Ingest,
   search, answer and graph runs all use the result. Two Engines never share
   embedders. `close()` releases the set.
4. **One model per collection (D7, D9).** A profile can change its model only
   when no bound collection has rows or a stamp for another model. Rows
   without a stamp always block, and the message says "not recorded".
5. **Binding refusal (D7).** A collection cannot follow a profile whose model
   differs from the collection's stamp. The check runs in the preview and in
   the confirm step. It applies to built-in profiles too, because they use the
   server default model. The web route and the MCP endpoint of `omrg web`
   both run it through `ProfileService.check_binding`.
   The stdio MCP server has no profile service and skips the check. It can
   only bind built-in profiles. A stamped collection that it binds to the
   wrong model still fails closed at the first query, through the store's
   stamp guard (ADR-051). See TDR-035.
6. **Check before save (D8).** "Check model" embeds one probe text and measures
   vector size and length. For `llamacpp` it also requires the model name in
   the server model list, because llama-server ignores the `model` field. Save
   runs the same check. `PUT /v1/profiles/{id}/embedding` takes the provider
   and the model together, or neither (server default). One without the other
   returns 400, so the profile never holds a half choice.
7. **The query cache key includes provider and model (D12).**

This ADR narrows the CLAUDE.md rule "Ask before mixing embedding models". It
does not remove it: a collection still holds vectors from exactly one model,
and the lock, binding refusal and check enforce that in code.

## Consequences

### Positive

- A user picks a model per use case in the web app.
- A mismatch fails closed in every path, with a message that names both models.

### Negative

- Extra keyword plumbing through ingestion and retrieval (default `None`
  keeps current callers unchanged).
- Changing a model needs a new collection and a new ingest.
- Fixed by `check-embedding-stamp-before-dimension`: the stores now check the
  model stamp before they embed or check vector shape, and the ingestion graph
  checks it before `embed.chunks`. A write with another model gets the
  model-mismatch error that names both models, whatever the vector size, and
  the embedder receives no text. Before this change a model of a different size
  got a dimension error after the batch was embedded. No row was written.

### Neutral

- Connection settings (URLs, keys) stay in `.env`. There is no model catalogue.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| A node parameter on `embed.chunks` | Ingest and search must use one model, and a node parameter lives in one slot graph only. |
| Put the choice into `EffectiveSettings` | The object is frozen and shared; slot graphs resolve settings from the base profile and would lose the overlay. |
| A store view per identity | Splits the BM25 cache identity and can open a second ChromaDB client. |
| A process-wide embedder cache | `engine-scoped-composition` requires that two Engines never share embedders. |
