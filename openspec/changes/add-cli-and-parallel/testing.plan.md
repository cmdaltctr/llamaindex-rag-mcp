# Testing Plan: CLI Interface & Parallel Ingestion

**Change ID**: `add-cli-and-parallel`
**Status**: planning
**Created**: 2026-05-18

## Executive Summary

The feature implementation is complete (all tasks in `tasks.md` checked `[x]`), but **CLI test
coverage is zero**. The 441-line `cli.py` has no dedicated test file; all existing tests focus
on the ingestion and retrieval layer below the CLI. This plan identifies gaps and proposes
tests organised by risk priority.

---

## 1. Current Coverage vs. Gap Analysis

### What IS tested

| Layer | Test file | Coverage notes |
|-------|-----------|----------------|
| `_gather_supported_files()` | `test_ingestion_parallel.py` | Single file, unsupported file, mixed directory |
| `_read_and_chunk_file()` | `test_ingestion_parallel.py` | .txt, .md, custom chunk_size, non-existent file |
| `_ingest_sequential()` | `test_ingestion_parallel.py` | `workers=1` end-to-end |
| `_ingest_parallel()` | `test_ingestion_parallel.py` | `workers=4` end-to-end, same chunk count as sequential |
| `_embed_and_write()` shutdown | `test_signal_handling.py` | Returns 0 when flag set, empty nodes |
| `_shutdown_requested` reset | `test_signal_handling.py` | Cleared on new `ingest_path()` call |
| Sequential early stop | `test_signal_handling.py` | Progress callback sets shutdown flag mid-run |
| Workers clamping | Both test files | 0, -5, 1, 100 |
| Error isolation | `test_ingestion_parallel.py` | Corrupt file skipped, good file indexed |
| Input validation (legacy) | `test_ingestion.py` | Non-existent path, unsupported extension, empty directory |
| MCP tools | `test_mcp_tools.py` | All 3 tools via in-memory ClientSession |
| Retrieval | `test_retrieval.py` | Threshold scaling, search integration |
| Reranker | `test_reranker.py` | Extensive (sigmoid, ONNX, singleton, fallback) |

### What is NOT tested (the GAPS)

| # | Area | Current status | Risk |
|---|------|---------------|------|
| 1 | **CLI `ingest` command** (Typer integration) | ❌ Zero coverage | 🔴 HIGH |
| 2 | **CLI `search` command** | ❌ Zero coverage | 🔴 HIGH |
| 3 | **CLI `list` command** | ❌ Zero coverage | 🟡 MEDIUM |
| 4 | **`callback()` → MCP fallback** when no args | ❌ Zero coverage | 🟡 MEDIUM |
| 5 | **Rich progress bars** | ❌ Not tested | 🟡 MEDIUM |
| 6 | **Plain-text progress** (non-TTY) | ❌ Not tested | 🟡 MEDIUM |
| 7 | **`--json` output format** on all commands | ❌ Not tested | 🟡 MEDIUM |
| 8 | **CLI SIGINT handler** (double-Ctrl+C) | ❌ Not tested | 🟡 MEDIUM |
| 9 | **`pool.shutdown(cancel_futures=True)`** during parallel shutdown | ❌ Not tested | 🟡 MEDIUM |
| 10 | **Concurrent `_write_lock`** with actual competing threads | ❌ Not tested | 🟡 MEDIUM |
| 11 | **`BoundedSemaphore` actual throttling** | ❌ Not tested | 🟢 LOW |
| 12 | **Path resolution** (`expanduser().resolve()`) | ❌ Not tested | 🟢 LOW |
| 13 | **`_sanitise_display_name()`** isolated unit test | ❌ Only exercised via search/list table | 🟢 LOW |
| 14 | **Exit code 130** on interrupt, **exit code 1** on error | ❌ Not tested | 🟢 LOW |
| 15 | **`--help` output** for all subcommands | ❌ Not tested | 🟢 LOW |
| 16 | **`--chunk-size` / `--chunk-overlap`** CLI override passthrough | ❌ Not tested | 🟢 LOW |
| 17 | **`_print_ollama_error()`** formatting | ❌ Not tested | 🟢 LOW |
| 18 | **Empty store** search and list output | ❌ Not tested | 🟢 LOW |

---

## 2. Test File: `tests/test_cli.py` (NEW — ~300 lines)

This will be the primary new test file covering all CLI integration paths.

### 2.1 Fixtures & Setup

```python
# Top-of-file setup needed:
# - CliRunner from typer.testing
# - Import `app` from rag_mcp.cli
# - Mock embedding (reuse conftest pattern — Settings.embed_model already mocked)
# - Mock ChromaDB (reuse conftest EphemeralClient)
# - Clean state between tests (clear _shutdown_requested, clear ChromaDB collections)

runner = CliRunner()
```

**Key constraint**: The CLI `callback()` imports `server.main` which starts an MCP stdio
server — this blocks forever. For callback tests we need to either:
- Mock `server.main` to assert it was called, OR
- Test that `app` has the correct callback configuration without invoking it

**Rich progress constraint**: Rich `Progress` hides output when `console.is_terminal` is
`False` (which it is inside `CliRunner`). To test progress bars:
- Use `force_terminal=True` on the Console (requires patching `cli.console`)
- Or test via the plain-text callback path (simpler and more reliable)

### 2.2 Test Classes

---

#### `TestEntryPoint` — Entry point routing

| Test | What it verifies | Approach |
|------|-----------------|----------|
| `test_no_args_does_not_error` | `rag-mcp` with no args returns exit code 0 | `runner.invoke(app, [])` — likely times out due to MCP server start. Instead: test that `callback()` is annotated `invoke_without_command=True` and test the routing logic in isolation. |
| `test_version_flag` | `rag-mcp --version` prints version and exits 0 | `runner.invoke(app, ["--version"])` — assert `"rag-mcp" in result.stdout` and `result.exit_code == 0` |
| `test_unknown_subcommand_shows_help` | `rag-mcp bogus` prints error to stderr, non-zero exit | `runner.invoke(app, ["bogus"])` — assert non-zero exit code, assert error message in `result.stderr` |
| `test_help_flag` | `rag-mcp --help` lists subcommands | `runner.invoke(app, ["--help"])` — assert `"ingest"` and `"search"` and `"list"` in `result.stdout` |

**Design note on callback/MCP fallback test**: `runner.invoke(app, [])` will call
`callback()` → `server.main()` → `mcp.run(transport="stdio")`, which blocks forever.
We'll skip this specific test (it's covered by the E2E stdio test) and instead test
the callback decoration metadata.

---

#### `TestIngestCLI` — CLI `ingest` command

All tests use `runner.invoke(app, ["ingest", ...])`.

| Test | Scenario | Assertions |
|------|----------|-----------|
| `test_ingest_single_txt_file` | Ingest a valid .txt file | `exit_code == 0`, `"Indexed"` in output, `"1 file(s)"` in output |
| `test_ingest_path_not_found` | `ingest /nonexistent/path/` | `exit_code != 0`, `"Error"` in stderr or stdout |
| `test_ingest_unsupported_extension` | Single .xyz file | `exit_code != 0`, `"Unsupported"` in output |
| `test_ingest_with_workers_flag` | `--workers 4` | `exit_code == 0` (test passes worker through) |
| `test_ingest_with_chunk_size` | `--chunk-size 128` | `exit_code == 0` |
| `test_ingest_with_chunk_overlap` | `--chunk-overlap 32` | `exit_code == 0` |
| `test_ingest_json_output` | `--json` flag | `exit_code == 0`, result.output is valid JSON, contains `"status"` key |
| `test_ingest_json_output_on_error` | `--json` with non-existent path | `exit_code != 0`, output is valid JSON with `"status": "error"` |
| `test_ingest_workers_clamped_negative` | `--workers -5` | `exit_code == 0` (clamped to 1, works) |
| `test_ingest_workers_zero` | `--workers 0` | `exit_code == 0` (clamped to 1, works) |
| `test_ingest_shows_success_message` | Valid file ingest | Output contains `✓` or `Indexed` |
| `test_ingest_exit_code_on_success` | Valid file ingest | `exit_code == 0` |
| `test_ingest_exit_code_on_error` | Non-existent path | `exit_code == 1` |
| `test_ingest_help` | `rag-mcp ingest --help` | Help text includes `--workers`, `--chunk-size`, `--chunk-overlap`, `--json` |

---

#### `TestSearchCLI` — CLI `search` command

| Test | Scenario | Assertions |
|------|----------|-----------|
| `test_search_empty_store` | Search with no indexed docs | `exit_code == 0`, `"No results"` in output |
| `test_search_after_ingest` | Index one file, then search | `exit_code == 0`, results contain source filename |
| `test_search_json_output` | `--json` flag | Output is valid JSON array |
| `test_search_json_empty_store` | `--json` with no results | Output is `"[]"` |
| `test_search_with_top_k` | `--top-k 3` | `exit_code == 0` |
| `test_search_with_threshold` | `--threshold 0.5` | `exit_code == 0` |
| `test_search_with_rerank` | `--rerank` | `exit_code == 0` (reranker handles it) |
| `test_search_rich_table_output` | Default (no --json) | Output contains `"Score"` and `"Source"` and `"Text"` (Rich table headers) |
| `test_search_help` | `rag-mcp search --help` | Help text includes `--top-k`, `--threshold`, `--rerank`, `--json` |

---

#### `TestListCLI` — CLI `list` command

| Test | Scenario | Assertions |
|------|----------|-----------|
| `test_list_empty_store` | No documents indexed | `exit_code == 0`, `"No indexed documents"` in output |
| `test_list_after_ingest` | Index one file, then list | `exit_code == 0`, output contains filename and chunk count |
| `test_list_json_output` | `--json` | Output is valid JSON array with `"source"` and `"chunks"` keys |
| `test_list_json_empty_store` | `--json` with no documents | Output is `"[]"` |
| `test_list_rich_table_output` | Default (no --json) | Output contains `"Source"` and `"Chunks"` headers |
| `test_list_shows_total` | After ingesting docs | Output contains `"document(s)"` and `"chunk(s) total"` |

---

#### `TestProgressReporting` — Progress output in both modes

These test the progress rendering, not the ingestion logic.

| Test | Scenario | Assertions |
|------|----------|-----------|
| `test_plain_text_progress_on_non_tty` | Ingest with non-TTY (CliRunner default) | `"Reading file"` appears in stderr output |
| `test_plain_text_shows_embedding` | Non-TTY ingest completes | `"Embedding"` appears in stderr output |
| `test_plain_text_shows_completion` | Non-TTY ingest completes | `"Embedding complete"` or chunk count in stderr |
| `test_json_suppresses_progress` | `--json` ingest | No `"Reading file"` in output (just JSON) |
| `test_rich_progress_callback_structure` | `_run_ingest_with_rich_progress` called with mock | Test the callback wiring: `on_progress("read", ...)`, `on_progress("embed_start", ...)`, `on_progress("embed", ...)` don't crash |

---

#### `TestSanitiseDisplayName` — ANSI escape stripping

| Test | Scenario | Assertions |
|------|----------|-----------|
| `test_no_ansi_passthrough` | Plain string | Returns same string |
| `test_strips_color_codes` | `"\x1b[32mgreen\x1b[0m"` | Returns `"green"` |
| `test_strips_cursor_movement` | `"\x1b[2Jcleared"` | Returns `"cleared"` |
| `test_empty_string` | `""` | Returns `""` |

---

#### `TestPrintOllamaError` — Error message formatting

| Test | Scenario | Assertions |
|------|----------|-----------|
| `test_console_output` | Default mode | Stderr contains `"Ollama"` and `"Is Ollama running?"` |
| `test_json_output` | `json_output=True` | Output is valid JSON with `"status": "error"` |
| `test_includes_detail` | `detail="Connection refused"` | Output contains `"Connection refused"` |

---

### 2.3 Mocking Strategy for CLI Tests

The CLI tests should reuse all three `conftest.py` autouse fixtures:
1. **ChromaDB** → `EphemeralClient` (no disk I/O)
2. **Settings.embed_model** → `MockEmbedding(384)` (no Ollama)
3. **Module-level constants** → patched for consistent collection naming

Specific additional mocks needed:
- `cli.console.is_terminal`: Set to `False` (CliRunner default) or mock for Rich tests
- `cli._OLLAMA_URL`: Already reads from env; mock `OLLAMA_BASE_URL` if needed
- Signal handler: Can be tested by directly setting `_shutdown_requested` and checking CLI output

---

## 3. Tests to Augment in Existing Files

### 3.1 `tests/test_ingestion_parallel.py` — Add ~40 lines

These extend the low-level ingestion tests to cover gaps the CLI tests won't reach.

| # | Test | File | What it verifies |
|---|------|------|-----------------|
| 1 | `test_parallel_shutdown_via_pool_cancel` | `test_ingestion_parallel.py` | `pool.shutdown(wait=False, cancel_futures=True)` is called when shutdown flag set during parallel phase |
| 2 | `test_concurrent_write_lock_serialises` | `test_ingestion_parallel.py` | Two threads trying to call `_embed_and_write` simultaneously — only one executes the critical section at a time |
| 3 | `test_embed_semaphore_limits_concurrency` | `test_ingestion_parallel.py` | `BoundedSemaphore(2)` — 4 threads, only 2 acquire simultaneously |

**Concurrency test design**: Spawn threads that acquire the lock, sleep briefly, release. Use
a counter to track how many are inside the critical section simultaneously. Assert max ≤ 1
for lock, max ≤ 2 for semaphore.

### 3.2 `tests/test_signal_handling.py` — Add ~30 lines

| # | Test | File | What it verifies |
|---|------|------|-----------------|
| 4 | `test_double_check_lock_rechecks_shutdown` | `test_signal_handling.py` | When shutdown set between first check and lock acquisition, `_embed_and_write` returns 0 |
| 5 | `test_ingest_path_resolves_tilde` | `test_signal_handling.py` | `ingest_path("~/some/path")` calls `expanduser()` — test with a temp dir under home |
| 6 | `test_ingest_path_resolves_relative` | `test_signal_handling.py` | `ingest_path("../relative/path")` calls `resolve()` |

---

## 4. Risks.MD Residual Coverage

From the security assessment, two risks remain unaddressed. These need documentation, not tests:

| Risk # | Finding | Action |
|--------|---------|--------|
| #3 (MEDIUM) | ChromaDB data exposure — no warning | Add a note to README about filesystem permissions (docs, not code) |
| #6 (MEDIUM) | No file deduplication | Documented as known limitation; future change for `--skip-existing` |

---

## 5. Test Execution Boundaries

### What NOT to test (avoid fragile tests)

1. **Actual Ollama connection** — `Settings.embed_model` is already mocked in conftest
2. **Actual ChromaDB persistence** — `EphemeralClient` in conftest
3. **Rich visual rendering** — Don't assert on specific bar characters or colours. Test
   that the callback doesn't crash and that text output appears in the right places.
4. **Signal delivery** — Can't reliably send SIGINT inside pytest. Test the handler
   logic by setting `_shutdown_requested` directly and checking CLI behaviour.
5. **Shell completion installation** — `--install-completion` is a Typer built-in;
   testing it directly requires interactive shell access.

### Concurrency test safety

Thread-based tests in pytest need care:
- Use `threading.Event` to synchronise thread start
- Use short timeouts (no `time.sleep(5)`)
- Always join threads with timeout
- Clean up module-level state (`_write_lock` state, `_embed_semaphore` count, `_shutdown_requested`) between tests

---

## 6. Implementation Order (Task Breakdown)

### Phase A: Foundation — CLI test file setup (~30 min)
- [ ] Create `tests/test_cli.py` with imports, fixtures, and `CliRunner`
- [ ] Verify all conftest fixtures apply correctly (ChromaDB + MockEmbedding + isolate_env)
- [ ] Write first smoke test: `test_version_flag`

### Phase B: CLI output tests — json mode (~45 min)
- [ ] `TestIngestCLI` — `--json` success, `--json` error, non-existent path, unsupported ext
- [ ] `TestSearchCLI` — `--json` empty, `--json` results
- [ ] `TestListCLI` — `--json` empty, `--json` with data
- [ ] `TestPrintOllamaError` — all scenarios

### Phase C: CLI output tests — Rich table mode (~30 min)
- [ ] `TestSearchCLI` — table output contains Score, Source, Text columns
- [ ] `TestListCLI` — table output contains Source, Chunks columns, total summary
- [ ] `TestSanitiseDisplayName` — all scenarios

### Phase D: CLI ingest — flags and exit codes (~30 min)
- [ ] `TestIngestCLI` — `--workers`, `--chunk-size`, `--chunk-overlap`, clamped values
- [ ] `TestEntryPoint` — `--help`, unknown subcommand, version flag
- [ ] Verify exit codes (0 on success, 1 on error)

### Phase E: Progress reporting tests (~30 min)
- [ ] `TestProgressReporting` — plain text reading/embedding/completion messages
- [ ] `TestProgressReporting` — JSON suppresses progress output

### Phase F: Concurrency & signal edge cases (~45 min)
- [ ] Concurrent write lock test in `test_ingestion_parallel.py`
- [ ] BoundedSemaphore throttling test
- [ ] Parallel pool shutdown test
- [ ] Path resolution tests (`expanduser`, `resolve`)

### Phase G: Validation & coverage (~15 min)
- [ ] `uv run pytest -m "not slow" -v` — all tests pass
- [ ] `uv run pytest -m "not slow" --cov=rag_mcp` — coverage ≥ 95%
- [ ] Check `cli.py` specifically has ≥ 90% coverage
