# Evidence: ingestion seams (tasks 3.3 and 3.4, extraction part)

Date: 2026-10-13. Branch: `feat/add-local-web-pipeline-workspace`.
Command prefix for every run below:

```bash
PATH=/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3/.venv/bin:$PATH \
  PYTHONPATH=src PDF_READER=pypdf python -m pytest -q -p no:cacheprovider <files>
```

## Scope

- 3.3: source preparation, read, normalise, enrich, and split seams. `ingest_path_async` keeps its signature, its result shape, and its per-file failure handling. It calls the same seams.
- 3.4 (extraction only): embedding preparation and protected commit are separate callable seams. Graph adapters are not built. `core.pipelines` is not imported.

## Seams

| Stage | Function | Module |
| --- | --- | --- |
| Discovery (existing) | `gather_supported_files(path, extensions=...)` | `core/ingestion/loader.py` |
| Content types | `detect_content_types(root, *, settings) -> dict[str, str]` | `core/ingestion/sources.py` |
| Bounded units | `iter_source_units(root, files, content_types) -> Iterator[SourceUnit]` | `sources.py` |
| Operation context | `build_ingestion_context(settings, *, chunk_size=None, chunk_overlap=None, markdown_chunking=None, embed_model=None, ocr_client=None) -> IngestionContext` | `sources.py` |
| Source identity | `async prepare_source(file_path, *, content_type, context, text_format_resolver=...) -> SourceIdentity` | `sources.py` |
| Compatibility and reuse | `async check_source_state(identity, *, store, collection_name, lineage_guard=..., completeness_check=...) -> SourceReuse(unchanged, existing_chunks)` | `sources.py` |
| Read to chunks (composite) | `async chunk_source(identity, *, context, store, ocr_client=None, chunker=...) -> list` | `sources.py` |
| Code/config dispatch | `async chunk_specialised_source(file_path, *, content_type, fallback_strategy, chunk_size, chunk_overlap, settings) -> list or None` | `core/ingestion/chunker.py` |
| Read (existing) | `async read_document(file_path, *, settings, ocr_client=None) -> BackendRead` | `backends/orchestrator.py` |
| Normalise | `normalise_backend_read(backend_read, file_path, *, content_type, settings) -> BackendRead` | `chunker.py` |
| Markdown declaration | `declares_markdown(file_path, backend_read) -> bool` | `chunker.py` |
| Enrich | `async enrich_documents(documents, file_path, *, content_type, taxonomy_mode, settings, store) -> (dict, bool)` | `chunker.py` |
| Split | `async split_documents(documents, file_path, *, structured, is_markdown, chunk_size, chunk_overlap, content_type, settings, markdown_chunking=None, doc_metadata=None) -> list` | `chunker.py` |
| Embed and commit (composite) | `async commit_source(nodes, identity, *, context, store, collection_name, progress_callback=None, replacer=...) -> ReplaceSourceOutcome` | `sources.py` |
| Embedding preparation | `prepare_source_embeddings(nodes, *, file_path, source_id, content_hash, index_identity, source_version, source_attempt, embed_model=None, embed_concurrency=2, norm_guard_enabled=True, norm_tolerance=0.001) -> PreparedSource` | `core/ingestion/replacement.py` |
| Protected commit | `commit_prepared_source(nodes, prepared, *, collection_name, store, embed_model=None) -> ReplaceSourceOutcome` | `core/ingestion/commit.py` |

Notes:

- `enrich_documents` has no default for `settings` or `store`. If you omit one, the call fails with `TypeError`.
- `commit_prepared_source` requires `store`. Before it takes the write lock, it checks node count, `source_id`, `source_attempt`, chunk count, chunk index order, and prepared embeddings. A mismatch raises `IngestionStageError("lineage")` and makes no mutation. The write, verification, and stale cleanup stay one locked operation.
- `read_and_chunk_file_async` now composes `chunk_specialised_source`, `read_document`, `normalise_backend_read`, `declares_markdown`, `enrich_documents`, and `split_documents`.
- `replace_source_nodes_async` now composes `prepare_source_embeddings` and `commit_prepared_source`. It keeps the same signature, the same shutdown checks, and the same progress callbacks.
- `ingest_path_async` passes this module's own bindings into the `*_resolver`, `lineage_guard`, `completeness_check`, `chunker`, and `replacer` keywords. These are `resolve_declared_text_format`, `assert_source_lineage_compatible`, `is_complete_current_version`, `read_and_chunk_file_async`, and `replace_source_nodes_async`. Existing tests monkeypatch these names on `core.ingestion.pipeline`, and those patches still take effect. Graph adapters omit the keywords and get the same functions.
- `commit.py` holds `WriteTimings`, `ReplaceSourceOutcome`, `IngestionStageError`, `STALE_DELETE_ID_BATCH_LIMIT`, and the new `PreparedSource`. `replacement.py` re-exports all of them.
- File sizes after the change: `pipeline.py` 448 (was 496), `sources.py` 348, `chunker.py` 334, `commit.py` 282, `replacement.py` 282.

## Test-first record

New tests:

- `tests/unit/test_ingestion_seams.py` (22): source units, content-type detection, identity, the pre-lineage guard, the Markdown declaration, normalisation scope, enrich with an explicit store and settings, split through the registry, specialised dispatch, the composed chunk path, one-source-at-a-time processing, and sibling commits kept after a failure.
- `tests/unit/test_ingestion_seams_replacement.py` (14): preparation outside the lock; malformed vectors (count, NaN, norm, dimension); five invalid-lineage cases; shutdown after preparation; failed verification that keeps the previous version and a retry that cleans it up; lock held for write, verify, and cleanup; replace composes prepare and commit.
- `tests/unit/test_ingestion_seams_parity.py` (3): seams compared with `ingest_path_async`, reuse on a second pass, and no process defaults read.

| Step | Files | Result |
| --- | --- | --- |
| Red, before implementation | the first two files plus the first two parity tests | 36 failed, 2 passed |
| Green, after implementation | all three files | 39 passed |

The two tests that passed on the red run test behaviour that already existed: one source at a time, and sibling commits kept after a failure. They are kept as regressions for the new composition.

Mutation checks. Each mutation was restored after the run:

| Mutation | Tests | Result |
| --- | --- | --- |
| Remove the `_check_prepared_lineage` call in `commit_prepared_source` | `test_ingestion_seams_replacement.py -k invalid_lineage` | 5 failed |
| `enrich_documents` forwards `store=None` | `test_ingestion_seams.py`, `test_document_registry_dispatch.py`, `test_metadata_store_ownership.py` | 7 failed, 63 passed |
| `commit_source` drops `store=` (falls back to the process default) | `test_ingestion_seams_parity.py -k never_reads` | failed with `RuntimeError: No default vector store has been composed yet` |
| All restored | the 3 seam files plus `test_document_registry_dispatch`, `test_metadata_store_ownership`, `test_no_global_settings_reads`, `test_file_size_ceiling` | 144 passed |

## Regression record

Focused ingestion set (28 files). These include `test_document_registry_dispatch.py`, `test_metadata_store_ownership.py`, `test_no_global_settings_reads.py`, `test_ingestion*.py`, `test_embedding_*`, `test_lineage_store_contract.py`, `test_stale_selection_bounds.py`, `test_signal_handling.py`, `test_markdown_chunking_pipeline.py`, `test_normalise_reader_chunker.py`, `test_ocr_identity_reingestion.py`, `test_file_size_ceiling.py`, `unit/test_type_aware_ingestion.py`, and `unit/test_index_identity_baseline.py`. Run with `-m "not slow"`:

| When | Result |
| --- | --- |
| Before the change | 453 passed, 18 skipped |
| After the change | 453 passed, 18 skipped |

Wider set: 37 more files that import the ingestion pipeline, chunker, or replacement. Slow and quality tests are excluded. The set includes `test_magika_parser_boundaries.py`, `test_watcher.py`, `test_engine.py`, `test_mcp_tools.py`, `test_cli.py`, and `test_retrieval.py`. Run with `-m "not slow"`:

| When | Result |
| --- | --- |
| After the change (worktree `src`) | 758 passed, 53 skipped, 3 deselected |
| HEAD `src` with worktree tests | 757 passed, 1 failed |

The one HEAD failure is `test_engine.py::test_public_api_exports_engine_effective_settings_version`. Another agent edited that test for its own export change, so it fails against HEAD `src`. It is not an ingestion regression.

Other checks:

- `ruff check` and `ruff format --check` on the touched files: pass.
- `lint-imports`: 12 contracts kept, 0 broken.

## Parity fixtures

- `tests/fixtures/pipeline_parity/ingestion/sources/` has three synthetic sources: `guide.md`, `notes.txt`, and `nested/appendix.md`. Together they produce 8 chunks.
- `snapshot.py` provides these helpers:
  - `copy_sources(tmp)` copies the source tree.
  - `pin_detection(monkeypatch)` returns the recorded Magika 1.0.3 content types, so results do not depend on `magika` being on `PATH`.
  - `collect_rows(store, collection, root)` returns all rows with full lineage. Use it to compare two runs over the same copied tree.
  - `portable_rows(rows)` drops path-bound and attempt-bound fields and adds `text_sha256`.
  - `load_expected()` loads the committed snapshot.
- `expected_chunks.json` is the portable snapshot of `ingest_path_async`. It was built with these settings: `extraction_mode="disabled"`, `pdf_reader="pypdf"`, `ocr_fallback_enabled=False`, empty tokenizer identity, and the unit-norm mock embedding. A real Magika run gave the same file.
- `test_seam_composition_matches_ingest_path_async` shows that the hand-composed seams write rows equal to `ingest_path_async`. The comparison covers `chunk_id`, `source_id`, `source_version`, `source_index_identity`, text, and metadata. Only `source_attempt` and filesystem bookkeeping are excluded.

## Status

- 3.3: done for the extraction scope. Seams are extracted. The dispatch and store-context regressions pass. Reader declarations and bounded per-source processing are tested.
- 3.4: done for the extraction scope only (embedding preparation and protected commit seams with their tests). The graph adapter itself is open.

## Open items for the lead

1. Add `core/ingestion/sources.py` and `core/ingestion/commit.py` to `_GUARDED_LEAVES` in `tests/test_no_global_settings_reads.py` (task 3.8). Neither imports a default accessor. Do not add `pipeline.py` or `replacement.py`, because both still use the `get_default_store` fallback for omitted stores.
2. Graph adapters should call the `sources.py` seams and omit the binding keywords. To get per-stage events, call the `chunker.py` stage seams and `prepare_source_embeddings`/`commit_prepared_source` directly instead of the two composites.
