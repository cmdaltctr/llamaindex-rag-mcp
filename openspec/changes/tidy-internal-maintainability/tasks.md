## 1. Ingestion Helper Cleanup

- [ ] 1.1 Remove or correct the unreachable unsupported-single-file branch in `_gather_supported_files()`.
- [ ] 1.2 Update any misleading test names/comments around unsupported single files.
- [ ] 1.3 Confirm `ingest_path_async()` still returns an explicit unsupported-extension error.

## 2. Benchmark Helper Boundary

- [ ] 2.1 Add a public `read_and_chunk_file_async()` wrapper in `ingestion.py` that delegates to `_read_and_chunk_file_async()`. Add a docstring noting it is an internal-supported helper shared with the benchmark CLI (not external public API).
- [ ] 2.2 Update `cli.py benchmark` to import `read_and_chunk_file_async` (the public name) instead of the underscored private function.
- [ ] 2.3 Add or update a benchmark-related test that imports the public wrapper to lock in the boundary.

## 3. Concurrency and Test Hygiene

- [ ] 3.1 Rename watcher `_timers_lock` to a clearer shared-state lock name if safe.
- [ ] 3.2 Add a lock around `_chroma_client` lazy initialization in `metadata_extractor.py`.
- [ ] 3.3 Replace or document the hardcoded test ChromaDB persist path in `tests/conftest.py`.

## 4. Verification

- [ ] 4.1 Run watcher, metadata extractor, ingestion, and CLI tests touched by this cleanup.
- [ ] 4.2 Validate the OpenSpec change.
