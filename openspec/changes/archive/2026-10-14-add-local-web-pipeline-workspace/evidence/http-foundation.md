# HTTP foundation (tasks 6.1, 6.2, 6.3)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted working tree.
Design D6, D8, D11. Specs `local-web-workspace` and `transport-separation`.

## Files

New runtime modules in `src/omrg/transports/api/`:

| File | Lines | Job |
|---|---|---|
| `__init__.py` | 6 | Empty package. Imports nothing, so `import omrg` never loads FastAPI. |
| `app.py` | 74 | `create_app(config, *, policy, engine_factory, run_service_factory)`. Registers routers in `API_ROUTERS`. |
| `lifespan.py` | 218 | `WebConfig`, `WebRuntime`, `Admission`, `RunServiceHook`, `build_lifespan`, `shutdown_runtime`, `get_runtime`. |
| `security.py` | 395 | `AccessPolicy`, `Principal`, `require_scope`, `validate_bind_host`, `redact`, `RedactingFilter`, `install_log_redaction`. |
| `middleware.py` | 87 | `GuardMiddleware`: Host, Origin, fetch metadata and query-string checks before any route. Pure ASGI. |
| `errors.py` | 83 | `error_response` and the envelope handlers. |
| `routes.py` | 186 | Health, session, credentials, roots, uploads. |
| `grants.py` | 142 | `RootGrants`, `Root`, `GrantDenied`. |
| `uploads.py` | 186 | `UploadStore`, `UploadRejected`, `DEFAULT_MAX_UPLOAD_BYTES`. |
| `static.py` | 67 | `FrontendFallback`: assets and SPA fallback as the router default. |

CLI: new `src/omrg/transports/cli/web.py` (146 lines). In `src/omrg/transports/cli/__init__.py`, the callback skips `_initialise_runtime()` when the subcommand is `web`. The import list adds `web`. The docstring names `web.py`.

Tests: `tests/unit/test_web_launch.py`, `tests/unit/test_web_security.py`, `tests/unit/test_web_files.py` (93 tests). Each module calls `pytest.importorskip("fastapi")`.

## Behaviour

### Launch and lifespan (6.1)

- `omrg web [--workspace PATH] [--port N] [--root DIR]... [--host ADDR]`. Defaults: `~/.omrg/workspace`, port 0 (a free port), host `127.0.0.1`.
- The command imports FastAPI and Uvicorn inside the function. When either is missing, it prints `pip install "omrg[web]"` and `uv sync --extra web` on stderr and exits 1. Other commands and `--help` do not import them.
- The command binds the socket first, so the real port is known for Host and Origin checks. One Uvicorn process, reload off, `lifespan="on"`, `proxy_headers=False`, `server_header=False`, `log_config=None` (logs go to the CLI's stderr handler).
- The launch URL is printed on stderr: `http://127.0.0.1:<port>/#bootstrap=<secret>`. stdout stays empty.
- The callback skips the legacy process-default installer for `web`. The lifespan builds ONE Engine through the injected `engine_factory` (default `compose.build_engine()`).
- Shutdown order (`shutdown_runtime`): close admission, call `run_service.shutdown()`, wait for admitted requests, then `engine.close()`. It is idempotent. A failing run-service start still closes the Engine.
- `omrg` with no arguments still runs the installer and starts MCP.

### Protection (6.2)

- `validate_bind_host` accepts only loopback addresses (`127.0.0.0/8`, `::1`, `localhost`). `0.0.0.0`, `::`, LAN addresses and names fail with a local-use message. The CLI exits 2. `create_app` raises `ValueError`.
- Every request needs a `Host` of `127.0.0.1`, `localhost`, `[::1]` or the bound address, with the bound port. Otherwise 400. This blocks DNS rebinding.
- On `/v1` paths: a foreign `Origin` (including `null`) gives 403. `Sec-Fetch-Site: cross-site` or `same-site` gives 403. A query key such as `token`, `bootstrap` or `access_token`, or any value with an OMRG credential prefix, gives 400.
- Bootstrap: `POST /v1/session {"bootstrap": ...}` needs the app's own Origin. The comparison is constant time. The secret works once. After 20 wrong guesses it stops working. Success sets cookie `omrg_session_<port>` with `HttpOnly; SameSite=Strict; Path=/`. Cookies ignore ports, so the name carries the port.
- Cookie-authenticated `POST`, `PUT`, `PATCH` and `DELETE` also need the app's Origin.
- Bearer credentials: `omrg_bt_<id>.<secret>`. Only the SHA-256 digest is kept. Scopes are limited to `graph`, `read` and `run`. `files`, `plugins` and `credentials` belong to the session only. Revocation takes effect on the next request.
- `require_scope(scope)` is the one dependency for every protected route, including streams. `GET /v1/health` and `POST /v1/session` are the only public `/v1` routes. A test fails when a new `/v1` route has no declared scope.
- Redaction: `redact()` removes OMRG credentials, `Bearer` values, session cookies and secret query values. `RedactingFilter` formats tracebacks, redacts them and drops `exc_info`. It also removes configured provider secrets (`compose.redaction_values()`). Unexpected errors return `{"status":"error","message":"Internal server error.","error_type":"internal"}` with no detail.
- Every response has `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` and a `frame-ancestors 'none'` CSP. API responses add `Cache-Control: no-store` and `nosniff`.

### Grants and uploads (6.3)

- `RootGrants.from_paths` resolves each `--root` with `resolve(strict=True)`. A missing path or a file fails the launch (exit 2). Root ids are `root_` plus 12 hex characters of the SHA-256 of the canonical path.
- `resolve(root_id, relative)` refuses absolute, `~` and NUL paths. It canonicalises the joined path (symlinks followed) and requires it inside the root. `check(path)` applies the same rule to an absolute path, such as one read from indexed metadata. Indexed metadata never adds a root.
- The workspace `uploads/` directory is added as a `managed` root.
- Uploads: `POST /v1/uploads` streams a raw body. The file name is in the percent-encoded `X-Upload-Name` header, so it stays out of the access log. `POST /v1/uploads/preflight {"name","size"}` checks before sending. Both need the session `files` scope.
- Preflight: plain names only (no separators, control characters, hidden names or URL schemes). The extension must be in the supplied ingestible set (`WebConfig.upload_extensions`, default `DEFAULT_INGEST_EXTENSIONS`). The store keeps no list of its own. Archives are not in that set, so they fail with 415. A declared size over the limit fails with 413.
- The limit is 50 MiB per file (`DEFAULT_MAX_UPLOAD_BYTES`). It is also enforced while streaming, so a body larger than its declared size stops at the limit.
- The body goes to `uploads/.partial/<id>.part` (mode 0600), then `os.replace` moves it to `uploads/<id>/<name>`. Any exception, disconnect or cancellation removes the partial file. Startup removes stale partial files. New directories get mode 0700.
- The response returns `id`, `name`, `size` and `sha256`. It does not return a server path.

### Static files and fallback

- `FrontendFallback` is the router default. It runs only when no route matched.
- Any `/v1` path gets the JSON envelope 404, never HTML. A missing file with an extension gets a plain 404. Other GET paths get `index.html`.
- Without built assets, `/` returns a 404 text that names `npm ci && npm run build`. The API still works.

## Test-first record

Environment for all commands: WT `.venv`, `PYTHONPATH=src`, `PDF_READER=pypdf`, `-p no:cacheprovider`.

1. Before implementation: `pytest tests/unit/test_web_launch.py tests/unit/test_web_security.py tests/unit/test_web_files.py`. Result: **3 errors during collection** (`ModuleNotFoundError: No module named 'omrg.transports.api.app'`). FAIL as expected.
2. First implementation run: **2 failed, 89 passed**. Rich markup removed `[web]` from the install hint. The no-argument test counted two installer calls, because MCP `main()` also calls `ensure_runtime_setup()` (already idempotent). Fixed the markup with `escape()`. Changed the assertion to "called".
3. After fixes: **91 passed**. After two more tests: **93 passed**.

## Mutation checks

Script: `scratchpad/mutate.py`. Each check edits one line, runs the three web test files, then restores the file.

| Id | Change | Result |
|---|---|---|
| M1 | Host check always passes | 3 failed |
| M2 | No Origin check on cookie state changes | 1 failed |
| M3 | Bootstrap secret not consumed | 1 failed |
| M4 | Bearer scope not checked | 2 failed |
| M5 | Revocation ignored | 2 failed |
| M6 | Root containment removed | 5 failed |
| M7 | Partial upload kept on failure | 3 failed |
| M8 | Streaming size limit not enforced | 1 failed |
| M9 | Fallback serves HTML for `/v1` | 4 failed |
| M10 | Engine closed before active work ends | 1 failed |
| M11 | `web` runs the legacy installer | 2 failed |
| M12 | Redaction is a no-op | 2 failed |
| M13 | Query-string credentials accepted | 1 failed |

## Related suites

Command: the three web files plus `tests/test_cli.py tests/test_cli_profile.py tests/test_file_size_ceiling.py tests/test_pipeline_import_boundaries.py tests/test_openapi_conformance.py tests/test_answer_transport_cli.py tests/test_no_global_settings_reads.py tests/test_contract_coverage.py tests/test_mcp_tools.py`.

Result: **415 passed, 5 skipped**.

Finding during this run: the no-argument MCP test let `mcp.main()` call `logging.basicConfig(force=True)` on a pytest capture stream. Later CLI JSON tests then saw "Logging error" text on stderr. The test now patches `logging.basicConfig`, as `tests/test_mcp_tools.py` does.

Static checks:

- `ruff format` and `ruff check` on all new and changed files: clean.
- `lint-imports`: **12 kept, 0 broken**. `omrg.core` imports nothing from `transports.api`.
- Largest new file: `security.py`, 395 lines.

Branch coverage of the new modules (web tests only): `app.py` 100%, `middleware.py` 99%, `static.py` 95%, `grants.py` 94%, `routes.py` 94%, `lifespan.py` 92%, `uploads.py` 92%, `security.py` 90%, `errors.py` 78% before the validation test was added, `cli/web.py` 73% (the real `_serve` path is covered by the smoke run below, not by unit tests).

## Real-socket smoke

Script: `scratchpad/smoke.py`. It runs `run_cli()` with `omrg web`, the real `_bind_socket` and Uvicorn, and a fake Engine factory (no models). A thread sends requests, then SIGINT.

| Request | Result |
|---|---|
| `GET /v1/health` | 200 `application/json` `{"status":"ok","ready":true}` |
| `GET /v1/nope` | 404 `application/json` envelope |
| `GET /` and `GET /library` | 200 `text/html` (the built `index.html`) |
| `GET /v1/session?token=omrg_bt_x.y` | 400 envelope. The access log shows `?token=***`. |
| `GET /v1/health` with `Host: evil.example` | 400 envelope |
| SIGINT | "Waiting for application shutdown", fake Engine closed, "Application shutdown complete" |

The launch URL appeared once on stderr with the bootstrap secret in the fragment.

## Deviations and open points

1. **`--host` option added.** The task lists `--workspace`, `--port` and `--root`. `--host` lets a user ask for `::1` or `localhost`, and gives the "remote bind requested" scenario a real input. Non-loopback values fail.
2. **Default workspace `~/.omrg/workspace`.** No earlier document fixes the location. Change it in `cli/web.py:default_workspace()` if the lead prefers another.
3. **Upload extension set.** `Engine` has no public accessor for resolved settings, so uploads use `WebConfig.upload_extensions` (default `DEFAULT_INGEST_EXTENSIONS`). A collection profile such as `codebase` adds `.py`. Ingestion still applies the collection's own set later. To use profile-resolved sets at upload time, add a public Engine accessor (owner of `engine.py`; `tests/test_engine.py` pins the public method set), then pass it into `WebConfig` or a resolver.
4. **Run service not wired.** `core/workspace/service.py` (`RunService`) appeared during this task, but no composition builds it (it needs an executor, an admitter and an artefact store). The hook is `create_app(..., run_service_factory=lambda runtime: RunService(...))`. The lifespan calls `await service.start()` after the Engine is built and `await service.shutdown()` before `engine.close()`. `RunService.start()` and `shutdown()` match `RunServiceHook`.
5. **Stream endpoints (task 6.6).** `shutdown_runtime` waits for every request inside `runtime.admission.enter()`. An SSE generator must end when `runtime.admission.is_open` becomes false, or must not hold admission, otherwise shutdown waits for it. Uploads hold admission while they stream.
6. **Static assets.** The fallback uses Starlette `StaticFiles(follow_symlink=False)` for path containment. The wheel force-include and the release check stay with task 6.8.
7. **OpenAPI.** Task 6.7 must declare: `GET /v1/health` (public), `POST /v1/session` (public, bootstrap), `GET /v1/session`, `POST|GET /v1/credentials`, `DELETE /v1/credentials/{credential_id}`, `GET /v1/roots`, `POST /v1/uploads` (raw body, `X-Upload-Name` header, 201/400/413/415), `POST /v1/uploads/preflight`, the cookie and bearer security schemes, and the scopes. The current document still says "no runtime HTTP code exists yet" and declares a JWT bearer.

## Not run

- Browser walk-through of the bootstrap fragment flow. The frontend does not yet read `#bootstrap=` and post it (task 7.x). Required client behaviour: read the fragment, remove it with `history.replaceState`, then `POST /v1/session` with `credentials: "same-origin"`.
- A real `compose.build_engine()` start. It needs the configured embedding model. The fake factory covers ownership and order.
- Full test suite and `local_ci.sh` (not permitted for this agent).
