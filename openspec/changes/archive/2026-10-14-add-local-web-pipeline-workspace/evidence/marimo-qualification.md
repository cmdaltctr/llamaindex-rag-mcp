# marimo qualification (task 8.4)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree. macOS (Darwin 27, arm64).
Design D10. Spec `notebook-plugins`. Inputs: the unconfirmed list in `plugins.md`, the connection-file follow-up in `experiment-transport.md`.

**Verdict: PASS for marimo 0.25.1.** The manifest range is now `>=0.25.1,<0.26.0`. No launch flag changed.
The starter notebook did not parse in real marimo. It is fixed (see section 3).

`<S>` below is the scratchpad folder `scratchpad/marimo-q/`. Throwaway HOME: `<S>/home`. Tokens never appear in this file.

## 1. Installation (user-approved, outside OMRG)

| Command | Output |
|---|---|
| `uv --version` | `uv 0.12.18 (01cb90c1a 2026-09-22 aarch64-apple-darwin)` |
| `uv tool install marimo` | `+ marimo==0.25.1` ... `Installed 1 executable: marimo` |
| `uv tool dir` | `/Users/aizat/.local/share/uv/tools` |
| `which marimo` | `/Users/aizat/.local/bin/marimo` (symlink to `/Users/aizat/.local/share/uv/tools/marimo/bin/marimo`) |
| `uv tool list` | `marimo v0.25.1` |
| `cd WT && .venv/bin/python -c "import marimo"` | `ModuleNotFoundError: No module named 'marimo'` (OMRG env untouched) |
| `shasum -a 256 uv.lock pyproject.toml` before and after all updates | identical (`shasum -c`: both `OK`) |

The only `marimo` strings in the `pyproject.toml` diff are the pre-existing import-linter forbidden-module entries.
Side effect: the first `marimo --version` created an empty `~/.config/marimo/marimo.toml` (marimo's own XDG user config). Nothing else in the real HOME changed. `~/.marimo.toml` does not exist and was not touched.

## 2. Unconfirmed items from `plugins.md`

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | `marimo --version` output and probe parsing | CONFIRMED | Output is exactly `0.25.1` (exit 0). OMRG recheck: `"marimo 0.25.1 is compatible"`, `version: "0.25.1"`. |
| 2 | `edit` flags | CONFIRMED, no change | `marimo edit --help` lists `-p, --port`, `--host` (default `127.0.0.1`), `--headless`, `--token / --no-token` (default token), `--token-password-file` ("Path to file containing token password, or '-' for stdin"), `--skip-update-check`, `--no-sandbox` ("Never run in a sandbox, and never prompt to"). Full text: `<S>/edit-help.txt`. |
| 3 | Launch-dir `.marimo.toml` over `~/.marimo.toml` | CONFIRMED | See 2a. |
| 4 | Notebook header can override | CHANGED (safer than documented) | Header `runtime.auto_instantiate = true` is ignored with a warning. See 2b. |
| 5 | `pyproject.toml` can override | CONFIRMED (limit) | A `pyproject.toml` in the notebook directory or any parent wins over the launch-dir file. See 2b. |
| 6 | Browser login URL / token mechanism | CONFIRMED | See 2c. |
| 7 | `OMRG_CONNECTION_FILE` reaches the kernel | CONFIRMED | See 2d and section 4. |
| 8 | Update check disabled | CONFIRMED | `marimo/_cli/cli.py:589`: `if not skip_update_check and os.getenv("MARIMO_SKIP_UPDATE_CHECK") != "1": ... check_for_updates(...)`. `lsof -a -p <pgid> -iTCP` on the OMRG-started editor showed only the loopback listener, no outbound connection. |
| 9 | Automatic package install disabled | CONFIRMED | `--no-sandbox` stops the uv sandbox that installs PEP 723 dependencies. Package installs exist only behind authenticated endpoints (`/api/packages/add`, `/remove`, `/sync`) that the UI calls after a user action. `PackageManagementConfig` has no auto-install switch (`manager` only). |
| 10 | Busy `--port` | CONFIRMED | marimo does not pick another port. With a listener on 127.0.0.1:2795: `ERROR: [Errno 48] error while attempting to bind on address ('127.0.0.1', 2795): [errno 48] address already in use`, then exit. OMRG's port pre-check stays required. |
| 11 | Tested range | CHANGED | `>=0.25.0,<0.26.0` -> `>=0.25.1,<0.26.0`. Only 0.25.1 had the full behaviour check. 0.25.0 passed the probe only. |

### 2a. Configuration precedence (throwaway HOME)

`<S>/home/.marimo.toml` (conflicting user config): `auto_instantiate = true`, `on_cell_change = "autorun"`.
`<S>/launch/.marimo.toml` (what OMRG writes): `auto_instantiate = false`, `on_cell_change = "lazy"`.

```text
$ cd <S>/empty  && env -i HOME=<S>/home PATH=/usr/bin:/bin marimo config show
User config from <S>/home/.marimo.toml ... on_cell_change = "autorun" ... auto_instantiate = true
$ cd <S>/launch && env -i HOME=<S>/home PATH=/usr/bin:/bin marimo config show
User config from <S>/launch/.marimo.toml ... on_cell_change = "lazy" ... auto_instantiate = false
```

marimo picks ONE user config file (cwd first). It does not merge the two.

Behaviour check with a probe notebook (`<S>/nb1/probe.py`, one cell that writes `ran.marker` with `os.environ["OMRG_CONNECTION_FILE"]`), launched with the manifest's exact flags and opened in Chrome (isolated context):

| Launch cwd | Served config (`GET /` after login) | Marker after the browser connected |
|---|---|---|
| `<S>/launch` (OMRG file) | `auto_instantiate: false`, `on_cell_change: "lazy"` | absent (nothing ran) |
| `<S>/empty` (control, user config only) | `auto_instantiate: true` | present (`control`): the cell ran at startup |

The control proves the check can detect startup execution.

### 2b. Notebook header and `pyproject.toml` (both launched from `<S>/launch`)

| Notebook | Marker after connect | marimo log |
|---|---|---|
| `nb2/probe.py` with PEP 723 header `[tool.marimo.runtime] auto_instantiate = true` | absent | `tool.marimo.runtime.auto_instantiate in script metadata is ignored for security reasons` |
| `nb3/probe.py` beside `pyproject.toml` with `[tool.marimo.runtime] auto_instantiate = true` | present (`pyproject`) | none |

Source (`marimo/_config/reader.py`): `ALLOWED_SCRIPT_CONFIG_TOP_KEYS` allows `runtime`, but `runtime.auto_instantiate`, `experimental.isolate_apps` and `display.custom_css` are stripped from script metadata.
A header can still set `runtime.on_cell_change` (source reading, not run).
`find_nearest_pyproject_toml` walks from the notebook directory up to the filesystem root. Config order (`manager.py`): user, project (`pyproject.toml`), script, environment, security.
The served page shows the user config only, so the page value is not proof of the effective value. The marker test is.

### 2c. Login and token

Launch output (token replaced): `URL: http://localhost:2799?access_token=<TOKEN>`. marimo prints the token to its own stdout. The OMRG launcher keeps output in memory and redacts it (8.3).

| Request to the editor | Result |
|---|---|
| `GET /` without token | 303 to `/auth/login?next=%2F` |
| `GET /?access_token=wrong` | 303 to `/auth/login?...` |
| `GET /?access_token=<right>` | 303 to `/`, sets a session cookie |
| `GET /` with that cookie | 200 |
| `POST /api/kernel/run` without session | 401 |
| `GET http://192.168.0.45:2799/` (LAN address) | connection refused (curl exit 7); `lsof`: `TCP 127.0.0.1:2799 (LISTEN)` |

OMRG returns `url_without_token: "http://127.0.0.1:2719/"` and the token once in the body. A client builds `<url>?access_token=<token>`; marimo then removes the token from the address bar by redirect.

### 2d. Environment reaches the kernel

Probe launch with `OMRG_CONNECTION_FILE=<S>/launch/fake_conn.json` and `auto_instantiate=false`. No marker at connect. After an explicit cell run (Shift+Enter), `ran.marker` held `<S>/launch/fake_conn.json`.
Process group of a marimo editor: the server process and a `multiprocessing.resource_tracker` child, same pgid.

## 3. Starter notebook against real marimo

| Step | Command | Result |
|---|---|---|
| Before | `marimo check plugins/marimo/starter_notebook.py` | `Failed to parse: ... (not a valid notebook)`, exit 1 |
| Cause | marimo's parser (`_ast/parse.py`, `parse_import`) | Header must be docstring, `import marimo`, `__generated_with`, `app = marimo.App(...)`. The `try: import marimo / except ImportError:` stand-in block is an "unexpected statement". |
| Test first | new assertion in `test_notebook_imports_without_marimo_and_keeps_explicit_run_controls` (first four top-level statements are `Expr, Import, Assign, Assign`, import is `marimo`) | old notebook: 1 failed, 24 passed |
| Fix | remove the stand-in block, plain `import marimo`; `marimo check --fix` dedented the Markdown cell | `marimo check --strict`: exit 0, no warnings |
| Test loader | `load_notebook` now injects a stand-in `marimo` module (`_StubApp`) instead of blocking marimo | 25 passed |

The notebook is 496 lines (was 529). The helpers stay standard-library only. Plain `python starter_notebook.py` without marimo now fails at `import marimo`; that is acceptable because the file is run by marimo.

## 4. End to end through OMRG's real launcher path

Server: the scratchpad launcher from `end-to-end.md` (`scratchpad/e2e/launch.py`: real `create_app`, LanceDB, hashed fake embedder, fake LLM, no network), started as
`env -i HOME=<S>/home PATH=/Users/aizat/.local/bin:/usr/bin:/bin PYTHONPATH=src PDF_READER=pypdf HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python <e2e>/launch.py <S>/run2`.
`<S>/home/.marimo.toml` still held the conflicting `auto_instantiate = true`. Client: `<S>/qual_client.py` (stdlib, never prints a secret).

| Step | Result |
|---|---|
| `GET /v1/plugins` before | `plugins: []`, install hint, trust notice |
| `POST /v1/plugins` (shipped manifest, `/Users/aizat/.local/bin/marimo`, `approved: true`) | 201, `unchecked` |
| `POST /v1/plugins/marimo/recheck` | 200, `compatible`, `"marimo 0.25.1 is compatible"` |
| `POST /v1/experiments` | 201, context `exp_df34e52b95f8e89d` |
| `POST /v1/plugins/marimo/editors` (`consent: true`) | 201, `url_without_token: http://127.0.0.1:2719/`, `token_delivery.method: response_body_once` |
| `GET /v1/credentials` | one `notebook editor` credential, bound to the context |
| argv (`ps`) | `marimo edit <ws>/starter_notebook.py --headless --host 127.0.0.1 --port 2719 --token-password-file <launch-dir>/access-token --skip-update-check --no-sandbox` |
| Editor env (`ps eww`) | `PATH`, `HOME`, `OMRG_CONNECTION_FILE=<workspace>/run/editors/launch-*/omrg_connection.json`; no provider key, no token |
| Launch dir | mode 700; `.marimo.toml`, `access-token`, `omrg_connection.json`, `omrg-api-token`, all mode 600; not in the experiment workspace |
| Editor auth | no token 303 login; wrong token 303 login; right token 303 `/` + cookie; cookie 200 |
| Browser opens the notebook | `GET /v1/runs`: 0 runs; server log: no `/v1/pipeline-templates`, no `POST /v1/runs` |
| Run the guarded cell (lazy mode runs its ancestors) | connection cell printed `Server http://127.0.0.1:56178, experiment context exp_df34e52b95f8e89d`; `GET /v1/pipeline-templates` 200 with the bound bearer; `mo.stop` showed "Nothing runs before that"; 0 runs |
| Change the query parameter | 0 runs, no `POST /v1/pipelines` |
| Press **Run graph**, then run the stale cell | `POST /v1/pipelines` 201, `POST .../revisions` 201, `POST /v1/runs` 202; run `7a3eafe4a9f34889b7548539951e0a85` `succeeded` in context `exp_df34e52b95f8e89d`; checkpoint `output/runs/search-7a3eafe4….json` with `backend`, `effective_settings`, `graph_revision`, `index_identity 2789ec2d3bf19f8d`, `inputs`, `outputs` |
| Token leak check | editor token and API token: 0 matches in the checkpoint, in `__marimo__/session/starter_notebook.py.json` and in the server log |
| `DELETE /v1/plugin-editors/{launch_id}` | 200 `stopped: true`; `pgrep -g <pgid>`: none; port 2719 free; launch dir gone; credential `revoked: true`; old API token `GET /v1/session` 401; notebook and `output/` kept |

Note: with `on_cell_change = "lazy"`, pressing **Run graph** marks the run cell stale. The user runs it (cell run button or Shift+Enter). This is the intended explicit control.

## 5. Independent update: stop -> update -> recheck -> start

The manifest edit (range minimum) came first. Before re-registration: `status: needs_approval`, `"manifest ... changed since approval; review it and register it again"`. Recheck ran nothing. Re-registration then recheck: `compatible`.

| Step | Command | OMRG result |
|---|---|---|
| Upgrade at latest | `uv tool upgrade marimo` | `Nothing to upgrade` |
| Simulate an update | `uv tool install marimo==0.25.0` (`- marimo==0.25.1`, `+ marimo==0.25.0`) | `GET /v1/plugins`: `unchecked`, `"/Users/aizat/.local/bin/marimo changed since it was last checked; recheck it before launch"` |
| Recheck | `POST .../recheck` | `incompatible`, `"marimo 0.25.0 is outside the tested range >=0.25.1,<0.26.0. Install a supported version outside OMRG, or update the plugin manifest, then recheck."` |
| Open while incompatible | `POST .../editors` | 409 with the same message; no editor process |
| Upgrade | `uv tool upgrade marimo` | `Nothing to upgrade` + hint: pinned by the exact install; use `uv tool install marimo@latest` |
| Upgrade (pinned case) | `uv tool install marimo@latest` (`- 0.25.0`, `+ 0.25.1`) | `unchecked` (executable changed) |
| Recheck | `POST .../recheck` | `compatible`, `0.25.1` |
| Start | `POST .../editors` | 201, editor on 2719 with the manifest flags |
| Stop by app shutdown | SIGINT to the server | "Application shutdown complete"; editor group gone; `run/editors/` empty |

The shim `~/.local/share/uv/tools/marimo/bin/marimo` kept its content (same SHA-256, size 333) across versions. Only its mtime changed. OMRG's identity check caught the mtime change, and `open` always rechecks first, so a same-content shim cannot hide a version change.
No OMRG reinstall, `uv sync` or lock change happened (`uv.lock`, `pyproject.toml` SHA-256 unchanged; `import marimo` still fails in `.venv`).

## 6. Files changed

| File | Change |
|---|---|
| `plugins/marimo/manifest.json` | `plugin_version` 0.2.0; `tested_versions.minimum` 0.25.1; description no longer says provisional. Flags unchanged. |
| `plugins/marimo/starter_notebook.py` | Canonical marimo header (stand-in removed); Markdown cell dedented by `marimo check --fix`. |
| `tests/unit/test_starter_notebook.py` | Loader injects a stand-in `marimo` module; new header-layout assertion. |
| `plugins/marimo/README.md` | Status, limits, ports and update sections rewritten from the confirmed results. |
| `docs/guides/notebooks.md` | "Not yet confirmed" replaced by "What task 8.4 confirmed"; pinned-install note in the update procedure. |

## 7. Tests and checks

`cd WT && PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider ...`

| Command (files) | Result |
|---|---|
| `test_starter_notebook.py` baseline | 25 passed |
| same, new assertion, old notebook | 1 failed, 24 passed |
| same, fixed notebook | 25 passed |
| `-m "not slow" test_notebooks_guide.py test_plugin_marimo_manifest.py test_process_launcher_editor.py` after the range edit, before the guide edit | 1 failed (`test_cited_ports_variables_and_range_match_the_code`), 16 passed |
| `-m "not slow" test_notebooks_guide.py test_plugin_*.py test_web_plugins*.py test_starter_notebook.py test_process_launcher*.py tests/test_file_size_ceiling.py tests/test_docs_references.py` | **209 passed**, 1 deselected |
| `ruff check` / `ruff format --check` (notebook, test) | clean |
| `marimo check --strict plugins/marimo/starter_notebook.py` | exit 0 |

Not run: the full suite, `tests/test_clean_base_tripwire.py`, the slow wheel test.

## 8. Clean-up

`pgrep -fl "marimo|launch.py|uvicorn"`: none. `lsof -iTCP:2719-2799 -sTCP:LISTEN`: none. Chrome test pages closed. marimo stays installed as a uv tool (0.25.1).

## 9. Open points

1. A `pyproject.toml` with `[tool.marimo.runtime] auto_instantiate = true` above an experiment workspace re-enables startup execution. OMRG cannot block it with a flag. Options: (a) document only (done); (b) refuse to open when such a file exists between the notebook and the filesystem root; (c) record the nearest `pyproject.toml` path in the open response.
2. A notebook header can set `runtime.on_cell_change = "autorun"`. The starter notebook's `mo.stop(not run_button.value, ...)` still blocks unrequested runs, but other notebooks have no such guard.
3. If the editor exits by itself, OMRG keeps the credential until Stop or shutdown (unchanged from 8.6).
