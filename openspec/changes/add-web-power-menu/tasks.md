# Tasks

## 1. Counter on the admission object

- [x] 1.1 Move `Admission` and `AdmissionClosed` from `lifespan.py` to `src/omrg/transports/api/admission.py` and re-export both names from `lifespan.py`. Verify: `uv run pytest tests -k "lifespan or admission or shutdown" -q` passes, `lifespan.py` is under 500 lines, and `uv run lint-imports` reports 0 broken.
- [x] 1.2 Test first: add a read-only `active` property that returns the number of admitted calls. Verify: a new unit test fails before the property exists, then passes; the count is 0 after the call ends.

## 2. Power control module and routes

- [x] 2.1 Test first: `tests/unit/test_power_control.py` pins that the `restart` and `off` argv lists equal `_launchagent.kill_command(uid, label, "SIGTERM")` and `_launchagent.bootout_command(uid, label)`. Verify: the test fails before `power_control.py` exists.
- [x] 2.2 Add `src/omrg/transports/api/power_control.py` with the two argv builders and a runner that uses no shell and a timeout. Verify: task 2.1 passes.
- [x] 2.3 Test first: route tests for `GET` and `POST /v1/server/power` cover each spec scenario: 403 for bearer, `managed: false` and 409 in the foreground, 409 with active work, 422 for an unknown action, 202 for each action. A fake runner records the argv, and the 202 test checks the runner runs after the response. Verify: all tests fail before the route exists.
- [x] 2.4 Add `routes/power.py` with the `manage` scope dependency, register it in the route list, and set `application.state.power_control` in `cli/web.py` only for `--login-item`. Verify: task 2.3 passes; mutate the scope to `read` and confirm the bearer test fails.
- [x] 2.5 Add both routes to `openapi.yaml`. Verify: the existing OpenAPI contract test passes.

## 3. The start command

- [x] 3.1 Test first: `tests/unit/test_web_login_item_start.py` covers start after Turn off, start when running, start when not installed and a non-macOS platform, with a fake launchctl. Verify: the tests fail before the command exists.
- [x] 3.2 Add `cli/web_login_item_start.py` and register `start` on the `web` group. Verify: task 3.1 passes and `omrg web --help` lists `start`.

## 4. The page

- [x] 4.1 Load the `omrg-design` skill and read `web/DESIGN.md`. Verify: no literal colour appears in the new files.
- [x] 4.2 Test first: component tests for `PowerMenu` cover the spec scenarios: confirmation before any POST, the post-action text for each action, disabled buttons with the reason when `managed` is false, and the 409 line. Verify: the tests fail before the component exists.
- [x] 4.3 Add the API client calls and types in `web/src/api/`, then `PowerMenu`, and use it in `NavFoot.tsx`. Verify: task 4.2 passes, `npm run lint`, `npm run typecheck` and `npm test` pass in `web/`, and every file stays under 500 lines.
- [ ] 4.4 Browser check against a scratch workspace (never the real login item or port 8765) at 1280 px and 390 px, with `managed` false and with a fake `managed` true. Verify: the panel fits both widths and the buttons read as disabled in the foreground case.

## 5. Real-Mac checks (user steps)

- [ ] 5.1 Reinstall the tool with `uv tool install` from the integration worktree and run `omrg web restart`. Verify: `omrg web status` shows the new version.
- [ ] 5.2 Press Restart in the page. Verify: the app answers again, `omrg web open` signs in, and the time to return is noted. If it is over 15 seconds, add a line about the wait to the dialog.
- [ ] 5.3 Press Turn off in the page. Verify: `omrg web status` shows the app stopped, the plist still exists, and `omrg web start` brings the app back.
- [ ] 5.4 Start an ingestion and press Turn off. Verify: the panel shows the 409 line and the app keeps running.

## 6. Docs and records

- [x] 6.1 Update `docs/guides/cli-reference.md` (the `start` command) and `docs/guides/web-workspace.md` (the power panel). Verify: grep the guides for "no Restart button" and "only uninstall" and fix any hit.
- [x] 6.2 Add `docs/adr/086-web-power-menu.md` and one addendum line in ADR-085 that says Turn off is a second way to stop the app. Verify: the ADR index lists 086.

## 7. Gates

- [ ] 7.1 Run `openspec validate --all --strict`, `uv run lint-imports`, ruff, the fast test suite and `./scripts/local_ci.sh`. Verify: all pass.
- [ ] 7.2 Commit each group with `uv run git commit` and a Conventional Commit message. Verify: the working tree is clean.
