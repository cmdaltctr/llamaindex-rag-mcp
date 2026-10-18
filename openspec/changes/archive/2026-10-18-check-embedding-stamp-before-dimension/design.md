# Design

## Context

Both stores call `materialise_and_validate_node_embeddings` first. It embeds nodes without vectors and checks the vector shape against `get_collection_dimension`. Then they call `_check_or_stamp_identity` (Lance: `meta.py:239`; Chroma: `identity.py:254`). The ingestion graph embeds earlier, in `embed_adapter`, and the store sees the nodes at commit.

The Lance guard already has a read-only half: `_reject_conflicting_identity` (`meta.py:220`). It returns when there is no active identity, no table, or no stamp. `_check_or_stamp_identity` adds `ensure_dataset_epoch`, which writes. Chroma has no read-only half. Its `_check_or_stamp_identity` takes a collection object that `write_nodes` gets from `get_or_create_collection`, which creates the collection.

`lancedb/store.py` is at the 500-line ceiling (`tests/test_file_size_ceiling.py`).

## Goals / Non-Goals

**Goals:**
- A wrong-model write names both models, whatever the vector size.
- A refused write or source costs no embedding request.
- No write, stamp or epoch change happens in the early check.

**Non-Goals:**
- No change to the error text or type.
- No change to `upsert_precomputed`. It has no embedding step and its identity argument is already required.
- No check inside the query path. It already checks before the query.
- No new setting or route.

## Decisions

### D1. One read-only method on the store contract

Add `check_embedding_identity(collection_name, identity=None) -> None` to `VectorStore` in `base.py`. The default does nothing, so a third-party store stays instantiable, as `get_collection_dimension` does. Lance implements it with `_reject_conflicting_identity`. Chroma implements it with `_get_collection` (which does not create) and `read_stored_identity` then `_reject_identity_mismatch`.

Alternative: call the private guards from the ingestion adapter. Rejected: `core/ingestion` would reach into store internals, and Chroma's guard needs a collection object.

### D2. `write_nodes` calls the method first

Both `write_nodes` call `self.check_embedding_identity(collection_name, embedding_identity)` before `materialise_and_validate_node_embeddings`. The later `_check_or_stamp_identity` stays: it stamps legacy collections and installs the epoch, and it repeats the compare as a second line of defence. The cost of a repeated compare is one metadata read.

To keep `lancedb/store.py` at or under 500 lines, the Lance method lives in `meta.py` (the mixin that holds the other guards) and the store adds only the call line. If the call line pushes the file over, move one existing helper to `meta.py` first.

### D3. `embed_adapter` checks before it embeds

In `embed_adapter`, call `store.check_embedding_identity(work.collection, chosen)` before `prepare_source_embeddings`. `chosen` is the `embedding_identity` resource, which `commit_adapter` already reads with `optional(context, EMBEDDING_IDENTITY_RESOURCE)`. The store resource is `required(context, STORE_RESOURCE)`. A run on the server-default model has no `chosen` and the store falls back to its composed identity, which is correct.

The call runs in a worker thread, because the store call reads a table or a collection. `embed_adapter` already hops to a thread for the embedding itself, so the check joins that hop.

A stamp that appears after this check is caught by the check inside `write_nodes` at commit (D2). The race stays and is safe: it wastes one embedding, not a mixed collection.

### D4. Direct `write_nodes` callers also gain the early check

Experiment harnesses and `embed_and_write_async` call `write_nodes` with nodes that may lack vectors. D2 covers them with no change to their code.

## Risks / Trade-offs

- [One extra metadata read for each write and each source.] → Lance reads table schema metadata; Chroma reads collection metadata. Both are small next to an embedding call. Measure on the fast suite; no benchmark is needed.
- [A third-party store keeps the default no-op and the old order.] → Accepted. The commit-time check still holds, and the contract test covers the two built-in stores.
- [Chroma `_get_collection` could raise for an unreachable cloud client.] → The same call already runs inside `get_collection_dimension` on every write, so the failure mode does not change.
