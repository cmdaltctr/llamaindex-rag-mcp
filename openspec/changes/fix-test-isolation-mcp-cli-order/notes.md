# Diagnosis notes — fix-test-isolation-mcp-cli-order (tasks 1.1–1.3)

Worktree: `feat/fix-test-isolation-mcp-cli-order` @ `8f9305b`.
Environment: pytest 9.1.1, Python 3.12.10 (uv cpython), macOS darwin, default
capture (fd+sys). Scratch instrumentation lived in `/tmp` only; no repo file
was modified for this diagnosis.

Line numbers for `tests/test_mcp_tools.py` refer to base commit `8f9305b`;
the fix adds lines near the file start and shifts them. Local absolute paths
are shortened: `<worktree>` is the change worktree, `<uv-dir>` the uv home.

## 1.1 Failing output

Canonical failing command (default capture, exit 1):

```
LOCAL_BACKEND=ollama uv run pytest tests/test_mcp_tools.py \
  "tests/test_cli.py::TestIngestCLI::test_ingest_json_output"
```

Result tail:

```
FAILED tests/test_cli.py::TestIngestCLI::test_ingest_json_output
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

The CLI test's local shows `result.output` begins with the logging error
report and ends with the valid JSON document (pytest truncates the middle of
the repr):

```
s = '--- Logging error ---\nTraceback (most recent call last):\n
  File "<uv-dir>/python/cpython-3.12.1...p_seconds":
  0.002881124964915216,\n    "total_seconds": 0.017136290902271867\n  },
\n  "peak_rss_bytes": 754417664\n}\n'
```

Verbatim `--- Logging error ---` block. Captured with the same ordered pair
plus `-s` so logging's error report prints to the real terminal unmodified.
The failing handler is the stdlib `logging.StreamHandler` (frame:
`logging/__init__.py:1163 StreamHandler.emit`); the exception is
`ValueError: I/O operation on closed file.` The "Call stack" section names
the code whose `logger.warning` triggered the emit. In the default-capture
run the same canonical text is written into the CliRunner buffer instead
(because `logging.handleError` writes to the *current* `sys.stderr`, which
inside `runner.invoke` is the runner's merged capture), which is how it
prepends itself to `result.output`:

```text
--- Logging error ---
Traceback (most recent call last):
  File "<uv-dir>/python/cpython-3.12.10-macos-aarch64-none/lib/python3.12/logging/__init__.py", line 1163, in emit
    stream.write(msg + self.terminator)
ValueError: I/O operation on closed file.
Call stack:
  File "<worktree>/.venv/bin/pytest", line 10, in <module>
    sys.exit(_console_main())
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/config/__init__.py", line 253, in _console_main
    code = _main(prog=_get_prog_name(sys.argv))
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/config/__init__.py", line 229, in _main
    ret: ExitCode | int = config.hook.pytest_cmdline_main(config=config)
```
```text
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/main.py", line 377, in pytest_cmdline_main
    return wrap_session(config, _main)
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/main.py", line 330, in wrap_session
    session.exitstatus = doit(config, session) or 0
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/main.py", line 384, in _main
    config.hook.pytest_runtestloop(session=session)
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/main.py", line 408, in pytest_runtestloop
    item.config.hook.pytest_runtest_protocol(item=item, nextitem=nextitem)
```
```text
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/runner.py", line 118, in pytest_runtest_protocol
    runtestprotocol(item, nextitem=nextitem)
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/runner.py", line 139, in runtestprotocol
    reports.append(call_and_report(item, "call", log))
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/runner.py", line 249, in call_and_report
    call = CallInfo.from_call(
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/runner.py", line 361, in from_call
    result: TResult | None = func()
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/runner.py", line 250, in <lambda>
    lambda: runtest_hook(item=item, **kwds),
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
```
```text
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_manager.py", line 120, in _hookexec
    return self._inner_hookexec(hook_name, methods, kwargs, firstresult)
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/runner.py", line 184, in pytest_runtest_call
    item.runtest()
  File "<worktree>/.venv/lib/python3.12/site-packages/pytest_asyncio/plugin.py", line 569, in runtest
    super().runtest()
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/python.py", line 1707, in runtest
    self.ihook.pytest_pyfunc_call(pyfuncitem=self)
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_hooks.py", line 512, in __call__
    return self._hookexec(self.name, self._hookimpls.copy(), kwargs, firstresult)
  File "<worktree>/.venv/lib/python3.12/site-packages/pluggy/_callers.py", line 121, in _multicall
    res = hook_impl.function(*args)
  File "<worktree>/.venv/lib/python3.12/site-packages/_pytest/python.py", line 167, in pytest_pyfunc_call
    result = testfunction(**testargs)
```
```text
  File "<worktree>/.venv/lib/python3.12/site-packages/pytest_asyncio/plugin.py", line 905, in inner
    runner.run(coro, context=context)
  File "<uv-dir>/python/cpython-3.12.10-macos-aarch64-none/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
  File "<uv-dir>/python/cpython-3.12.10-macos-aarch64-none/lib/python3.12/asyncio/base_events.py", line 678, in run_until_complete
    self.run_forever()
  File "<uv-dir>/python/cpython-3.12.10-macos-aarch64-none/lib/python3.12/asyncio/base_events.py", line 645, in run_forever
    self._run_once()
  File "<uv-dir>/python/cpython-3.12.10-macos-aarch64-none/lib/python3.12/asyncio/base_events.py", line 1999, in _run_once
    handle._run()
  File "<uv-dir>/python/cpython-3.12.10-macos-aarch64-none/lib/python3.12/asyncio/events.py", line 88, in _run
    self._context.run(self._callback, *self._args)
  File "<worktree>/tests/test_mcp_tools.py", line 750, in test_search_documents_returns_filter_matches
    await client.call_tool(
```
```text
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/client/client.py", line 812, in call_tool
    result = await self._drive_input_required(await retry(input_responses, request_state), retry)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/client/client.py", line 799, in retry
    return await self.session.call_tool(
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/client/session.py", line 1048, in call_tool
    result = await self.send_request(
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/shared/direct_dispatcher.py", line 149, in send_raw_request
    return await self._peer._dispatch_request(method, params, opts)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/shared/direct_dispatcher.py", line 266, in _dispatch_request
    return await self._on_request(dctx, method, params)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/runner.py", line 863, in handle
    return await serve_one(
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/runner.py", line 836, in serve_one
    return await runner.on_request(dctx, method, params)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/runner.py", line 230, in _on_request
    result = _dump_result(await call(ctx))
```
```text
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/_otel.py", line 44, in __call__
    result = await call_next(ctx)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/request_state.py", line 361, in __call__
    result = await call_next(ctx)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/runner.py", line 217, in _inner
    result = await entry.handler(ctx, typed_params)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/mcpserver/server.py", line 420, in _handle_call_tool
    return await self.call_tool(params.name, params.arguments or {}, context)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/mcpserver/server.py", line 504, in call_tool
    return await self._tool_manager.call_tool(name, arguments, context, convert_result=True)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/mcpserver/tools/tool_manager.py", line 87, in call_tool
    return await tool.run(arguments, context, convert_result=convert_result)
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/mcpserver/tools/base.py", line 152, in run
    result = await self.fn_metadata.call_fn_with_arg_validation(
```
```text
  File "<worktree>/.venv/lib/python3.12/site-packages/mcp/server/mcpserver/utilities/func_metadata.py", line 106, in call_fn_with_arg_validation
    return await fn(**arguments_parsed_dict)
  File "<worktree>/src/rag_mcp/transports/mcp.py", line 152, in ingest_documents
    return await ingest_path_async(
  File "<worktree>/src/rag_mcp/core/ingestion/pipeline.py", line 168, in ingest_path_async
    inventory = detect_file_types(str(path_obj))
  File "<worktree>/src/rag_mcp/core/codebase/codebase_map.py", line 218, in detect_file_types
    logger.warning("Magika CLI not installed; using suffix-based detection")
Message: 'Magika CLI not installed; using suffix-based detection'
Arguments: ()
```

(Note: in the `-s` run this first block fires during
`test_search_documents_returns_filter_matches` — an in-file victim of the
already-dead handler. In the default-capture canonical run the equivalent
block is what lands inside `result.output` of the CLI test, whose ingest
path emits the same `codebase_map.py:218` warning — see "Captured log call"
in the failure report.)

## 1.2 Bisection

Method: scratch plugin `/tmp/handler_snapshot.py` (no repo file touched),
loaded with `PYTHONPATH=/tmp ... -p handler_snapshot`. It appends to
`/tmp/handler_snapshots.txt` a snapshot of `logging.root.handlers`
(class, level, id, stream repr, `closed`, identity vs current
`sys.stderr` / `sys.__stderr__`) at session start, after each test's
teardown (`pytest_runtest_logreport` when `when == "teardown"`), and at
session finish.

Step 1 — full file, snapshot diff. Ran the whole `tests/test_mcp_tools.py`
alone (passes, exit 0). Diff of the between-tests snapshots:

- Session start: root = pytest's `_LiveLoggingNullHandler` +
  `_FileHandler(stream=/dev/null)`. Root level 30 (stdlib default
  WARNING).
- **NEW after `test_main_calls_mcp_run`** (n drops 2→1):
  `logging.StreamHandler lvl=0` holding
  `<_io.TextIOWrapper name="<_io.FileIO name=8 mode='rb+' closefd=True>" mode='r+' encoding='utf-8'>`
  — pytest's per-test fd-capture temp file. `closed=False` at that point.
  This is `force=True` stripping pytest's two handlers and installing the
  production one.
- After the *next* test `test_main_reports_runtime_setup_error`: root
  still `n=1` `logging.StreamHandler`, stream now
  `<_io.TextIOWrapper encoding='UTF-8'>` with **`closed=True`** — and it
  stays on root, closed, through every later snapshot to session finish.
  (The id stayed identical to the previous handler's; that is CPython
  address reuse — `force=True` in the second test removed+closed the
  first handler and the replacement was allocated at the same address.
  The stream object differs, proving it is a different handler.)

Step 2 — solo runs isolate each candidate:

- `tests/test_mcp_tools.py::test_main_calls_mcp_run` alone: leaves ONE
  `logging.StreamHandler` whose stream is the fd-capture temp file,
  `closed=False` even at session finish (the temp file object is not
  closed promptly; it lingers).
- `tests/test_mcp_tools.py::test_main_reports_runtime_setup_error` alone:
  leaves ONE `logging.StreamHandler` whose stream is
  `<_io.TextIOWrapper encoding='UTF-8'>` with `closed=True` already at
  after-teardown — this test uses the `capsys` fixture, so `sys.stderr`
  at `main()` time is pytest's sys-capture replacement (a
  `_pytest.capture` `CaptureIO`, a TextIOWrapper over a BytesIO), which
  `SysCapture.done()` closes at fixture teardown.

Step 3 — pair each candidate with the CLI JSON test:

| Prefix (in order) | CLI JSON test result | Handler state entering CLI test |
|---|---|---|
| `test_main_calls_mcp_run` | **2 passed** | StreamHandler, temp file, `closed=False` — emits succeed, no contamination |
| `test_main_reports_runtime_setup_error` | **1 failed** (JSONDecodeError, `--- Logging error ---` in `result.output`) | StreamHandler, capsys stream, `closed=True` |
| full `tests/test_mcp_tools.py` | 1 failed (canonical pair) | StreamHandler, capsys stream, `closed=True` |

Minimal reproducing pair (exit 1):

```
LOCAL_BACKEND=ollama uv run pytest \
  "tests/test_mcp_tools.py::test_main_reports_runtime_setup_error" \
  "tests/test_cli.py::TestIngestCLI::test_ingest_json_output"
```

Pinned test: **`tests/test_mcp_tools.py::test_main_reports_runtime_setup_error`**
(def at `tests/test_mcp_tools.py:647`; `main()` called at :659).

Installing call path:

```
test_main_reports_runtime_setup_error            tests/test_mcp_tools.py:647
  └─ from rag_mcp.transports.mcp import main     tests/test_mcp_tools.py:657
  └─ main()                                      tests/test_mcp_tools.py:659
      └─ logging.basicConfig(                    src/rag_mcp/transports/mcp.py:469
             level=logging.WARNING, format=..., datefmt=...,
             stream=sys.stderr, force=True)      src/rag_mcp/transports/mcp.py:470-474
```

At that moment `sys.stderr` is the capsys replacement object, so
`basicConfig(force=True)` (a) removes and closes pytest's two root
handlers and (b) installs `StreamHandler(<capsys CaptureIO>)` on
`logging.root`. Nothing undoes this:

- the test's `patch(...)` contexts restore only what they patched —
  `logging.basicConfig` is not patched in this test;
- pytest's logging plugin (`_pytest.logging.catching_logs`) only removes
  its own per-test `LogCaptureHandler`; foreign handlers added during a
  test persist;
- capsys teardown restores `sys.stderr` and closes the replacement
  stream — the handler now holds a closed stream on root for the rest of
  the session.

Co-leaker (does not fail the pair solo, but leaks in the ordered run):
`test_main_calls_mcp_run` (`tests/test_mcp_tools.py:629`) also calls real
`main()`; its handler binds the per-test fd-capture temp file, which is
still open when the next test starts, so the CLI pair passes. In the
ordered full-file run its handler is replaced (closed) by the pinned
test's own `force=True` reconfiguration.

Proposal lead, refined: three tests invoke `main()` — :629, :647, and
:1096. Only `test_main_settings_failure_prints_reason` (:1096) stubs
`logging.basicConfig` (tests/test_mcp_tools.py:1112). The failing pair is
caused by :647; :629 is a latent second leak. Module import time is clean
(zero `--- Logging error ---` before `main()` tests; no handler appears
at session start beyond pytest's own).

## 1.3 Stream confirmation

Snapshot evidence (after the CLI test in the minimal pair, and from the
pinned test's teardown):

```
HANDLER logging.StreamHandler lvl=0 stream=<_io.TextIOWrapper encoding='UTF-8'>
  closed=True is_cur_sys_stderr=False is_dunder=False
```

- `closed=True` — the held stream is closed; `StreamHandler.emit` raises
  `ValueError: I/O operation on closed file` (verbatim block in 1.1).
- `is_cur_sys_stderr=False` — the stream is not the `sys.stderr` in effect
  when later tests run (pytest restored the real one after capsys
  teardown).
- `is_dunder=False` — it is also not the process's original
  `sys.__stderr__`.
- Stream identity: closed `TextIOWrapper` repr with `encoding='UTF-8'`
  and no name matches `_pytest.capture`'s sys-capture replacement for
  `capsys` (`CaptureIO`, a `TextIOWrapper` over `BytesIO`), distinct from
  the fd-capture temp-file wrapper the co-leaker at :629 captured
  (`name="<_io.FileIO name=8 mode='rb+'>"`).

Failure mechanics into `result.output`: during the CLI test,
`detect_file_types` (`src/rag_mcp/core/codebase/codebase_map.py:218`)
emits `logger.warning('Magika CLI not installed; using suffix-based
detection')`, which propagates to root; the dead handler's `emit`
raises; `logging.handleError` writes the `--- Logging error ---` report
to the *current* `sys.stderr` — which inside `runner.invoke(app, ...)`
is Typer CliRunner's merged capture — so the report is prepended to
`result.output` and `json.loads` fails at char 0.

## Beyond test isolation? (input for task 2.2)

No production logging defect is implicated. Both configuration sites are
deliberate process-entry-point behaviour, each run once per process:

- `src/rag_mcp/transports/mcp.py:465-475` — `main()` forces root logging
  to `sys.stderr` so the stdio MCP protocol channel (stdout) stays clean.
- `src/rag_mcp/transports/cli/__init__.py:120-145` — `_setup_logging()`
  installs the RichHandler (stderr) with `force=True`; its only caller is
  `run_cli()` (`cli/__init__.py:207-216`), the console-script entry
  point. CLI tests bypass it via `runner.invoke(app, ...)`, which is why
  nothing reconfigures root logging to displace the leaked handler
  mid-test.

The blast radius is in-process invocation of these entry points while a
test harness owns the streams — i.e. test isolation, not production.
One latent observation for the record: any *embedding* use of
`rag_mcp.transports.mcp.main` / `run_cli` inside another host process
would silently reconfigure that host's global logging (`force=True`);
that is accepted entry-point semantics, not a bug.

## Unexpected findings

1. The co-leaker at :629 produces a handler that does NOT close promptly
   (fd-capture temp file stays open into later tests), so single-test
   attribution via "run each test + CLI test" alone would have missed the
   leak at :629 — only the handler-snapshot diff exposed it.
2. `id()` reuse made the full-file snapshot look like one handler was
   "flipping" closed; the stream repr change proves it was replaced by a
   second `force=True` call.
3. The `-s` run shows five `--- Logging error ---` blocks *inside*
   `tests/test_mcp_tools.py` itself — later tests in that file are
   already victims of the dead handler, even though the file passes.
