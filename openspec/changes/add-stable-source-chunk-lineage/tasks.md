# Tasks: add-stable-source-chunk-lineage

> Sequencing: implement after `validate-embedding-write-contract`. Do not
> implement concurrently with `implement-native-sparse-backend-strategy`.
> This change extends the accepted ADR-048 source-state seam; it does not add a
> new identity service, registry, vector-store API, configuration switch, or
> migration framework.

## 1. Pin the lineage contract with failing tests

- [x] 1.1 Add pure deterministic tests for `source_id`: same canonical path
  across edits/collections is stable; equal bytes at different paths have
  different source IDs; the exact UTF-8/NUL/SHA-256 formula is pinned.
- [x] 1.2 Add pure deterministic tests for `chunk_id`: identical source
  version/text/index is stable, changed text or source version changes the ID,
  and repeated equal text at different indices remains distinct.
- [x] 1.3 Add node-stamping tests for the shared `SOURCE` relationship,
  `source_chunk_count`, contiguous zero-based `source_chunk_index`, unique
  `chunk_id`, retained `file_path`, and all required metadata keys.
- [x] 1.4 Capture `MetadataMode.EMBED` and LLM-visible content before and after
  lineage stamping. Assert that identity/replacement metadata changes neither.
- [x] 1.5 Add replacement regressions proving an identical forced re-ingest
  keeps stable chunk IDs, uses different attempt row IDs, preserves the old
  attempt until verification, and remains failure-safe at every existing
  injected failure point.
- [x] 1.6 Extend real ChromaDB and LanceDB contract fixtures to prove lineage
  persistence and source-scoped stale cleanup without backend-specific lineage
  code.
- [x] 1.7 Add dense, BM25, hybrid-fusion, reranker-success, and reranker-failure
  tests proving stable lineage survives every result path while internal row
  IDs remain hidden from ordinary results.
- [x] 1.8 Add listing, metadata-filter, deletion-preview, and path-deletion
  tests keyed by `source_id`, including equal-content sources at two paths.
- [x] 1.9 Replace the pre-lineage auto-migration regression with a clean-boundary
  regression: rows for the same `file_path` that lack or disagree on
  `source_id` fail before parse/embed/write, preserve existing rows, and name
  the required rebuild action. Do not scan unrelated experiment collections at
  startup.

## 2. Extend the existing source-state seam

- [x] 2.1 Add `SOURCE_ID_KEY` and `CHUNK_ID_KEY` plus deterministic
  `build_source_id` and `build_chunk_id` helpers in
  `core/ingestion/source_state.py`. Retain `source_content_hash`; do not add a
  `document_hash` alias.
- [x] 2.2 Keep source path canonicalisation consistent with the resolved
  absolute path already used by `ingest_path_async`. Share the helper with
  deletion preview/deletion rather than duplicating path rules.
- [x] 2.3 Refine the current stamping seam in `source_state.py` so stable
  lineage and attempt identity are one coherent operation (or a minimal pair
  of plain helpers in the same module). Do not introduce a service/class
  hierarchy.
- [x] 2.4 Derive `chunk_id` from `MetadataMode.NONE` text, stamp the exact
  count/index invariants, set `NodeRelationship.SOURCE` to `source_id`, and
  derive the attempt row ID from `source_id`, `source_attempt`, and `chunk_id`.
- [x] 2.5 Add all machine identity/replacement keys to both metadata exclusion
  lists before embedding.

## 3. Preserve bounded, failure-safe ingestion

- [x] 3.1 Build `source_id` once per canonical source in `pipeline.py` and pass
  it through the existing bounded per-source call chain. Do not add global
  state or settings reads.
- [x] 3.2 Move lineage/attempt stamping before `_embed_missing_nodes` in
  `replacement.py`, while preserving the post-Experiment-18 narrow mutation
  lock and per-source node lifetime.
- [x] 3.3 Select unchanged rows, candidate verification, and stale cleanup by
  shared `source_id` plus the existing version/attempt fields. Do not use
  stable `chunk_id` as a store primary key.
- [x] 3.4 Preserve the existing recovery semantics for parse, embedding,
  structural-validation, partial-write, verification, and stale-cleanup
  failures. Do not reimplement the open embedding validator.
- [x] 3.5 Detect rows for the same canonical `file_path` that lack or disagree
  on `source_id` before mutation. Fail with a rebuild instruction; do not infer,
  upgrade, or delete them in the normal ingestion path.

## 4. Expose lineage through existing core consumers

- [x] 4.1 Update `core/ingestion/loader.py` so document listing groups by
  `source_id`, includes the human-readable path, and reports the chunk count.
- [x] 4.2 Update deletion preview and `remove_document` in
  `core/ingestion/writer.py` to derive/select `source_id` through the shared
  source-state helper. Keep transports thin and public command shapes stable.
- [x] 4.3 Add stable lineage fields to dense and BM25 core result construction;
  prove fusion/reranking preserve them and ordinary public stripping removes
  only the attempt-specific row ID/diagnostics.
- [x] 4.4 Preserve existing metadata-filter syntax so `source_id`,
  `source_version`, and `chunk_id` need no special query API.
- [x] 4.5 Leave `VectorStore`, ChromaDB, LanceDB, and
  `upsert_precomputed()` contracts unchanged except for contract tests showing
  generic metadata persistence.

## 5. Document and verify

- [x] 5.1 Update `docs/guides/ingestion.md`,
  `docs/guides/architecture.md`, and `docs/guides/mcp-tools.md` with the
  identity hierarchy, ordered reconstruction example, move/copy semantics,
  and the boundary between indexed-sequence reconstruction and original-file
  recovery.
- [ ] 5.2 Correct the living `document-deletion` baseline when this change is
  archived so it names `core/ingestion/writer.py` and write-verify-delete
  replacement rather than the deleted monolith and delete-before-read flow.
- [x] 5.3 Create an ADR after implementation confirms the formulas and
  ownership. Record stable lineage versus attempt row identity, path-based
  move semantics, the fail-before-mutation incompatibility guard, and the
  deliberate absence of migration/aliases.
- [x] 5.4 Run `uv run openspec validate add-stable-source-chunk-lineage --strict`
  and `uv run openspec validate --all --strict`.
- [x] 5.5 Run the focused source-state, ingestion, replacement, deletion,
  retrieval, reranker, MCP, ChromaDB, LanceDB, import-contract, and file-size
  tests.
- [x] 5.6 Run `uv sync`, Ruff check/format, `uv run lint-imports`, and
  `uv run pytest -m "not slow" --cov=rag_mcp` at the repository coverage
  floors before the implementation commit is accepted.
