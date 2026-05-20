## 1. Pre-flight & Dependencies

- [x] 1.1 Confirm with user whether to add `httpx` as a core dependency (per AGENTS.md "ask before adding"); if vetoed, plan to use `asyncio.to_thread(urllib.request.urlopen, ...)` in `_extract_ollama_async`.
- [x] 1.2 Add `httpx` (or chosen alternative) to `pyproject.toml` and run `uv sync`.
- [x] 1.3 Verify `pyproject.toml` already sets `asyncio_mode = "auto"` for pytest-asyncio; add it if missing.

## 2. Async Metadata Extraction

- [x] 2.1 Add `_extract_keyword_async(text)` in `metadata_extractor.py` — thin async wrapper around the existing sync function (no I/O, just `async def` for uniformity).
- [x] 2.2 Add `_extract_ollama_async(text)` using `httpx.AsyncClient` (or `asyncio.to_thread` fallback). Preserve hybrid taxonomy logic from `_extract_ollama` and the JSON parsing in `_parse_ollama_json_response`.
- [x] 2.3 Add `_extract_llamaindex_async(text, file_name)` that calls `IngestionPipeline.arun(documents=[doc])` directly, with no nested-loop detection or `ThreadPoolExecutor` branch.
- [x] 2.4 Add public `extract_metadata_async(file_text, file_name)` dispatcher mirroring the sync `extract_metadata`.
- [ ] 2.5 Add unit tests for each async extractor under `TestAsyncMetadataExtraction`, mirroring the sync tests but with `@pytest.mark.asyncio` and async mocks.

## 3. Async Ingestion Path

- [x] 3.1 Add `_read_and_chunk_file_async(file_path, ...)` in `ingestion.py`. Read file via `asyncio.to_thread` (sync libs like `pypdf` stay sync), call `extract_metadata_async`, return chunks + metadata.
- [x] 3.2 Add `ingest_path_async(path, collection_name="documents", ...)` that mirrors `ingest_path` but uses `await` for metadata extraction and wraps `chroma_collection.add/delete/get` in `asyncio.to_thread`.
- [x] 3.3 Preserve return-dict shape exactly (`files_indexed`, `chunks_created`, `file_details`, `error_type`, `message`) — verified by a structural test against `ingest_path`'s output.
- [ ] 3.4 Add an integration test that ingests a fixture folder via both sync and async paths and asserts identical ChromaDB state and identical return dicts.

## 4. Server, Watcher, CLI Migration

- [x] 4.1 Update the MCP `ingest_path` tool handler in `server.py` to `await ingest_path_async(...)`. Wrap exceptions in the standard `{"status": "error", ...}` envelope.
- [ ] 4.2 In `server.py`, capture the running loop (`asyncio.get_running_loop()`) at server startup and pass it to the watcher constructor.
- [x] 4.3 Update `watcher.py` to dispatch ingest via `asyncio.run_coroutine_threadsafe(ingest_path_async(...), self._loop)`. Attach `Future.add_done_callback` that logs exceptions at WARNING level.
- [x] 4.4 Preserve all existing watcher behaviour: debounce, hash dedup, size limit, symlink check, semaphore throttling, FileNotFoundError-during-debounce, ConnectionError CRITICAL alerting.
- [x] 4.5 Update `cli.py` to call `asyncio.run(ingest_path_async(path, ...))` at the entry point. Confirm stderr output, exit code, and `--report` output are byte-identical for a fixture folder.

## 5. Responsiveness Verification

- [ ] 5.1 Add `tests/test_async_ingest_responsiveness.py` with an integration test that starts an `ingest_path_async` task on a fixture folder containing at least one file with `METADATA_EXTRACTION_MODE=ollama`, then issues a concurrent mock-MCP `search` call after 100 ms and asserts the search returns within 500 ms.
- [ ] 5.2 Add a regression test that intentionally inserts a `time.sleep(2)` into the async path (in a temporary monkeypatch) and confirms the responsiveness test fails — proves the test catches blocking calls.
- [ ] 5.3 Smoke test the llamaindex mode end-to-end with a real Ollama against a single PDF; compare output to the sync workaround path. File results in `experiments/experiment-2/` if numbers diverge.

## 6. Retire Workaround & Sync API

- [x] 6.1 Verify all internal callers (CLI, watcher, server, tests) use `ingest_path_async`; grep for any remaining `ingest_path(` calls without the `_async` suffix.
- [x] 6.2 Remove the `concurrent.futures.ThreadPoolExecutor` nested-loop branch in `_extract_llamaindex` (the one added per ADR-013 "Implementation Notes").
- [x] 6.3 Remove the sync `_extract_llamaindex`, `_extract_ollama`, `extract_metadata`, `ingest_path` functions and their helpers; keep `_extract_keyword` only if any sync caller (e.g., a CLI report formatter) still needs it.
- [x] 6.4 Update / delete sync test classes in `tests/test_metadata_extractor.py` and `tests/test_ingestion.py` whose subjects no longer exist; ensure async tests fully replace coverage.

## 7. Documentation

- [ ] 7.1 Update `docs/adr/013-hybrid-category-taxonomy-for-ollama-metadata.md` "Implementation Notes" — replace the workaround description with a pointer to the now-active async path; mark the `ThreadPoolExecutor` pattern as historical.
- [ ] 7.2 Add new ADR `docs/adr/014-async-ingestion-path.md` documenting: the responsiveness requirement, the choice of `httpx` vs `aiohttp` vs `asyncio.to_thread`, the choice of `arun()` over `nest_asyncio`, ChromaDB sync wrapping via `to_thread`, watcher dispatch via `run_coroutine_threadsafe`.
- [ ] 7.3 Update `AGENTS.md` "Architecture (3 lines)" if any line becomes stale; update the "Hard Boundaries" table if `httpx` is now allowed.
- [ ] 7.4 Update `README.md` and any developer docs that say "ingest is sync" or describe the watcher running ingest inline.

## 8. Validate & Archive

- [ ] 8.1 Run `uv run pytest -m "not slow" --cov=rag_mcp` and confirm coverage stays ≥ 95%.
- [ ] 8.2 Run `uv run pytest -m slow` for the E2E stdio test; confirm it still passes against the async ingest path.
- [ ] 8.3 Run `openspec validate make-ingest-path-async` and resolve any structural issues.
- [ ] 8.4 Manual smoke test: start `uv run rag-mcp` (MCP stdio), trigger ingest of a folder of PDFs from a connected client, and issue concurrent `search` calls; confirm searches return promptly.
- [ ] 8.5 Archive the change via the `openspec-archive-change` skill once all the above are green.
