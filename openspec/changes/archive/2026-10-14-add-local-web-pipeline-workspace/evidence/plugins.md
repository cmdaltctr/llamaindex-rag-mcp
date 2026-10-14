# Plugins (tasks 8.1, 8.2, 8.3)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted working tree.
Design D10. Spec `notebook-plugins`. ADR-075 section 4.

marimo is not installed (`import marimo` gives `ModuleNotFoundError`; `marimo` is not on `PATH`).
Task 8.4 stays NOT RUN. All tests use fake executables in `tmp_path`.
No command in this work ran `uvx`, `uv tool install`, `pip install` or `uv sync`.

## Files

| File | Purpose |
|---|---|
| `src/omrg/core/plugins/__init__.py` | Public exports. |
| `src/omrg/core/plugins/manifest.py` | Closed manifest schema, validation, version range, substitution, TOML config rendering. |
| `src/omrg/core/plugins/registration.py` | `PluginRegistry`: explicit trust, change detection, probing through an injected runner. |
| `src/omrg/core/plugins/editor.py` | `NotebookEditorSupervisor`, `build_launch_plan`, `ProcessLauncher` protocol. |
| `src/omrg/integrations/process_launcher.py` | `SubprocessProbeRunner`, `OwnedProcessLauncher`. The only plugin code that starts processes. |
| `plugins/marimo/manifest.json` | Separately distributed marimo manifest (outside the wheel). |
| `plugins/marimo/README.md` | Install outside OMRG, register, recheck, launch, stop, update. |
| `tests/unit/test_plugin_manifest.py` | 8.1 manifest validation (58 tests). |
| `tests/unit/test_plugin_registration.py` | 8.1 registration, change detection, probing (25 tests). |
| `tests/unit/test_plugin_editor.py` | 8.3 supervisor with a fake launcher (11 tests). |
| `tests/unit/test_plugin_marimo_manifest.py` | 8.2 shipped manifest, wheel exclusion, external-version recheck (7 tests, 1 `slow`). |
| `tests/unit/test_process_launcher.py` | 8.3 launcher against fake executables (22 tests). |
| `tests/unit/test_process_launcher_editor.py` | 8.3 end to end: shipped manifest, real launcher, fake marimo (3 tests). |
| `tests/unit/test_process_launcher_support.py` | Fake executables and helpers (no tests). |
| `tests/unit/test_plugin_boundaries.py` | AST import checks for `core/plugins` and the launcher (12 tests). |

## Public interface for later tasks (8.5 to 8.7, HTTP routes)

Composition constructs these. Nothing here reads a process default.

```python
from omrg.core.plugins import PluginRegistry, NotebookEditorSupervisor
from omrg.integrations.process_launcher import OwnedProcessLauncher, SubprocessProbeRunner

registry = PluginRegistry(workspace_repository, SubprocessProbeRunner())
launcher = OwnedProcessLauncher(workspace_dir / "run" / "editors")
editors = NotebookEditorSupervisor(registry, launcher, ports=[2719, 2720, 2721])

registry.register(manifest_path, executable_path, approved=True)  # trust decision, runs nothing
registry.state("marimo")  # PluginState, no process; .status, .message, .launchable
registry.recheck("marimo")  # runs only the probe recipe
session = editors.open("marimo", notebook_path, consent=True)  # rechecks first
editors.stop(session.launch_id)
editors.stop_all()  # at agreed app shutdown
```

- `PluginState.status`: `compatible`, `incompatible`, `unchecked` (stored), `needs_approval`, `unavailable` (derived from disk).
- `EditorSession(launch_id, plugin, notebook, host, port, token)`. `token` is excluded from `repr`.
  The transport needs it to open the browser tab. Keep it in memory only.
- Errors: `ManifestError` (lists every problem), `PluginTrustError`, `PluginConsentError`, `PluginLaunchError`.
  Every message says what the operator can do.
- Repository methods used: `register_plugin`, `set_plugin_compatibility`, `get_plugin`, `list_plugins`.
  The executable identity, probed version and message live in the record's `detail`.

## Manifest rules (8.1)

- Closed schema at every level. An unknown key or recipe is an error. Fixed recipes: `probe`, `launch_notebook`.
- Arguments are JSON lists of short strings. A string is a shell string error.
  Whitespace and `; & | $ \` < > ( ) ! * ? ~ " ' \` are rejected.
- Substitutions: `{notebook_path}`, `{host}`, `{port}`, `{token_file}` only, in launch arguments only.
  Probe arguments allow none. `{executable}` is not supported: the host always places the approved executable at `argv[0]`.
- Rejected: interpreter or installer executables (`python*`, `sh`, `bash`, `uv`, `uvx`, `pip`, `pipx`, `conda`, `npm`, ...),
  paths in `tool.executable`, tokens such as `install`, `upgrade`, `update`, `-c`, `-m`, `__import__`, `--upgrade*`,
  literal credentials (`--x-token=...`, a password or secret flag followed by a literal), credential-named config keys,
  duplicate JSON keys, files over 64 KiB.
- `config_file`: a plain file name and tables of scalars. Rendered as TOML into the private launch directory.
- Capabilities map to a launch argument or a config value. Validation proves each declared capability is present in the recipe.
  `loopback_bind` must use `{host}` and `token_auth` must use `{token_file}`.
- Required for launch: `loopback_bind`, `token_auth`, `startup_execution_disabled`, `auto_install_disabled`, `update_check_disabled`.
  A missing one leaves the manifest valid but the plugin `incompatible`, and the message names it.

## Registration and probing (8.1)

- `register(..., approved=False)` raises and stores nothing. A valid registration runs no process.
- Stored: manifest SHA-256 (raw bytes), absolute executable path, and the executable identity (real path, size, `mtime_ns`, SHA-256).
- Executable checks: absolute path, regular file, executable bit, not writable by other users.
- Manifest edited or deleted: `needs_approval`. Recheck runs nothing until a new registration.
- Executable changed: `unchecked` until a recheck passes.
- Executable missing: `unavailable`. Nothing runs. The message says to install or update the tool outside OMRG.
- Recheck runs `<exe> --version`, compares the version with the tested range, then runs `<exe> edit --help`
  and confirms every argument-backed capability flag appears in the help text.
- `NotebookEditorSupervisor.open` always calls `recheck` first. This catches an upgrade that keeps the same entry-point shim
  (covered by `test_external_version_change_triggers_recheck`).

## marimo CLI evidence (8.2), Context7 `/websites/marimo_io` and `/marimo-team/marimo`

Confirmed by the documentation:

| Item | Documentation says |
|---|---|
| `marimo --version` | Top-level option: "Show the version and exit." Output format not shown. The host takes the first dotted number. |
| `marimo edit [OPTIONS] [NAME]` | Edit command usage. |
| `--host` | "Host to attach to." Default `127.0.0.1`. |
| `-p, --port` | "Port to attach to." |
| `--headless` | "Don't launch a browser." |
| `--token / --no-token` | Token auth on by default; random token unless `--token-password` is set. |
| `--token-password-file` | "Path to file containing token password, or '-' for stdin. Mutually exclusive with --token-password." |
| `--skip-update-check` | "Don't check if a new version of marimo is available for download." |
| `--sandbox` / `--no-sandbox` | Sandbox installs declared dependencies automatically; `--no-sandbox` means "Never run in a sandbox, and never prompt to." |
| `-y, --yes` | Global "automatic yes to prompts". The manifest does not use it. |
| `[runtime] auto_instantiate = false` | Disables autorun on startup (user config file). |
| `[runtime] on_cell_change = "lazy"` | Shown in the script-metadata example. |
| Config precedence | "Script config > pyproject.toml config > user config". |
| Config file search | `.marimo.toml` in the current directory, then parent directories, then `~/.marimo.toml`, then the XDG path. |
| Package install | Install happens from the package panel or when the user accepts a prompt for a missing import. |

Not confirmed (task 8.4 must check against a real installation):

1. No CLI flag disables startup execution. The plugin writes `.marimo.toml` into the launch directory and starts marimo there.
   That the cwd file wins over `~/.marimo.toml` is from the search-order text only.
2. A notebook PEP 723 header or a `pyproject.toml` near the notebook can override these settings. This is documented precedence, not a bug.
3. No documented config switch turns off the missing-package prompt. It needs a user action, so it is not automatic.
4. The exact `--version` output and the browser login URL format (for example an `access_token` query parameter) are not documented in the retrieved pages.
5. The tested range `>=0.25.0,<0.26.0` is provisional. PyPI lists 0.25.1 as the latest release on 2026-10-13. No real version was run.
6. Whether marimo binds another port when `--port` is busy is unknown. The host checks the port first and never relies on that behaviour.

## Launch and supervision (8.3)

- Host is always `127.0.0.1`. The launcher also accepts `::1` and refuses `0.0.0.0`, `localhost` and other addresses.
- A new token for each launch (`secrets.token_urlsafe(32)`) is written to `<launch-dir>/access-token`, mode 0o600, `O_EXCL | O_NOFOLLOW`.
  The launcher refuses an argv that contains a secret. Output lines are kept in memory only (200 lines), with secrets replaced by `[redacted]`.
- Launch directory: `mkdtemp` (0o700) under the injected runtime directory. It is the process cwd. It is removed on stop.
- Environment: allow list only (`PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TZ`, `TMPDIR`, `TERM`, `SYSTEMROOT`).
  OMRG provider keys do not reach the editor.
- No shell. `start_new_session=True` gives each launch its own process group (pgid = leader pid).
- Port check before start: a loopback connect, then a bind with `SO_REUSEADDR`. A busy port raises `PortInUseError` (`EADDRINUSE`).
  The supervisor then tries the next permitted port, or fails with "OMRG does not stop other programs".
- Ready means the leader is alive and the port accepts connections. Early exit or a timeout stops the owned group and reports the redacted output tail.
- Stop: `killpg(SIGTERM)`, wait `grace_seconds`, then `killpg(SIGKILL)`, wait `kill_wait_seconds`. The leader is reaped.
  Stop of an unknown id raises `KeyError` and signals nothing.

## Test-first record

Environment: `cd WT && PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider ...`

| Step | Command (files) | Result |
|---|---|---|
| Registration and editor tests before `registration.py`/`editor.py` existed | `test_plugin_registration.py` | 1 collection error: `ImportError: cannot import name 'ManifestError' from 'omrg.core.plugins'` |
| Same, both files | `test_plugin_editor.py test_plugin_registration.py` | 2 collection errors |
| Launcher tests before `process_launcher.py` existed | `test_process_launcher.py` | 1 collection error (module missing) |
| README test before `README.md` existed | `-m "not slow" test_plugin_marimo_manifest.py test_process_launcher_editor.py` | 1 failed (`FileNotFoundError`), 8 passed |
| New malformed-section tests | `test_plugin_manifest.py` | 2 failed. One was a real bug: a non-object config table raised `TypeError` instead of `ManifestError`. Fixed in `ConfigFile.lookup`. |
| Final | `-m "not slow" tests/unit/test_plugin_*.py tests/unit/test_process_launcher*.py` | **137 passed**, 1 deselected |
| Wheel test | `-m slow tests/unit/test_plugin_marimo_manifest.py` | 1 passed |

Deviation from strict test-first: `manifest.py` was drafted before `test_plugin_manifest.py`. The mutation checks below cover it.

## Mutation checks

Script: `<scratchpad>/plugin-mut/run.py`. It copies `src/` to the scratchpad, makes one change, and runs all plugin and launcher tests with `PYTHONPATH` set to the copy.
The control run (no change) gave 114 passed. Every mutation made at least one test fail.

| Id | Change | Result | First failing test |
|---|---|---|---|
| M1 | No shell-syntax check | 2 failed | `test_rejects_unsafe_or_malformed_manifests[...shell syntax]` |
| M2 | Any substitution allowed | 3 failed | `...[unknown substitution]` |
| M3 | No installer/hook token check | 4 failed | `...[import hooks]` |
| M4 | Manifest hash not compared | 2 failed | `test_changed_manifest_requires_new_approval` |
| M5 | Executable identity not compared | 1 failed | `test_changed_executable_invalidates_until_recheck` |
| M6 | Version range ignored | 3 failed | `test_external_version_change_triggers_recheck` |
| M7 | Approval not required | 1 failed | `test_registration_requires_explicit_trust` |
| M8 | Token passed in argv | 3 failed | `test_open_and_stop_owned_editor` |
| M9 | `open` skips the recheck | 9 failed | `test_open_rechecks_then_launches_loopback_with_token_file` |
| M10 | Consent ignored | 1 failed | `test_open_requires_consent` |
| M11 | No port pre-check | 1 failed | `test_unrelated_listener_is_refused_and_left_running` |
| M12 | Full environment passed | 1 failed | `test_environment_is_allow_listed` |
| M13 | No output redaction | 1 failed | `test_token_never_in_argv_and_output_is_redacted` |
| M14 | No SIGKILL escalation | 1 failed | `test_stop_escalates_after_bounded_wait` |
| M15 | Non-loopback host accepted | 3 failed | `test_non_loopback_host_is_refused[...]` |
| M16 | Launch directory kept after stop | 3 failed | `test_stop_cleans_the_whole_owned_group` |

M14 left two fake editors running (they ignore SIGTERM and the mutation removed SIGKILL). They were killed by pid.
After the final real run, `pgrep` found no leftover fake processes.

## Wheel exclusion (8.2)

`uv build --wheel --offline -o <scratchpad>/wheel-8.2` built `omrg-2.2.0-py3-none-any.whl` (272 entries). This is a build, not an install.

- Entries containing `plugins`: only `omrg/core/plugins/{__init__,editor,manifest,registration}.py`. No `plugins/marimo/` entry.
- Entries containing `marimo`: none.
- `pyproject.toml` (read only): `[tool.hatch.build.targets.wheel] packages = ["src/omrg"]`. No `force-include`, `include` or `artifacts` entry names `plugins/`.
  marimo is in neither `dependencies` nor `optional-dependencies`.

## Static checks

- `ruff format` and `ruff check` on all owned files: clean.
- `lint-imports`: 15 kept, 0 broken.
- Guards: `tests/test_file_size_ceiling.py tests/test_pipeline_import_boundaries.py tests/test_contract_coverage.py tests/test_no_global_settings_reads.py`: 115 passed.
- Largest file: `core/plugins/manifest.py`, 473 lines.
- Branch coverage (`COVERAGE_FILE` in the scratchpad): `core/plugins` 99%, `integrations/process_launcher.py` 96%, total 99%.

Incident: one guard run also selected `tests/test_clean_base_tripwire.py`. That test runs the full fast suite in a subprocess.
It was stopped after about five minutes and no result was used. Its output is not evidence.

## Proposed import-linter change (not made; `pyproject.toml` is not owned)

No contract names `omrg.core.plugins` yet. `core-free-of-web-notebook-and-sqlite-runtimes` covers it for `sqlite3`, web packages and `marimo`,
but nothing forbids `subprocess` there. `tests/unit/test_plugin_boundaries.py` checks this with an AST scan in the meantime. Proposed contract:

```toml
[[tool.importlinter.contracts]]
name = "plugin-host-starts-no-processes"
type = "forbidden"
source_modules = ["omrg.core.plugins"]
forbidden_modules = [
    "omrg.core.ingestion", "omrg.core.retrieval", "omrg.core.answer", "omrg.core.providers",
    "omrg.transports", "omrg.integrations",
    "subprocess", "socket", "signal", "sqlite3", "fastapi", "starlette", "uvicorn", "marimo",
]
unmatched_ignore_imports_alerting = "error"
```

Also add `"omrg.core.plugins"` to the sources of `core-business-avoids-providers-transports`.
`omrg.integrations.process_launcher` is already covered by `integrations-are-leaves`.

## Open points for later tasks

1. `register_plugin` resets `detail` to `{}`. The registry then calls `set_plugin_compatibility(name, "unchecked", detail=...)`
   to store the approved executable identity. Side effect: `checked_at` is set at registration time.
   A `detail` argument on `register_plugin` would remove this; it needs a repository change (task 5.1 owner).
2. There is no unregister method in the repository. The README says to remove the manifest file, which leaves the registration disabled.
3. Ready detection uses a loopback connect. If an unrelated program takes the port between the check and the bind, the editor exits
   and the launch fails, but a connect in that window can succeed against the other program. A real marimo login check belongs to 8.4.
4. A process that leaves the group with `setsid` is not tracked. The fake editor's child stays in the group and is cleaned.
5. The transport (8.6) must build the browser URL with the session token and never log it. The login URL format is unconfirmed (see above).
6. Composition must call `NotebookEditorSupervisor.stop_all()` during agreed application shutdown. Nothing registers this automatically.

## Lead follow-up: import contract applied

`pyproject.toml` now has `plugin-host-starts-no-processes`, and `omrg.core.plugins` is a source of
`core-business-avoids-providers-transports`. `lint-imports`: 16 kept, 0 broken. With a temporary
`import subprocess` in `core/plugins/editor.py`: `plugin-host-starts-no-processes` BROKEN (restored).
`tests/test_pipeline_import_boundaries.py`, `tests/test_contract_coverage.py`,
`tests/unit/test_plugin_boundaries.py`: 56 passed.
