# Proposal

## Why

`add-profile-embedding-model` (ADR-081) lets a collection use its own embedding model. A write with the wrong model must fail with a message that names both models. Today it can fail with a vector-size message instead, and only after the provider has embedded the whole batch.

Both stores run the checks in this order (`core/vectordb/lancedb/store.py:217-224`, `core/vectordb/chroma/store.py:199-208`):

1. `materialise_and_validate_node_embeddings` embeds the nodes that have no vector, then checks the vector shape against the collection's size.
2. `_check_or_stamp_identity` compares the collection's model stamp.

When model B has a different vector size from the stamped model A, step 1 raises a size error and step 2 never runs. The user sees "dimension 768 does not match 1024" and not "this collection was made with A". A paid provider (OpenRouter) has also billed the batch by then.

The ingestion graph embeds earlier still. `embed_adapter` calls `prepare_source_embeddings` outside the write lock (`core/ingestion/graph_adapters.py:302-337`), and the store sees the nodes only at commit. A refused source is embedded in full before the first check can refuse it.

ADR-081 records this as a negative consequence with a follow-up. The review of `add-profile-embedding-model` rated it a warning, not a blocker, because no row is written.

## What Changes

- Both stores check the model stamp before they embed or validate vectors in `write_nodes`. The check is read-only. It does not create a collection, stamp a legacy collection or advance the generation. The existing post-embed stamp step stays, because it also stamps legacy collections.
- The `VectorStore` contract gets one read-only method that raises the identity-mismatch error for a collection and an identity. `embed_adapter` calls it before `prepare_source_embeddings`, so a refused source is never embedded.
- The error text does not change. It already names both models (`build_identity_mismatch_error`).
- A collection with no stamp, a collection that does not exist, and a store composed with no identity keep today's behaviour: the check passes.
- No new settings, routes or web changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `embedding-write-contract`: two requirements are added. One orders the stamp check before embedding and before vector-shape validation. The other moves the check ahead of provider calls in the ingestion graph.

## Impact

- `src/omrg/core/vectordb/base.py`, `identity.py`, `lancedb/meta.py`, `lancedb/store.py`, `chroma/store.py`: the new read-only check and its call in `write_nodes`. `lancedb/store.py` is at 500 lines, so the call must replace lines, not add them, or the code moves to `meta.py`.
- `src/omrg/core/ingestion/graph_adapters.py`: one call in `embed_adapter`.
- Tests: `tests/test_embedding_write_contract.py`, `tests/test_vectordb_contract.py`, ingestion graph adapter tests. `tests/test_clean_base_tripwire.py` needs a new `_BASE_EXECUTED` count and the web-case count stays the same.
- Docs: ADR-081 consequence line and `docs/guides/ingestion.md`.
- Amends the write contract of ADR-051. Needs a short ADR-051 amendment note, not a new ADR.
- No breaking change. A caller that passed before still passes.
