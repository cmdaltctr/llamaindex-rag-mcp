# Tasks: add-lancedb-vectordb-backend

## 1. Dependency and configuration

- [x] 1.1 Add `llama-index-vector-stores-lancedb` via `uv add`; confirm the resolved tree pulls `lancedb` and `pyarrow` only and no `torch`
- [x] 1.2 Add `LANCEDB_URI` (default `./lancedb`, the parent directory for LanceDB tables) to `config/__init__.py` and mirror it in `core/settings.py`; accept `VECTOR_STORE=lancedb`; document both in `.env.example`

## 2. Vector-store registry (DD3)

- [x] 2.1 Add `core/vectordb/registry.py` following `core/retrieval/registry.py`: lazy registration by `VECTOR_STORE` name, lookup returning a constructor; no `if/elif` over names, no concrete-store import at module top level
- [x] 2.2 Register `chroma` (existing) and `lancedb` (new) under their names
- [x] 2.3 Replace the `if settings.vector_store == "chroma"` branch in `compose.py:build_vector_store` with a registry lookup; unknown names raise a clear error listing registered names

## 3. LanceDB filter translation (DD2)

- [x] 3.1 Add `core/vectordb/lance_filter.py`: translate the ChromaDB `where` dict to a `lancedb.expr` expression tree (`col`, `lit`, `&`, `|`); support `$eq $ne $gt $gte $lt $lte $in $nin $and $or`; raise a clear error on any other operator; build no SQL strings by interpolation
- [x] 3.2 Support the bare-equality shorthand (`{"field": value}`) and the nested-operator form (`{"field": {"$gt": value}}`)

## 4. LanceDB paged reads (DD4)

- [x] 4.1 Add `core/vectordb/lance_paged.py` mixin: `iter_metadatas`, `iter_documents` (bounded pages via the scanner `limit`/`offset`), `fetch_all` (full scan via `to_pandas`/scanner), returning the same store-neutral shapes the ABC docstrings specify

## 5. LanceDB store (DD1, DD4, DD5)

- [x] 5.1 Add `core/vectordb/lancedb.py` `LanceVectorStore(VectorStore)` holding one `lancedb.connect(uri)`; implement collection lifecycle (`create_collection` lazy, `collection_exists`, `delete_collection`, `list_collections`) mapping collection to table
- [x] 5.2 Implement `write_nodes` via a per-table `LanceDBVectorStore(connection=conn, table_name=name)` fed to `VectorStoreIndex`; implement `upsert_precomputed` via `table.add()`/`merge_insert`
- [x] 5.3 Implement `query_dense` (vector search + translated filter), `count`, `count_where`, `delete_where`
- [x] 5.4 Implement embedding-identity and profile metadata via table `update_config` read-merge-write; port the legacy-stamp-then-reject rule from `identity.py` behind a small store-supplied accessor (do not depend on a ChromaDB collection handle). If `update_config` proves unsuitable, fall back to `replace_schema_metadata`
- [x] 5.5 Implement `bump_generation`/`get_generation` on the same process-local dict contract the ChromaDB store owns
- [x] 5.6 Keep every new file under 500 lines (invariant #11); split further if needed

## 6. Tests

- [x] 6.1 Parametrise the shared `VectorStore` contract tests to run against both ChromaDB and LanceDB; assert create-then-write, write-without-create, and dimension-lock-on-first-write parity
- [x] 6.2 `lance_filter.py` unit tests: one assertion per supported operator mapping, a boolean-composition case, an injection case (single-quote value stays a literal), and an unknown-operator rejection
- [x] 6.3 Identity/profile config round-trip test: write, reopen the connection, assert values survive; mismatch-rejection and legacy-stamp tests mirroring the ChromaDB identity tests
- [x] 6.4 Hybrid-retrieval test over a LanceDB collection: BM25 index builds from `iter_documents`, and a write/delete advances the generation counter
- [x] 6.5 Single-import-site test: `import lancedb` appears only under `core/vectordb/`; base-path import test asserting no `torch`
- [x] 6.6 Registry tests: registered names resolve, unknown name fails with a listing, no `if/elif` over names in the dispatch path

## 7. Documentation and validation

- [x] 7.1 Update `docs/guides/architecture.md` and `docs/guides/configuration.md` for the second backend, `VECTOR_STORE=lancedb`, and `LANCEDB_URI`; note the deferred native-FTS/hybrid path and the LanceDB-Cloud-out-of-scope decision
- [x] 7.2 Run `openspec validate add-lancedb-vectordb-backend --strict` and `uv run pytest -m "not slow" --cov=rag_mcp`; record the ADR for the LanceDB backend decision under `docs/adr/`
