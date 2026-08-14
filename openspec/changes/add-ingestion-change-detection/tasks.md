# Tasks: add-ingestion-change-detection

## 1. Hashing helper relocation

- [ ] 1.1 Create `src/rag_mcp/core/ingestion/hashing.py` with `sha256_file` (public name, Google-style docstring) and `MAX_FILE_SIZE`, moved verbatim from `daemon/_shared.py`
- [ ] 1.2 Change `daemon/_shared.py` to re-export from `core/ingestion/hashing.py`; keep `_sha256_file` importable for `daemon/runner.py` and `daemon/watcher.py`
- [ ] 1.3 Run existing daemon tests (`uv run pytest tests/test_watcher.py -m "not slow"`) to confirm the relocation is behaviour-preserving

## 2. Settings

- [ ] 2.1 Add `skip_unchanged: bool = True` to the ingestion settings block in `config/__init__.py` and mirror it in `core/settings.py` (frozen model, nested env var `INGESTION__SKIP_UNCHANGED`)
- [ ] 2.2 Add the variable to `.env.example` with a comment naming the forced-re-embed use case (embedding-model or chunking-parameter changes)

## 3. Hash storage and lookup

- [ ] 3.1 In `core/ingestion/writer.py`, stamp every chunk's metadata with `source_content_hash` at write time (additive field; no existing field renamed)
- [ ] 3.2 Add a `get_stored_hashes(file_paths, collection_name) -> dict[str, str | None]` helper in `writer.py` that batch-queries chunk metadata by `file_path` and returns the stored hash per file (or `None` where absent), wrapped for `to_thread` use by callers

## 4. Pipeline skip logic

- [ ] 4.1 In `ingest_path_async`, after Magika detection and before the `remove_document` loop: compute per-file hashes via `to_thread(sha256_file, ...)`, fetch stored hashes, and partition files into `unchanged` and `to_ingest` (respect `skip_unchanged` setting: when `false`, treat all files as `to_ingest`)
- [ ] 4.2 Restrict the delete loop and the chunk/embed loop to `to_ingest` files only
- [ ] 4.3 Add `file_details` entries with `status: "skipped_unchanged"`, `chunks: 0` for skipped files, and a top-level `files_skipped_unchanged` counter on every result dict (including error returns), `0` when none skipped
- [ ] 4.4 Keep skipped files out of `files_indexed`, `chunks_created`, and `chunks_removed` counts

## 5. Tests

- [ ] 5.1 Unit test: second `ingest_path_async` on an unchanged directory skips all files (`files_skipped_unchanged == N`, `files_indexed == 0`, chunk count unchanged in the collection) — verify it fails before task 4.1 by running against the unmodified pipeline
- [ ] 5.2 Unit test: modified file is re-ingested, its chunks' `source_content_hash` metadata equals the new digest, and old chunks are gone
- [ ] 5.3 Unit test: legacy collection (chunks written without the hash field) re-ingests once, then skips on the following call
- [ ] 5.4 Unit test: mixed directory (one of three modified) reports `files_skipped_unchanged == 2`, `files_indexed == 1`
- [ ] 5.5 Unit test: `INGESTION__SKIP_UNCHANGED=false` forces full re-ingest with `files_skipped_unchanged == 0` while still stamping current hashes
- [ ] 5.6 Unit test: result-shape contract — all pre-existing keys and types unchanged, new key present on error-path dicts too
- [ ] 5.7 Confirm existing suites still pass: `uv run pytest tests/test_ingestion.py tests/test_watcher.py tests/test_cli.py -m "not slow"`

## 6. Documentation, ADR, and surface pass

- [ ] 6.1 Pass `files_skipped_unchanged` through the CLI report (`transports/cli/_report.py` summary table) and leave the MCP tool result pass-through as-is (dict already flows through)
- [ ] 6.2 Update `docs/guides/ingestion.md` with the skip behaviour, the one-time legacy re-ingest, and the `INGESTION__SKIP_UNCHANGED` escape hatch
- [ ] 6.3 Grep `docs/guides/` for stale claims that ingestion always re-embeds; fix any found
- [ ] 6.4 Write `docs/adr/ADR-0XX-ingestion-change-detection.md` recording: (a) hash source decision — SHA-256 of file bytes over mtime+size proxy (misses same-size edits, breaks on checkout-mtime resets) and git-commit keying (only valid in repos; ingestion targets often are not); (b) hash storage in Chroma chunk metadata over a sidecar state file (hash lifetime stays exactly as stale as the chunks; no second store to drift); (c) the skip-before-delete ordering constraint (deleting first discards the stored hash); (d) the known limitation that the hash covers file content only — embedding-model or chunking-parameter changes require `INGESTION__SKIP_UNCHANGED=false` or a collection rebuild, deliberately not mixed into the hash (YAGNI); (e) cross-reference to `add-per-collection-persist-dirs`: a collection migrated to a fresh persist dir re-ingests once, which is the legacy-chunks scenario by design
- [ ] 6.5 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm coverage floors hold for touched modules (`core/ingestion` ≥95%)
- [ ] 6.6 Run `ruff check`, `ruff format --check`, and the import-contract suite; fix any violations
