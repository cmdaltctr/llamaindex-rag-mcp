## Context

The MCP server for `rag-mcp` is built on FastMCP with `transport="stdio"`,
which runs a single asyncio event loop on the main thread. Today, every
ingestion code path is synchronous:

- `ingest_path()` in `ingestion.py` is `def`, not `async def`.
- It calls `extract_metadata()` synchronously, which in `ollama` mode uses
  `urllib.request.urlopen(...)` (blocking), and in `llamaindex` mode calls
  `IngestionPipeline.run()` (sync facade over an async pipeline).
- It calls `chroma_collection.add(...)` and `chroma_collection.delete(...)`
  synchronously (ChromaDB `PersistentClient` is sync-only as of v0.5).
- The MCP `ingest_path` tool handler (when added) and the
  watcher's `_ingest_dispatch()` both call this sync function inline,
  occupying the event loop for the duration of the run.

Symptoms surfaced during real ingestion of a folder of PDFs with
`METADATA_EXTRACTION_MODE=llamaindex`:

1. `IngestionPipeline.run()` raised "Detected nested async" because it
   refuses to nest inside an already-running loop. We worked around this in
   `metadata_extractor.py` by offloading the sync call to a fresh
   `ThreadPoolExecutor` worker — see ADR-013, "Implementation Notes".
2. The workaround unblocks correctness but does not unblock the loop:
   the calling thread (the MCP loop) still waits on `.result()`. So
   concurrent `search` requests queue behind a long ingest.

The `ThreadPoolExecutor` workaround is acceptable as a tactical fix because
it preserves a single-call-site contract and avoids a new dependency, but it
is the wrong long-term shape. The proper fix is end-to-end async on the
ingest path.

Constraints that frame the design:

- **No PyTorch at runtime** — applies broadly, not specific to this change.
- **Ask before adding core dependencies** — `httpx` is the proposed addition.
- **Backward compatibility** — CLI flags, MCP tool names, `.env` variables,
  ChromaDB on-disk format must not change.
- **ChromaDB is sync-only** — its `PersistentClient` does not expose `async`
  methods. We cannot fully eliminate sync calls; we have to wrap them.
- **`urllib.request.urlopen` is blocking** — the current `_extract_ollama`
  needs to switch HTTP libraries or be wrapped in `asyncio.to_thread()`.

## Goals / Non-Goals

**Goals:**

- The MCP server event loop remains responsive during ingestion. A `search`
  request issued mid-ingest returns within ~100 ms, not after the entire
  ingest completes.
- The "nested async" error in `_extract_llamaindex` goes away by calling
  `IngestionPipeline.arun()` instead of working around `pipeline.run()`.
- The `ThreadPoolExecutor` workaround in `metadata_extractor.py` is
  retired (no more loop-detect-then-offload pattern in production code).
- CLI behaviour observable to the user is unchanged. Same flags, same
  output, same exit codes.
- Watcher behaviour observable to the user is unchanged. Same debounce,
  same idempotency.

**Non-Goals:**

- Replacing ChromaDB with an async-native vector store. Out of scope —
  ChromaDB stays, we wrap its sync calls in `asyncio.to_thread()`.
- Parallelising ingest across multiple files concurrently. The current
  contract is one file at a time; this change preserves that. Concurrent
  per-file ingest is a separate concern (would need rate-limiting,
  ordering guarantees, and ChromaDB write contention analysis).
- Streaming progress updates back to the MCP client during long ingest.
  Useful, but a separate feature.
- Refactoring retrieval. Retrieval (`retrieval.py`) is already fast enough
  per-call and does not block on long-running LLM operations.
- Adding `nest_asyncio`. Considered and rejected — see Decisions.

## Decisions

### D1: End-to-end async, not `nest_asyncio`

`nest_asyncio.apply()` would silence the "Detected nested async" error in
~3 lines of code. Rejected because:

- It monkeypatches asyncio globally, with subtle interaction effects on
  other async libraries.
- It is a workaround, not a solution: `pipeline.run()` would still block
  the loop while the LLM call runs.
- It adds a new dependency for negative value.

Going `async def` end-to-end is more work but has linear, predictable
benefits: every `await` point is a yield to the loop.

**Alternatives considered:**

- `nest_asyncio.apply()` — rejected as above.
- Run ingestion in a separate process — solves responsiveness but adds IPC
  complexity and breaks the "single SQLite file = single process"
  assumption ChromaDB is happiest with.

### D2: `httpx` for async HTTP to Ollama

The current `_extract_ollama` uses `urllib.request.urlopen(...)` —
stdlib only, blocking. To make ollama mode async, we need an async HTTP
client. Options:

- **`httpx`** — chosen. Sync and async in one package. Already common in
  the LlamaIndex ecosystem (transitively pulled by `llama-index-core`,
  so `pip` resolution typically already has it cached). Stable, well-
  maintained.
- **`aiohttp`** — bigger surface area, opinionated session lifecycle. We
  do not need its server features.
- **`asyncio.to_thread(urllib.request.urlopen, ...)`** — keeps stdlib
  but loses the cleanliness of native async. Acceptable as a fallback if
  the user vetoes adding `httpx`.

**User confirmation gate:** AGENTS.md says "ask before adding new core
dependencies". The implementation phase must surface this for approval
before adding `httpx` to `pyproject.toml`. If vetoed, fall back to
`asyncio.to_thread(urllib.request.urlopen, ...)`.

### D3: Wrap ChromaDB sync calls in `asyncio.to_thread`

ChromaDB's `PersistentClient` does not expose async methods. We cannot
make `collection.add(...)` truly async, but we can yield the loop while
it runs by wrapping in `asyncio.to_thread(...)`:

```python
await asyncio.to_thread(
    chroma_collection.add,
    ids=ids,
    documents=documents,
    metadatas=metadatas,
    embeddings=embeddings,
)
```

This is what `to_thread` exists for — running blocking sync code without
blocking the loop. The thread pool is `loop.run_in_executor`'s default,
which is fine for our usage (one ChromaDB write per file).

### D4: CLI wraps async function in `asyncio.run`

`cli.py` runs synchronously from the user's shell. Approach:

```python
def _cli_ingest(path: str, ...) -> int:
    return asyncio.run(ingest_path_async(path, ...))
```

This is the standard pattern for "library is async, CLI entry point is
sync". The CLI has no existing event loop, so `asyncio.run(...)`
creates one, runs the coroutine, and tears down.

### D5: Watcher dispatches via `run_coroutine_threadsafe`

The `watchdog` library calls `on_modified`/`on_created` from a
non-asyncio thread. To submit work to the MCP loop:

```python
asyncio.run_coroutine_threadsafe(
    ingest_path_async(file_path, ...),
    self._loop,  # captured at watcher startup from the MCP loop
)
```

This requires capturing the loop reference at watcher startup. The MCP
server already has access to the running loop, so it passes it to the
watcher constructor.

### D6: Keep sync `_extract_llamaindex` only as a fallback

The CLI path is the only context that has no enclosing loop. We could
either:

(a) **Keep both sync and async variants** of `_extract_llamaindex` and
dispatch based on context.

(b) **Always go async**, and have the CLI use `asyncio.run(...)` to
provide a loop.

Choosing (b). Single code path, fewer branches. The CLI's
`asyncio.run(...)` adds negligible overhead (a few ms of loop setup
per ingest run). The sync `pipeline.run()` call is dropped entirely.

This means the `ThreadPoolExecutor` workaround in
`metadata_extractor.py` goes away — no more loop-detect-then-offload
branch. Cleaner.

### D7: Test the responsiveness contract, not just functional correctness

Existing ingestion tests verify functional correctness (right chunks,
right metadata, right ChromaDB state). They do not verify that the loop
remains responsive. Add an integration test:

```python
async def test_search_responsive_during_ingest(connected_client):
    ingest_task = asyncio.create_task(ingest_path_async("./large_folder"))
    await asyncio.sleep(0.5)  # let ingest start
    start = time.monotonic()
    result = await connected_client.call_tool("search", {"query": "x"})
    elapsed = time.monotonic() - start
    assert elapsed < 0.5  # should not block on ingest
    await ingest_task
```

If a future change accidentally re-introduces a sync call into the
ingest path, this test catches it.

## Risks / Trade-offs

| Risk | Mitigation |
|------|-----------|
| `LlamaIndex.IngestionPipeline.arun()` has different behaviour than `.run()` (different node ordering, different metadata field names, different error types) | Smoke test with real Ollama before committing the cutover. Add a comparison test in `experiments/` that runs both paths on the same document and diffs the result. |
| Half-async refactor — one stray sync call in the chain blocks the loop | The responsiveness test (D7) is the safety net. If it passes, the chain is async. If not, the test pinpoints which `await` is missing. |
| `httpx` introduces new dependency surface (TLS verification, connection pooling) that the stdlib `urllib` did not | `httpx` is widely deployed and well-audited. Use default verification. Fallback to `asyncio.to_thread(urllib.request.urlopen, ...)` is available if the user vetoes adding `httpx`. |
| ChromaDB writes are still sync internally — `to_thread` only yields the loop, the write itself still serialises | Acceptable. ChromaDB writes are fast (~10s of ms for typical chunk batches). The loop yield is what we need; the write speed is unchanged. |
| Watcher `run_coroutine_threadsafe` returns a `Future` that nobody awaits — exceptions from ingest get silently lost | Add a `Future.add_done_callback(...)` that logs exceptions to stderr. Match existing watcher error-handling style. |
| Tests need `@pytest.mark.asyncio` decoration en masse — risk of missing one and the test silently passing without awaiting | Configure `asyncio_mode = "auto"` in `pyproject.toml` (already set per `pytest.ini_options`), so pytest-asyncio auto-detects async tests. Verify by intentionally `await asyncio.sleep(99)` in a new test and confirming it blocks. |
| LlamaIndex `arun()` may itself spawn threads or processes that conflict with our model — opaque internals | Time-box debugging to one day. If `arun()` is buggy or unstable, fall back to `to_thread(pipeline.run, ...)` for the llamaindex mode only — keeps the rest of the async refactor intact. |

## Migration Plan

The change can be rolled out file-by-file without flipping a global
switch. The order matters because each step depends on its predecessor
being async-ready.

1. **Add `_extract_llamaindex_async` and `_extract_ollama_async`** in
   `metadata_extractor.py`, alongside the existing sync versions. This
   is purely additive — nothing breaks.
2. **Add `extract_metadata_async`** as the public async entry point that
   dispatches to the async variants.
3. **Add `ingest_path_async`** in `ingestion.py` alongside `ingest_path`.
   Same logic, but `async def` and `await`s on metadata extraction and
   ChromaDB writes (via `asyncio.to_thread`).
4. **Update the MCP `ingest_path` tool handler** in `server.py` to
   `await ingest_path_async(...)`.
5. **Update the watcher** in `watcher.py` to dispatch via
   `run_coroutine_threadsafe`. Capture the loop reference at watcher
   startup.
6. **Update the CLI** in `cli.py` to call `asyncio.run(ingest_path_async(...))`.
7. **Remove the sync `ingest_path` and `_extract_*` sync variants**
   once all callers are migrated. Remove the `ThreadPoolExecutor`
   workaround in `_extract_llamaindex` at the same time.
8. **Update ADR-013** "Implementation Notes" to point at the new async
   path; mark the workaround as historical.

Rollback strategy: each step in 1–6 is additive (sync versions still
exist). If the responsiveness test or smoke test fails at any step, the
caller can revert to the sync version without dependency removal. Step
7 is the point of no return — gate it on green tests.

## Open Questions

- **Confirm `httpx` is acceptable as a new core dependency.** AGENTS.md
  requires the ask. If vetoed, the fallback is
  `asyncio.to_thread(urllib.request.urlopen, ...)`, which works but
  loses the niceness of native async HTTP.
- **Should `ingest_path_async` accept a per-file concurrency parameter
  for future use?** E.g. `max_concurrent_files: int = 1`. Adding the
  parameter now (default 1) is cheap and avoids a future signature
  break. Defer the actual concurrent-files implementation to a separate
  change, but reserve the API.
- **Does the watcher need a queue and a single async consumer task,
  rather than firing one `run_coroutine_threadsafe` per file event?**
  Probably yes for backpressure and ordering, but it's a separate
  design decision. For this change, one Future per file event is fine.
