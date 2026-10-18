# Tasks

## 1. Store contract and both backends

- [x] 1.1 Add tests to `tests/test_embedding_write_contract.py` for ChromaDB and LanceDB: a collection stamped A and a store or call that uses model B of another vector size raises the identity-mismatch error naming A and B (not a size error), the embedder is never called, no row persists and the generation does not advance. Repeat with model B of the same size. Run them and see the different-size case fail.
- [x] 1.2 Add tests for the passing cases to the same file: a legacy collection with rows and no stamp is stamped after the write, an absent collection is not created by the early check, and a matching stamp writes. Run them. They should already pass; confirm that each one fails if the early check creates, stamps or advances.
- [x] 1.3 Add `check_embedding_identity(collection_name, identity=None)` to `VectorStore` in `src/omrg/core/vectordb/base.py` with a no-op default and a docstring that states it is read-only. Verify that `tests/test_vectordb_contract.py` still collects.
- [x] 1.4 Implement the method for LanceDB in `src/omrg/core/vectordb/lancedb/meta.py` with `_reject_conflicting_identity`, and for ChromaDB in `src/omrg/core/vectordb/chroma/store.py` with `_get_collection`, `read_stored_identity` and `_reject_identity_mismatch`. Verify that it creates nothing for an absent collection.
- [x] 1.5 Call the method first in `write_nodes` of `lancedb/store.py` and `chroma/store.py`, before `materialise_and_validate_node_embeddings`. Verify that tests 1.1 and 1.2 pass and `tests/test_file_size_ceiling.py` passes (`lancedb/store.py` stays at or under 500 lines).

## 2. Ingestion graph

- [x] 2.1 Add tests to `tests/unit/test_graph_profile_embedding.py` or the ingestion adapter tests: a source bound for a collection stamped A, run with model B, fails at `embed.chunks` with the mismatch error and the fake embedder receives no text; an absent collection is embedded; a stamp written between `embed.chunks` and the commit is still refused at commit. Run them and see the first fail.
- [x] 2.2 In `embed_adapter` (`src/omrg/core/ingestion/graph_adapters.py`), call `store.check_embedding_identity(work.collection, chosen)` in the worker thread before `prepare_source_embeddings`. Verify that tests 2.1 pass and the file stays under 500 lines.

## 3. Documents and gates

- [x] 3.1 Update the negative consequence in `docs/adr/081-per-profile-embedding-models.md` (the "stores check vector shape before the model stamp" line) to say it is fixed by this change. Add a short amendment note to `docs/adr/051-fail-closed-embedding-write-contract.md`. Verify the two ADR index rows in `docs/adr/ADR_README.md`.
- [x] 3.2 Update `docs/guides/ingestion.md`: a refused source is not embedded. Grep `docs/guides/` for "dimension error" wording that this change makes false.
- [x] 3.3 Re-baseline `_BASE_EXECUTED` in `tests/test_clean_base_tripwire.py` with a dated comment. Measure the count in a base venv, with and without the `web` extra, as the previous change did. Verify that the tripwire passes in both.
- [x] 3.4 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`, `uv run lint-imports`, `uv run ruff check`, `uv run ruff format --check` and `openspec validate check-embedding-stamp-before-dimension --strict`. Then run `./scripts/local_ci.sh`. Verify that all pass.
