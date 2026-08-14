# Tasks: add-ingestion-change-detection

## 1. Hashing helper relocation

- [ ] 1.1 Create `src/rag_mcp/core/ingestion/hashing.py` with `sha256_file` (public name, Google-style docstring) and `MAX_FILE_SIZE`, moved verbatim from `daemon/_shared.py`
- [ ] 1.2 Change `daemon/_shared.py` to re-export from `core/ingestion/hashing.py`; keep `_sha256_file` importable for `daemon/runner.py` and `daemon/watcher.py`
- [ ] 1.3 Run existing daemon tests (`uv run pytest tests/test_watcher.py -m "not slow"`) to confirm the relocation is behaviour-preserving

## 2. Settings

- [ ] 2.1 Add `skip_unchanged: bool = True` to `IngestionSettings` in `core/ingestion/settings.py` and the matching frozen `IngestionBlock` in `core/settings.py`; verify that the nested config model resolves `INGESTION__SKIP_UNCHANGED`
- [ ] 2.2 Add the variable to `.env.example` with a comment naming the forced-re-embed use case (embedding-model or chunking-parameter changes)

## 3. Hash storage and lookup

- [ ] 3.1 In `core/ingestion/writer.py`, stamp every chunk's metadata with the canonical `source_content_hash` field at write time, regardless of the `skip_unchanged` setting (additive field; no existing field renamed)
- [ ] 3.2 Add a filtered metadata-read method to the `VectorStore` ABC, its ChromaDB implementation, and the vector-store contract tests; pipeline and writer code must not call ChromaDB APIs directly
- [ ] 3.3 Add a `get_stored_hashes(file_paths, collection_name) -> dict[str, list[str | None]]` helper in `writer.py` that returns every matching chunk hash per file and is safe to call through `asyncio.to_thread`

## 4. Pipeline skip logic

- [ ] 4.1 In `ingest_path_async`, after Magika detection and before `remove_document`: keep binary files on the existing `status: "skipped"` path, compute hashes for eligible non-binary files via `asyncio.to_thread(sha256_file, ...)`, fetch every stored chunk hash, and partition eligible files into `unchanged` and `to_ingest`
- [ ] 4.2 Classify a file as unchanged only when at least one chunk exists and every stored hash is non-null and equals the current hash; mixed, missing, or different hashes must enter `to_ingest`
- [ ] 4.3 When `sha256_file` raises `FileNotFoundError` or `OSError`, record that file as `status: "failed"` with `chunks: 0`, leave its existing chunks untouched, and continue sibling files
- [ ] 4.4 Restrict the delete and chunk/embed loops to `to_ingest`; when `skip_unchanged` is `false`, place every eligible non-binary file in `to_ingest`
- [ ] 4.5 Add `file_details` entries with `status: "skipped_unchanged"`, `chunks: 0` for files skipped by change detection, and a top-level `files_skipped_unchanged` counter on every result dict (including error returns), `0` when none skipped
- [ ] 4.6 Keep files skipped by change detection out of `files_indexed`, `chunks_created`, and `chunks_removed`; exclude binary and unsupported-extension files from `files_skipped_unchanged`
- [ ] 4.7 Adjust the terminal status guard so a run where all eligible files are `skipped_unchanged` returns `status: "ok"` even though `files_indexed == 0`

## 5. Tests

- [ ] 5.1 Unit test: second `ingest_path_async` on an unchanged directory skips all files (`files_skipped_unchanged == N`, `files_indexed == 0`, chunk count unchanged in the collection) — verify it fails before task 4.1 by running against the unmodified pipeline
- [ ] 5.2 Unit test: modified file is re-ingested, its chunks' `source_content_hash` metadata equals the new digest, and old chunks are gone
- [ ] 5.3 Unit test: legacy collection (chunks written without the hash field) re-ingests once, then skips on the following call
- [ ] 5.4 Unit test: mixed directory (one of three modified) reports `files_skipped_unchanged == 2`, `files_indexed == 1`
- [ ] 5.5 Unit test: `INGESTION__SKIP_UNCHANGED=false` forces full re-ingest with `files_skipped_unchanged == 0` while still stamping every chunk with the current `source_content_hash`
- [ ] 5.6 Unit test: result-shape contract — all pre-existing keys and types unchanged, new key present on error-path dicts too
- [ ] 5.7 Unit test: mixed and missing `source_content_hash` values across one file's chunks force re-ingestion; only a non-empty all-matching set skips
- [ ] 5.8 Unit test: parameterised `FileNotFoundError` and `OSError` hash failures record a failed file, preserve its existing chunks, and allow sibling files to finish; include the oversized-file path
- [ ] 5.9 Unit test: a supported-extension binary file retains `status: "skipped"` and is excluded from `files_skipped_unchanged` in both setting modes
- [ ] 5.10 Confirm existing suites still pass: `uv run pytest tests/test_ingestion.py tests/test_watcher.py tests/test_cli.py -m "not slow"`

## 6. Documentation, ADR, and surface pass

- [ ] 6.1 Add a distinct `skipped_unchanged` bucket to the CLI report's JSON summary and Markdown table so it remains separate from the existing `skipped` status; leave the MCP tool result pass-through as-is
- [ ] 6.2 Update `docs/guides/ingestion.md` with the skip behaviour, the one-time legacy re-ingest, and the `INGESTION__SKIP_UNCHANGED` escape hatch
- [ ] 6.3 Grep `docs/guides/` for stale claims that ingestion always re-embeds; fix any found
- [ ] 6.4 Write `docs/adr/ADR-0XX-ingestion-change-detection.md` recording: (a) hash source decision — SHA-256 of file bytes over mtime+size proxy (misses same-size edits, breaks on checkout-mtime resets) and git-commit keying (only valid in repos; ingestion targets often are not); (b) hash storage in Chroma chunk metadata over a sidecar state file (hash lifetime stays exactly as stale as the chunks; no second store to drift); (c) the skip-before-delete ordering constraint (deleting first discards the stored hash); (d) the known limitation that the hash covers file content only — embedding-model or chunking-parameter changes require `INGESTION__SKIP_UNCHANGED=false` or a collection rebuild, deliberately not mixed into the hash (YAGNI); (e) cross-reference to `add-per-collection-persist-dirs`: a collection migrated to a fresh persist dir re-ingests once, which is the legacy-chunks scenario by design
- [ ] 6.5 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm coverage floors hold for touched modules (`core/ingestion` ≥95%)
- [ ] 6.6 Run `ruff check`, `ruff format --check`, and the import-contract suite; fix any violations
