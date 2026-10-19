# Tasks

Work in a feature worktree that forks from `integration/core-web`, named `llamaindex-rag-mcp-feat-add-web-login-item`. Do not work in the main checkout. Read `src/omrg/transports/AGENTS.md` first. Commit with `uv run git commit`. Tests use a temporary home folder and a fake `launchctl` runner; no test touches the real `~/Library`.

## 1. Make `web` a command group

- [x] 1.1 Add `tests/unit/test_web_group.py`. Cases: `omrg web --help` lists `install`, `uninstall`, `status`, `restart` and `open`; `omrg web --port 0 --workspace <tmp>` still reaches the server start (patch `_serve`); `omrg web install --help` prints help. Run the file and confirm that the new cases fail.
- [x] 1.2 Convert `web` in `transports/cli/web.py` to a sub-app whose callback keeps today's options and body (`invoke_without_command=True`, runs only when no subcommand is named). Keep every option name, default and message. Run `uv run pytest tests/unit/test_web_group.py -q` and `uv run pytest -q -k "web and cli"` and confirm that all pass. If Click cannot keep the old form, stop and update design D1 to the flat names before you go on.
- [x] 1.3 Add `--login-item` as a hidden boolean option on the callback. For now it only rejects `--port 0` with exit code 2 and a message that names both options. Add a case to `tests/unit/test_web_group.py` and confirm that it passes.

## 2. Hand over a renewed private sign-in link

- [x] 2.1 Add `tests/unit/test_launch_link.py` for the `local-web-workspace` scenarios: file mode 0600 and content is a link for the bound port; link absent from captured stdout, stderr and the log buffer; a successful sign-in replaces the file content with a different link and the first link is refused; 20 wrong secrets disable the old secret and the file holds a working new link; clean shutdown removes the file; the foreground policy is unchanged. Run it and confirm that it fails.
- [x] 2.2 Create `transports/api/launch_link.py` with `RearmingAccessPolicy` (design D4: overrides `for_launch` to take `link_file` and overrides `exchange_bootstrap`; replaces the secret under the policy lock after a sign-in and when the 20-failure limit is reached) and a small writer that creates the file with mode 0600 and replaces it atomically. Keep `security.py` unchanged (`git diff --stat` shows no change to it). Run `tests/unit/test_launch_link.py` and `tests/unit/test_web_security.py` and confirm that they pass.
- [x] 2.3 Wire `--login-item` in `web.py`: use `RearmingAccessPolicy`, write the file after the socket is bound, skip the printed link, pass `access_log=False` to Uvicorn, and remove the file in the shutdown path. Run `tests/unit/test_web_group.py` and `tests/unit/test_launch_link.py` and confirm that they pass. Run `uv run pytest -q tests/test_openapi_conformance.py tests/unit/test_web_openapi_conformance.py` and confirm that no route changed.
- [x] 2.4 Add the "Keep the app running" section to `docs/guides/web-workspace.md`: what the link file is, who can read it, that a restart signs the browser out, that the access log is off in this mode, and that the login item reads `~/.omrg/.env` while a hand-run `omrg web` reads the `.env` of its own folder. Run `uv run pytest tests/test_docs_references.py -q` and confirm that it passes.

## 3. Build the LaunchAgent plan

- [x] 3.1 Move the atomic write out of `write_plist` in `cli/_launchagent.py` into `write_plist_atomic(path, content, overwrite)`. `write_plist` calls it. Run `uv run pytest tests/unit/test_launchagent.py tests/test_install_login_watcher.py -q` and confirm that they pass without any change to those tests.
- [x] 3.2 Add `tests/unit/test_web_login_item_plan.py` for the `web-login-item` plist scenarios: label `com.omrg.web`; argument list with and without each option; `KeepAlive` is `{SuccessfulExit: false}`; `ThrottleInterval` is 60; `PATH` value; `WorkingDirectory` is the absolute `<home>/.omrg`; log paths; relative `--command-path` refused; the checkout warning fires for `<dir>/.venv/bin/omrg` when `<dir>/.git` exists and not otherwise; the settings message names `<home>/.omrg/.env` when it is missing and asks to copy only when the current folder has a `.env`. Run it and confirm that it fails.
- [x] 3.3 Add `cli/_web_login_item.py` with the plan dataclass, `build_plan`, `render_plist`, the checkout check and the health and version helpers from design D6. Reuse `compute_paths`, `resolve_command_path` and the `launchctl` argument builders. Run `tests/unit/test_web_login_item_plan.py` and confirm that it passes. Run `uv run pytest tests/test_file_size_ceiling.py -q` and confirm that it passes.

## 4. Add the commands

- [x] 4.1 Add `tests/unit/test_web_login_item_cli.py` for `install`: plan output; write and load with the fake runner; `<home>/.omrg` created; existing plist refused without `--force`; `--dry-run` writes nothing and runs on a non-macOS platform; non-macOS install refused; port-in-use warning; checkout confirmation; health time-out exits non-zero and keeps the plist; no `.env` file is created or read (assert the temporary home has no `.omrg/.env` and the current folder's `.env` is unchanged). Run it and confirm that it fails.
- [x] 4.2 Add `cli/web_login_item.py` with `install` and register it on the `web` group (and in the module list in `cli/__init__.py`). Wait for health up to 60 seconds (injectable clock in tests) and name the error log on time-out. Run the file and confirm that the `install` cases pass.
- [x] 4.3 Add cases and code for `uninstall`: unload, delete the plist, keep the workspace, confirm unless `--yes`, succeed when nothing is installed. Run the file and confirm that the cases pass.
- [x] 4.4 Add cases and code for `status` (text and `--json`; exit 0 only when the app answers; version difference message; not-installed message). Run the file and confirm that the cases pass.
- [x] 4.5 Add cases and code for `restart` (design D8: `launchctl kill SIGTERM`, wait for health to stop, then `kickstart` without `-k`; wait for health; not-installed message) and `open` (reads the link file, checks health first, runs `open` through an injectable runner, prints the address without the secret, `--print` prints the full link and opens nothing, missing file and dead port both give the not-running message). Assert that the secret never appears in captured output without `--print`. Run the file and confirm that the cases pass.
- [x] 4.6 Update `docs/guides/cli-reference.md` with the `omrg web` group, the five subcommands, the exit codes, and the `~/.omrg/.env` and sparse-environment notes from design D7. Add ADR-085 `docs/adr/085-web-login-item.md` with D1 to D5 and register it in `docs/adr/ADR_README.md`. Run `uv run pytest tests/test_docs_references.py -q` and confirm that it passes.
- [x] 4.7 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`, `uv run lint-imports` and `uv run ruff check src tests`. Confirm that all pass. When the user approves, commit this group as `feat(cli): keep the web app running as a macOS login item`.

## 5. Check on the real Mac

These tasks change the user's machine. Ask before each one.

- [x] 5.1 With approval, install the application as a tool from the main checkout with the `web` extra (`uv tool install`). Record the exact command that works in `docs/guides/cli-reference.md`. Run `omrg --version` from a new shell and confirm that it prints a version.
- [x] 5.2 With approval, stop the scratch `omrg web` process that the user started by hand, so the port and the workspace lock are free. Run `lsof -nP -iTCP:8765 -sTCP:LISTEN` and confirm no output.
- [x] 5.3 Ask the user to copy their settings to `~/.omrg/.env` themselves (never copy `.env` for them). Run `omrg web install --dry-run` and read the plan. With approval, run `omrg web install`. Confirm that `omrg web status` exits 0, shows the installed version as running, and that Settings shows the embedding model from `~/.omrg/.env`.
- [x] 5.4 Run `omrg web open`, sign in, save a provider key in Settings > Providers, then run `omrg web restart` and `omrg web open` again. Confirm that the provider card still shows the key as set. This proves the keychain read under launchd. If it fails, update design D7 and the CLI reference before you go on.
- [x] 5.5 Run `omrg web uninstall --yes` and then `omrg web install` again. Confirm that `~/.omrg/workspace` kept its data and that the app answers.
- [x] 5.6 Ask the user to log out and in, or reboot, and then run `omrg web status`. Record the result in the group's commit message. This task is for the user to do.
- [x] 5.7 Run `openspec validate add-web-login-item --strict` and `openspec validate --all --strict` and confirm that both pass. With approval, run `./scripts/local_ci.sh` and confirm that it passes. When the user approves, commit any remaining change as `docs(web): record the login item checks on macOS`. Run this after groups 6 and 7.

## 6. Fix the two bugs found on the real Mac

Uvicorn re-raises SIGTERM after its clean shutdown, so launchd sees a death by signal and restarts the app. Code after `serve()` never runs, so the link file stays behind after a stop.

- [x] 6.1 Add failing cases to `tests/unit/test_web_login_item_cli.py` for `restart`: launchd restarts the app itself (no kickstart); launchd restarts after a short delay inside the 5-second grace; launchd does not restart (kickstart runs). Run the file and confirm that the new cases fail.
- [x] 6.2 Fix `restart` in `cli/web_login_item.py` (design D8): read the process id from `launchctl print`, wait up to 15 seconds for the old id to go, wait up to 5 seconds for a new one, and run `kickstart` only when none appears. Move the stop logic into its own helper (this is the third patch to this function), and keep the file under 500 lines. Run `tests/unit/test_web_login_item_cli.py` and confirm that it passes.
- [x] 6.3 Add failing cases to `tests/unit/test_launch_link.py`: the stop hook runs inside Uvicorn's shutdown, and a real subprocess that gets SIGTERM removes the link file before it dies by signal. Run the file and confirm that the new cases fail.
- [x] 6.4 Add an `on_stop` hook to `_serve` in `cli/web.py` that runs inside `Server.shutdown`, and pass the policy's `retire` for the login item. Run `tests/unit/test_launch_link.py` and confirm that it passes.
- [x] 6.5 Correct `docs/guides/cli-reference.md`, `docs/guides/web-workspace.md` and `docs/adr/085-web-login-item.md`. Run `uv run pytest tests/test_docs_references.py -q` and confirm that it passes.
- [x] 6.6 Re-measure the clean-base tripwire pins in `tests/test_clean_base_tripwire.py`. Then run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`, the tripwire, `uv run lint-imports` and `uv run ruff check src tests`. Confirm that all pass. When the user approves, commit as `fix(cli): restart waits for launchd and the link file is removed at shutdown`.
- [x] 6.7 With approval, reinstall the tool (`uv tool install --reinstall` from the checkout). Run `omrg web restart` and confirm exit code 0 and a new process id. Then run `omrg web uninstall --yes` and `omrg web install`, and confirm that `~/.omrg/workspace/launch-link` is gone after a restart and written again after the start.

## 7. Add the navigation foot

- [x] 7.1 Load the `omrg-design` skill. Write failing component tests in `web/src`: four controls in order (theme, Settings, power, GitHub); no language control; a theme click writes the stored preference; the Settings link goes to `#/settings`; the power light is green when health answers and grey when it does not; the GitHub link has the right address and opens in a new tab; the collapsed layout shows icons only. Run the tests and confirm that they fail.
- [x] 7.2 Add the component under `web/src/components` and mount it at the foot of the side navigation (design D9). No new route. Run the tests and confirm that they pass.
- [x] 7.3 Check in a browser at 1280 px and 390 px against a scratch workspace. Report PASS or FAIL for each control. Ask before you start a server or a browser.
- [x] 7.4 Add a short "Navigation foot" paragraph to `docs/guides/web-workspace.md`. Run `uv run pytest tests/test_docs_references.py -q` and confirm that it passes.
- [x] 7.5 Run `npm run build` and the web tests in `web/`. Run `openspec validate add-web-login-item --strict` and `openspec validate --all --strict`. Confirm that all pass. When the user approves, commit as `feat(web): add the navigation foot`.
