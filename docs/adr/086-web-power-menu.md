# ADR-086: Web Power Menu

- **Date:** 2026-10-19
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-085](085-web-login-item.md) (the login item), [ADR-079](079-approve-extra-loopback-origins-at-launch.md) (sign-in and origins)
- **Change:** `openspec/changes/add-web-power-menu/` (design D1 to D8)

## Context

The power icon in the navigation foot showed a status light and two terminal commands. The user pressed it and expected an off switch. Nothing happened.

The web app runs as a login item (ADR-085). Only `omrg web uninstall` stopped it, and that command removes the plist. A stop signal does not stop it, because Uvicorn re-raises the signal and launchd counts the exit as a crash. The user needs a way to turn the app off or restart it from the page.

Three files sit at the 500-line ceiling: `lifespan.py`, `security.py` and `cli/web_login_item.py`. New behaviour goes into new files.

## Decision

1. **Two actions, two launchd steps** (D1). `restart` sends `SIGTERM` with `launchctl kill`, the step that `omrg web restart` uses, and launchd starts the app again. `off` runs `launchctl bootout`. launchd unloads the agent, so `KeepAlive` has nothing to restart. The plist stays on disk, so `RunAtLoad` loads it at the next login.
2. **The server answers first and acts after** (D2). `POST /v1/server/power` answers 202. A background task then runs the launchctl argv after 0.5 seconds. The argv is a fixed list with no shell and a timeout.
3. **Only the login item can act** (D3). `omrg web --login-item` sets `application.state.power_control`. `GET /v1/server/power` answers `managed` from its presence. Without it, `POST` answers 409. A foreground server never signals a launchd job.
4. **No action while work runs** (D4). `POST` answers 409 while a run, an ingestion or a map call is in progress. The launchd exit timeout would kill long work. `Admission` moves to `transports/api/admission.py` and gets a read-only `active` count. `lifespan.py` re-exports the names.
5. **A way back on** (D5). `omrg web start` loads the agent again, waits for health and prints the `omrg web open` line. It lives in `cli/web_login_item_start.py`.
6. **Two copies of the argv, one test** (D6). The API must not import from `transports/cli`. `power_control.py` builds its own argv. A test compares it with `_launchagent.kill_command` and `_launchagent.bootout_command`.
7. **The route is as strict as other destructive routes** (D8). It needs the browser session with the `manage` scope. A bearer credential receives 403. The Host and Origin checks cover it. The body is a closed enum, so no free text reaches an argv.
8. **The page** (D7). A `PowerMenu` component offers Turn off and Restart, each behind a confirmation dialog. Disabled buttons show the reason as text.

## Consequences

### Positive

- The user turns the app off from the page, and `omrg web start` brings it back.
- Turn off keeps the plist, so the app returns at the next login.
- A foreground server is safe, because it never holds `power_control`.
- Running work blocks both actions, so launchd does not kill it at its exit timeout.

### Negative

- Both actions end the browser session, because sessions stay in memory. The user signs in again with `omrg web open`.
- Turn off cannot be undone from the page. The user needs a terminal and `omrg web start`.
- Work can start between the 409 check and the signal. The window is 0.5 seconds. Shutdown waits for admitted work, so only the exit timeout is at risk.
- Restart can take up to 60 seconds, because the plist sets `ThrottleInterval` to 60. The real-Mac check (task 5.2) measures it.

### Neutral

- macOS only. Elsewhere `managed` is false and the buttons stay disabled.
- The argv exists in two places. The test in decision 6 keeps them equal.
- No new dependency.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Exit with status 0 for Turn off** | Uvicorn re-raises the signal, so the exit status is not under our control (ADR-085 addendum). |
| **Run `omrg web uninstall` for Turn off** | It removes the plist, so the app would not return at the next login. |
| **`kickstart -k` for Restart** | ADR-085 rejected it. It can skip the clean shutdown and leave the link file. |
| **Start the app from the page after Turn off** | The page is gone when the app is off. |
| **Control a foreground server** | The server cannot restart itself without launchd, and a stray signal could hit an unrelated job. |
| **A confirmation token on the route** | The action loses no data. The dialog is the confirmation. |

## References

- `src/omrg/transports/api/routes/power.py`, `src/omrg/transports/api/power_control.py`, `src/omrg/transports/api/admission.py`
- `src/omrg/transports/cli/web_login_item_start.py`, `src/omrg/transports/cli/web.py`
- `web/src/components/PowerMenu.tsx`, `web/src/components/NavFoot.tsx`
- `docs/guides/cli-reference.md`, `docs/guides/web-workspace.md`
